import math
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ResourceNotFoundException,
)
from app.models.member import Member
from app.models.membership import MembershipRecord
from app.models.owner import Owner
from app.models.payment import Payment, PaymentRefund
from app.models.sequence import SystemSequence, member_code_seq
from app.schemas.member import (
    MemberCreate,
    MemberListResponse,
    MemberMembershipHistoryItem,
    MemberMembershipHistoryResponse,
    MemberPaymentHistoryItem,
    MemberPaymentHistoryResponse,
    MemberResponse,
    MemberSortField,
    MemberUpdate,
    SortOrder,
    normalize_phone_number,
)
from app.services.audit import log_audit_event

IST = timezone(timedelta(hours=5, minutes=30))


def _get_business_today():
    return datetime.now(timezone.utc).astimezone(IST).date()


def _is_postgresql(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name == "postgresql"


def _acquire_phone_advisory_locks(db: Session, *phones: str) -> None:
    """
    Acquire transaction-scoped PostgreSQL advisory locks in deterministic
    lexicographical order to serialize concurrent member phone operations
    without deadlocks. No-op on SQLite test databases.
    """
    if not _is_postgresql(db):
        return
    unique_sorted = sorted({p for p in phones if p})
    for phone in unique_sorted:
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:phone, 0))"),
            {"phone": phone},
        )


def _generate_member_code(db: Session) -> str:
    """
    Generate the next sequential RF member code (RF001, RF002, ...).

    - PostgreSQL: uses the atomic `member_code_seq` database sequence and
      syncs `system_sequences` metadata if present.
    - SQLite (tests): atomically increments `system_sequences` row for
      `member_code_seq` inside the active transaction.
    """
    seq_meta = db.execute(
        select(SystemSequence).where(SystemSequence.sequence_name == "member_code_seq")
    ).scalar_one_or_none()

    prefix = seq_meta.prefix if seq_meta else "RF"
    padding = seq_meta.padding_digits if seq_meta else 3

    if _is_postgresql(db):
        next_val = int(db.execute(select(member_code_seq.next_value())).scalar_one())
    else:
        if seq_meta is None:
            seq_meta = SystemSequence(
                sequence_name="member_code_seq",
                prefix="RF",
                padding_digits=3,
                current_value=0,
                description="Sequential gym member IDs (RF001, RF002, ...)",
            )
            db.add(seq_meta)
            db.flush()
        seq_meta.current_value = int(seq_meta.current_value) + 1
        db.flush()
        next_val = int(seq_meta.current_value)

    return f"{prefix}{next_val:0{padding}d}"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _get_member_or_404(
    db: Session, member_id: uuid.UUID, for_update: bool = False
) -> Member:
    stmt = select(Member).where(Member.id == member_id)
    if for_update and _is_postgresql(db):
        stmt = stmt.with_for_update()
    member = db.execute(stmt).scalar_one_or_none()
    if member is None:
        raise ResourceNotFoundException(resource="Member", identifier=str(member_id))
    return member


def _ensure_phone_available(
    db: Session,
    phone_number: str,
    exclude_member_id: Optional[uuid.UUID] = None,
) -> None:
    stmt = select(Member.id).where(
        Member.phone_number == phone_number,
        Member.is_archived.is_(False),
    )
    if exclude_member_id is not None:
        stmt = stmt.where(Member.id != exclude_member_id)
    existing_id = db.execute(stmt).scalar_one_or_none()
    if existing_id is not None:
        raise ConflictException(
            detail="An active (non-archived) member with this phone number already exists."
        )


def _serialize_member_audit_fields(member: Member) -> Dict[str, Any]:
    return {
        "member_code": member.member_code,
        "full_name": member.full_name,
        "phone_number": member.phone_number,
        "date_of_birth": member.date_of_birth.isoformat() if member.date_of_birth else None,
        "age": member.age,
        "gender": member.gender,
        "address": member.address,
        "joining_date": member.joining_date.isoformat() if member.joining_date else None,
        "emergency_contact_name": member.emergency_contact_name,
        "emergency_contact_phone": member.emergency_contact_phone,
        "profile_photo_url": member.profile_photo_url,
        "is_archived": member.is_archived,
    }


def create_member(
    db: Session,
    payload: MemberCreate,
    owner: Owner,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MemberResponse:
    """
    Create a new member with a sequential RF code and normalized phone number.
    Does NOT create memberships, payments, or invoices.
    """
    _acquire_phone_advisory_locks(db, payload.phone_number)
    _ensure_phone_available(db, payload.phone_number)

    member_code = _generate_member_code(db)
    joining_date = payload.joining_date or _get_business_today()

    member = Member(
        id=uuid.uuid4(),
        member_code=member_code,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        date_of_birth=payload.date_of_birth,
        age=payload.age,
        gender=payload.gender,
        address=payload.address,
        joining_date=joining_date,
        emergency_contact_name=payload.emergency_contact_name,
        emergency_contact_phone=payload.emergency_contact_phone,
        profile_photo_url=payload.profile_photo_url,
        is_archived=False,
        created_by_owner_id=owner.id,
    )

    try:
        db.add(member)
        db.flush()
        log_audit_event(
            db=db,
            action="member.created",
            entity_type="member",
            entity_id=member.id,
            owner_id=owner.id,
            new_values=_serialize_member_audit_fields(member),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictException(
            detail="Member could not be created due to a phone number or code conflict."
        ) from exc

    db.refresh(member)
    return MemberResponse.model_validate(member)


def list_members(
    db: Session,
    search: Optional[str] = None,
    gender: Optional[str] = None,
    is_archived: bool = False,
    sort_by: MemberSortField = "created_at",
    sort_order: SortOrder = "desc",
    page: int = 1,
    page_size: int = 20,
) -> MemberListResponse:
    """
    List and search members with pagination, filtering, and sorting.
    Defaults to non-archived members (is_archived=False).
    """
    filters = [Member.is_archived.is_(is_archived)]

    if gender is not None and gender.strip():
        filters.append(func.lower(Member.gender) == gender.strip().lower())

    if search is not None and search.strip():
        raw_q = search.strip()
        escaped = _escape_like(raw_q)
        pattern = f"%{escaped}%"
        search_clauses = [
            Member.member_code.ilike(pattern, escape="\\"),
            Member.full_name.ilike(pattern, escape="\\"),
            Member.phone_number.ilike(pattern, escape="\\"),
        ]
        try:
            normalized_q = normalize_phone_number(raw_q)
            search_clauses.append(Member.phone_number == normalized_q)
        except ValueError:
            pass
        filters.append(or_(*search_clauses))

    total = db.execute(select(func.count(Member.id)).where(*filters)).scalar_one()

    sort_columns = {
        "created_at": Member.created_at,
        "joining_date": Member.joining_date,
        "full_name": func.lower(Member.full_name),
        "member_code": Member.member_code,
    }
    sort_col = sort_columns[sort_by]
    primary_order = sort_col.asc() if sort_order == "asc" else sort_col.desc()

    offset = (page - 1) * page_size
    rows = (
        db.execute(
            select(Member)
            .where(*filters)
            .order_by(primary_order, Member.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return MemberListResponse(
        items=[MemberResponse.model_validate(m) for m in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_member_details(db: Session, member_id: uuid.UUID) -> MemberResponse:
    """Retrieve a single member profile by UUID (including archived members)."""
    member = _get_member_or_404(db, member_id)
    return MemberResponse.model_validate(member)


def update_member(
    db: Session,
    member_id: uuid.UUID,
    payload: MemberUpdate,
    owner: Owner,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MemberResponse:
    """
    Partially update permitted member fields.
    Uses sorted advisory locks and row-level locking on PostgreSQL when phone changes.
    """
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise BadRequestException(detail="No valid fields provided for update.")

    existing = _get_member_or_404(db, member_id)
    old_phone = existing.phone_number
    new_phone = update_data.get("phone_number", old_phone)

    _acquire_phone_advisory_locks(db, old_phone, new_phone)
    member = _get_member_or_404(db, member_id, for_update=True)

    if "phone_number" in update_data and member.phone_number != old_phone:
        raise ConflictException(
            detail="Member phone number was modified concurrently. Please retry."
        )

    if "phone_number" in update_data and new_phone != member.phone_number:
        if not member.is_archived:
            _ensure_phone_available(db, new_phone, exclude_member_id=member.id)

    previous_values: Dict[str, Any] = {}
    new_values: Dict[str, Any] = {}

    for field, val in update_data.items():
        current_val = getattr(member, field)
        if current_val != val:
            previous_values[field] = (
                current_val.isoformat() if hasattr(current_val, "isoformat") else current_val
            )
            new_values[field] = (
                val.isoformat() if hasattr(val, "isoformat") else val
            )
            setattr(member, field, val)

    try:
        if new_values:
            db.flush()
            log_audit_event(
                db=db,
                action="member.updated",
                entity_type="member",
                entity_id=member.id,
                owner_id=owner.id,
                previous_values=previous_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictException(
            detail="An active (non-archived) member with this phone number already exists."
        ) from exc

    db.refresh(member)
    return MemberResponse.model_validate(member)


def archive_member(
    db: Session,
    member_id: uuid.UUID,
    owner: Owner,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MemberResponse:
    """
    Soft-archive a member without deleting or altering memberships/payments/invoices.
    Rejects repeated archive attempts.
    """
    member = _get_member_or_404(db, member_id, for_update=True)
    if member.is_archived:
        raise ConflictException(detail="Member is already archived.")

    now_utc = datetime.now(timezone.utc)
    previous_values = {
        "is_archived": member.is_archived,
        "archived_at": None,
        "archive_reason": member.archive_reason,
    }

    member.is_archived = True
    member.archived_at = now_utc
    member.archive_reason = reason

    db.flush()
    log_audit_event(
        db=db,
        action="member.archived",
        entity_type="member",
        entity_id=member.id,
        owner_id=owner.id,
        previous_values=previous_values,
        new_values={
            "is_archived": True,
            "archived_at": now_utc.isoformat(),
            "archive_reason": reason,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(member)
    return MemberResponse.model_validate(member)


def reactivate_member(
    db: Session,
    member_id: uuid.UUID,
    owner: Owner,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> MemberResponse:
    """
    Reactivate an archived member after checking active-member phone uniqueness.
    Preserves member_code and all historical records; does NOT activate memberships.
    """
    existing = _get_member_or_404(db, member_id)
    _acquire_phone_advisory_locks(db, existing.phone_number)
    member = _get_member_or_404(db, member_id, for_update=True)

    if not member.is_archived:
        raise ConflictException(detail="Member is already active (not archived).")

    _ensure_phone_available(db, member.phone_number, exclude_member_id=member.id)

    previous_values = {
        "is_archived": True,
        "archived_at": member.archived_at.isoformat() if member.archived_at else None,
        "archive_reason": member.archive_reason,
    }

    member.is_archived = False
    member.archived_at = None
    member.archive_reason = None

    try:
        db.flush()
        log_audit_event(
            db=db,
            action="member.reactivated",
            entity_type="member",
            entity_id=member.id,
            owner_id=owner.id,
            previous_values=previous_values,
            new_values={
                "is_archived": False,
                "archived_at": None,
                "archive_reason": None,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictException(
            detail="Cannot reactivate member: another active member uses this phone number."
        ) from exc

    db.refresh(member)
    return MemberResponse.model_validate(member)


def get_member_memberships(
    db: Session,
    member_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> MemberMembershipHistoryResponse:
    """Return paginated membership history for a member, newest first."""
    member = _get_member_or_404(db, member_id)

    total = db.execute(
        select(func.count(MembershipRecord.id)).where(
            MembershipRecord.member_id == member.id
        )
    ).scalar_one()

    offset = (page - 1) * page_size
    records = (
        db.execute(
            select(MembershipRecord)
            .where(MembershipRecord.member_id == member.id)
            .order_by(MembershipRecord.start_date.desc(), MembershipRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return MemberMembershipHistoryResponse(
        member_id=member.id,
        member_code=member.member_code,
        items=[MemberMembershipHistoryItem.model_validate(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_member_payments(
    db: Session,
    member_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> MemberPaymentHistoryResponse:
    """
    Return paginated payment history for a member, newest first,
    with aggregated processed refund amounts (no N+1 queries).
    """
    member = _get_member_or_404(db, member_id)

    total = db.execute(
        select(func.count(Payment.id)).where(Payment.member_id == member.id)
    ).scalar_one()

    offset = (page - 1) * page_size
    payments = (
        db.execute(
            select(Payment)
            .where(Payment.member_id == member.id)
            .order_by(Payment.payment_date.desc(), Payment.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    payment_ids = [p.id for p in payments]
    refund_totals: Dict[uuid.UUID, Decimal] = {}
    if payment_ids:
        refund_rows = db.execute(
            select(
                PaymentRefund.original_payment_id,
                func.coalesce(func.sum(PaymentRefund.amount), Decimal("0.00")),
            )
            .where(
                PaymentRefund.original_payment_id.in_(payment_ids),
                PaymentRefund.status == "processed",
            )
            .group_by(PaymentRefund.original_payment_id)
        ).all()
        refund_totals = {pid: Decimal(str(amt)) for pid, amt in refund_rows}

    items: List[MemberPaymentHistoryItem] = []
    for p in payments:
        refunded = refund_totals.get(p.id, Decimal("0.00"))
        items.append(
            MemberPaymentHistoryItem(
                id=p.id,
                payment_number=p.payment_number,
                membership_record_id=p.membership_record_id,
                amount=p.amount,
                payment_type=p.payment_type,
                payment_method=p.payment_method,
                transaction_reference=p.transaction_reference,
                payment_date=p.payment_date,
                status=p.status,
                notes=p.notes,
                refunded_amount=refunded,
                has_refunds=refunded > Decimal("0.00"),
                created_at=p.created_at,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return MemberPaymentHistoryResponse(
        member_id=member.id,
        member_code=member.member_code,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

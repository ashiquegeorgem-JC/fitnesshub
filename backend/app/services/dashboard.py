import math
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    and_,
    case,
    distinct,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException
from app.models.audit import AuditLog
from app.models.member import Member
from app.models.membership import MembershipDueSchedule, MembershipRecord
from app.models.owner import Owner
from app.models.payment import Payment, PaymentRefund
from app.models.plan import MembershipPlan
from app.schemas.dashboard import (
    ActivitySummaryItem,
    AnalyticsPeriod,
    DashboardOverviewResponse,
    FinancialAnalyticsResponse,
    FinancialSummaryOverview,
    FinancialTotals,
    MemberCountsOverview,
    MembershipAlertsOverview,
    MembershipAnalyticsResponse,
    MembershipAnalyticsSummary,
    MembershipTypeBreakdown,
    MembershipTypeRevenue,
    MonthMetricsOverview,
    PaginationMetadata,
    PaymentMethodMetric,
    PaymentTypeBreakdown,
    PaymentTypeMetric,
    PlanDistributionItem,
    RecentActivityItem,
    RecentActivityResponse,
    RenewalPipelineItem,
    RenewalPipelineResponse,
    RenewalPipelineSummary,
    TodayMetricsOverview,
)

IST = timezone(timedelta(hours=5, minutes=30))


def get_business_today() -> date:
    """Return current business date in Asia/Kolkata timezone (UTC+5:30)."""
    return datetime.now(timezone.utc).astimezone(IST).date()


def resolve_date_range(
    preset: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Tuple[date, date, str]:
    """
    Resolve and validate date filters.
    Presets: 'today', 'this_week', 'this_month', 'this_year', 'custom'.
    Returns (start_date, end_date, resolved_preset_name).
    """
    today = get_business_today()

    if preset == "today":
        return today, today, "today"
    elif preset == "this_week":
        start = today - timedelta(days=today.weekday())
        return start, today, "this_week"
    elif preset == "this_month":
        start = today.replace(day=1)
        return start, today, "this_month"
    elif preset == "this_year":
        start = today.replace(month=1, day=1)
        return start, today, "this_year"
    elif preset == "custom":
        if not start_date or not end_date:
            raise BadRequestException(
                detail="Both 'start_date' and 'end_date' are required when preset='custom'."
            )
        if start_date > end_date:
            raise BadRequestException(
                detail="start_date cannot be later than end_date."
            )
        return start_date, end_date, "custom"
    else:
        if start_date and end_date:
            if start_date > end_date:
                raise BadRequestException(
                    detail="start_date cannot be later than end_date."
                )
            return start_date, end_date, "custom"
        elif start_date:
            return start_date, today, "custom"
        else:
            return today.replace(day=1), today, "this_month"


def _active_contract_clause(ref_date: date):
    """
    SQLAlchemy condition for active contracts:
    - Manual override: is_manual_override = True AND override_status = 'active'
    - Standard active: is_manual_override = False AND system_status = 'active' AND start_date <= ref_date <= expiry_date
    """
    return or_(
        and_(
            MembershipRecord.is_manual_override.is_(True),
            MembershipRecord.override_status == "active",
        ),
        and_(
            MembershipRecord.is_manual_override.is_(False),
            MembershipRecord.system_status == "active",
            MembershipRecord.start_date <= ref_date,
            MembershipRecord.expiry_date >= ref_date,
        ),
    )


def _contract_outstanding_subqueries():
    """
    Returns correlated scalar subqueries to compute contract balance:
    (gross_paid_subq, refunds_subq, waived_subq)
    """
    gross_paid_subq = (
        select(func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
        .where(
            Payment.membership_record_id == MembershipRecord.id,
            Payment.status == "confirmed",
        )
        .scalar_subquery()
    )

    refunds_subq = (
        select(func.coalesce(func.sum(PaymentRefund.amount), Decimal("0.00")))
        .select_from(PaymentRefund)
        .join(Payment, PaymentRefund.original_payment_id == Payment.id)
        .where(
            Payment.membership_record_id == MembershipRecord.id,
            PaymentRefund.status == "processed",
        )
        .scalar_subquery()
    )

    waived_subq = (
        select(func.coalesce(func.sum(MembershipDueSchedule.due_amount), Decimal("0.00")))
        .where(
            MembershipDueSchedule.membership_record_id == MembershipRecord.id,
            MembershipDueSchedule.is_waived.is_(True),
        )
        .scalar_subquery()
    )

    return gross_paid_subq, refunds_subq, waived_subq


def get_total_outstanding_dues(db: Session) -> Decimal:
    """
    Aggregate outstanding membership dues across all contracts for non-archived members.
    Formula: max(0.00, total_fee - (gross_paid - refunded) - waived)
    """
    gross_paid_subq, refunds_subq, waived_subq = _contract_outstanding_subqueries()

    net_paid_expr = gross_paid_subq - refunds_subq
    contract_balance_expr = MembershipRecord.total_fee - net_paid_expr - waived_subq

    outstanding_case = case(
        (contract_balance_expr > Decimal("0.00"), contract_balance_expr),
        else_=Decimal("0.00"),
    )

    total_outstanding = db.execute(
        select(func.coalesce(func.sum(outstanding_case), Decimal("0.00")))
        .select_from(MembershipRecord)
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(Member.is_archived.is_(False))
    ).scalar() or Decimal("0.00")

    return Decimal(str(total_outstanding)).quantize(Decimal("0.01"))


def get_collections_for_period(
    db: Session, start_date: date, end_date: date
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Returns (gross_confirmed, processed_refunds, net_collections) for the given date range.
    """
    gross_confirmed = db.execute(
        select(func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
        .where(
            Payment.status == "confirmed",
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date,
        )
    ).scalar() or Decimal("0.00")

    start_dt_utc = datetime(
        start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=IST
    ).astimezone(timezone.utc)
    end_dt_utc = datetime(
        end_date.year, end_date.month, end_date.day, 23, 59, 59, 999999, tzinfo=IST
    ).astimezone(timezone.utc)

    processed_refunds = db.execute(
        select(func.coalesce(func.sum(PaymentRefund.amount), Decimal("0.00")))
        .where(
            PaymentRefund.status == "processed",
            PaymentRefund.created_at >= start_dt_utc,
            PaymentRefund.created_at <= end_dt_utc,
        )
    ).scalar() or Decimal("0.00")

    gross_dec = Decimal(str(gross_confirmed)).quantize(Decimal("0.01"))
    refunds_dec = Decimal(str(processed_refunds)).quantize(Decimal("0.01"))
    net_dec = (gross_dec - refunds_dec).quantize(Decimal("0.01"))

    return gross_dec, refunds_dec, net_dec


def _format_activity_description(action: str, entity_type: str, actor_name: Optional[str]) -> str:
    actor = actor_name or "Owner"
    action_map = {
        "LOGIN_SUCCESS": f"{actor} logged in successfully",
        "LOGIN_FAILED": "Failed login attempt detected",
        "TOKEN_REFRESH": f"Session refreshed for {actor}",
        "LOGOUT": f"{actor} logged out",
        "LOGOUT_ALL_SESSIONS": f"All sessions revoked for {actor}",
        "PASSWORD_RESET_REQUESTED": "Password reset OTP requested",
        "OTP_VERIFICATION_SUCCESS": "Password reset OTP verified",
        "OTP_VERIFICATION_FAILED": "Invalid OTP verification attempt",
        "PASSWORD_RESET_SUCCESS": f"Password reset completed for {actor}",
        "REFRESH_TOKEN_REUSE_DETECTED": "Security warning: refresh token reuse detected",
        "ACTIVATE_MEMBERSHIP": f"Membership activated by {actor}",
        "PAYMENT_CONFIRMED": f"Payment confirmed by {actor}",
        "REFUND_PROCESSED": f"Refund processed by {actor}",
        "MEMBER_ARCHIVED": f"Member archived by {actor}",
        "MEMBER_REACTIVATED": f"Member reactivated by {actor}",
    }
    return action_map.get(action, f"{action.replace('_', ' ').capitalize()} recorded on {entity_type}")


# ---------------------------------------------------------------------------
# Endpoint Service 1: Overview
# ---------------------------------------------------------------------------


def get_dashboard_overview(db: Session) -> DashboardOverviewResponse:
    today = get_business_today()

    # Active member subquery
    active_member_subq = (
        select(MembershipRecord.member_id)
        .where(_active_contract_clause(today))
        .distinct()
    )

    # 1. Member Counts
    total_members = db.execute(
        select(func.count(Member.id)).where(Member.is_archived.is_(False))
    ).scalar() or 0

    archived_members = db.execute(
        select(func.count(Member.id)).where(Member.is_archived.is_(True))
    ).scalar() or 0

    active_members = db.execute(
        select(func.count(Member.id)).where(
            Member.is_archived.is_(False),
            Member.id.in_(active_member_subq),
        )
    ).scalar() or 0

    expired_member_subq = (
        select(MembershipRecord.member_id)
        .where(
            or_(
                and_(
                    MembershipRecord.is_manual_override.is_(False),
                    or_(
                        MembershipRecord.system_status == "expired",
                        and_(
                            MembershipRecord.system_status == "active",
                            MembershipRecord.expiry_date < today,
                        ),
                    ),
                ),
                and_(
                    MembershipRecord.is_manual_override.is_(True),
                    MembershipRecord.override_status == "expired",
                ),
            )
        )
        .distinct()
    )

    expired_members = db.execute(
        select(func.count(Member.id)).where(
            Member.is_archived.is_(False),
            Member.id.not_in(active_member_subq),
            Member.id.in_(expired_member_subq),
        )
    ).scalar() or 0

    # 2. Membership Alerts
    expiring_7d = db.execute(
        select(func.count(distinct(MembershipRecord.member_id)))
        .select_from(MembershipRecord)
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(
            Member.is_archived.is_(False),
            MembershipRecord.is_manual_override.is_(False),
            MembershipRecord.system_status == "active",
            MembershipRecord.start_date <= today,
            MembershipRecord.expiry_date >= today,
            MembershipRecord.expiry_date <= today + timedelta(days=7),
        )
    ).scalar() or 0

    expiring_3d = db.execute(
        select(func.count(distinct(MembershipRecord.member_id)))
        .select_from(MembershipRecord)
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(
            Member.is_archived.is_(False),
            MembershipRecord.is_manual_override.is_(False),
            MembershipRecord.system_status == "active",
            MembershipRecord.start_date <= today,
            MembershipRecord.expiry_date >= today,
            MembershipRecord.expiry_date <= today + timedelta(days=3),
        )
    ).scalar() or 0

    # 3. Today Metrics
    new_admissions_today = db.execute(
        select(func.count(Member.id)).where(
            Member.is_archived.is_(False),
            Member.joining_date == today,
        )
    ).scalar() or 0

    _, _, collections_today = get_collections_for_period(db, today, today)

    # 4. Month Metrics
    first_day_of_month = today.replace(day=1)
    _, _, collections_this_month = get_collections_for_period(
        db, first_day_of_month, today
    )

    # 5. Financial Summary
    outstanding_dues = get_total_outstanding_dues(db)

    # 6. Recent Activity (last 5)
    recent_logs = db.execute(
        select(AuditLog, Owner.name.label("owner_name"))
        .outerjoin(Owner, AuditLog.owner_id == Owner.id)
        .order_by(AuditLog.created_at.desc())
        .limit(5)
    ).all()

    activity_items = [
        ActivitySummaryItem(
            id=log.AuditLog.id,
            action=log.AuditLog.action,
            entity_type=log.AuditLog.entity_type,
            entity_id=log.AuditLog.entity_id,
            description=_format_activity_description(
                log.AuditLog.action, log.AuditLog.entity_type, log.owner_name
            ),
            actor_owner_name=log.owner_name,
            created_at=log.AuditLog.created_at,
        )
        for log in recent_logs
    ]

    return DashboardOverviewResponse(
        business_date=today,
        member_counts=MemberCountsOverview(
            total_members=total_members,
            active_members=active_members,
            expired_members=expired_members,
            archived_members=archived_members,
        ),
        membership_alerts=MembershipAlertsOverview(
            expiring_within_7_days=expiring_7d,
            expiring_within_3_days=expiring_3d,
        ),
        today_metrics=TodayMetricsOverview(
            new_admissions_today=new_admissions_today,
            collections_today=collections_today,
        ),
        month_metrics=MonthMetricsOverview(
            collections_this_month=collections_this_month,
        ),
        financial_summary=FinancialSummaryOverview(
            outstanding_dues=outstanding_dues,
        ),
        recent_activity=activity_items,
    )


# ---------------------------------------------------------------------------
# Endpoint Service 2: Membership Analytics
# ---------------------------------------------------------------------------


def get_membership_analytics(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> MembershipAnalyticsResponse:
    today = get_business_today()
    if start_date is not None or end_date is not None:
        resolved_start, resolved_end, preset = resolve_date_range(
            start_date=start_date, end_date=end_date
        )
    else:
        resolved_start, resolved_end, preset = None, None, "all_time"

    # 1. New Admissions in period
    admissions_query = select(func.count(Member.id)).where(Member.is_archived.is_(False))
    if resolved_start is not None:
        admissions_query = admissions_query.where(Member.joining_date >= resolved_start)
    if resolved_end is not None:
        admissions_query = admissions_query.where(Member.joining_date <= resolved_end)
    new_admissions = db.execute(admissions_query).scalar() or 0

    # 2. Renewals in period
    renewals_query = (
        select(func.count(MembershipRecord.id))
        .select_from(MembershipRecord)
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(
            Member.is_archived.is_(False),
            or_(
                MembershipRecord.membership_type == "renewal",
                MembershipRecord.previous_membership_id.is_not(None),
            ),
        )
    )
    if resolved_start is not None:
        renewals_query = renewals_query.where(MembershipRecord.start_date >= resolved_start)
    if resolved_end is not None:
        renewals_query = renewals_query.where(MembershipRecord.start_date <= resolved_end)
    renewals = db.execute(renewals_query).scalar() or 0

    # 3. Current active and expired counts
    active_member_subq = (
        select(MembershipRecord.member_id)
        .where(_active_contract_clause(today))
        .distinct()
    )

    total_active_members = db.execute(
        select(func.count(Member.id)).where(
            Member.is_archived.is_(False),
            Member.id.in_(active_member_subq),
        )
    ).scalar() or 0

    expired_member_subq = (
        select(MembershipRecord.member_id)
        .where(
            or_(
                and_(
                    MembershipRecord.is_manual_override.is_(False),
                    or_(
                        MembershipRecord.system_status == "expired",
                        and_(
                            MembershipRecord.system_status == "active",
                            MembershipRecord.expiry_date < today,
                        ),
                    ),
                ),
                and_(
                    MembershipRecord.is_manual_override.is_(True),
                    MembershipRecord.override_status == "expired",
                ),
            )
        )
        .distinct()
    )

    total_expired_members = db.execute(
        select(func.count(Member.id)).where(
            Member.is_archived.is_(False),
            Member.id.not_in(active_member_subq),
            Member.id.in_(expired_member_subq),
        )
    ).scalar() or 0

    expiring_7d = db.execute(
        select(func.count(distinct(MembershipRecord.member_id)))
        .select_from(MembershipRecord)
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(
            Member.is_archived.is_(False),
            MembershipRecord.is_manual_override.is_(False),
            MembershipRecord.system_status == "active",
            MembershipRecord.start_date <= today,
            MembershipRecord.expiry_date >= today,
            MembershipRecord.expiry_date <= today + timedelta(days=7),
        )
    ).scalar() or 0

    expiring_3d = db.execute(
        select(func.count(distinct(MembershipRecord.member_id)))
        .select_from(MembershipRecord)
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(
            Member.is_archived.is_(False),
            MembershipRecord.is_manual_override.is_(False),
            MembershipRecord.system_status == "active",
            MembershipRecord.start_date <= today,
            MembershipRecord.expiry_date >= today,
            MembershipRecord.expiry_date <= today + timedelta(days=3),
        )
    ).scalar() or 0

    # 4. Plan distribution (optimized grouped queries - zero N+1)
    plans = db.execute(
        select(MembershipPlan).where(MembershipPlan.is_archived.is_(False))
    ).scalars().all()

    active_by_plan = dict(
        db.execute(
            select(
                MembershipRecord.plan_id,
                func.count(MembershipRecord.id),
            )
            .select_from(MembershipRecord)
            .join(Member, MembershipRecord.member_id == Member.id)
            .where(
                Member.is_archived.is_(False),
                _active_contract_clause(today),
            )
            .group_by(MembershipRecord.plan_id)
        ).all()
    )

    total_by_plan = dict(
        db.execute(
            select(
                MembershipRecord.plan_id,
                func.count(MembershipRecord.id),
            )
            .select_from(MembershipRecord)
            .join(Member, MembershipRecord.member_id == Member.id)
            .where(Member.is_archived.is_(False))
            .group_by(MembershipRecord.plan_id)
        ).all()
    )

    plan_dist_items: List[PlanDistributionItem] = [
        PlanDistributionItem(
            plan_id=p.id,
            plan_name=p.name,
            duration_days=p.duration_days,
            base_price=Decimal(str(p.base_price)),
            active_members_count=active_by_plan.get(p.id, 0),
            total_contracts_count=total_by_plan.get(p.id, 0),
        )
        for p in plans
    ]

    # 5. Membership Type Breakdown (contracts in period or all non-archived)
    type_query = (
        select(
            MembershipRecord.membership_type,
            func.count(MembershipRecord.id),
        )
        .select_from(MembershipRecord)
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(Member.is_archived.is_(False))
    )
    if resolved_start is not None:
        type_query = type_query.where(MembershipRecord.start_date >= resolved_start)
    if resolved_end is not None:
        type_query = type_query.where(MembershipRecord.start_date <= resolved_end)

    type_counts = db.execute(
        type_query.group_by(MembershipRecord.membership_type)
    ).all()

    type_dict = {row[0]: row[1] for row in type_counts}

    return MembershipAnalyticsResponse(
        period=AnalyticsPeriod(
            start_date=resolved_start,
            end_date=resolved_end,
            preset=preset,
        ),
        summary=MembershipAnalyticsSummary(
            new_admissions=new_admissions,
            renewals=renewals,
            total_active_members=total_active_members,
            total_expired_members=total_expired_members,
            expiring_within_7_days=expiring_7d,
            expiring_within_3_days=expiring_3d,
        ),
        plan_distribution=plan_dist_items,
        membership_type_breakdown=MembershipTypeBreakdown(
            new_count=type_dict.get("new", 0),
            renewal_count=type_dict.get("renewal", 0),
            upgrade_count=type_dict.get("upgrade", 0),
        ),
    )


# ---------------------------------------------------------------------------
# Endpoint Service 3: Financial Analytics
# ---------------------------------------------------------------------------


def get_financial_analytics(
    db: Session,
    preset: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> FinancialAnalyticsResponse:
    resolved_start, resolved_end, resolved_preset = resolve_date_range(
        preset=preset, start_date=start_date, end_date=end_date
    )

    gross_confirmed, processed_refunds, net_collections = get_collections_for_period(
        db, resolved_start, resolved_end
    )
    total_outstanding_dues = get_total_outstanding_dues(db)

    # Breakdown by Payment Type
    pt_rows = db.execute(
        select(
            Payment.payment_type,
            func.coalesce(func.sum(Payment.amount), Decimal("0.00")),
            func.count(Payment.id),
        )
        .where(
            Payment.status == "confirmed",
            Payment.payment_date >= resolved_start,
            Payment.payment_date <= resolved_end,
        )
        .group_by(Payment.payment_type)
    ).all()

    pt_dict = {
        row[0]: PaymentTypeMetric(amount=Decimal(str(row[1])), count=row[2])
        for row in pt_rows
    }

    by_payment_type = PaymentTypeBreakdown(
        full=pt_dict.get("full", PaymentTypeMetric(amount=Decimal("0.00"), count=0)),
        partial=pt_dict.get("partial", PaymentTypeMetric(amount=Decimal("0.00"), count=0)),
        installment=pt_dict.get(
            "installment", PaymentTypeMetric(amount=Decimal("0.00"), count=0)
        ),
        advance=pt_dict.get("advance", PaymentTypeMetric(amount=Decimal("0.00"), count=0)),
    )

    # Revenue by Membership Type (new vs renewal)
    mt_rows = db.execute(
        select(
            func.coalesce(MembershipRecord.membership_type, "other"),
            func.coalesce(func.sum(Payment.amount), Decimal("0.00")),
        )
        .select_from(Payment)
        .outerjoin(MembershipRecord, Payment.membership_record_id == MembershipRecord.id)
        .where(
            Payment.status == "confirmed",
            Payment.payment_date >= resolved_start,
            Payment.payment_date <= resolved_end,
        )
        .group_by(func.coalesce(MembershipRecord.membership_type, "other"))
    ).all()

    mt_dict = {row[0]: Decimal(str(row[1])) for row in mt_rows}

    by_membership_type = MembershipTypeRevenue(
        new_membership_revenue=mt_dict.get("new", Decimal("0.00")),
        renewal_revenue=mt_dict.get("renewal", Decimal("0.00")),
        other_revenue=mt_dict.get("other", Decimal("0.00")) + mt_dict.get("upgrade", Decimal("0.00")),
    )

    # Breakdown by Payment Method
    pm_rows = db.execute(
        select(
            Payment.payment_method,
            func.coalesce(func.sum(Payment.amount), Decimal("0.00")),
            func.count(Payment.id),
        )
        .where(
            Payment.status == "confirmed",
            Payment.payment_date >= resolved_start,
            Payment.payment_date <= resolved_end,
        )
        .group_by(Payment.payment_method)
    ).all()

    by_payment_method = [
        PaymentMethodMetric(
            method=row[0],
            amount=Decimal(str(row[1])),
            count=row[2],
        )
        for row in pm_rows
    ]

    return FinancialAnalyticsResponse(
        period=AnalyticsPeriod(
            start_date=resolved_start,
            end_date=resolved_end,
            preset=resolved_preset,
        ),
        totals=FinancialTotals(
            gross_confirmed_collections=gross_confirmed,
            processed_refunds=processed_refunds,
            net_collections=net_collections,
            total_outstanding_dues=total_outstanding_dues,
        ),
        by_payment_type=by_payment_type,
        by_membership_type=by_membership_type,
        by_payment_method=by_payment_method,
    )


# ---------------------------------------------------------------------------
# Endpoint Service 4: Renewal Pipeline
# ---------------------------------------------------------------------------


def get_renewal_pipeline(
    db: Session,
    category: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> RenewalPipelineResponse:
    today = get_business_today()
    if page < 1:
        raise BadRequestException(detail="page must be greater than or equal to 1.")
    if page_size < 1 or page_size > 100:
        raise BadRequestException(detail="page_size must be between 1 and 100.")

    valid_categories = {
        "all",
        "expiring_7_days",
        "expiring_3_days",
        "urgent_expiry",
        "expiring_soon",
        "already_expired",
        "renewal_pending",
        "recently_renewed",
    }
    if category not in valid_categories:
        raise BadRequestException(
            detail=f"Invalid category '{category}'. Must be one of {sorted(list(valid_categories))}."
        )

    # Subqueries for contract financial dues
    gross_paid_subq, refunds_subq, waived_subq = _contract_outstanding_subqueries()
    net_paid_expr = gross_paid_subq - refunds_subq
    contract_balance_expr = MembershipRecord.total_fee - net_paid_expr - waived_subq
    outstanding_case = case(
        (contract_balance_expr > Decimal("0.00"), contract_balance_expr),
        else_=Decimal("0.00"),
    )

    # Fetch non-archived members and their contracts in a single join query (Zero N+1)
    stmt = (
        select(
            Member,
            MembershipRecord,
            outstanding_case.label("outstanding_dues"),
        )
        .join(Member, MembershipRecord.member_id == Member.id)
        .where(Member.is_archived.is_(False))
        .order_by(Member.full_name.asc(), MembershipRecord.expiry_date.desc(), MembershipRecord.created_at.desc())
    )
    rows = db.execute(stmt).all()

    # Group contracts by member preserving Member.full_name order
    from collections import OrderedDict
    member_map: Dict[uuid.UUID, Member] = OrderedDict()
    member_contracts: Dict[uuid.UUID, List[Any]] = {}

    for m, c, dues in rows:
        if m.id not in member_map:
            member_map[m.id] = m
            member_contracts[m.id] = []
        member_contracts[m.id].append((c, dues))

    pipeline_items: List[RenewalPipelineItem] = []
    expiring_7d_count = 0
    expiring_3d_count = 0
    already_expired_count = 0
    renewal_pending_count = 0
    recently_renewed_count = 0

    for m_id, m in member_map.items():
        contracts = member_contracts[m_id]
        if not contracts:
            continue

        # Look for active contracts first
        active_contract = None
        pending_contract = None
        latest_expired_contract = None
        recent_renewal_contract = None

        for row in contracts:
            c = row[0]
            # Check for active
            is_active = (
                (c.is_manual_override and c.override_status == "active")
                or (not c.is_manual_override and c.system_status == "active" and c.start_date <= today <= c.expiry_date)
            )
            if is_active and not active_contract:
                active_contract = row

            if c.system_status == "pending_activation" and not pending_contract:
                pending_contract = row

            if not is_active and c.expiry_date < today and not latest_expired_contract:
                latest_expired_contract = row

            # Recently renewed in past 30 days
            is_renewal = (c.membership_type == "renewal" or c.previous_membership_id is not None)
            if is_renewal and c.start_date >= today - timedelta(days=30) and not recent_renewal_contract:
                recent_renewal_contract = row

        # Determine pipeline status and entry
        item: Optional[RenewalPipelineItem] = None

        if active_contract:
            c = active_contract[0]
            dues = Decimal(str(active_contract[1] or "0.00")).quantize(Decimal("0.01"))
            days_left = (c.expiry_date - today).days

            if 0 <= days_left <= 3:
                expiring_3d_count += 1
                expiring_7d_count += 1
                item = RenewalPipelineItem(
                    member_id=m.id,
                    member_code=m.member_code,
                    member_name=m.full_name,
                    phone_number=m.phone_number,
                    membership_id=c.id,
                    plan_name=c.plan_snapshot_name,
                    expiry_date=c.expiry_date,
                    days_until_expiry=days_left,
                    outstanding_dues=dues,
                    pipeline_status="urgent_expiry",
                )
            elif 4 <= days_left <= 7:
                expiring_7d_count += 1
                item = RenewalPipelineItem(
                    member_id=m.id,
                    member_code=m.member_code,
                    member_name=m.full_name,
                    phone_number=m.phone_number,
                    membership_id=c.id,
                    plan_name=c.plan_snapshot_name,
                    expiry_date=c.expiry_date,
                    days_until_expiry=days_left,
                    outstanding_dues=dues,
                    pipeline_status="expiring_soon",
                )
            elif recent_renewal_contract:
                recently_renewed_count += 1
                rc = recent_renewal_contract[0]
                r_dues = Decimal(str(recent_renewal_contract[1] or "0.00")).quantize(Decimal("0.01"))
                item = RenewalPipelineItem(
                    member_id=m.id,
                    member_code=m.member_code,
                    member_name=m.full_name,
                    phone_number=m.phone_number,
                    membership_id=rc.id,
                    plan_name=rc.plan_snapshot_name,
                    expiry_date=rc.expiry_date,
                    days_until_expiry=(rc.expiry_date - today).days,
                    outstanding_dues=r_dues,
                    pipeline_status="recently_renewed",
                )
        elif pending_contract and latest_expired_contract:
            renewal_pending_count += 1
            pc = pending_contract[0]
            p_dues = Decimal(str(pending_contract[1] or "0.00")).quantize(Decimal("0.01"))
            item = RenewalPipelineItem(
                member_id=m.id,
                member_code=m.member_code,
                member_name=m.full_name,
                phone_number=m.phone_number,
                membership_id=pc.id,
                plan_name=pc.plan_snapshot_name,
                expiry_date=pc.expiry_date,
                days_until_expiry=(pc.expiry_date - today).days,
                outstanding_dues=p_dues,
                pipeline_status="renewal_pending",
            )
        elif latest_expired_contract:
            already_expired_count += 1
            ec = latest_expired_contract[0]
            e_dues = Decimal(str(latest_expired_contract[1] or "0.00")).quantize(Decimal("0.01"))
            days_overdue = (today - ec.expiry_date).days
            item = RenewalPipelineItem(
                member_id=m.id,
                member_code=m.member_code,
                member_name=m.full_name,
                phone_number=m.phone_number,
                membership_id=ec.id,
                plan_name=ec.plan_snapshot_name,
                expiry_date=ec.expiry_date,
                days_until_expiry=-days_overdue,
                outstanding_dues=e_dues,
                pipeline_status="already_expired",
            )

        if item:
            pipeline_items.append(item)

    # Filter items by category if requested
    filtered_items: List[RenewalPipelineItem] = []
    for it in pipeline_items:
        if category == "all":
            filtered_items.append(it)
        elif category in ("expiring_3_days", "urgent_expiry") and it.pipeline_status == "urgent_expiry":
            filtered_items.append(it)
        elif category == "expiring_soon" and it.pipeline_status == "expiring_soon":
            filtered_items.append(it)
        elif category == "expiring_7_days" and it.pipeline_status in ("urgent_expiry", "expiring_soon"):
            filtered_items.append(it)
        elif category == "already_expired" and it.pipeline_status == "already_expired":
            filtered_items.append(it)
        elif category == "renewal_pending" and it.pipeline_status == "renewal_pending":
            filtered_items.append(it)
        elif category == "recently_renewed" and it.pipeline_status == "recently_renewed":
            filtered_items.append(it)

    # Paginate
    total_count = len(filtered_items)
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
    offset = (page - 1) * page_size
    paged_items = filtered_items[offset : offset + page_size]

    return RenewalPipelineResponse(
        summary=RenewalPipelineSummary(
            expiring_7_days_count=expiring_7d_count,
            expiring_3_days_count=expiring_3d_count,
            already_expired_count=already_expired_count,
            renewal_pending_count=renewal_pending_count,
            recently_renewed_count=recently_renewed_count,
        ),
        items=paged_items,
        pagination=PaginationMetadata(
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


# ---------------------------------------------------------------------------
# Endpoint Service 5: Recent Activity
# ---------------------------------------------------------------------------


def get_recent_activity(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    action_filter: Optional[str] = None,
) -> RecentActivityResponse:
    if page < 1:
        raise BadRequestException(detail="page must be greater than or equal to 1.")
    if page_size < 1 or page_size > 100:
        raise BadRequestException(detail="page_size must be between 1 and 100.")

    base_query = select(AuditLog, Owner.name.label("owner_name")).outerjoin(
        Owner, AuditLog.owner_id == Owner.id
    )

    count_query = select(func.count(AuditLog.id))

    if action_filter:
        base_query = base_query.where(AuditLog.action == action_filter)
        count_query = count_query.where(AuditLog.action == action_filter)

    total_count = db.execute(count_query).scalar() or 0
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

    offset = (page - 1) * page_size
    rows = db.execute(
        base_query.order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    ).all()

    items = [
        RecentActivityItem(
            id=row.AuditLog.id,
            action=row.AuditLog.action,
            entity_type=row.AuditLog.entity_type,
            entity_id=row.AuditLog.entity_id,
            description=_format_activity_description(
                row.AuditLog.action, row.AuditLog.entity_type, row.owner_name
            ),
            actor_owner_id=row.AuditLog.owner_id,
            actor_owner_name=row.owner_name,
            ip_address=row.AuditLog.ip_address,
            timestamp=row.AuditLog.created_at,
        )
        for row in rows
    ]

    return RecentActivityResponse(
        items=items,
        pagination=PaginationMetadata(
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )

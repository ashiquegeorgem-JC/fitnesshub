import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import (
    Member,
    MembershipPlan,
    MembershipRecord,
    Owner,
    OwnerSession,
    Payment,
    PaymentRefund,
)
from app.models.sequence import SystemSequence
from app.core.security import create_access_token, hash_password


# ---------------------------------------------------------------------------
# Shared test database and client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(test_engine) -> Generator[Session, None, None]:
    with Session(test_engine) as session:
        yield session
        session.rollback()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Shared helper factories
# ---------------------------------------------------------------------------

def _make_owner(db: Session, suffix: str = "") -> Owner:
    unique = uuid.uuid4().hex[:8]
    owner = Owner(
        id=uuid.uuid4(),
        name=f"Owner {suffix or unique}",
        phone_number=f"+9199{unique[:8]}",
        email=f"owner_{unique}@regalfitness.com",
        password_hash=hash_password("SecurePass1!"),
    )
    db.add(owner)
    db.flush()
    return owner


def _make_session(db: Session, owner: Owner) -> str:
    """Create a valid owner session and return a bearer token."""
    session_id = uuid.uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    owner_session = OwnerSession(
        id=session_id,
        owner_id=owner.id,
        refresh_token_hash="dummy_hash_" + uuid.uuid4().hex,
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(owner_session)
    db.flush()
    token = create_access_token(
        owner_id=owner.id,
        session_id=session_id,
        expires_delta=timedelta(hours=1),
    )
    return token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _ensure_seq(db: Session) -> None:
    """Ensure system_sequences row exists for SQLite tests."""
    existing = db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(SystemSequence).where(
            SystemSequence.sequence_name == "member_code_seq"
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            SystemSequence(
                sequence_name="member_code_seq",
                prefix="RF",
                padding_digits=3,
                current_value=0,
                description="Sequential member IDs",
            )
        )
        db.flush()


def _make_member(
    db: Session,
    phone: str = "+919000000001",
    is_archived: bool = False,
    code: str = None,
) -> Member:
    if code is None:
        code = f"RF{uuid.uuid4().int % 9000 + 1000:04d}"
    member = Member(
        id=uuid.uuid4(),
        member_code=code,
        full_name="Test Member",
        phone_number=phone,
        gender="male",
        joining_date=date.today(),
        is_archived=is_archived,
    )
    db.add(member)
    db.flush()
    return member


def _make_plan(db: Session, owner: Owner) -> MembershipPlan:
    plan = MembershipPlan(
        id=uuid.uuid4(),
        name="Basic Plan",
        category="general",
        duration_days=30,
        base_price=Decimal("5000.00"),
        created_by_owner_id=owner.id,
    )
    db.add(plan)
    db.flush()
    return plan


def _make_membership(
    db: Session, member: Member, plan: MembershipPlan, owner: Owner
) -> MembershipRecord:
    today = date.today()
    mr = MembershipRecord(
        id=uuid.uuid4(),
        member_id=member.id,
        plan_id=plan.id,
        plan_snapshot_name=plan.name,
        plan_snapshot_duration_days=plan.duration_days,
        plan_snapshot_base_price=plan.base_price,
        plan_snapshot_is_pt=False,
        discount_amount=Decimal("0.00"),
        total_fee=plan.base_price,
        start_date=today,
        expiry_date=today + timedelta(days=30),
        system_status="pending_activation",
        is_manual_override=False,
        membership_type="new",
        created_by_owner_id=owner.id,
    )
    db.add(mr)
    db.flush()
    return mr


def _make_payment(
    db: Session, member: Member, mr: MembershipRecord = None, amount: Decimal = Decimal("5000.00"), status: str = "confirmed"
) -> Payment:
    pay = Payment(
        id=uuid.uuid4(),
        payment_number=f"PAY{uuid.uuid4().hex[:8].upper()}",
        member_id=member.id,
        membership_record_id=mr.id if mr else None,
        amount=amount,
        payment_type="full",
        payment_method="cash",
        payment_date=date.today(),
        status=status,
    )
    db.add(pay)
    db.flush()
    return pay


# ===========================================================================
# PART 1: AUTHENTICATION TESTS
# ===========================================================================

class TestMemberAuthentication:
    def test_unauthenticated_create_rejected(self, client: TestClient) -> None:
        resp = client.post("/api/v1/members/", json={
            "full_name": "John Doe", "phone_number": "9876543210", "gender": "male"
        })
        assert resp.status_code == 401

    def test_unauthenticated_list_rejected(self, client: TestClient) -> None:
        assert client.get("/api/v1/members/").status_code == 401

    def test_unauthenticated_get_rejected(self, client: TestClient) -> None:
        assert client.get(f"/api/v1/members/{uuid.uuid4()}").status_code == 401

    def test_unauthenticated_update_rejected(self, client: TestClient) -> None:
        assert client.patch(f"/api/v1/members/{uuid.uuid4()}", json={"full_name": "X"}).status_code == 401

    def test_unauthenticated_archive_rejected(self, client: TestClient) -> None:
        assert client.post(f"/api/v1/members/{uuid.uuid4()}/archive").status_code == 401

    def test_unauthenticated_reactivate_rejected(self, client: TestClient) -> None:
        assert client.post(f"/api/v1/members/{uuid.uuid4()}/reactivate").status_code == 401

    def test_unauthenticated_memberships_rejected(self, client: TestClient) -> None:
        assert client.get(f"/api/v1/members/{uuid.uuid4()}/memberships").status_code == 401

    def test_unauthenticated_payments_rejected(self, client: TestClient) -> None:
        assert client.get(f"/api/v1/members/{uuid.uuid4()}/payments").status_code == 401

    def test_invalid_token_rejected(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/members/",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_both_owners_have_equal_access(self, db: Session, client: TestClient) -> None:
        """Both owners see the same member list."""
        owner1 = _make_owner(db, "owner1")
        owner2 = _make_owner(db, "owner2")
        token1 = _make_session(db, owner1)
        token2 = _make_session(db, owner2)
        db.commit()

        resp1 = client.get("/api/v1/members/", headers=_auth_headers(token1))
        resp2 = client.get("/api/v1/members/", headers=_auth_headers(token2))
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["total"] == resp2.json()["total"]


# ===========================================================================
# PART 2: CREATE MEMBER TESTS
# ===========================================================================

class TestCreateMember:
    def test_create_member_success(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        db.commit()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Alice Kumar", "phone_number": "9811111111", "gender": "female"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["full_name"] == "Alice Kumar"
        assert data["phone_number"] == "+919811111111"
        assert data["gender"] == "female"
        assert data["is_archived"] is False
        assert data["member_code"].startswith("RF")

    def test_create_member_generates_rf_code(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        db.commit()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Bob Singh", "phone_number": "9822222222", "gender": "male"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        code = resp.json()["member_code"]
        assert code.startswith("RF")
        assert code[2:].isdigit()

    def test_phone_normalized_on_create(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        db.commit()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Carol Nair", "phone_number": "98 3333 3333", "gender": "female"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        assert resp.json()["phone_number"] == "+919833333333"

    def test_duplicate_active_phone_rejected(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        _make_member(db, phone="+919844444444")
        db.commit()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Dave Pillai", "phone_number": "9844444444", "gender": "male"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 409

    def test_archived_phone_can_be_reused(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        _make_member(db, phone="+919855555555", is_archived=True)
        db.commit()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Eve Thomas", "phone_number": "9855555555", "gender": "female"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201

    def test_create_does_not_create_membership(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        from app.models import MembershipRecord as MR
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        db.commit()

        before = db.execute(sa_select(MR)).scalars().all()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Frank Jose", "phone_number": "9866666666", "gender": "male"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        after = db.execute(sa_select(MR)).scalars().all()
        assert len(after) == len(before), "Create member must not create membership records"

    def test_create_does_not_create_payment(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        db.commit()

        before = db.execute(sa_select(Payment)).scalars().all()
        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Grace Menon", "phone_number": "9877777777", "gender": "female"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        after = db.execute(sa_select(Payment)).scalars().all()
        assert len(after) == len(before), "Create member must not create payment records"

    def test_missing_required_field_rejected(self, client: TestClient, db: Session) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()
        resp = client.post(
            "/api/v1/members/",
            json={"phone_number": "9800000001"},  # missing full_name and gender
            headers=_auth_headers(token),
        )
        assert resp.status_code == 422

    def test_invalid_gender_rejected(self, client: TestClient, db: Session) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()
        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Harry", "phone_number": "9800000002", "gender": "alien"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 422

    def test_protected_field_member_code_forbidden(self, client: TestClient, db: Session) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()
        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Ian", "phone_number": "9800000003", "gender": "male", "member_code": "RF999"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 422  # extra="forbid" in schema

    def test_e164_phone_accepted_directly(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        db.commit()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Jaya Rajan", "phone_number": "+447911123456", "gender": "female"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        assert resp.json()["phone_number"] == "+447911123456"

    def test_future_dob_rejected(self, client: TestClient, db: Session) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()
        future_date = (date.today() + timedelta(days=10)).isoformat()
        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Kiran", "phone_number": "9800000005", "gender": "male", "date_of_birth": future_date},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 422

    def test_audit_event_created_on_member_creation(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        from app.models.audit import AuditLog
        owner = _make_owner(db)
        token = _make_session(db, owner)
        _ensure_seq(db)
        db.commit()

        resp = client.post(
            "/api/v1/members/",
            json={"full_name": "Lena Babu", "phone_number": "9888000001", "gender": "female"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        member_id = resp.json()["id"]

        audit = db.execute(
            sa_select(AuditLog).where(
                AuditLog.action == "member.created",
                AuditLog.entity_type == "member",
            )
        ).scalars().all()
        ids = [str(a.entity_id) for a in audit]
        assert member_id in ids


# ===========================================================================
# PART 3: LIST AND SEARCH MEMBERS
# ===========================================================================

class TestListMembers:
    def test_list_defaults_to_non_archived(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        active = _make_member(db, phone="+919100000001")
        archived = _make_member(db, phone="+919100000002", is_archived=True)
        db.commit()

        resp = client.get("/api/v1/members/", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        ids = [item["id"] for item in data["items"]]
        assert str(active.id) in ids
        assert str(archived.id) not in ids

    def test_list_archived_returns_only_archived(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        archived = _make_member(db, phone="+919100000003", is_archived=True)
        db.commit()

        resp = client.get("/api/v1/members/?is_archived=true", headers=_auth_headers(token))
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(archived.id) in ids

    def test_search_by_full_name(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919200000001")
        member.full_name = "UniqueNameXYZ"
        db.flush()
        db.commit()

        resp = client.get("/api/v1/members/?search=UniqueNameXYZ", headers=_auth_headers(token))
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(member.id) in ids

    def test_search_by_rf_code(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919200000002", code="RF7777")
        db.commit()

        resp = client.get("/api/v1/members/?search=RF7777", headers=_auth_headers(token))
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(member.id) in ids

    def test_search_by_phone_normalized(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919200000003")
        db.commit()

        resp = client.get("/api/v1/members/?search=9200000003", headers=_auth_headers(token))
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(member.id) in ids

    def test_filter_by_gender(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        male = _make_member(db, phone="+919300000001")
        male.gender = "male"
        female = _make_member(db, phone="+919300000002")
        female.gender = "female"
        db.flush()
        db.commit()

        resp = client.get("/api/v1/members/?gender=female", headers=_auth_headers(token))
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(female.id) in ids
        assert str(male.id) not in ids

    def test_pagination_metadata(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get("/api/v1/members/?page=1&page_size=5", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "page" in data
        assert "page_size" in data
        assert "total" in data
        assert "total_pages" in data
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_empty_search_returns_no_error(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get("/api/v1/members/?search=ZZZNOMATCH99999", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_sort_by_full_name_asc(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get(
            "/api/v1/members/?sort_by=full_name&sort_order=asc",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200

    def test_invalid_page_size_rejected(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get("/api/v1/members/?page_size=200", headers=_auth_headers(token))
        assert resp.status_code == 422

    def test_page_zero_rejected(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get("/api/v1/members/?page=0", headers=_auth_headers(token))
        assert resp.status_code == 422


# ===========================================================================
# PART 4: GET MEMBER DETAILS
# ===========================================================================

class TestGetMemberDetails:
    def test_get_existing_member(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919400000001")
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(member.id)
        assert data["member_code"] == member.member_code

    def test_get_archived_member_accessible(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        archived = _make_member(db, phone="+919400000002", is_archived=True)
        db.commit()

        resp = client.get(f"/api/v1/members/{archived.id}", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["is_archived"] is True

    def test_get_unknown_member_returns_404(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get(f"/api/v1/members/{uuid.uuid4()}", headers=_auth_headers(token))
        assert resp.status_code == 404

    def test_response_does_not_expose_password_hash(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919400000003")
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}", headers=_auth_headers(token))
        assert resp.status_code == 200
        body = resp.text
        assert "password_hash" not in body
        assert "password" not in body


# ===========================================================================
# PART 5: UPDATE MEMBER
# ===========================================================================

class TestUpdateMember:
    def test_partial_update_name(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919500000001")
        db.commit()

        resp = client.patch(
            f"/api/v1/members/{member.id}",
            json={"full_name": "Updated Name"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    def test_partial_update_phone_normalized(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919500000002")
        db.commit()

        resp = client.patch(
            f"/api/v1/members/{member.id}",
            json={"phone_number": "9511111111"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["phone_number"] == "+919511111111"

    def test_update_phone_conflict_returns_409(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member1 = _make_member(db, phone="+919500000003")
        _make_member(db, phone="+919500000004")
        db.commit()

        resp = client.patch(
            f"/api/v1/members/{member1.id}",
            json={"phone_number": "9500000004"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 409

    def test_update_nonexistent_member_returns_404(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.patch(
            f"/api/v1/members/{uuid.uuid4()}",
            json={"full_name": "Ghost"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 404

    def test_protected_field_member_code_rejected(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919500000005")
        db.commit()

        resp = client.patch(
            f"/api/v1/members/{member.id}",
            json={"member_code": "RF9999"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 422

    def test_protected_field_is_archived_rejected(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919500000006")
        db.commit()

        resp = client.patch(
            f"/api/v1/members/{member.id}",
            json={"is_archived": True},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 422

    def test_empty_update_returns_400(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919500000007")
        db.commit()

        resp = client.patch(
            f"/api/v1/members/{member.id}",
            json={},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 400

    def test_update_audit_event_recorded(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        from app.models.audit import AuditLog
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919500000008")
        db.commit()

        client.patch(
            f"/api/v1/members/{member.id}",
            json={"full_name": "Audited Name"},
            headers=_auth_headers(token),
        )
        audit = db.execute(
            sa_select(AuditLog).where(
                AuditLog.action == "member.updated",
                AuditLog.entity_type == "member",
            )
        ).scalars().all()
        entity_ids = [str(a.entity_id) for a in audit]
        assert str(member.id) in entity_ids


# ===========================================================================
# PART 6: ARCHIVE AND REACTIVATE
# ===========================================================================

class TestArchiveReactivate:
    def test_archive_member_success(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000001")
        db.commit()

        resp = client.post(f"/api/v1/members/{member.id}/archive", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_archived"] is True
        assert data["archived_at"] is not None

    def test_archive_with_reason(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000002")
        db.commit()

        resp = client.post(
            f"/api/v1/members/{member.id}/archive",
            json={"reason": "Relocated abroad"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["archive_reason"] == "Relocated abroad"

    def test_archive_already_archived_returns_409(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000003", is_archived=True)
        db.commit()

        resp = client.post(f"/api/v1/members/{member.id}/archive", headers=_auth_headers(token))
        assert resp.status_code == 409

    def test_archive_preserves_member_id(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000004")
        original_id = str(member.id)
        original_code = member.member_code
        db.commit()

        resp = client.post(f"/api/v1/members/{member.id}/archive", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == original_id
        assert resp.json()["member_code"] == original_code

    def test_archive_nonexistent_returns_404(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.post(f"/api/v1/members/{uuid.uuid4()}/archive", headers=_auth_headers(token))
        assert resp.status_code == 404

    def test_archived_member_still_viewable(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000005")
        db.commit()

        client.post(f"/api/v1/members/{member.id}/archive", headers=_auth_headers(token))
        resp = client.get(f"/api/v1/members/{member.id}", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["is_archived"] is True

    def test_archive_audit_event_recorded(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        from app.models.audit import AuditLog
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000006")
        db.commit()

        client.post(f"/api/v1/members/{member.id}/archive", headers=_auth_headers(token))
        audit = db.execute(
            sa_select(AuditLog).where(
                AuditLog.action == "member.archived",
                AuditLog.entity_type == "member",
            )
        ).scalars().all()
        entity_ids = [str(a.entity_id) for a in audit]
        assert str(member.id) in entity_ids

    def test_reactivate_archived_member_success(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000007", is_archived=True)
        db.commit()

        resp = client.post(f"/api/v1/members/{member.id}/reactivate", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_archived"] is False
        assert data["archived_at"] is None
        assert data["member_code"] == member.member_code

    def test_reactivate_preserves_original_code(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000008", is_archived=True, code="RF8888")
        db.commit()

        resp = client.post(f"/api/v1/members/{member.id}/reactivate", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["member_code"] == "RF8888"

    def test_reactivate_phone_conflict_returns_409(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        archived = _make_member(db, phone="+919600000009", is_archived=True)
        _make_member(db, phone="+919600000009", code="RF9009")  # another active member with same phone
        db.commit()

        resp = client.post(f"/api/v1/members/{archived.id}/reactivate", headers=_auth_headers(token))
        assert resp.status_code == 409

    def test_reactivate_active_member_returns_409(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000010")
        db.commit()

        resp = client.post(f"/api/v1/members/{member.id}/reactivate", headers=_auth_headers(token))
        assert resp.status_code == 409

    def test_reactivate_does_not_activate_membership(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000011", is_archived=True)
        plan = _make_plan(db, owner)
        mr = _make_membership(db, member, plan, owner)
        assert mr.system_status == "pending_activation"
        db.commit()

        client.post(f"/api/v1/members/{member.id}/reactivate", headers=_auth_headers(token))

        from sqlalchemy import select as sa_select
        updated_mr = db.execute(
            sa_select(MembershipRecord).where(MembershipRecord.id == mr.id)
        ).scalar_one()
        assert updated_mr.system_status == "pending_activation", \
            "Reactivation must not activate existing memberships"

    def test_reactivate_audit_event_recorded(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        from app.models.audit import AuditLog
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919600000012", is_archived=True)
        db.commit()

        client.post(f"/api/v1/members/{member.id}/reactivate", headers=_auth_headers(token))
        audit = db.execute(
            sa_select(AuditLog).where(
                AuditLog.action == "member.reactivated",
                AuditLog.entity_type == "member",
            )
        ).scalars().all()
        entity_ids = [str(a.entity_id) for a in audit]
        assert str(member.id) in entity_ids


# ===========================================================================
# PART 7: HISTORY ENDPOINTS
# ===========================================================================

class TestMemberHistory:
    def test_membership_history_returns_all_records(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919700000001")
        plan = _make_plan(db, owner)
        mr1 = _make_membership(db, member, plan, owner)
        mr2 = _make_membership(db, member, plan, owner)
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}/memberships", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        ids = [item["id"] for item in data["items"]]
        assert str(mr1.id) in ids
        assert str(mr2.id) in ids

    def test_membership_history_nonexistent_returns_404(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get(f"/api/v1/members/{uuid.uuid4()}/memberships", headers=_auth_headers(token))
        assert resp.status_code == 404

    def test_membership_history_empty_for_new_member(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919700000002")
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}/memberships", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_membership_history_isolation(self, db: Session, client: TestClient) -> None:
        """History for member A must not include membership records of member B."""
        owner = _make_owner(db)
        token = _make_session(db, owner)
        memberA = _make_member(db, phone="+919700000003")
        memberB = _make_member(db, phone="+919700000004")
        plan = _make_plan(db, owner)
        mr_a = _make_membership(db, memberA, plan, owner)
        _make_membership(db, memberB, plan, owner)
        db.commit()

        resp = client.get(f"/api/v1/members/{memberA.id}/memberships", headers=_auth_headers(token))
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(mr_a.id) in ids
        assert len(ids) == 1

    def test_membership_history_does_not_modify_records(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919700000005")
        plan = _make_plan(db, owner)
        mr = _make_membership(db, member, plan, owner)
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}/memberships", headers=_auth_headers(token))
        assert resp.status_code == 200
        updated = db.execute(sa_select(MembershipRecord).where(MembershipRecord.id == mr.id)).scalar_one()
        assert updated.system_status == mr.system_status

    def test_payment_history_returns_all_records(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919700000006")
        plan = _make_plan(db, owner)
        mr = _make_membership(db, member, plan, owner)
        p1 = _make_payment(db, member, mr)
        p2 = _make_payment(db, member, mr, status="pending")
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}/payments", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        ids = [item["id"] for item in data["items"]]
        assert str(p1.id) in ids
        assert str(p2.id) in ids

    def test_payment_history_isolation(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        memberA = _make_member(db, phone="+919700000007")
        memberB = _make_member(db, phone="+919700000008")
        plan = _make_plan(db, owner)
        mr_a = _make_membership(db, memberA, plan, owner)
        mr_b = _make_membership(db, memberB, plan, owner)
        p_a = _make_payment(db, memberA, mr_a)
        _make_payment(db, memberB, mr_b)
        db.commit()

        resp = client.get(f"/api/v1/members/{memberA.id}/payments", headers=_auth_headers(token))
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(p_a.id) in ids
        assert len(ids) == 1

    def test_payment_history_refund_amounts(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919700000009")
        plan = _make_plan(db, owner)
        mr = _make_membership(db, member, plan, owner)
        payment = _make_payment(db, member, mr, amount=Decimal("5000.00"))
        refund = PaymentRefund(
            id=uuid.uuid4(),
            refund_number=f"REF{uuid.uuid4().hex[:8].upper()}",
            original_payment_id=payment.id,
            member_id=member.id,
            amount=Decimal("1000.00"),
            refund_reason="Partial refund",
            refund_method="cash",
            status="processed",
            processed_by_owner_id=owner.id,
        )
        db.add(refund)
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}/payments", headers=_auth_headers(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        pay_item = next(i for i in items if i["id"] == str(payment.id))
        assert pay_item["has_refunds"] is True
        assert float(pay_item["refunded_amount"]) == 1000.0

    def test_payment_history_nonexistent_member_returns_404(self, db: Session, client: TestClient) -> None:
        owner = _make_owner(db)
        token = _make_session(db, owner)
        db.commit()

        resp = client.get(f"/api/v1/members/{uuid.uuid4()}/payments", headers=_auth_headers(token))
        assert resp.status_code == 404

    def test_payment_history_does_not_modify_records(self, db: Session, client: TestClient) -> None:
        from sqlalchemy import select as sa_select
        owner = _make_owner(db)
        token = _make_session(db, owner)
        member = _make_member(db, phone="+919700000010")
        plan = _make_plan(db, owner)
        mr = _make_membership(db, member, plan, owner)
        payment = _make_payment(db, member, mr)
        db.commit()

        resp = client.get(f"/api/v1/members/{member.id}/payments", headers=_auth_headers(token))
        assert resp.status_code == 200
        updated = db.execute(sa_select(Payment).where(Payment.id == payment.id)).scalar_one()
        assert updated.status == payment.status


# ===========================================================================
# PART 8: SCHEMA AND PHONE NORMALIZATION UNIT TESTS
# ===========================================================================

class TestPhoneNormalization:
    def test_10_digit_normalized_to_e164(self) -> None:
        from app.schemas.member import normalize_phone_number
        assert normalize_phone_number("9876543210") == "+919876543210"

    def test_11_digit_leading_zero_normalized(self) -> None:
        from app.schemas.member import normalize_phone_number
        assert normalize_phone_number("09876543210") == "+919876543210"

    def test_12_digit_91_normalized(self) -> None:
        from app.schemas.member import normalize_phone_number
        assert normalize_phone_number("919876543210") == "+919876543210"

    def test_e164_accepted_unchanged(self) -> None:
        from app.schemas.member import normalize_phone_number
        assert normalize_phone_number("+919876543210") == "+919876543210"

    def test_uk_e164_accepted(self) -> None:
        from app.schemas.member import normalize_phone_number
        assert normalize_phone_number("+447911123456") == "+447911123456"

    def test_spaces_stripped(self) -> None:
        from app.schemas.member import normalize_phone_number
        assert normalize_phone_number("98 765 43210") == "+919876543210"

    def test_dashes_stripped(self) -> None:
        from app.schemas.member import normalize_phone_number
        assert normalize_phone_number("98-765-43210") == "+919876543210"

    def test_empty_string_raises(self) -> None:
        from app.schemas.member import normalize_phone_number
        with pytest.raises(ValueError):
            normalize_phone_number("")

    def test_non_digit_string_raises(self) -> None:
        from app.schemas.member import normalize_phone_number
        with pytest.raises(ValueError):
            normalize_phone_number("ABCDE")

    def test_too_short_raises(self) -> None:
        from app.schemas.member import normalize_phone_number
        with pytest.raises(ValueError):
            normalize_phone_number("123")


# ===========================================================================
# PART 9: CONCURRENCY AND LIMITATIONS NOTE
# ===========================================================================

class TestConcurrencyNotes:
    """
    SQLite test limitations for concurrency:
    - The advisory lock protocol (`pg_advisory_xact_lock`) runs only on PostgreSQL.
    - The `member_code_seq` PostgreSQL sequence is replaced by SystemSequence
      atomic increments under SQLite. True concurrent sequence safety requires
      PostgreSQL.
    - The `idx_uq_members_active_phone` partial index is CREATE'd in the SQLite
      schema by Alembic without the `postgresql_where` clause (SQLite partial
      index has `sqlite_where`). The constraint is enforced at the ORM/service
      level in this test suite.
    - Full concurrent safety (phone uniqueness under race conditions, RF code
      uniqueness under simultaneous requests) must be verified on PostgreSQL
      staging, not on the SQLite test database.
    """

    def test_sqlite_sequence_increments_monotonically(self, db: Session) -> None:
        """SystemSequence row increments correctly in SQLite (single-threaded)."""
        from app.services.member import _generate_member_code
        from sqlalchemy import select as sa_select

        _ensure_seq(db)
        db.commit()

        seq1 = _generate_member_code(db)
        db.flush()
        seq2 = _generate_member_code(db)
        db.flush()

        n1 = int(seq1[2:])
        n2 = int(seq2[2:])
        assert n2 == n1 + 1

    def test_sqlite_phone_uniqueness_service_layer(self, db: Session) -> None:
        """Service raises ConflictException for duplicate active phone (SQLite)."""
        from app.services.member import _ensure_phone_available
        from app.core.exceptions import ConflictException
        _make_member(db, phone="+919900000001")
        db.commit()

        with pytest.raises(ConflictException):
            _ensure_phone_available(db, "+919900000001")

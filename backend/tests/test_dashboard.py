import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.main import app
from app.models.audit import AuditLog
from app.models.member import Member
from app.models.membership import MembershipDueSchedule, MembershipRecord
from app.models.owner import Owner, OwnerSession
from app.models.payment import Payment, PaymentRefund
from app.models.plan import MembershipPlan
from app.services.dashboard import get_business_today


# ---------------------------------------------------------------------------
# Test Fixtures (SQLite in-memory with StaticPool)
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db():
    """Isolated in-memory SQLite database per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(test_db: Session):
    """TestClient wired to isolated in-memory DB."""
    limiter.clear()

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seed_data(test_db: Session):
    """Seed comprehensive gym data covering owners, plans, members, contracts, payments, and refunds."""
    today = get_business_today()

    # 1. Seed two co-owners
    owner1 = Owner(
        id=uuid.uuid4(),
        name="Vikram Singh",
        phone_number="+919876543210",
        email="vikram@regalfitness.com",
        password_hash=hash_password("OwnerPass1!"),
        account_status="active",
    )
    owner2 = Owner(
        id=uuid.uuid4(),
        name="Rohit Sharma",
        phone_number="+919876543211",
        email="rohit@regalfitness.com",
        password_hash=hash_password("OwnerPass2!"),
        account_status="active",
    )
    test_db.add_all([owner1, owner2])
    test_db.flush()

    # Seed active session for owner 1
    session1_id = uuid.uuid4()
    session1 = OwnerSession(
        id=session1_id,
        owner_id=owner1.id,
        refresh_token_hash="dummy_hash_1",
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    test_db.add(session1)

    # Seed active session for owner 2
    session2_id = uuid.uuid4()
    session2 = OwnerSession(
        id=session2_id,
        owner_id=owner2.id,
        refresh_token_hash="dummy_hash_2",
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    test_db.add(session2)

    # 2. Seed Membership Plans
    plan_monthly = MembershipPlan(
        id=uuid.uuid4(),
        name="Monthly General",
        category="general",
        duration_days=30,
        base_price=Decimal("1500.00"),
        created_by_owner_id=owner1.id,
    )
    plan_annual = MembershipPlan(
        id=uuid.uuid4(),
        name="Annual Strength",
        category="strength",
        duration_days=365,
        base_price=Decimal("12000.00"),
        created_by_owner_id=owner1.id,
    )
    test_db.add_all([plan_monthly, plan_annual])
    test_db.flush()

    # 3. Seed Members
    # Member 1: Active, joined today
    m1 = Member(
        id=uuid.uuid4(),
        member_code="RF001",
        full_name="Amit Kumar",
        phone_number="+919800000001",
        gender="male",
        joining_date=today,
        is_archived=False,
        created_by_owner_id=owner1.id,
    )
    # Member 2: Active, expiring in 2 days (urgent expiry)
    m2 = Member(
        id=uuid.uuid4(),
        member_code="RF002",
        full_name="Pooja Verma",
        phone_number="+919800000002",
        gender="female",
        joining_date=today - timedelta(days=28),
        is_archived=False,
        created_by_owner_id=owner1.id,
    )
    # Member 3: Active, expiring in 6 days (expiring soon)
    m3 = Member(
        id=uuid.uuid4(),
        member_code="RF003",
        full_name="Ravi Teja",
        phone_number="+919800000003",
        gender="male",
        joining_date=today - timedelta(days=24),
        is_archived=False,
        created_by_owner_id=owner1.id,
    )
    # Member 4: Expired 5 days ago, no renewal
    m4 = Member(
        id=uuid.uuid4(),
        member_code="RF004",
        full_name="Sneha Patel",
        phone_number="+919800000004",
        gender="female",
        joining_date=today - timedelta(days=60),
        is_archived=False,
        created_by_owner_id=owner1.id,
    )
    # Member 5: Expired 2 days ago, renewal pending activation
    m5 = Member(
        id=uuid.uuid4(),
        member_code="RF005",
        full_name="Karan Johar",
        phone_number="+919800000005",
        gender="male",
        joining_date=today - timedelta(days=40),
        is_archived=False,
        created_by_owner_id=owner1.id,
    )
    # Member 6: Archived member
    m6 = Member(
        id=uuid.uuid4(),
        member_code="RF006",
        full_name="Old Member",
        phone_number="+919800000006",
        gender="male",
        joining_date=today - timedelta(days=100),
        is_archived=True,
        archived_at=datetime.now(timezone.utc),
        created_by_owner_id=owner1.id,
    )
    # Member 7: Active via manual override (even though start_date is in future)
    m7 = Member(
        id=uuid.uuid4(),
        member_code="RF007",
        full_name="Override Member",
        phone_number="+919800000007",
        gender="other",
        joining_date=today - timedelta(days=5),
        is_archived=False,
        created_by_owner_id=owner1.id,
    )
    test_db.add_all([m1, m2, m3, m4, m5, m6, m7])
    test_db.flush()

    # 4. Seed Contracts
    # c1: Active for m1 (joined today, expires in 29 days)
    c1 = MembershipRecord(
        id=uuid.uuid4(),
        member_id=m1.id,
        plan_id=plan_monthly.id,
        plan_snapshot_name=plan_monthly.name,
        plan_snapshot_duration_days=plan_monthly.duration_days,
        plan_snapshot_base_price=plan_monthly.base_price,
        discount_amount=Decimal("0.00"),
        total_fee=Decimal("1500.00"),
        start_date=today,
        expiry_date=today + timedelta(days=29),
        system_status="active",
        membership_type="new",
        created_by_owner_id=owner1.id,
        activated_by_owner_id=owner1.id,
    )
    # c2: Active for m2, expiring in 2 days
    c2 = MembershipRecord(
        id=uuid.uuid4(),
        member_id=m2.id,
        plan_id=plan_monthly.id,
        plan_snapshot_name=plan_monthly.name,
        plan_snapshot_duration_days=plan_monthly.duration_days,
        plan_snapshot_base_price=plan_monthly.base_price,
        discount_amount=Decimal("0.00"),
        total_fee=Decimal("1500.00"),
        start_date=today - timedelta(days=27),
        expiry_date=today + timedelta(days=2),
        system_status="active",
        membership_type="new",
        created_by_owner_id=owner1.id,
        activated_by_owner_id=owner1.id,
    )
    # c3: Active for m3, expiring in 6 days
    c3 = MembershipRecord(
        id=uuid.uuid4(),
        member_id=m3.id,
        plan_id=plan_monthly.id,
        plan_snapshot_name=plan_monthly.name,
        plan_snapshot_duration_days=plan_monthly.duration_days,
        plan_snapshot_base_price=plan_monthly.base_price,
        discount_amount=Decimal("0.00"),
        total_fee=Decimal("1500.00"),
        start_date=today - timedelta(days=23),
        expiry_date=today + timedelta(days=6),
        system_status="active",
        membership_type="new",
        created_by_owner_id=owner1.id,
        activated_by_owner_id=owner1.id,
    )
    # c4: Expired 5 days ago for m4
    c4 = MembershipRecord(
        id=uuid.uuid4(),
        member_id=m4.id,
        plan_id=plan_monthly.id,
        plan_snapshot_name=plan_monthly.name,
        plan_snapshot_duration_days=plan_monthly.duration_days,
        plan_snapshot_base_price=plan_monthly.base_price,
        discount_amount=Decimal("0.00"),
        total_fee=Decimal("1500.00"),
        start_date=today - timedelta(days=35),
        expiry_date=today - timedelta(days=5),
        system_status="expired",
        membership_type="new",
        created_by_owner_id=owner1.id,
        activated_by_owner_id=owner1.id,
    )
    # c5_old: Expired 2 days ago for m5
    c5_old = MembershipRecord(
        id=uuid.uuid4(),
        member_id=m5.id,
        plan_id=plan_monthly.id,
        plan_snapshot_name=plan_monthly.name,
        plan_snapshot_duration_days=plan_monthly.duration_days,
        plan_snapshot_base_price=plan_monthly.base_price,
        discount_amount=Decimal("0.00"),
        total_fee=Decimal("1500.00"),
        start_date=today - timedelta(days=32),
        expiry_date=today - timedelta(days=2),
        system_status="expired",
        membership_type="new",
        created_by_owner_id=owner1.id,
        activated_by_owner_id=owner1.id,
    )
    # c5_new: Renewal pending activation for m5
    c5_new = MembershipRecord(
        id=uuid.uuid4(),
        member_id=m5.id,
        plan_id=plan_monthly.id,
        plan_snapshot_name=plan_monthly.name,
        plan_snapshot_duration_days=plan_monthly.duration_days,
        plan_snapshot_base_price=plan_monthly.base_price,
        discount_amount=Decimal("0.00"),
        total_fee=Decimal("1500.00"),
        start_date=today - timedelta(days=1),
        expiry_date=today + timedelta(days=28),
        system_status="pending_activation",
        membership_type="renewal",
        previous_membership_id=c5_old.id,
        created_by_owner_id=owner1.id,
    )
    # c7: Active via manual override
    c7 = MembershipRecord(
        id=uuid.uuid4(),
        member_id=m7.id,
        plan_id=plan_monthly.id,
        plan_snapshot_name=plan_monthly.name,
        plan_snapshot_duration_days=plan_monthly.duration_days,
        plan_snapshot_base_price=plan_monthly.base_price,
        discount_amount=Decimal("0.00"),
        total_fee=Decimal("1500.00"),
        start_date=today + timedelta(days=10),
        expiry_date=today + timedelta(days=40),
        system_status="pending_activation",
        is_manual_override=True,
        override_status="active",
        override_reason="Special VIP complimentary access",
        override_by_owner_id=owner1.id,
        overridden_at=datetime.now(timezone.utc),
        membership_type="new",
        created_by_owner_id=owner1.id,
    )
    test_db.add_all([c1, c2, c3, c4, c5_old, c5_new, c7])
    test_db.flush()

    # 5. Seed Payments & Refunds
    # Payment 1 on c1: Full payment confirmed today (₹1500)
    p1 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY001",
        member_id=m1.id,
        membership_record_id=c1.id,
        amount=Decimal("1500.00"),
        payment_type="full",
        payment_method="upi",
        payment_date=today,
        status="confirmed",
        confirmed_by_owner_id=owner1.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    # Payment 2 on c2: Partial payment confirmed yesterday (₹1000 of ₹1500) -> Dues ₹500
    p2 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY002",
        member_id=m2.id,
        membership_record_id=c2.id,
        amount=Decimal("1000.00"),
        payment_type="partial",
        payment_method="cash",
        payment_date=today - timedelta(days=1),
        status="confirmed",
        confirmed_by_owner_id=owner1.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    # Payment 3 on c3: Confirmed today ₹1500, but ₹200 refunded today! -> Net ₹1300, Dues ₹200
    p3 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY003",
        member_id=m3.id,
        membership_record_id=c3.id,
        amount=Decimal("1500.00"),
        payment_type="full",
        payment_method="card",
        payment_date=today,
        status="confirmed",
        confirmed_by_owner_id=owner1.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    # Payment 4 on c4: Unconfirmed pending payment (should be excluded from collections)
    p4 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY004",
        member_id=m4.id,
        membership_record_id=c4.id,
        amount=Decimal("1500.00"),
        payment_type="full",
        payment_method="upi",
        payment_date=today,
        status="pending",
    )
    test_db.add_all([p1, p2, p3, p4])
    test_db.flush()

    # Refund on p3 of ₹200 processed today
    ref1 = PaymentRefund(
        id=uuid.uuid4(),
        refund_number="REF001",
        original_payment_id=p3.id,
        member_id=m3.id,
        amount=Decimal("200.00"),
        refund_reason="Overcharge adjustment",
        refund_method="upi",
        status="processed",
        processed_by_owner_id=owner1.id,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(ref1)

    # 6. Seed Audit Logs
    log1 = AuditLog(
        id=uuid.uuid4(),
        owner_id=owner1.id,
        action="LOGIN_SUCCESS",
        entity_type="owner_session",
        entity_id=session1.id,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    log2 = AuditLog(
        id=uuid.uuid4(),
        owner_id=owner1.id,
        action="PAYMENT_CONFIRMED",
        entity_type="payment",
        entity_id=p1.id,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    test_db.add_all([log1, log2])
    test_db.commit()

    # Generate JWT auth headers for testing
    token1 = create_access_token(owner1.id, session1.id)
    token2 = create_access_token(owner2.id, session2.id)

    return {
        "owner1": owner1,
        "owner2": owner2,
        "headers1": {"Authorization": f"Bearer {token1}"},
        "headers2": {"Authorization": f"Bearer {token2}"},
        "today": today,
    }


# ---------------------------------------------------------------------------
# 1. Authentication & Security Tests
# ---------------------------------------------------------------------------


class TestDashboardAuthentication:
    def test_unauthenticated_request_rejected(self, client: TestClient):
        """Endpoints must return HTTP 401 when no token is provided."""
        routes = [
            "/api/v1/dashboard/overview",
            "/api/v1/dashboard/membership-analytics",
            "/api/v1/dashboard/financial-analytics",
            "/api/v1/dashboard/renewal-pipeline",
            "/api/v1/dashboard/recent-activity",
        ]
        for r in routes:
            resp = client.get(r)
            assert resp.status_code == 401
            assert "not authenticated" in resp.json()["error"]["message"].lower() or "bearer" in resp.json()["error"]["message"].lower()

    def test_both_owners_have_equal_dashboard_access(self, client: TestClient, seed_data: dict):
        """Both co-owners have equal root access to all dashboard endpoints."""
        for headers in [seed_data["headers1"], seed_data["headers2"]]:
            resp = client.get("/api/v1/dashboard/overview", headers=headers)
            assert resp.status_code == 200
            assert "member_counts" in resp.json()


# ---------------------------------------------------------------------------
# 2. Dashboard Overview Tests
# ---------------------------------------------------------------------------


class TestDashboardOverview:
    def test_overview_metrics_correctness(self, client: TestClient, seed_data: dict):
        """Verify calculations for member counts, alerts, collections, dues, and recent activity."""
        headers = seed_data["headers1"]
        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Member counts:
        # Non-archived: m1, m2, m3, m4, m5, m7 = 6
        # Archived: m6 = 1
        assert data["member_counts"]["total_members"] == 6
        assert data["member_counts"]["archived_members"] == 1

        # Active members:
        # m1 (active contract), m2 (active contract), m3 (active contract), m7 (override active) = 4
        assert data["member_counts"]["active_members"] == 4

        # Expired members:
        # m4 (expired, no active), m5 (expired old contract, renewal pending) = 2
        assert data["member_counts"]["expired_members"] == 2

        # Membership alerts:
        # Expiring within 7 days: m2 (2 days), m3 (6 days) = 2
        assert data["membership_alerts"]["expiring_within_7_days"] == 2
        # Urgent within 3 days: m2 (2 days) = 1
        assert data["membership_alerts"]["expiring_within_3_days"] == 1

        # Today metrics:
        # New admissions today: m1 (joining_date == today) = 1
        assert data["today_metrics"]["new_admissions_today"] == 1

        # Collections today:
        # Confirmed payments today: p1 (₹1500) + p3 (₹1500) = ₹3000
        # Processed refunds today: ref1 (₹200)
        # Net collections today: ₹3000 - ₹200 = ₹2800.00
        assert Decimal(str(data["today_metrics"]["collections_today"])) == Decimal("2800.00")

        # Month collections includes today + p2 (yesterday ₹1000)
        # Net: ₹2800 + ₹1000 = ₹3800.00
        assert Decimal(str(data["month_metrics"]["collections_this_month"])) == Decimal("3800.00")

        # Outstanding dues:
        # c1: 1500 - 1500 = 0
        # c2: 1500 - 1000 = 500
        # c3: 1500 - (1500 - 200) = 200
        # c4: 1500 - 0 = 1500 (p4 is pending so not confirmed)
        # c5_old: 1500 - 0 = 1500
        # c5_new: 1500 - 0 = 1500
        # c7: 1500 - 0 = 1500
        # Total outstanding = 500 + 200 + 1500 + 1500 + 1500 + 1500 = 6700.00
        assert Decimal(str(data["financial_summary"]["outstanding_dues"])) == Decimal("6700.00")

        # Recent activity
        assert len(data["recent_activity"]) == 2
        assert data["recent_activity"][0]["action"] == "PAYMENT_CONFIRMED"


# ---------------------------------------------------------------------------
# 3. Membership Analytics Tests
# ---------------------------------------------------------------------------


class TestMembershipAnalytics:
    def test_membership_analytics_summary_and_plans(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        resp = client.get("/api/v1/dashboard/membership-analytics", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["summary"]["total_active_members"] == 4
        assert data["summary"]["total_expired_members"] == 2
        assert data["summary"]["expiring_within_7_days"] == 2
        assert data["summary"]["expiring_within_3_days"] == 1

        # Plan distribution
        assert len(data["plan_distribution"]) == 2
        monthly_plan = next(p for p in data["plan_distribution"] if p["plan_name"] == "Monthly General")
        assert monthly_plan["active_members_count"] == 4
        assert monthly_plan["total_contracts_count"] == 7

        # Type breakdown
        assert data["membership_type_breakdown"]["new_count"] >= 5
        assert data["membership_type_breakdown"]["renewal_count"] >= 1

    def test_membership_analytics_date_filter_validation(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        # Invalid date range: start after end
        resp = client.get(
            "/api/v1/dashboard/membership-analytics?start_date=2026-12-31&end_date=2026-01-01",
            headers=headers,
        )
        assert resp.status_code == 400
        assert "cannot be later than" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 4. Financial Analytics Tests
# ---------------------------------------------------------------------------


class TestFinancialAnalytics:
    def test_financial_analytics_today_preset(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        resp = client.get("/api/v1/dashboard/financial-analytics?preset=today", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert Decimal(str(data["totals"]["gross_confirmed_collections"])) == Decimal("3000.00")
        assert Decimal(str(data["totals"]["processed_refunds"])) == Decimal("200.00")
        assert Decimal(str(data["totals"]["net_collections"])) == Decimal("2800.00")
        assert Decimal(str(data["totals"]["total_outstanding_dues"])) == Decimal("6700.00")

        # Payment types today: p1 (full ₹1500) + p3 (full ₹1500) = ₹3000 full
        assert Decimal(str(data["by_payment_type"]["full"]["amount"])) == Decimal("3000.00")
        assert data["by_payment_type"]["full"]["count"] == 2

    def test_financial_analytics_this_month_preset(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        resp = client.get("/api/v1/dashboard/financial-analytics?preset=this_month", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Gross: p1 (1500) + p2 (1000) + p3 (1500) = 4000
        # Refunds: 200
        # Net: 3800
        assert Decimal(str(data["totals"]["gross_confirmed_collections"])) == Decimal("4000.00")
        assert Decimal(str(data["totals"]["processed_refunds"])) == Decimal("200.00")
        assert Decimal(str(data["totals"]["net_collections"])) == Decimal("3800.00")

        # Payment methods: cash ₹1000, card ₹1500, upi ₹1500
        method_map = {m["method"]: Decimal(str(m["amount"])) for m in data["by_payment_method"]}
        assert method_map.get("cash") == Decimal("1000.00")
        assert method_map.get("card") == Decimal("1500.00")
        assert method_map.get("upi") == Decimal("1500.00")

    def test_financial_analytics_custom_range_validation(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        # custom requires both start and end
        resp = client.get("/api/v1/dashboard/financial-analytics?preset=custom", headers=headers)
        assert resp.status_code == 400

        # start cannot be after end
        resp2 = client.get(
            "/api/v1/dashboard/financial-analytics?preset=custom&start_date=2026-11-20&end_date=2026-11-10",
            headers=headers,
        )
        assert resp2.status_code == 400


# ---------------------------------------------------------------------------
# 5. Renewal Pipeline Tests
# ---------------------------------------------------------------------------


class TestRenewalPipeline:
    def test_renewal_pipeline_categories_and_summary(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        resp = client.get("/api/v1/dashboard/renewal-pipeline", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        summary = data["summary"]
        assert summary["expiring_3_days_count"] == 1  # m2
        assert summary["expiring_7_days_count"] == 2  # m2 + m3
        assert summary["already_expired_count"] == 1  # m4
        assert summary["renewal_pending_count"] == 1  # m5

        # Verify pipeline items
        items = data["items"]
        statuses = [it["pipeline_status"] for it in items]
        assert "urgent_expiry" in statuses
        assert "expiring_soon" in statuses
        assert "already_expired" in statuses
        assert "renewal_pending" in statuses

    def test_renewal_pipeline_filtering_by_category(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        # Filter for urgent_expiry
        resp = client.get("/api/v1/dashboard/renewal-pipeline?category=expiring_3_days", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["member_name"] == "Pooja Verma"
        assert items[0]["pipeline_status"] == "urgent_expiry"

    def test_renewal_pipeline_pagination(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        resp = client.get("/api/v1/dashboard/renewal-pipeline?page=1&page_size=2", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2
        assert data["pagination"]["total_pages"] >= 2


# ---------------------------------------------------------------------------
# 6. Recent Activity Tests
# ---------------------------------------------------------------------------


class TestRecentActivity:
    def test_recent_activity_pagination_and_ordering(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        resp = client.get("/api/v1/dashboard/recent-activity?page=1&page_size=10", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["items"]) == 2
        # First item should be the most recent (PAYMENT_CONFIRMED)
        assert data["items"][0]["action"] == "PAYMENT_CONFIRMED"
        assert "Vikram Singh" in data["items"][0]["actor_owner_name"]
        assert "description" in data["items"][0]

    def test_recent_activity_action_filter(self, client: TestClient, seed_data: dict):
        headers = seed_data["headers1"]
        resp = client.get(
            "/api/v1/dashboard/recent-activity?action_filter=LOGIN_SUCCESS",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["action"] == "LOGIN_SUCCESS"


# ---------------------------------------------------------------------------
# 7. Edge Cases & Empty Database Tests
# ---------------------------------------------------------------------------


class TestDashboardEdgeCases:
    def test_empty_database_returns_safe_zeros(self, client: TestClient, test_db: Session):
        """When database contains no members or transactions, endpoints must return 0 without failing."""
        # Create an owner to authenticate
        owner = Owner(
            id=uuid.uuid4(),
            name="Empty Owner",
            phone_number="+919999999999",
            email="empty@regalfitness.com",
            password_hash=hash_password("OwnerPass1!"),
            account_status="active",
        )
        test_db.add(owner)
        test_db.flush()

        session = OwnerSession(
            id=uuid.uuid4(),
            owner_id=owner.id,
            refresh_token_hash="empty_hash",
            is_revoked=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        test_db.add(session)
        test_db.commit()

        token = create_access_token(owner.id, session.id)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Overview
        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["member_counts"]["total_members"] == 0
        assert data["member_counts"]["active_members"] == 0
        assert Decimal(str(data["today_metrics"]["collections_today"])) == Decimal("0.00")
        assert Decimal(str(data["financial_summary"]["outstanding_dues"])) == Decimal("0.00")
        assert len(data["recent_activity"]) == 0

        # 2. Financial Analytics
        resp_fin = client.get("/api/v1/dashboard/financial-analytics?preset=this_month", headers=headers)
        assert resp_fin.status_code == 200
        assert Decimal(str(resp_fin.json()["totals"]["net_collections"])) == Decimal("0.00")

        # 3. Renewal Pipeline
        resp_pipe = client.get("/api/v1/dashboard/renewal-pipeline", headers=headers)
        assert resp_pipe.status_code == 200
        assert resp_pipe.json()["pagination"]["total_count"] == 0
        assert len(resp_pipe.json()["items"]) == 0


# ---------------------------------------------------------------------------
# Part 1: Financial Calculation Validation Tests
# ---------------------------------------------------------------------------


class TestFinancialCalculationValidation:
    def _setup_base_member(self, test_db: Session):
        owner = Owner(
            id=uuid.uuid4(),
            name="Fin Owner",
            email=f"fin_owner_{uuid.uuid4().hex[:8]}@regalfitness.com",
            phone_number="+919700000001",
            password_hash=hash_password("Pass1!aaaa"),
            account_status="active",
        )
        plan = MembershipPlan(
            id=uuid.uuid4(),
            name="Test Plan",
            category="general",
            duration_days=30,
            base_price=Decimal("2000.00"),
            is_active=True,
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        member = Member(
            id=uuid.uuid4(),
            member_code="RF_FIN_01",
            full_name="Financial Test Member",
            phone_number="+919700000002",
            gender="male",
            joining_date=get_business_today(),
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        session = OwnerSession(
            id=uuid.uuid4(),
            owner_id=owner.id,
            refresh_token_hash="hash_fin",
            is_revoked=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        test_db.add_all([owner, plan, member, session])
        test_db.flush()
        token = create_access_token(owner.id, session.id)
        return owner, plan, member, {"Authorization": f"Bearer {token}"}

    def test_pending_and_failed_payments_excluded(self, client: TestClient, test_db: Session):
        owner, plan, member, headers = self._setup_base_member(test_db)
        today = get_business_today()

        contract = MembershipRecord(
            id=uuid.uuid4(),
            member_id=member.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("2000.00"),
            start_date=today,
            expiry_date=today + timedelta(days=29),
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add(contract)
        test_db.flush()

        p_confirmed = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-CONF-01",
            member_id=member.id,
            membership_record_id=contract.id,
            amount=Decimal("1000.00"),
            payment_type="partial",
            payment_method="cash",
            payment_date=today,
            status="confirmed",
            confirmed_by_owner_id=owner.id,
            confirmed_at=datetime.now(timezone.utc),
        )
        p_pending = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-PEND-01",
            member_id=member.id,
            membership_record_id=contract.id,
            amount=Decimal("500.00"),
            payment_type="partial",
            payment_method="upi",
            payment_date=today,
            status="pending",
        )
        p_failed = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-FAIL-01",
            member_id=member.id,
            membership_record_id=contract.id,
            amount=Decimal("500.00"),
            payment_type="partial",
            payment_method="card",
            payment_date=today,
            status="failed",
        )
        test_db.add_all([p_confirmed, p_pending, p_failed])
        test_db.commit()

        resp = client.get("/api/v1/dashboard/financial-analytics?preset=today", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["totals"]["gross_confirmed_collections"])) == Decimal("1000.00")
        assert Decimal(str(data["totals"]["net_collections"])) == Decimal("1000.00")
        # Outstanding dues = total_fee (2000) - confirmed_paid (1000) = 1000
        assert Decimal(str(data["totals"]["total_outstanding_dues"])) == Decimal("1000.00")

    def test_pending_and_rejected_refunds_excluded(self, client: TestClient, test_db: Session):
        owner, plan, member, headers = self._setup_base_member(test_db)
        today = get_business_today()

        contract = MembershipRecord(
            id=uuid.uuid4(),
            member_id=member.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("2000.00"),
            start_date=today,
            expiry_date=today + timedelta(days=29),
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add(contract)
        test_db.flush()

        payment = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-REF-TEST",
            member_id=member.id,
            membership_record_id=contract.id,
            amount=Decimal("2000.00"),
            payment_type="full",
            payment_method="upi",
            payment_date=today,
            status="confirmed",
            confirmed_by_owner_id=owner.id,
            confirmed_at=datetime.now(timezone.utc),
        )
        test_db.add(payment)
        test_db.flush()

        ref_processed = PaymentRefund(
            id=uuid.uuid4(),
            refund_number="REF-PROC-01",
            original_payment_id=payment.id,
            member_id=member.id,
            amount=Decimal("500.00"),
            refund_method="upi",
            status="processed",
            refund_reason="Customer request",
            processed_by_owner_id=owner.id,
            created_at=datetime.now(timezone.utc),
        )
        ref_pending = PaymentRefund(
            id=uuid.uuid4(),
            refund_number="REF-PEND-01",
            original_payment_id=payment.id,
            member_id=member.id,
            amount=Decimal("300.00"),
            refund_method="upi",
            status="pending",
            refund_reason="Under review",
            processed_by_owner_id=owner.id,
        )
        ref_rejected = PaymentRefund(
            id=uuid.uuid4(),
            refund_number="REF-REJ-01",
            original_payment_id=payment.id,
            member_id=member.id,
            amount=Decimal("200.00"),
            refund_method="upi",
            status="rejected",
            refund_reason="Policy violation",
            processed_by_owner_id=owner.id,
        )
        test_db.add_all([ref_processed, ref_pending, ref_rejected])
        test_db.commit()

        resp = client.get("/api/v1/dashboard/financial-analytics?preset=today", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["totals"]["gross_confirmed_collections"])) == Decimal("2000.00")
        assert Decimal(str(data["totals"]["processed_refunds"])) == Decimal("500.00")
        assert Decimal(str(data["totals"]["net_collections"])) == Decimal("1500.00")
        # Net paid = 2000 - 500 = 1500; Outstanding = 2000 - 1500 = 500
        assert Decimal(str(data["totals"]["total_outstanding_dues"])) == Decimal("500.00")

    def test_waivers_subtracted_correctly_and_overpayment_capped_at_zero(
        self, client: TestClient, test_db: Session
    ):
        owner, plan, member, headers = self._setup_base_member(test_db)
        today = get_business_today()

        # Contract 1: With confirmed waiver
        c1 = MembershipRecord(
            id=uuid.uuid4(),
            member_id=member.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("2000.00"),
            start_date=today,
            expiry_date=today + timedelta(days=29),
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add(c1)
        test_db.flush()

        # Waived schedule: 500 waived
        due_waived = MembershipDueSchedule(
            id=uuid.uuid4(),
            membership_record_id=c1.id,
            member_id=member.id,
            installment_number=1,
            due_amount=Decimal("500.00"),
            due_date=today,
            status="waived",
            is_waived=True,
            waiver_reason="Promotional concession",
            waived_by_owner_id=owner.id,
            waived_at=datetime.now(timezone.utc),
            assigned_by_owner_id=owner.id,
        )
        # Payment: 1000 confirmed
        p1 = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-WAIVE-01",
            member_id=member.id,
            membership_record_id=c1.id,
            amount=Decimal("1000.00"),
            payment_type="partial",
            payment_method="cash",
            payment_date=today,
            status="confirmed",
            confirmed_by_owner_id=owner.id,
            confirmed_at=datetime.now(timezone.utc),
        )
        test_db.add_all([due_waived, p1])

        # Contract 2: Overpayment scenario (total_fee 1000, paid 1500)
        c2 = MembershipRecord(
            id=uuid.uuid4(),
            member_id=member.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=Decimal("1000.00"),
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1000.00"),
            start_date=today,
            expiry_date=today + timedelta(days=29),
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add(c2)
        test_db.flush()

        p2 = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-OVERPAY-01",
            member_id=member.id,
            membership_record_id=c2.id,
            amount=Decimal("1500.00"),
            payment_type="full",
            payment_method="cash",
            payment_date=today,
            status="confirmed",
            confirmed_by_owner_id=owner.id,
            confirmed_at=datetime.now(timezone.utc),
        )
        test_db.add(p2)
        test_db.commit()

        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # c1 outstanding: 2000 - 1000 (paid) - 500 (waived) = 500
        # c2 outstanding: max(0.00, 1000 - 1500) = 0.00
        # Total outstanding dues = 500.00 + 0.00 = 500.00 (not negative!)
        assert Decimal(str(data["financial_summary"]["outstanding_dues"])) == Decimal("500.00")


# ---------------------------------------------------------------------------
# Part 2: Membership Edge Cases Tests
# ---------------------------------------------------------------------------


class TestMembershipEdgeCases:
    def _create_owner_and_plan(self, test_db: Session):
        owner = Owner(
            id=uuid.uuid4(),
            name="Edge Owner",
            email=f"edge_owner_{uuid.uuid4().hex[:8]}@regalfitness.com",
            phone_number="+919600000001",
            password_hash=hash_password("Pass1!aaaa"),
            account_status="active",
        )
        plan = MembershipPlan(
            id=uuid.uuid4(),
            name="General Monthly",
            category="general",
            duration_days=30,
            base_price=Decimal("1500.00"),
            is_active=True,
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        session = OwnerSession(
            id=uuid.uuid4(),
            owner_id=owner.id,
            refresh_token_hash="hash_edge",
            is_revoked=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        test_db.add_all([owner, plan, session])
        test_db.flush()
        token = create_access_token(owner.id, session.id)
        return owner, plan, {"Authorization": f"Bearer {token}"}

    def test_expiring_today_boundary(self, client: TestClient, test_db: Session):
        owner, plan, headers = self._create_owner_and_plan(test_db)
        today = get_business_today()

        m = Member(
            id=uuid.uuid4(),
            member_code="RF_EXP_TODAY",
            full_name="Expiring Today Member",
            phone_number="+919600000010",
            gender="male",
            joining_date=today - timedelta(days=29),
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        c = MembershipRecord(
            id=uuid.uuid4(),
            member_id=m.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1500.00"),
            start_date=today - timedelta(days=29),
            expiry_date=today,  # Expiring today!
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add_all([m, c])
        test_db.commit()

        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        data = resp.json()
        assert data["member_counts"]["active_members"] == 1
        assert data["membership_alerts"]["expiring_within_7_days"] == 1
        assert data["membership_alerts"]["expiring_within_3_days"] == 1

        resp_pipe = client.get("/api/v1/dashboard/renewal-pipeline", headers=headers)
        p_data = resp_pipe.json()
        assert len(p_data["items"]) == 1
        assert p_data["items"][0]["days_until_expiry"] == 0
        assert p_data["items"][0]["pipeline_status"] == "urgent_expiry"

    def test_expiring_exactly_3_and_7_days(self, client: TestClient, test_db: Session):
        owner, plan, headers = self._create_owner_and_plan(test_db)
        today = get_business_today()

        # Member 1: Exactly 3 days
        m3 = Member(
            id=uuid.uuid4(),
            member_code="RF_EXP_3D",
            full_name="Expiring 3D Member",
            phone_number="+919600000003",
            gender="male",
            joining_date=today - timedelta(days=27),
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        c3 = MembershipRecord(
            id=uuid.uuid4(),
            member_id=m3.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1500.00"),
            start_date=today - timedelta(days=27),
            expiry_date=today + timedelta(days=3),  # Exactly 3 days
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )

        # Member 2: Exactly 7 days
        m7 = Member(
            id=uuid.uuid4(),
            member_code="RF_EXP_7D",
            full_name="Expiring 7D Member",
            phone_number="+919600000007",
            gender="female",
            joining_date=today - timedelta(days=23),
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        c7 = MembershipRecord(
            id=uuid.uuid4(),
            member_id=m7.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1500.00"),
            start_date=today - timedelta(days=23),
            expiry_date=today + timedelta(days=7),  # Exactly 7 days
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add_all([m3, c3, m7, c7])
        test_db.commit()

        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        data = resp.json()
        assert data["membership_alerts"]["expiring_within_7_days"] == 2
        assert data["membership_alerts"]["expiring_within_3_days"] == 1

        resp_pipe = client.get("/api/v1/dashboard/renewal-pipeline", headers=headers)
        items = resp_pipe.json()["items"]
        item_map = {it["member_code"]: it for it in items}
        assert item_map["RF_EXP_3D"]["pipeline_status"] == "urgent_expiry"
        assert item_map["RF_EXP_3D"]["days_until_expiry"] == 3
        assert item_map["RF_EXP_7D"]["pipeline_status"] == "expiring_soon"
        assert item_map["RF_EXP_7D"]["days_until_expiry"] == 7

    def test_expired_yesterday(self, client: TestClient, test_db: Session):
        owner, plan, headers = self._create_owner_and_plan(test_db)
        today = get_business_today()

        m = Member(
            id=uuid.uuid4(),
            member_code="RF_EXP_YEST",
            full_name="Expired Yesterday Member",
            phone_number="+919600000020",
            gender="other",
            joining_date=today - timedelta(days=31),
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        c = MembershipRecord(
            id=uuid.uuid4(),
            member_id=m.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1500.00"),
            start_date=today - timedelta(days=31),
            expiry_date=today - timedelta(days=1),  # Expired yesterday
            system_status="expired",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add_all([m, c])
        test_db.commit()

        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        data = resp.json()
        assert data["member_counts"]["active_members"] == 0
        assert data["member_counts"]["expired_members"] == 1

        resp_pipe = client.get("/api/v1/dashboard/renewal-pipeline", headers=headers)
        items = resp_pipe.json()["items"]
        assert len(items) == 1
        assert items[0]["pipeline_status"] == "already_expired"
        assert items[0]["days_until_expiry"] == -1

    def test_manual_overrides_activation_and_deactivation(
        self, client: TestClient, test_db: Session
    ):
        owner, plan, headers = self._create_owner_and_plan(test_db)
        today = get_business_today()

        # m_active: Expired by date, but manual override active
        m_active = Member(
            id=uuid.uuid4(),
            member_code="RF_OVR_ACT",
            full_name="Override Active Member",
            phone_number="+919600000030",
            gender="male",
            joining_date=today - timedelta(days=50),
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        c_active = MembershipRecord(
            id=uuid.uuid4(),
            member_id=m_active.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1500.00"),
            start_date=today - timedelta(days=50),
            expiry_date=today - timedelta(days=20),
            system_status="expired",
            is_manual_override=True,
            override_status="active",
            override_reason="VIP guest pass",
            override_by_owner_id=owner.id,
            overridden_at=datetime.now(timezone.utc),
            membership_type="new",
            created_by_owner_id=owner.id,
        )

        # m_expired: Active dates, but manual override expired
        m_expired = Member(
            id=uuid.uuid4(),
            member_code="RF_OVR_EXP",
            full_name="Override Expired Member",
            phone_number="+919600000031",
            gender="female",
            joining_date=today,
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        c_expired = MembershipRecord(
            id=uuid.uuid4(),
            member_id=m_expired.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1500.00"),
            start_date=today,
            expiry_date=today + timedelta(days=30),
            system_status="active",
            is_manual_override=True,
            override_status="expired",
            override_reason="Disciplinary revocation",
            override_by_owner_id=owner.id,
            overridden_at=datetime.now(timezone.utc),
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add_all([m_active, c_active, m_expired, c_expired])
        test_db.commit()

        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        data = resp.json()
        assert data["member_counts"]["active_members"] == 1  # m_active
        assert data["member_counts"]["expired_members"] == 1  # m_expired

    def test_archived_member_excluded(self, client: TestClient, test_db: Session):
        owner, plan, headers = self._create_owner_and_plan(test_db)
        today = get_business_today()

        m_archived = Member(
            id=uuid.uuid4(),
            member_code="RF_ARCHIVED",
            full_name="Archived Member",
            phone_number="+919600000040",
            gender="male",
            joining_date=today,
            is_archived=True,
            archived_at=datetime.now(timezone.utc),
            created_by_owner_id=owner.id,
        )
        c = MembershipRecord(
            id=uuid.uuid4(),
            member_id=m_archived.id,
            plan_id=plan.id,
            plan_snapshot_name=plan.name,
            plan_snapshot_duration_days=plan.duration_days,
            plan_snapshot_base_price=plan.base_price,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("1500.00"),
            start_date=today,
            expiry_date=today + timedelta(days=30),
            system_status="active",
            membership_type="new",
            created_by_owner_id=owner.id,
        )
        test_db.add_all([m_archived, c])
        test_db.commit()

        resp = client.get("/api/v1/dashboard/overview", headers=headers)
        data = resp.json()
        assert data["member_counts"]["active_members"] == 0
        assert data["member_counts"]["archived_members"] == 1

        resp_pipe = client.get("/api/v1/dashboard/renewal-pipeline", headers=headers)
        assert len(resp_pipe.json()["items"]) == 0


# ---------------------------------------------------------------------------
# Part 3: Timezone Validation Tests
# ---------------------------------------------------------------------------


class TestTimezoneValidation:
    def test_get_business_today_returns_ist(self):
        IST = timezone(timedelta(hours=5, minutes=30))
        expected_today = datetime.now(timezone.utc).astimezone(IST).date()
        assert get_business_today() == expected_today

    def test_collections_midnight_ist_boundary(self, client: TestClient, test_db: Session):
        IST = timezone(timedelta(hours=5, minutes=30))
        owner = Owner(
            id=uuid.uuid4(),
            name="TZ Owner",
            email=f"tz_owner_{uuid.uuid4().hex[:8]}@regalfitness.com",
            phone_number="+919500000001",
            password_hash=hash_password("Pass1!aaaa"),
            account_status="active",
        )
        member = Member(
            id=uuid.uuid4(),
            member_code="RF_TZ_01",
            full_name="Timezone Member",
            phone_number="+919500000002",
            gender="female",
            joining_date=date(2026, 11, 23),
            is_archived=False,
            created_by_owner_id=owner.id,
        )
        session = OwnerSession(
            id=uuid.uuid4(),
            owner_id=owner.id,
            refresh_token_hash="hash_tz",
            is_revoked=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        test_db.add_all([owner, member, session])
        test_db.flush()
        token = create_access_token(owner.id, session.id)
        headers = {"Authorization": f"Bearer {token}"}

        p1 = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-TZ-01",
            member_id=member.id,
            amount=Decimal("1000.00"),
            payment_type="full",
            payment_method="upi",
            payment_date=date(2026, 11, 23),
            status="confirmed",
            confirmed_by_owner_id=owner.id,
            confirmed_at=datetime.now(timezone.utc),
        )
        test_db.add(p1)
        test_db.flush()

        # Refund 1 at 11:55 PM IST on 2026-11-23 -> 2026-11-23 18:25:00 UTC
        dt_1155pm_ist = datetime(2026, 11, 23, 23, 55, 0, tzinfo=IST)
        r1 = PaymentRefund(
            id=uuid.uuid4(),
            refund_number="REF-TZ-1155PM",
            original_payment_id=p1.id,
            member_id=member.id,
            amount=Decimal("200.00"),
            refund_method="upi",
            status="processed",
            refund_reason="Night transaction",
            processed_by_owner_id=owner.id,
            created_at=dt_1155pm_ist.astimezone(timezone.utc),
        )

        # Refund 2 at 12:05 AM IST on 2026-11-24 -> 2026-11-23 18:35:00 UTC
        dt_1205am_ist = datetime(2026, 11, 24, 0, 5, 0, tzinfo=IST)
        r2 = PaymentRefund(
            id=uuid.uuid4(),
            refund_number="REF-TZ-1205AM",
            original_payment_id=p1.id,
            member_id=member.id,
            amount=Decimal("300.00"),
            refund_method="upi",
            status="processed",
            refund_reason="Next day early morning",
            processed_by_owner_id=owner.id,
            created_at=dt_1205am_ist.astimezone(timezone.utc),
        )
        test_db.add_all([r1, r2])
        test_db.commit()

        # Query custom range for Nov 23 only
        resp_nov23 = client.get(
            "/api/v1/dashboard/financial-analytics?preset=custom&start_date=2026-11-23&end_date=2026-11-23",
            headers=headers,
        )
        assert resp_nov23.status_code == 200
        data_nov23 = resp_nov23.json()
        # Only r1 (₹200) was in Nov 23 IST, r2 (₹300) was in Nov 24 IST
        assert Decimal(str(data_nov23["totals"]["processed_refunds"])) == Decimal("200.00")
        assert Decimal(str(data_nov23["totals"]["net_collections"])) == Decimal("800.00")

        # Query custom range for Nov 24 only
        resp_nov24 = client.get(
            "/api/v1/dashboard/financial-analytics?preset=custom&start_date=2026-11-24&end_date=2026-11-24",
            headers=headers,
        )
        assert resp_nov24.status_code == 200
        data_nov24 = resp_nov24.json()
        assert Decimal(str(data_nov24["totals"]["processed_refunds"])) == Decimal("300.00")
        assert Decimal(str(data_nov24["totals"]["net_collections"])) == Decimal("-300.00")

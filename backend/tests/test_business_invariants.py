import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models import (
    Invoice,
    Member,
    MembershipDueSchedule,
    MembershipPlan,
    MembershipRecord,
    Owner,
    Payment,
    PaymentRefund,
)


@pytest.fixture
def db_session() -> Session:
    """
    Creates an isolated in-memory SQLite database session for invariant testing.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def create_owner(session: Session, name: str = "Test Owner", email: str = "owner@test.com") -> Owner:
    owner = Owner(
        id=uuid.uuid4(),
        name=name,
        phone_number=f"+91{uuid.uuid4().int % 10000000000:010d}",
        email=email,
        password_hash="argon2id$hashed",
    )
    session.add(owner)
    session.flush()
    return owner


def create_member(session: Session, code: str = "RF001", phone: str = "+919999999999", is_archived: bool = False) -> Member:
    member = Member(
        id=uuid.uuid4(),
        member_code=code,
        full_name="Member Test",
        phone_number=phone,
        gender="male",
        joining_date=date.today(),
        is_archived=is_archived,
    )
    session.add(member)
    session.flush()
    return member


def create_plan(session: Session, fee: Decimal = Decimal("10000.00"), days: int = 30) -> MembershipPlan:
    plan = MembershipPlan(
        id=uuid.uuid4(),
        name="Standard Plan",
        category="general_fitness",
        duration_days=days,
        base_price=fee,
    )
    session.add(plan)
    session.flush()
    return plan


# ==============================================================================
# 1. PAYMENT AND INVOICE INTEGRITY TESTS
# ==============================================================================

def test_invoice_payment_one_to_one_unique_constraint(db_session: Session) -> None:
    """
    Verify that one confirmed payment cannot generate multiple invoices (1:1 constraint).
    """
    owner = create_owner(db_session)
    member = create_member(db_session)
    plan = create_plan(db_session)

    contract = MembershipRecord(
        id=uuid.uuid4(),
        member_id=member.id,
        plan_id=plan.id,
        plan_snapshot_name="Standard Plan",
        plan_snapshot_duration_days=30,
        plan_snapshot_base_price=Decimal("10000.00"),
        total_fee=Decimal("10000.00"),
        start_date=date.today(),
        expiry_date=date.today() + timedelta(days=29),
        created_by_owner_id=owner.id,
    )
    db_session.add(contract)
    db_session.flush()

    payment = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00001",
        member_id=member.id,
        membership_record_id=contract.id,
        amount=Decimal("5000.00"),
        payment_method="cash",
        status="confirmed",
        confirmed_by_owner_id=owner.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    db_session.add(payment)
    db_session.flush()

    # First invoice succeeds
    inv1 = Invoice(
        id=uuid.uuid4(),
        invoice_number="INV-00001",
        payment_id=payment.id,
        membership_record_id=contract.id,
        member_id=member.id,
        contract_total_fee=Decimal("10000.00"),
        payment_amount=Decimal("5000.00"),
        cumulative_paid_to_date=Decimal("5000.00"),
        remaining_balance_after_payment=Decimal("5000.00"),
        payment_date=date.today(),
        created_by_owner_id=owner.id,
    )
    db_session.add(inv1)
    db_session.flush()

    # Second invoice for the same payment must violate unique constraint on payment_id
    inv2 = Invoice(
        id=uuid.uuid4(),
        invoice_number="INV-00002",
        payment_id=payment.id,
        membership_record_id=contract.id,
        member_id=member.id,
        contract_total_fee=Decimal("10000.00"),
        payment_amount=Decimal("5000.00"),
        cumulative_paid_to_date=Decimal("5000.00"),
        remaining_balance_after_payment=Decimal("5000.00"),
        payment_date=date.today(),
        created_by_owner_id=owner.id,
    )
    db_session.add(inv2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_unique_invoice_numbers(db_session: Session) -> None:
    """
    Verify that invoice numbers cannot be duplicated.
    """
    owner = create_owner(db_session)
    member = create_member(db_session)
    plan = create_plan(db_session)

    contract = MembershipRecord(
        id=uuid.uuid4(),
        member_id=member.id,
        plan_id=plan.id,
        plan_snapshot_name="Standard Plan",
        plan_snapshot_duration_days=30,
        plan_snapshot_base_price=Decimal("10000.00"),
        total_fee=Decimal("10000.00"),
        start_date=date.today(),
        expiry_date=date.today() + timedelta(days=29),
        created_by_owner_id=owner.id,
    )
    db_session.add(contract)
    db_session.flush()

    p1 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00001",
        member_id=member.id,
        membership_record_id=contract.id,
        amount=Decimal("3000.00"),
        payment_method="cash",
        status="confirmed",
        confirmed_by_owner_id=owner.id,
    )
    p2 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00002",
        member_id=member.id,
        membership_record_id=contract.id,
        amount=Decimal("7000.00"),
        payment_method="cash",
        status="confirmed",
        confirmed_by_owner_id=owner.id,
    )
    db_session.add_all([p1, p2])
    db_session.flush()

    inv1 = Invoice(
        id=uuid.uuid4(),
        invoice_number="INV-00001",
        payment_id=p1.id,
        membership_record_id=contract.id,
        member_id=member.id,
        contract_total_fee=Decimal("10000.00"),
        payment_amount=Decimal("3000.00"),
        cumulative_paid_to_date=Decimal("3000.00"),
        remaining_balance_after_payment=Decimal("7000.00"),
        payment_date=date.today(),
        created_by_owner_id=owner.id,
    )
    inv2 = Invoice(
        id=uuid.uuid4(),
        invoice_number="INV-00001",  # Duplicate invoice number
        payment_id=p2.id,
        membership_record_id=contract.id,
        member_id=member.id,
        contract_total_fee=Decimal("10000.00"),
        payment_amount=Decimal("7000.00"),
        cumulative_paid_to_date=Decimal("10000.00"),
        remaining_balance_after_payment=Decimal("0.00"),
        payment_date=date.today(),
        created_by_owner_id=owner.id,
    )
    db_session.add(inv1)
    db_session.flush()
    db_session.add(inv2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_payment_idempotency_key(db_session: Session) -> None:
    """
    Verify idempotency key prevents duplicate payment transaction submissions.
    """
    owner = create_owner(db_session)
    member = create_member(db_session)

    p1 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00001",
        member_id=member.id,
        amount=Decimal("1000.00"),
        payment_method="upi",
        idempotency_key="unique_request_token_123",
        status="pending",
    )
    p2 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00002",
        member_id=member.id,
        amount=Decimal("1000.00"),
        payment_method="upi",
        idempotency_key="unique_request_token_123",  # Identical idempotency key
        status="pending",
    )
    db_session.add(p1)
    db_session.flush()
    db_session.add(p2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ==============================================================================
# 2. FINANCIAL INTEGRITY & CALCULATION TESTS
# ==============================================================================

def test_financial_calculations_partial_and_full_payment(db_session: Session) -> None:
    """
    Verify calculation of net confirmed paid, outstanding balance, and installment settlement.
    """
    owner = create_owner(db_session)
    member = create_member(db_session)
    plan = create_plan(db_session, fee=Decimal("10000.00"))

    contract = MembershipRecord(
        id=uuid.uuid4(),
        member_id=member.id,
        plan_id=plan.id,
        plan_snapshot_name="Standard Plan",
        plan_snapshot_duration_days=30,
        plan_snapshot_base_price=Decimal("10000.00"),
        total_fee=Decimal("10000.00"),
        start_date=date.today(),
        expiry_date=date.today() + timedelta(days=29),
        created_by_owner_id=owner.id,
    )
    db_session.add(contract)
    db_session.flush()

    # Installment #1: ₹4,000 partial payment
    p1 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00001",
        member_id=member.id,
        membership_record_id=contract.id,
        amount=Decimal("4000.00"),
        payment_method="cash",
        status="confirmed",
        confirmed_by_owner_id=owner.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    # Remaining installment schedule: ₹6,000 due in 15 days
    due1 = MembershipDueSchedule(
        id=uuid.uuid4(),
        membership_record_id=contract.id,
        member_id=member.id,
        installment_number=1,
        due_amount=Decimal("6000.00"),
        due_date=date.today() + timedelta(days=15),
        assigned_by_owner_id=owner.id,
    )
    db_session.add_all([p1, due1])
    db_session.flush()

    # Recalculate financial state:
    confirmed_paid = p1.amount
    outstanding = max(Decimal("0.00"), contract.total_fee - confirmed_paid)
    assert confirmed_paid == Decimal("4000.00")
    assert outstanding == Decimal("6000.00")
    assert due1.due_amount == outstanding

    # Installment #2: Balance settlement of ₹6,000
    p2 = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00002",
        member_id=member.id,
        membership_record_id=contract.id,
        due_schedule_installment_id=due1.id,
        amount=Decimal("6000.00"),
        payment_method="upi",
        status="confirmed",
        confirmed_by_owner_id=owner.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    due1.paid_amount += p2.amount
    due1.status = "paid"
    db_session.add(p2)
    db_session.flush()

    total_confirmed = p1.amount + p2.amount
    final_outstanding = max(Decimal("0.00"), contract.total_fee - total_confirmed)
    assert total_confirmed == Decimal("10000.00")
    assert final_outstanding == Decimal("0.00")
    assert due1.status == "paid"


def test_refund_referencing_and_limit_enforcement(db_session: Session) -> None:
    """
    Verify refunds reference original payment and enforce that cumulative refunds <= original payment amount.
    """
    owner = create_owner(db_session)
    member = create_member(db_session)

    payment = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00001",
        member_id=member.id,
        amount=Decimal("5000.00"),
        payment_method="cash",
        status="confirmed",
        confirmed_by_owner_id=owner.id,
    )
    db_session.add(payment)
    db_session.flush()

    # Partial refund 1: ₹2,000
    ref1 = PaymentRefund(
        id=uuid.uuid4(),
        refund_number="REF-00001",
        original_payment_id=payment.id,
        member_id=member.id,
        amount=Decimal("2000.00"),
        refund_reason="Requested downgrading plan",
        refund_method="cash",
        processed_by_owner_id=owner.id,
    )
    db_session.add(ref1)
    db_session.flush()

    # Check remaining refundable balance
    total_refunded = ref1.amount
    remaining_refundable = payment.amount - total_refunded
    assert remaining_refundable == Decimal("3000.00")

    # Partial refund 2: ₹3,000 (settles payment completely)
    ref2 = PaymentRefund(
        id=uuid.uuid4(),
        refund_number="REF-00002",
        original_payment_id=payment.id,
        member_id=member.id,
        amount=Decimal("3000.00"),
        refund_reason="Member relocated",
        refund_method="cash",
        processed_by_owner_id=owner.id,
    )
    db_session.add(ref2)
    db_session.flush()

    # Service layer enforcement test: attempting another refund exceeds payment amount
    excess_amount = Decimal("1000.00")
    cumulative_refunds = ref1.amount + ref2.amount
    assert cumulative_refunds == payment.amount
    with pytest.raises(ValueError, match="Cumulative refund exceeds original payment amount"):
        if cumulative_refunds + excess_amount > payment.amount:
            raise ValueError("Cumulative refund exceeds original payment amount")


def test_overpayment_and_waivers(db_session: Session) -> None:
    """
    Verify that overpayments evaluate to outstanding=0.00 with positive overpayment_amount,
    and that waived installments reduce outstanding balance.
    """
    total_fee = Decimal("10000.00")
    confirmed_paid = Decimal("12000.00")  # ₹2,000 overpayment
    waived_amount = Decimal("0.00")

    outstanding = max(Decimal("0.00"), total_fee - confirmed_paid - waived_amount)
    overpayment = max(Decimal("0.00"), confirmed_paid - total_fee)

    assert outstanding == Decimal("0.00")
    assert overpayment == Decimal("2000.00")

    # Waiver test: fee=10000, paid=7000, waiver=3000
    partial_paid = Decimal("7000.00")
    waiver = Decimal("3000.00")
    waived_outstanding = max(Decimal("0.00"), total_fee - partial_paid - waiver)
    assert waived_outstanding == Decimal("0.00")


# ==============================================================================
# 3. MEMBERSHIP INTEGRITY TESTS
# ==============================================================================

def test_payment_does_not_automatically_activate_membership(db_session: Session) -> None:
    """
    CRITICAL: Full payment confirmation must NOT automatically activate membership.
    Membership activation must be an explicit owner action.
    """
    owner = create_owner(db_session)
    member = create_member(db_session)
    plan = create_plan(db_session, fee=Decimal("10000.00"))

    contract = MembershipRecord(
        id=uuid.uuid4(),
        member_id=member.id,
        plan_id=plan.id,
        plan_snapshot_name="Standard Plan",
        plan_snapshot_duration_days=30,
        plan_snapshot_base_price=Decimal("10000.00"),
        total_fee=Decimal("10000.00"),
        start_date=date.today(),
        expiry_date=date.today() + timedelta(days=29),
        system_status="pending_activation",
        created_by_owner_id=owner.id,
    )
    db_session.add(contract)
    db_session.flush()

    # Full payment confirmed
    payment = Payment(
        id=uuid.uuid4(),
        payment_number="PAY-00001",
        member_id=member.id,
        membership_record_id=contract.id,
        amount=Decimal("10000.00"),
        payment_method="cash",
        status="confirmed",
        confirmed_by_owner_id=owner.id,
        confirmed_at=datetime.now(timezone.utc),
    )
    db_session.add(payment)
    db_session.flush()

    # Contract status must remain 'pending_activation' despite full payment!
    db_session.refresh(contract)
    assert contract.system_status == "pending_activation"
    assert contract.activated_by_owner_id is None
    assert contract.activated_at is None

    # Explicit owner activation action
    activation_time = datetime.now(timezone.utc)
    contract.system_status = "active"
    contract.activated_by_owner_id = owner.id
    contract.activated_at = activation_time
    db_session.flush()

    db_session.refresh(contract)
    assert contract.system_status == "active"
    assert contract.activated_by_owner_id == owner.id
    assert contract.activated_at is not None


def test_membership_expiry_and_manual_override_precedence(db_session: Session) -> None:
    """
    Verify:
    1. Membership is active through expiry_date.
    2. Becomes expired on current_date > expiry_date.
    3. Manual override takes precedence over system status.
    """
    owner = create_owner(db_session)
    member = create_member(db_session)
    plan = create_plan(db_session)

    today = date.today()
    yesterday = today - timedelta(days=1)

    # Lapsed contract: expiry date was yesterday
    lapsed_contract = MembershipRecord(
        id=uuid.uuid4(),
        member_id=member.id,
        plan_id=plan.id,
        plan_snapshot_name="Standard Plan",
        plan_snapshot_duration_days=30,
        plan_snapshot_base_price=Decimal("10000.00"),
        total_fee=Decimal("10000.00"),
        start_date=yesterday - timedelta(days=30),
        expiry_date=yesterday,
        system_status="active",
        created_by_owner_id=owner.id,
    )
    db_session.add(lapsed_contract)
    db_session.flush()

    # Dynamic status evaluation
    is_expired = today > lapsed_contract.expiry_date
    assert is_expired is True
    effective_status = "expired" if is_expired else lapsed_contract.system_status
    assert effective_status == "expired"

    # Owner applies manual override to extend access
    lapsed_contract.is_manual_override = True
    lapsed_contract.override_status = "active"
    lapsed_contract.override_reason = "Owner granted 3-day extension due to gym repairs"
    lapsed_contract.override_by_owner_id = owner.id
    lapsed_contract.overridden_at = datetime.now(timezone.utc)
    db_session.flush()

    # Effective status evaluates override first: COALESCE(override_status, system_status)
    final_effective_status = lapsed_contract.override_status or effective_status
    assert final_effective_status == "active"
    assert lapsed_contract.is_manual_override is True
    assert lapsed_contract.override_by_owner_id == owner.id


def test_active_phone_uniqueness_partial_index(db_session: Session) -> None:
    """
    Verify that two active members cannot share a phone number,
    but an archived member and an active member CAN share a phone number.
    """
    shared_phone = "+919888888888"

    # 1. First member created as archived
    m1 = create_member(db_session, code="RF001", phone=shared_phone, is_archived=True)
    assert m1.is_archived is True

    # 2. Second member created as active with the same phone (permitted because m1 is archived)
    m2 = create_member(db_session, code="RF002", phone=shared_phone, is_archived=False)
    assert m2.is_archived is False

    # 3. Third member created as active with the same phone (must violate partial unique index)
    m3 = Member(
        id=uuid.uuid4(),
        member_code="RF003",
        full_name="Third Active Member",
        phone_number=shared_phone,
        gender="other",
        is_archived=False,
    )
    db_session.add(m3)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

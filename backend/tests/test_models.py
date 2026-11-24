import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models import (
    AuditLog,
    GalleryImage,
    GeneralEnquiry,
    GymVisitRequest,
    Invoice,
    JoiningApplication,
    Member,
    MembershipDueSchedule,
    MembershipPlan,
    MembershipRecord,
    Notification,
    Owner,
    OwnerDevicePushSubscription,
    OwnerNotificationPreference,
    OwnerPasswordResetOTP,
    OwnerSession,
    Payment,
    PaymentRefund,
    SystemSequence,
    SystemSetting,
    WhatsAppMessageLog,
)

EXPECTED_TABLES = {
    "owners",
    "owner_notification_preferences",
    "owner_device_push_subscriptions",
    "owner_password_reset_otps",
    "owner_sessions",
    "members",
    "membership_plans",
    "membership_records",
    "membership_due_schedules",
    "payments",
    "payment_refunds",
    "invoices",
    "joining_applications",
    "general_enquiries",
    "gym_visit_requests",
    "notifications",
    "audit_logs",
    "gallery_images",
    "system_settings",
    "whatsapp_message_logs",
    "system_sequences",
}


def test_table_inventory_count_and_names() -> None:
    """
    Verify all 21 tables are registered in Base.metadata and match expected table names.
    """
    registered_tables = set(Base.metadata.tables.keys())
    assert len(registered_tables) == 21
    assert registered_tables == EXPECTED_TABLES


def test_in_memory_sqlite_schema_creation() -> None:
    """
    Verify all 21 tables can be created cleanly in a test engine without circular or syntax errors.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    created_tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(created_tables)


def test_model_instantiation_and_relationships() -> None:
    """
    Verify that models instantiate with appropriate types, foreign keys, and relationships.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # 1. Owner
        owner = Owner(
            id=uuid.uuid4(),
            name="John Owner",
            phone_number="+919876543210",
            email="owner@regalfitness.com",
            password_hash="argon2id$hashed",
            account_status="active",
        )
        session.add(owner)
        session.flush()

        # 2. Preferences & Push device
        pref = OwnerNotificationPreference(
            owner_id=owner.id,
            notify_new_application=True,
            channel_push=True,
        )
        push_dev = OwnerDevicePushSubscription(
            owner_id=owner.id,
            endpoint="https://fcm.googleapis.com/test-endpoint",
            device_name="Owner Phone",
        )
        otp = OwnerPasswordResetOTP(
            owner_id=owner.id,
            otp_hmac="hmac_sha256_hash",
            cooldown_until=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
        )
        sess = OwnerSession(
            owner_id=owner.id,
            refresh_token_hash="sha256_refresh_token_hash",
            expires_at=datetime.now(timezone.utc),
        )
        session.add_all([pref, push_dev, otp, sess])
        session.flush()

        # 3. Member
        member = Member(
            id=uuid.uuid4(),
            member_code="RF001",
            full_name="Alice Member",
            phone_number="+919123456789",
            gender="female",
            joining_date=date.today(),
            created_by_owner_id=owner.id,
        )
        session.add(member)
        session.flush()

        # 4. Plan
        plan = MembershipPlan(
            id=uuid.uuid4(),
            name="Annual Plan",
            category="general_fitness",
            duration_days=365,
            duration_months=12,
            base_price=Decimal("12000.00"),
            created_by_owner_id=owner.id,
        )
        session.add(plan)
        session.flush()

        # 5. Membership Record (Requires explicit owner activation)
        contract = MembershipRecord(
            id=uuid.uuid4(),
            member_id=member.id,
            plan_id=plan.id,
            plan_snapshot_name="Annual Plan",
            plan_snapshot_duration_days=365,
            plan_snapshot_base_price=Decimal("12000.00"),
            plan_snapshot_is_pt=False,
            discount_amount=Decimal("0.00"),
            total_fee=Decimal("12000.00"),
            start_date=date.today(),
            expiry_date=date.today(),
            system_status="pending_activation",
            created_by_owner_id=owner.id,
            activated_by_owner_id=owner.id,
            activated_at=datetime.now(timezone.utc),
        )
        session.add(contract)
        session.flush()

        # 6. Due Schedule
        due = MembershipDueSchedule(
            id=uuid.uuid4(),
            membership_record_id=contract.id,
            member_id=member.id,
            installment_number=1,
            due_amount=Decimal("6000.00"),
            due_date=date.today(),
            assigned_by_owner_id=owner.id,
        )
        session.add(due)
        session.flush()

        # 7. Payment (Immutable ledger entry)
        payment = Payment(
            id=uuid.uuid4(),
            payment_number="PAY-00001",
            member_id=member.id,
            membership_record_id=contract.id,
            due_schedule_installment_id=due.id,
            amount=Decimal("6000.00"),
            payment_type="partial",
            payment_method="cash",
            status="confirmed",
            confirmed_by_owner_id=owner.id,
            confirmed_at=datetime.now(timezone.utc),
        )
        session.add(payment)
        session.flush()

        # 8. Invoice
        invoice = Invoice(
            id=uuid.uuid4(),
            invoice_number="INV-00001",
            payment_id=payment.id,
            membership_record_id=contract.id,
            member_id=member.id,
            contract_total_fee=Decimal("12000.00"),
            payment_amount=Decimal("6000.00"),
            cumulative_paid_to_date=Decimal("6000.00"),
            remaining_balance_after_payment=Decimal("6000.00"),
            payment_date=date.today(),
            created_by_owner_id=owner.id,
        )
        session.add(invoice)
        session.flush()

        # 9. Verify relationships
        assert member.membership_records[0].id == contract.id
        assert contract.member.full_name == "Alice Member"
        assert contract.plan.name == "Annual Plan"
        assert contract.activated_by_owner.name == "John Owner"
        assert payment.invoice.invoice_number == "INV-00001"
        assert invoice.payment.amount == Decimal("6000.00")
        assert len(owner.device_push_subscriptions) == 1
        assert owner.notification_preferences.notify_new_application is True

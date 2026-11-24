"""initial_schema_21_tables

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-11-18 00:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. STANDALONE POSTGRESQL SEQUENCES
    # --------------------------------------------------------------------------
    op.execute(sa.schema.CreateSequence(sa.Sequence('member_code_seq', start=1)))
    op.execute(sa.schema.CreateSequence(sa.Sequence('invoice_number_seq', start=1)))
    op.execute(sa.schema.CreateSequence(sa.Sequence('payment_number_seq', start=1)))
    op.execute(sa.schema.CreateSequence(sa.Sequence('refund_number_seq', start=1)))

    # --------------------------------------------------------------------------
    # 2. MODULE A: OWNER MANAGEMENT TABLES
    # --------------------------------------------------------------------------
    op.create_table(
        'owners',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('account_status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_owners')),
        sa.UniqueConstraint('email', name=op.f('uq_owners_email')),
        sa.UniqueConstraint('phone_number', name=op.f('uq_owners_phone_number'))
    )
    op.create_index(op.f('ix_owners_email'), 'owners', ['email'], unique=True)
    op.create_index(op.f('ix_owners_phone_number'), 'owners', ['phone_number'], unique=True)

    op.create_table(
        'owner_notification_preferences',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('notify_new_application', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_new_enquiry', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_new_visit', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_payment_confirmation', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_upcoming_expiry', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_overdue_dues', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_daily_report_9am', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('channel_in_app', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('channel_whatsapp', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('channel_push', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], name=op.f('fk_owner_notification_preferences_owner_id_owners'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_owner_notification_preferences')),
        sa.UniqueConstraint('owner_id', name=op.f('uq_owner_notification_preferences_owner_id'))
    )
    op.create_index(op.f('ix_owner_notification_preferences_owner_id'), 'owner_notification_preferences', ['owner_id'], unique=True)

    op.create_table(
        'owner_device_push_subscriptions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh_key', sa.Text(), nullable=True),
        sa.Column('auth_key', sa.Text(), nullable=True),
        sa.Column('device_name', sa.String(length=100), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], name=op.f('fk_owner_device_push_subscriptions_owner_id_owners'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_owner_device_push_subscriptions')),
        sa.UniqueConstraint('endpoint', name=op.f('uq_owner_device_push_subscriptions_endpoint'))
    )
    op.create_index(op.f('ix_owner_device_push_subscriptions_owner_id'), 'owner_device_push_subscriptions', ['owner_id'], unique=False)

    op.create_table(
        'owner_password_reset_otps',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('otp_hmac', sa.String(length=255), nullable=False),
        sa.Column('attempts_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_used', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], name=op.f('fk_owner_password_reset_otps_owner_id_owners'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_owner_password_reset_otps'))
    )
    op.create_index(op.f('ix_owner_password_reset_otps_owner_id'), 'owner_password_reset_otps', ['owner_id'], unique=False)

    op.create_table(
        'owner_sessions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('refresh_token_hash', sa.String(length=255), nullable=False),
        sa.Column('device_info', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], name=op.f('fk_owner_sessions_owner_id_owners'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_owner_sessions')),
        sa.UniqueConstraint('refresh_token_hash', name=op.f('uq_owner_sessions_refresh_token_hash'))
    )
    op.create_index(op.f('ix_owner_sessions_owner_id'), 'owner_sessions', ['owner_id'], unique=False)
    op.create_index(op.f('ix_owner_sessions_refresh_token_hash'), 'owner_sessions', ['refresh_token_hash'], unique=True)

    # --------------------------------------------------------------------------
    # 3. MODULE B: MEMBERS
    # --------------------------------------------------------------------------
    op.create_table(
        'members',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('member_code', sa.String(length=16), nullable=False),
        sa.Column('full_name', sa.String(length=100), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('date_of_birth', sa.Date(), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('gender', sa.String(length=20), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('joining_date', sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column('emergency_contact_name', sa.String(length=100), nullable=True),
        sa.Column('emergency_contact_phone', sa.String(length=20), nullable=True),
        sa.Column('profile_photo_url', sa.String(length=500), nullable=True),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archive_reason', sa.Text(), nullable=True),
        sa.Column('created_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('age IS NULL OR age > 0', name='ck_members_age_range'),
        sa.ForeignKeyConstraint(['created_by_owner_id'], ['owners.id'], name=op.f('fk_members_created_by_owner_id_owners'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_members')),
        sa.UniqueConstraint('member_code', name=op.f('uq_members_member_code'))
    )
    op.create_index(op.f('ix_members_is_archived'), 'members', ['is_archived'], unique=False)
    op.create_index(op.f('ix_members_member_code'), 'members', ['member_code'], unique=True)
    op.create_index('idx_members_search_name', 'members', ['full_name'], unique=False)
    op.create_index(
        'idx_uq_members_active_phone',
        'members',
        ['phone_number'],
        unique=True,
        postgresql_where=sa.text('is_archived = false')
    )

    # --------------------------------------------------------------------------
    # 4. MODULE C: MEMBERSHIP PLANS
    # --------------------------------------------------------------------------
    op.create_table(
        'membership_plans',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('duration_months', sa.Integer(), nullable=True),
        sa.Column('base_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_personal_training', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_custom_offer', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('base_price >= 0.00', name='ck_plans_price_non_negative'),
        sa.CheckConstraint('duration_days > 0', name='ck_plans_duration_positive'),
        sa.ForeignKeyConstraint(['created_by_owner_id'], ['owners.id'], name=op.f('fk_membership_plans_created_by_owner_id_owners'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_membership_plans'))
    )
    op.create_index(op.f('ix_membership_plans_is_active'), 'membership_plans', ['is_active'], unique=False)
    op.create_index(op.f('ix_membership_plans_is_archived'), 'membership_plans', ['is_archived'], unique=False)

    # --------------------------------------------------------------------------
    # 5. MODULE D: MEMBERSHIP RECORDS
    # --------------------------------------------------------------------------
    op.create_table(
        'membership_records',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('plan_id', sa.UUID(), nullable=False),
        sa.Column('plan_snapshot_name', sa.String(length=100), nullable=False),
        sa.Column('plan_snapshot_duration_days', sa.Integer(), nullable=False),
        sa.Column('plan_snapshot_base_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('plan_snapshot_is_pt', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('total_fee', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('system_status', sa.String(length=30), server_default='pending_activation', nullable=False),
        sa.Column('override_status', sa.String(length=30), nullable=True),
        sa.Column('is_manual_override', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('override_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('overridden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('activated_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('membership_type', sa.String(length=30), server_default='new', nullable=False),
        sa.Column('previous_membership_id', sa.UUID(), nullable=True),
        sa.Column('created_by_owner_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('discount_amount >= 0.00', name='ck_membership_discount_non_negative'),
        sa.CheckConstraint('expiry_date >= start_date', name='ck_membership_dates_valid'),
        sa.CheckConstraint('plan_snapshot_base_price >= 0.00', name='ck_membership_base_price_non_negative'),
        sa.CheckConstraint('plan_snapshot_duration_days > 0', name='ck_membership_duration_positive'),
        sa.CheckConstraint('total_fee >= 0.00', name='ck_membership_fee_positive'),
        sa.ForeignKeyConstraint(['activated_by_owner_id'], ['owners.id'], name=op.f('fk_membership_records_activated_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_owner_id'], ['owners.id'], name=op.f('fk_membership_records_created_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_membership_records_member_id_members'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['override_by_owner_id'], ['owners.id'], name=op.f('fk_membership_records_override_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['plan_id'], ['membership_plans.id'], name=op.f('fk_membership_records_plan_id_membership_plans'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['previous_membership_id'], ['membership_records.id'], name=op.f('fk_membership_records_previous_membership_id_membership_records'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_membership_records'))
    )
    op.create_index(op.f('ix_membership_records_expiry_date'), 'membership_records', ['expiry_date'], unique=False)
    op.create_index(op.f('ix_membership_records_member_id'), 'membership_records', ['member_id'], unique=False)
    op.create_index(op.f('ix_membership_records_plan_id'), 'membership_records', ['plan_id'], unique=False)
    op.create_index(op.f('ix_membership_records_system_status'), 'membership_records', ['system_status'], unique=False)
    op.create_index('idx_membership_expiry_date', 'membership_records', ['expiry_date', 'system_status'], unique=False)
    op.create_index('idx_membership_member_status', 'membership_records', ['member_id', 'system_status', 'is_manual_override'], unique=False)

    # --------------------------------------------------------------------------
    # 6. MODULE F: MULTI-INSTALLMENT DUE SCHEDULES
    # --------------------------------------------------------------------------
    op.create_table(
        'membership_due_schedules',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('membership_record_id', sa.UUID(), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('installment_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('due_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='pending', nullable=False),
        sa.Column('paid_amount', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('is_waived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('waiver_reason', sa.Text(), nullable=True),
        sa.Column('waived_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('waived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assigned_by_owner_id', sa.UUID(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('due_amount > 0.00 AND paid_amount >= 0.00', name='ck_due_schedule_amount_positive'),
        sa.CheckConstraint('installment_number > 0', name='ck_due_schedule_installment_positive'),
        sa.ForeignKeyConstraint(['assigned_by_owner_id'], ['owners.id'], name=op.f('fk_membership_due_schedules_assigned_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_membership_due_schedules_member_id_members'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['membership_record_id'], ['membership_records.id'], name=op.f('fk_membership_due_schedules_membership_record_id_membership_records'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['waived_by_owner_id'], ['owners.id'], name=op.f('fk_membership_due_schedules_waived_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_membership_due_schedules')),
        sa.UniqueConstraint('membership_record_id', 'installment_number', name='uq_due_schedules_installment')
    )
    op.create_index(op.f('ix_membership_due_schedules_due_date'), 'membership_due_schedules', ['due_date'], unique=False)
    op.create_index(op.f('ix_membership_due_schedules_is_waived'), 'membership_due_schedules', ['is_waived'], unique=False)
    op.create_index(op.f('ix_membership_due_schedules_member_id'), 'membership_due_schedules', ['member_id'], unique=False)
    op.create_index(op.f('ix_membership_due_schedules_membership_record_id'), 'membership_due_schedules', ['membership_record_id'], unique=False)
    op.create_index('idx_dues_schedule_overdue', 'membership_due_schedules', ['due_date', 'is_waived'], unique=False)

    # --------------------------------------------------------------------------
    # 7. MODULE E: PAYMENTS & REFUNDS
    # --------------------------------------------------------------------------
    op.create_table(
        'payments',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('payment_number', sa.String(length=32), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('membership_record_id', sa.UUID(), nullable=True),
        sa.Column('due_schedule_installment_id', sa.UUID(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_type', sa.String(length=30), server_default='full', nullable=False),
        sa.Column('payment_method', sa.String(length=30), nullable=False),
        sa.Column('transaction_reference', sa.String(length=100), nullable=True),
        sa.Column('payment_date', sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='pending', nullable=False),
        sa.Column('confirmed_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('amount > 0.00', name='ck_payments_amount_positive'),
        sa.ForeignKeyConstraint(['confirmed_by_owner_id'], ['owners.id'], name=op.f('fk_payments_confirmed_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['due_schedule_installment_id'], ['membership_due_schedules.id'], name=op.f('fk_payments_due_schedule_installment_id_membership_due_schedules'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_payments_member_id_members'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['membership_record_id'], ['membership_records.id'], name=op.f('fk_payments_membership_record_id_membership_records'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
        sa.UniqueConstraint('idempotency_key', name=op.f('uq_payments_idempotency_key')),
        sa.UniqueConstraint('payment_number', name=op.f('uq_payments_payment_number'))
    )
    op.create_index(op.f('ix_payments_due_schedule_installment_id'), 'payments', ['due_schedule_installment_id'], unique=False)
    op.create_index(op.f('ix_payments_member_id'), 'payments', ['member_id'], unique=False)
    op.create_index(op.f('ix_payments_membership_record_id'), 'payments', ['membership_record_id'], unique=False)
    op.create_index(op.f('ix_payments_payment_date'), 'payments', ['payment_date'], unique=False)
    op.create_index(op.f('ix_payments_payment_number'), 'payments', ['payment_number'], unique=True)
    op.create_index(op.f('ix_payments_status'), 'payments', ['status'], unique=False)
    op.create_index('idx_payments_confirmation_date', 'payments', ['payment_date', 'status'], unique=False)
    op.create_index('idx_payments_membership_id', 'payments', ['membership_record_id', 'status'], unique=False)

    op.create_table(
        'payment_refunds',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('refund_number', sa.String(length=32), nullable=False),
        sa.Column('original_payment_id', sa.UUID(), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('refund_reason', sa.Text(), nullable=False),
        sa.Column('refund_method', sa.String(length=30), nullable=False),
        sa.Column('transaction_reference', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='processed', nullable=False),
        sa.Column('processed_by_owner_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('amount > 0.00', name='ck_refunds_amount_positive'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_payment_refunds_member_id_members'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['original_payment_id'], ['payments.id'], name=op.f('fk_payment_refunds_original_payment_id_payments'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['processed_by_owner_id'], ['owners.id'], name=op.f('fk_payment_refunds_processed_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_refunds')),
        sa.UniqueConstraint('refund_number', name=op.f('uq_payment_refunds_refund_number'))
    )
    op.create_index(op.f('ix_payment_refunds_member_id'), 'payment_refunds', ['member_id'], unique=False)
    op.create_index(op.f('ix_payment_refunds_original_payment_id'), 'payment_refunds', ['original_payment_id'], unique=False)
    op.create_index(op.f('ix_payment_refunds_refund_number'), 'payment_refunds', ['refund_number'], unique=True)

    # --------------------------------------------------------------------------
    # 8. MODULE G: INVOICES & RECEIPTS
    # --------------------------------------------------------------------------
    op.create_table(
        'invoices',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('invoice_number', sa.String(length=32), nullable=False),
        sa.Column('payment_id', sa.UUID(), nullable=False),
        sa.Column('membership_record_id', sa.UUID(), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('contract_total_fee', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('cumulative_paid_to_date', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('remaining_balance_after_payment', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('pdf_storage_path', sa.String(length=500), nullable=True),
        sa.Column('pdf_file_name', sa.String(length=150), nullable=True),
        sa.Column('pdf_generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_via_whatsapp', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_owner_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('contract_total_fee >= 0.00 AND payment_amount > 0.00 AND remaining_balance_after_payment >= 0.00', name='ck_invoices_balances_valid'),
        sa.ForeignKeyConstraint(['created_by_owner_id'], ['owners.id'], name=op.f('fk_invoices_created_by_owner_id_owners'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_invoices_member_id_members'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['membership_record_id'], ['membership_records.id'], name=op.f('fk_invoices_membership_record_id_membership_records'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], name=op.f('fk_invoices_payment_id_payments'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_invoices')),
        sa.UniqueConstraint('invoice_number', name=op.f('uq_invoices_invoice_number')),
        sa.UniqueConstraint('payment_id', name=op.f('uq_invoices_payment_id'))
    )
    op.create_index(op.f('ix_invoices_invoice_number'), 'invoices', ['invoice_number'], unique=True)
    op.create_index(op.f('ix_invoices_member_id'), 'invoices', ['member_id'], unique=False)
    op.create_index(op.f('ix_invoices_membership_record_id'), 'invoices', ['membership_record_id'], unique=False)
    op.create_index(op.f('ix_invoices_payment_id'), 'invoices', ['payment_id'], unique=True)
    op.create_index('idx_invoices_contract_id', 'invoices', ['membership_record_id'], unique=False)
    op.create_index('idx_invoices_payment_id', 'invoices', ['payment_id'], unique=False)

    # --------------------------------------------------------------------------
    # 9. MODULE H, I, J: PUBLIC WEBSITE INTAKE (DEVELOPER 1 BOUNDARY)
    # --------------------------------------------------------------------------
    op.create_table(
        'joining_applications',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('applicant_name', sa.String(length=100), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('date_of_birth', sa.Date(), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('gender', sa.String(length=20), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('selected_plan_id', sa.UUID(), nullable=True),
        sa.Column('wants_visit_first', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('preferred_visit_date', sa.Date(), nullable=True),
        sa.Column('preferred_visit_time_slot', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='submitted', nullable=False),
        sa.Column('handling_owner_id', sa.UUID(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('converted_member_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('age IS NULL OR age > 0', name='ck_joining_apps_age'),
        sa.ForeignKeyConstraint(['converted_member_id'], ['members.id'], name=op.f('fk_joining_applications_converted_member_id_members'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['handling_owner_id'], ['owners.id'], name=op.f('fk_joining_applications_handling_owner_id_owners'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['selected_plan_id'], ['membership_plans.id'], name=op.f('fk_joining_applications_selected_plan_id_membership_plans'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_joining_applications')),
        sa.UniqueConstraint('converted_member_id', name=op.f('uq_joining_applications_converted_member_id'))
    )
    op.create_index(op.f('ix_joining_applications_phone_number'), 'joining_applications', ['phone_number'], unique=False)
    op.create_index(op.f('ix_joining_applications_status'), 'joining_applications', ['status'], unique=False)

    op.create_table(
        'general_enquiries',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='pending', nullable=False),
        sa.Column('assigned_owner_id', sa.UUID(), nullable=True),
        sa.Column('response_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['assigned_owner_id'], ['owners.id'], name=op.f('fk_general_enquiries_assigned_owner_id_owners'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_general_enquiries'))
    )
    op.create_index(op.f('ix_general_enquiries_status'), 'general_enquiries', ['status'], unique=False)

    op.create_table(
        'gym_visit_requests',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('visitor_name', sa.String(length=100), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('preferred_date', sa.Date(), nullable=False),
        sa.Column('preferred_time_slot', sa.String(length=50), nullable=False),
        sa.Column('suggested_alternative_date', sa.Date(), nullable=True),
        sa.Column('suggested_alternative_time_slot', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='pending', nullable=False),
        sa.Column('handling_owner_id', sa.UUID(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['handling_owner_id'], ['owners.id'], name=op.f('fk_gym_visit_requests_handling_owner_id_owners'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_gym_visit_requests'))
    )
    op.create_index(op.f('ix_gym_visit_requests_status'), 'gym_visit_requests', ['status'], unique=False)

    # --------------------------------------------------------------------------
    # 10. MODULE K: NOTIFICATIONS
    # --------------------------------------------------------------------------
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('recipient_owner_id', sa.UUID(), nullable=False),
        sa.Column('notification_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('related_entity_type', sa.String(length=50), nullable=True),
        sa.Column('related_entity_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['recipient_owner_id'], ['owners.id'], name=op.f('fk_notifications_recipient_owner_id_owners'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications'))
    )
    op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)
    op.create_index(op.f('ix_notifications_recipient_owner_id'), 'notifications', ['recipient_owner_id'], unique=False)

    # --------------------------------------------------------------------------
    # 11. MODULE L: AUDIT LOGS
    # --------------------------------------------------------------------------
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('previous_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], name=op.f('fk_audit_logs_owner_id_owners'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_owner_id'), 'audit_logs', ['owner_id'], unique=False)

    # --------------------------------------------------------------------------
    # 12. MODULE M: GALLERY MANAGEMENT
    # --------------------------------------------------------------------------
    op.create_table(
        'gallery_images',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=True),
        sa.Column('storage_path', sa.String(length=500), nullable=False),
        sa.Column('file_name', sa.String(length=150), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_cover_image', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('uploaded_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('file_size_bytes > 0', name='ck_gallery_file_size_positive'),
        sa.ForeignKeyConstraint(['uploaded_by_owner_id'], ['owners.id'], name=op.f('fk_gallery_images_uploaded_by_owner_id_owners'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_gallery_images'))
    )
    op.create_index(op.f('ix_gallery_images_display_order'), 'gallery_images', ['display_order'], unique=False)
    op.create_index(op.f('ix_gallery_images_is_active'), 'gallery_images', ['is_active'], unique=False)
    op.create_index(
        'idx_uq_gallery_single_cover',
        'gallery_images',
        ['is_cover_image'],
        unique=True,
        postgresql_where=sa.text('is_cover_image = true AND is_active = true')
    )

    # --------------------------------------------------------------------------
    # 13. MODULE N: SYSTEM SETTINGS
    # --------------------------------------------------------------------------
    op.create_table(
        'system_settings',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('setting_key', sa.String(length=100), nullable=False),
        sa.Column('setting_value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_encrypted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('updated_by_owner_id', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['updated_by_owner_id'], ['owners.id'], name=op.f('fk_system_settings_updated_by_owner_id_owners'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_system_settings')),
        sa.UniqueConstraint('setting_key', name=op.f('uq_system_settings_setting_key'))
    )
    op.create_index(op.f('ix_system_settings_setting_key'), 'system_settings', ['setting_key'], unique=True)

    # --------------------------------------------------------------------------
    # 14. MODULE O: WHATSAPP INTEGRATION
    # --------------------------------------------------------------------------
    op.create_table(
        'whatsapp_message_logs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('message_type', sa.String(length=50), nullable=False),
        sa.Column('recipient_phone', sa.String(length=20), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=True),
        sa.Column('related_entity_type', sa.String(length=50), nullable=True),
        sa.Column('related_entity_id', sa.UUID(), nullable=True),
        sa.Column('provider_message_id', sa.String(length=100), nullable=True),
        sa.Column('delivery_status', sa.String(length=30), server_default='queued', nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_whatsapp_message_logs_member_id_members'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_whatsapp_message_logs'))
    )
    op.create_index(op.f('ix_whatsapp_message_logs_delivery_status'), 'whatsapp_message_logs', ['delivery_status'], unique=False)
    op.create_index(op.f('ix_whatsapp_message_logs_member_id'), 'whatsapp_message_logs', ['member_id'], unique=False)
    op.create_index(op.f('ix_whatsapp_message_logs_provider_message_id'), 'whatsapp_message_logs', ['provider_message_id'], unique=False)
    op.create_index(op.f('ix_whatsapp_message_logs_recipient_phone'), 'whatsapp_message_logs', ['recipient_phone'], unique=False)

    # --------------------------------------------------------------------------
    # 15. MODULE P: SYSTEM SEQUENCES REGISTRY
    # --------------------------------------------------------------------------
    op.create_table(
        'system_sequences',
        sa.Column('sequence_name', sa.String(length=50), nullable=False),
        sa.Column('prefix', sa.String(length=10), nullable=False),
        sa.Column('padding_digits', sa.Integer(), nullable=False),
        sa.Column('current_value', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('sequence_name', name=op.f('pk_system_sequences'))
    )


def downgrade() -> None:
    # --------------------------------------------------------------------------
    # DROP TABLES IN REVERSE TOPOLOGICAL ORDER
    # --------------------------------------------------------------------------
    op.drop_table('system_sequences')
    op.drop_index(op.f('ix_whatsapp_message_logs_recipient_phone'), table_name='whatsapp_message_logs')
    op.drop_index(op.f('ix_whatsapp_message_logs_provider_message_id'), table_name='whatsapp_message_logs')
    op.drop_index(op.f('ix_whatsapp_message_logs_member_id'), table_name='whatsapp_message_logs')
    op.drop_index(op.f('ix_whatsapp_message_logs_delivery_status'), table_name='whatsapp_message_logs')
    op.drop_table('whatsapp_message_logs')

    op.drop_index(op.f('ix_system_settings_setting_key'), table_name='system_settings')
    op.drop_table('system_settings')

    op.drop_index('idx_uq_gallery_single_cover', table_name='gallery_images', postgresql_where=sa.text('is_cover_image = true AND is_active = true'))
    op.drop_index(op.f('ix_gallery_images_is_active'), table_name='gallery_images')
    op.drop_index(op.f('ix_gallery_images_display_order'), table_name='gallery_images')
    op.drop_table('gallery_images')

    op.drop_index(op.f('ix_audit_logs_owner_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_type'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index(op.f('ix_notifications_recipient_owner_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_is_read'), table_name='notifications')
    op.drop_table('notifications')

    op.drop_index(op.f('ix_gym_visit_requests_status'), table_name='gym_visit_requests')
    op.drop_table('gym_visit_requests')

    op.drop_index(op.f('ix_general_enquiries_status'), table_name='general_enquiries')
    op.drop_table('general_enquiries')

    op.drop_index(op.f('ix_joining_applications_status'), table_name='joining_applications')
    op.drop_index(op.f('ix_joining_applications_phone_number'), table_name='joining_applications')
    op.drop_table('joining_applications')

    op.drop_index('idx_invoices_payment_id', table_name='invoices')
    op.drop_index('idx_invoices_contract_id', table_name='invoices')
    op.drop_index(op.f('ix_invoices_payment_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_membership_record_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_member_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_invoice_number'), table_name='invoices')
    op.drop_table('invoices')

    op.drop_index(op.f('ix_payment_refunds_refund_number'), table_name='payment_refunds')
    op.drop_index(op.f('ix_payment_refunds_original_payment_id'), table_name='payment_refunds')
    op.drop_index(op.f('ix_payment_refunds_member_id'), table_name='payment_refunds')
    op.drop_table('payment_refunds')

    op.drop_index('idx_payments_membership_id', table_name='payments')
    op.drop_index('idx_payments_confirmation_date', table_name='payments')
    op.drop_index(op.f('ix_payments_status'), table_name='payments')
    op.drop_index(op.f('ix_payments_payment_number'), table_name='payments')
    op.drop_index(op.f('ix_payments_payment_date'), table_name='payments')
    op.drop_index(op.f('ix_payments_membership_record_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_member_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_due_schedule_installment_id'), table_name='payments')
    op.drop_table('payments')

    op.drop_index('idx_dues_schedule_overdue', table_name='membership_due_schedules')
    op.drop_index(op.f('ix_membership_due_schedules_membership_record_id'), table_name='membership_due_schedules')
    op.drop_index(op.f('ix_membership_due_schedules_member_id'), table_name='membership_due_schedules')
    op.drop_index(op.f('ix_membership_due_schedules_is_waived'), table_name='membership_due_schedules')
    op.drop_index(op.f('ix_membership_due_schedules_due_date'), table_name='membership_due_schedules')
    op.drop_table('membership_due_schedules')

    op.drop_index('idx_membership_member_status', table_name='membership_records')
    op.drop_index('idx_membership_expiry_date', table_name='membership_records')
    op.drop_index(op.f('ix_membership_records_system_status'), table_name='membership_records')
    op.drop_index(op.f('ix_membership_records_plan_id'), table_name='membership_records')
    op.drop_index(op.f('ix_membership_records_member_id'), table_name='membership_records')
    op.drop_index(op.f('ix_membership_records_expiry_date'), table_name='membership_records')
    op.drop_table('membership_records')

    op.drop_index(op.f('ix_membership_plans_is_archived'), table_name='membership_plans')
    op.drop_index(op.f('ix_membership_plans_is_active'), table_name='membership_plans')
    op.drop_table('membership_plans')

    op.drop_index('idx_uq_members_active_phone', table_name='members', postgresql_where=sa.text('is_archived = false'))
    op.drop_index('idx_members_search_name', table_name='members')
    op.drop_index(op.f('ix_members_member_code'), table_name='members')
    op.drop_index(op.f('ix_members_is_archived'), table_name='members')
    op.drop_table('members')

    op.drop_index(op.f('ix_owner_sessions_refresh_token_hash'), table_name='owner_sessions')
    op.drop_index(op.f('ix_owner_sessions_owner_id'), table_name='owner_sessions')
    op.drop_table('owner_sessions')

    op.drop_index(op.f('ix_owner_password_reset_otps_owner_id'), table_name='owner_password_reset_otps')
    op.drop_table('owner_password_reset_otps')

    op.drop_index(op.f('ix_owner_device_push_subscriptions_owner_id'), table_name='owner_device_push_subscriptions')
    op.drop_table('owner_device_push_subscriptions')

    op.drop_index(op.f('ix_owner_notification_preferences_owner_id'), table_name='owner_notification_preferences')
    op.drop_table('owner_notification_preferences')

    op.drop_index(op.f('ix_owners_phone_number'), table_name='owners')
    op.drop_index(op.f('ix_owners_email'), table_name='owners')
    op.drop_table('owners')

    # --------------------------------------------------------------------------
    # DROP SEQUENCES
    # --------------------------------------------------------------------------
    op.execute(sa.schema.DropSequence(sa.Sequence('refund_number_seq')))
    op.execute(sa.schema.DropSequence(sa.Sequence('payment_number_seq')))
    op.execute(sa.schema.DropSequence(sa.Sequence('invoice_number_seq')))
    op.execute(sa.schema.DropSequence(sa.Sequence('member_code_seq')))

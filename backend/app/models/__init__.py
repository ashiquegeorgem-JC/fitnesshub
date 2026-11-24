"""
Regal Fitness Database Models Package.
Exports all 21 SQLAlchemy ORM models and sequences defined in docs/DATABASE_SCHEMA.md.
"""

from app.database.base import Base

# Module A: Owner Management
from app.models.owner import (
    Owner,
    OwnerDevicePushSubscription,
    OwnerNotificationPreference,
    OwnerPasswordResetOTP,
    OwnerSession,
)

# Module B: Member Management
from app.models.member import Member

# Module C: Plan Catalog
from app.models.plan import MembershipPlan

# Module D & F: Membership Lifecycle & Due Schedules
from app.models.membership import MembershipDueSchedule, MembershipRecord

# Module E: Payments & Adjustments
from app.models.payment import Payment, PaymentRefund

# Module G: Billing & Receipts
from app.models.invoice import Invoice

# Module H, I, J: Public Website Intake (Developer 1 Boundary)
from app.models.public import GeneralEnquiry, GymVisitRequest, JoiningApplication

# Module K: Internal Notifications
from app.models.notification import Notification

# Module L: Audit Logs
from app.models.audit import AuditLog

# Module M: Gallery Management
from app.models.gallery import GalleryImage

# Module N: System Settings
from app.models.setting import SystemSetting

# Module O: WhatsApp Integration
from app.models.whatsapp import WhatsAppMessageLog

# Module P: Sequence Registry & Standalone Sequences
from app.models.sequence import (
    SystemSequence,
    invoice_number_seq,
    member_code_seq,
    payment_number_seq,
    refund_number_seq,
)

__all__ = [
    "Base",
    # Module A
    "Owner",
    "OwnerNotificationPreference",
    "OwnerDevicePushSubscription",
    "OwnerPasswordResetOTP",
    "OwnerSession",
    # Module B
    "Member",
    # Module C
    "MembershipPlan",
    # Module D & F
    "MembershipRecord",
    "MembershipDueSchedule",
    # Module E
    "Payment",
    "PaymentRefund",
    # Module G
    "Invoice",
    # Module H, I, J
    "JoiningApplication",
    "GeneralEnquiry",
    "GymVisitRequest",
    # Module K
    "Notification",
    # Module L
    "AuditLog",
    # Module M
    "GalleryImage",
    # Module N
    "SystemSetting",
    # Module O
    "WhatsAppMessageLog",
    # Module P
    "SystemSequence",
    "member_code_seq",
    "invoice_number_seq",
    "payment_number_seq",
    "refund_number_seq",
]

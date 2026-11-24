import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Dashboard Overview Schemas
# ---------------------------------------------------------------------------


class MemberCountsOverview(BaseModel):
    total_members: int = Field(..., description="Total non-archived registered members")
    active_members: int = Field(..., description="Currently active gym members")
    expired_members: int = Field(..., description="Members with expired memberships and no active contract")
    archived_members: int = Field(..., description="Archived member profiles")


class MembershipAlertsOverview(BaseModel):
    expiring_within_7_days: int = Field(..., description="Active memberships expiring in the next 7 days")
    expiring_within_3_days: int = Field(..., description="Active memberships expiring in the next 3 days (urgent)")


class TodayMetricsOverview(BaseModel):
    new_admissions_today: int = Field(..., description="New members joined today")
    collections_today: Decimal = Field(..., description="Net confirmed revenue collected today")


class MonthMetricsOverview(BaseModel):
    collections_this_month: Decimal = Field(..., description="Net confirmed revenue collected month-to-date")


class FinancialSummaryOverview(BaseModel):
    outstanding_dues: Decimal = Field(..., description="Total outstanding membership fees across all active/expired contracts")


class ActivitySummaryItem(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    description: str
    actor_owner_name: Optional[str] = None
    created_at: datetime


class DashboardOverviewResponse(BaseModel):
    """Main dashboard overview summary."""

    business_date: date = Field(..., description="Current business date (Asia/Kolkata)")
    member_counts: MemberCountsOverview
    membership_alerts: MembershipAlertsOverview
    today_metrics: TodayMetricsOverview
    month_metrics: MonthMetricsOverview
    financial_summary: FinancialSummaryOverview
    recent_activity: List[ActivitySummaryItem]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 2. Membership Analytics Schemas
# ---------------------------------------------------------------------------


class PlanDistributionItem(BaseModel):
    plan_id: uuid.UUID
    plan_name: str
    duration_days: int
    base_price: Decimal
    active_members_count: int
    total_contracts_count: int


class MembershipTypeBreakdown(BaseModel):
    new_count: int = Field(..., description="Count of new membership contracts")
    renewal_count: int = Field(..., description="Count of renewal contracts")
    upgrade_count: int = Field(..., description="Count of upgrade contracts")


class MembershipAnalyticsSummary(BaseModel):
    new_admissions: int = Field(..., description="New members joined in period")
    renewals: int = Field(..., description="Memberships renewed in period")
    total_active_members: int = Field(..., description="Currently active members")
    total_expired_members: int = Field(..., description="Currently expired members")
    expiring_within_7_days: int = Field(..., description="Expiring within 7 days")
    expiring_within_3_days: int = Field(..., description="Expiring within 3 days")


class AnalyticsPeriod(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    preset: Optional[str] = None


class MembershipAnalyticsResponse(BaseModel):
    """Membership statistics and distribution."""

    period: AnalyticsPeriod
    summary: MembershipAnalyticsSummary
    plan_distribution: List[PlanDistributionItem]
    membership_type_breakdown: MembershipTypeBreakdown

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 3. Financial Analytics Schemas
# ---------------------------------------------------------------------------


class PaymentTypeMetric(BaseModel):
    amount: Decimal
    count: int


class PaymentTypeBreakdown(BaseModel):
    full: PaymentTypeMetric
    partial: PaymentTypeMetric
    installment: PaymentTypeMetric
    advance: PaymentTypeMetric


class MembershipTypeRevenue(BaseModel):
    new_membership_revenue: Decimal
    renewal_revenue: Decimal
    other_revenue: Decimal


class PaymentMethodMetric(BaseModel):
    method: str
    amount: Decimal
    count: int


class FinancialTotals(BaseModel):
    gross_confirmed_collections: Decimal = Field(..., description="Gross confirmed payments received")
    processed_refunds: Decimal = Field(..., description="Total processed refunds")
    net_collections: Decimal = Field(..., description="Gross confirmed payments minus processed refunds")
    total_outstanding_dues: Decimal = Field(..., description="Current outstanding dues across all members")


class FinancialAnalyticsResponse(BaseModel):
    """Financial revenue, collections, and dues breakdown."""

    period: AnalyticsPeriod
    totals: FinancialTotals
    by_payment_type: PaymentTypeBreakdown
    by_membership_type: MembershipTypeRevenue
    by_payment_method: List[PaymentMethodMetric]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 4. Renewal Pipeline Schemas
# ---------------------------------------------------------------------------


class RenewalPipelineSummary(BaseModel):
    expiring_7_days_count: int = Field(..., description="Count of memberships expiring in 4 to 7 days")
    expiring_3_days_count: int = Field(..., description="Count of memberships expiring in 0 to 3 days (urgent)")
    already_expired_count: int = Field(..., description="Count of members whose term expired with no renewal in flight")
    renewal_pending_count: int = Field(..., description="Count of expired members with renewal pending activation")
    recently_renewed_count: int = Field(..., description="Count of members renewed in the past 30 days")


class RenewalPipelineItem(BaseModel):
    member_id: uuid.UUID
    member_code: str
    member_name: str
    phone_number: str
    membership_id: Optional[uuid.UUID] = None
    plan_name: Optional[str] = None
    expiry_date: Optional[date] = None
    days_until_expiry: Optional[int] = Field(
        None, description="Days remaining until expiry (negative if expired, 0 if today)"
    )
    outstanding_dues: Decimal = Field(Decimal("0.00"), description="Outstanding dues on this contract")
    pipeline_status: str = Field(
        ...,
        description="'urgent_expiry' (0-3d), 'expiring_soon' (4-7d), 'already_expired', 'renewal_pending', 'recently_renewed'",
    )


class PaginationMetadata(BaseModel):
    total_count: int
    page: int
    page_size: int
    total_pages: int


class RenewalPipelineResponse(BaseModel):
    """Paginated renewal pipeline with category summary."""

    summary: RenewalPipelineSummary
    items: List[RenewalPipelineItem]
    pagination: PaginationMetadata

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 5. Recent Activity Schemas
# ---------------------------------------------------------------------------


class RecentActivityItem(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    description: str
    actor_owner_id: Optional[uuid.UUID] = None
    actor_owner_name: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime


class RecentActivityResponse(BaseModel):
    """Paginated recent system activity from audit logs."""

    items: List[RecentActivityItem]
    pagination: PaginationMetadata

    model_config = ConfigDict(from_attributes=True)

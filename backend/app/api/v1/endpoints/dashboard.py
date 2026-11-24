from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_owner, get_db
from app.models.owner import Owner
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    FinancialAnalyticsResponse,
    MembershipAnalyticsResponse,
    RecentActivityResponse,
    RenewalPipelineResponse,
)
from app.services.dashboard import (
    get_dashboard_overview,
    get_financial_analytics,
    get_membership_analytics,
    get_recent_activity,
    get_renewal_pipeline,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Dashboard Overview",
    description="Retrieve high-level overview metrics, alerts, collections, dues, and recent activity.",
)
def overview(
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> DashboardOverviewResponse:
    return get_dashboard_overview(db=db)


@router.get(
    "/membership-analytics",
    response_model=MembershipAnalyticsResponse,
    summary="Membership Analytics",
    description="Retrieve membership acquisition, renewal rates, plan distribution, and expiration metrics with date filtering.",
)
def membership_analytics(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MembershipAnalyticsResponse:
    return get_membership_analytics(db=db, start_date=start_date, end_date=end_date)


@router.get(
    "/financial-analytics",
    response_model=FinancialAnalyticsResponse,
    summary="Financial Analytics",
    description="Retrieve gross/net collections, refunds, outstanding dues, and revenue broken down by payment type, membership type, and method.",
)
def financial_analytics(
    preset: Optional[str] = Query(
        None,
        description="Date range preset: 'today', 'this_week', 'this_month', 'this_year', 'custom'",
    ),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD) for custom preset"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD) for custom preset"),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> FinancialAnalyticsResponse:
    return get_financial_analytics(
        db=db, preset=preset, start_date=start_date, end_date=end_date
    )


@router.get(
    "/renewal-pipeline",
    response_model=RenewalPipelineResponse,
    summary="Renewal Pipeline",
    description="Paginated list of upcoming expirations, urgent expirations, expired members, and renewals in flight.",
)
def renewal_pipeline(
    category: str = Query(
        "all",
        description="Filter category: 'all', 'expiring_7_days', 'expiring_3_days', 'already_expired', 'renewal_pending', 'recently_renewed'",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> RenewalPipelineResponse:
    return get_renewal_pipeline(
        db=db, category=category, page=page, page_size=page_size
    )


@router.get(
    "/recent-activity",
    response_model=RecentActivityResponse,
    summary="Recent Activity Log",
    description="Paginated audit ledger log of recent system state transitions, authentications, and owner actions.",
)
def recent_activity(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    action_filter: Optional[str] = Query(None, description="Optional action filter (e.g. 'PAYMENT_CONFIRMED')"),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> RecentActivityResponse:
    return get_recent_activity(
        db=db, page=page, page_size=page_size, action_filter=action_filter
    )

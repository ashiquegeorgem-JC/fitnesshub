import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_owner, get_db
from app.api.v1.endpoints.auth import _extract_request_metadata
from app.models.owner import Owner
from app.schemas.member import (
    MemberArchiveRequest,
    MemberCreate,
    MemberListResponse,
    MemberMembershipHistoryResponse,
    MemberPaymentHistoryResponse,
    MemberResponse,
    MemberSortField,
    MemberUpdate,
    SortOrder,
)
from app.services.member import (
    archive_member,
    create_member,
    get_member_details,
    get_member_memberships,
    get_member_payments,
    list_members,
    reactivate_member,
    update_member,
)

router = APIRouter(prefix="/members", tags=["Members"])


@router.post(
    "/",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Member",
    description="Register a new gym member with an auto-generated RF member code. Does not create memberships or payments.",
)
def create_member_endpoint(
    payload: MemberCreate,
    request: Request,
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberResponse:
    ip_address, user_agent = _extract_request_metadata(request)
    return create_member(
        db=db,
        payload=payload,
        owner=current_owner,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.get(
    "/",
    response_model=MemberListResponse,
    summary="List Members",
    description="Search, filter, sort, and paginate members. Defaults to non-archived members.",
)
def list_members_endpoint(
    search: Optional[str] = Query(
        None, description="Search by RF member code, full name, or phone number"
    ),
    gender: Optional[str] = Query(
        None, description="Filter by gender (male, female, other, prefer_not_to_say)"
    ),
    is_archived: bool = Query(
        False, description="Filter archive status (false=active, true=archived)"
    ),
    sort_by: MemberSortField = Query(
        "created_at",
        description="Sort field: created_at, joining_date, full_name, member_code",
    ),
    sort_order: SortOrder = Query("desc", description="Sort direction: asc, desc"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberListResponse:
    return list_members(
        db=db,
        search=search,
        gender=gender,
        is_archived=is_archived,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{member_id}",
    response_model=MemberResponse,
    summary="Get Member Details",
    description="Retrieve a member's full profile by UUID (including archived members).",
)
def get_member_endpoint(
    member_id: uuid.UUID,
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberResponse:
    return get_member_details(db=db, member_id=member_id)


@router.patch(
    "/{member_id}",
    response_model=MemberResponse,
    summary="Update Member",
    description="Partially update permitted member profile fields. Protected fields are rejected.",
)
def update_member_endpoint(
    member_id: uuid.UUID,
    payload: MemberUpdate,
    request: Request,
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberResponse:
    ip_address, user_agent = _extract_request_metadata(request)
    return update_member(
        db=db,
        member_id=member_id,
        payload=payload,
        owner=current_owner,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.post(
    "/{member_id}/archive",
    response_model=MemberResponse,
    summary="Archive Member",
    description="Soft-archive a member while preserving all membership and financial history.",
)
def archive_member_endpoint(
    member_id: uuid.UUID,
    request: Request,
    payload: Optional[MemberArchiveRequest] = Body(default=None),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberResponse:
    ip_address, user_agent = _extract_request_metadata(request)
    return archive_member(
        db=db,
        member_id=member_id,
        owner=current_owner,
        reason=payload.reason if payload else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.post(
    "/{member_id}/reactivate",
    response_model=MemberResponse,
    summary="Reactivate Member",
    description="Reactivate an archived member after verifying phone uniqueness. Does not activate memberships.",
)
def reactivate_member_endpoint(
    member_id: uuid.UUID,
    request: Request,
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberResponse:
    ip_address, user_agent = _extract_request_metadata(request)
    return reactivate_member(
        db=db,
        member_id=member_id,
        owner=current_owner,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.get(
    "/{member_id}/memberships",
    response_model=MemberMembershipHistoryResponse,
    summary="Member Membership History",
    description="Retrieve paginated historical membership contracts for a member, newest first.",
)
def member_memberships_endpoint(
    member_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberMembershipHistoryResponse:
    return get_member_memberships(
        db=db,
        member_id=member_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{member_id}/payments",
    response_model=MemberPaymentHistoryResponse,
    summary="Member Payment History",
    description="Retrieve paginated payment history for a member, including processed refund totals.",
)
def member_payments_endpoint(
    member_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_owner: Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
) -> MemberPaymentHistoryResponse:
    return get_member_payments(
        db=db,
        member_id=member_id,
        page=page,
        page_size=page_size,
    )

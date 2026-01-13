from fastapi import APIRouter, Depends, Request, status
from httpcore import request

from app.schemas.staff.member_schemas import (
    StaffMemberListResponse,
    CreateStaffMemberRequest,
    UpdateStaffMemberRequest,
    StaffMemberItem,
)
from app.services.staff.member_service import get_member_service

from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError
from app.middlewares.auth_middleware import require_staff


members_router = APIRouter(dependencies=[Depends(require_staff)])


# API Endpoints
@members_router.get(
    "",
    response_model=StaffMemberListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all staff members",
    description="Retrieve a list of all staff members with their details.",
)
async def get_all_members(request: Request, member_service=Depends(get_member_service)):
    """Get all staff members"""
    try:
        members = await member_service.get_all_members_with_count()

        return ResponseBuilder.success(
            request=request,
            data={
                "members": [member.model_dump(by_alias=True) for member in members],
                "total_count": len(members),
            },
            message=f"Retrieved {len(members)} staff member{'s' if len(members) != 1 else ''}",
            status_code=status.HTTP_200_OK,
        )

    except Exception as e:
        raise BusinessLogicError(
            message=str(e) or "Failed to retrieve staff members",
            error_code="STAFF_MEMBERS_RETRIEVAL_FAILED",
        )


@members_router.post(
    "",
    response_model=StaffMemberItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new staff member",
    description="Create a new staff member with the provided details.",
)
async def create_staff_member(
    request: Request,
    member_data: CreateStaffMemberRequest,
    member_service=Depends(get_member_service),
):
    """Create a new staff member"""
    try:
        data = await member_service.create_member(member_data)
        return ResponseBuilder.success(
            request=request,
            data=data.model_dump(by_alias=True),
            message="Staff member created successfully",
            status_code=status.HTTP_201_CREATED,
        )
    except Exception as e:
        raise BusinessLogicError(
            message=str(e) or "Failed to create staff member",
            error_code="STAFF_MEMBER_CREATION_FAILED",
        )


@members_router.put(
    "/{staff_id}",
    response_model=StaffMemberItem,
    status_code=status.HTTP_200_OK,
    summary="Update a staff member",
    description="Update an existing staff member's details.",
)
async def update_staff_member(
    request: Request,
    staff_id: str,
    member_data: UpdateStaffMemberRequest,
    member_service=Depends(get_member_service),
):
    """Update a staff member"""
    try:
        data = await member_service.update_member(staff_id, member_data)
        return ResponseBuilder.success(
            request=request,
            data=data.model_dump(by_alias=True),
            message="Staff member updated successfully",
            status_code=status.HTTP_200_OK,
        )
    except Exception as e:
        raise BusinessLogicError(
            message=str(e) or "Failed to update staff member",
            error_code="STAFF_MEMBER_UPDATE_FAILED",
        )

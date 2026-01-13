from datetime import datetime
from pydantic import Field

from app.schemas.camel_base_model import CamelCaseBaseModel


class StaffMemberItem(CamelCaseBaseModel):
    """Response schema for a staff member item"""

    id: str = Field(..., description="Staff member ID")
    username: str = Field(..., description="Staff member username")
    first_name: str = Field(..., description="Staff member first name")
    last_name: str = Field(..., description="Staff member last name")
    is_active: bool = Field(..., description="Whether the staff member is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class StaffMemberListResponse(CamelCaseBaseModel):
    """Response schema for a list of staff members"""

    members: list[StaffMemberItem] = Field(..., description="List of staff members")
    total_count: int = Field(..., description="Total number of staff members")


class CreateStaffMemberRequest(CamelCaseBaseModel):
    """Request schema for creating a new staff member"""

    username: str = Field(..., description="Staff member username")
    first_name: str = Field(..., description="Staff member first name")
    last_name: str = Field(..., description="Staff member last name")


class UpdateStaffMemberRequest(CamelCaseBaseModel):
    """Request schema for updating an existing staff member"""

    first_name: str = Field(..., description="Staff member first name")
    last_name: str = Field(..., description="Staff member last name")
    # is_active: bool = Field(..., description="Whether the staff member is active")

from datetime import datetime
from typing import Optional
from pydantic import Field, field_validator

from app.schemas.camel_base_model import CamelCaseBaseModel as BaseModel
from app.utils.datetime_utils import utc_now, to_utc


class CreateProgramRequirementScheduleRequest(BaseModel):
    """Request schema for creating a new program requirement schedule"""

    program_requirement_id: str = Field(
        ..., description="Program requirement ID for the schedule"
    )
    academic_year_id: str = Field(..., description="Academic year ID for the schedule")
    submission_deadline: datetime = Field(
        ..., description="Submission deadline for this schedule"
    )
    grace_period_days: Optional[int] = Field(
        default=7, ge=0, le=365, description="Grace period in days after deadline"
    )
    notification_days_before_deadline: Optional[int] = Field(
        default=90,
        ge=0,
        le=365,
        description="Days before deadline to start sending notifications",
    )

    @field_validator("submission_deadline")
    @classmethod
    def validate_deadline_future(cls, v: datetime) -> datetime:
        """Ensure deadline is in the future"""
        if to_utc(v) <= utc_now():
            raise ValueError("Submission deadline must be in the future")
        return v

    @field_validator("grace_period_days")
    @classmethod
    def validate_grace_period(cls, v: Optional[int]) -> Optional[int]:
        """Validate grace period range"""
        if v is not None and (v < 0 or v > 365):
            raise ValueError("Grace period must be between 0 and 365 days")
        return v

    @field_validator("notification_days_before_deadline")
    @classmethod
    def validate_notification_days(cls, v: Optional[int]) -> Optional[int]:
        """Validate notification days range"""
        if v is not None and (v < 0 or v > 365):
            raise ValueError("Notification days must be between 0 and 365")
        return v


class UpdateProgramRequirementScheduleRequest(CreateProgramRequirementScheduleRequest):
    """Request schema for updating an existing program requirement schedule"""

    id: str = Field(..., description="Schedule ID to update")


class ProgramRequirementScheduleResponse(BaseModel):
    """Response schema for program requirement schedule data"""

    id: str = Field(..., description="Schedule ID")
    program_requirement_id: str = Field(..., description="Program requirement ID")
    academic_year_id: str = Field(..., description="Academic year ID")
    submission_deadline: datetime = Field(..., description="Submission deadline")
    grace_period_deadline: datetime = Field(..., description="Grace period deadline")
    start_notify_at: datetime = Field(
        ..., description="When to start sending notifications"
    )
    last_notified_at: Optional[datetime] = Field(
        None, description="Last notification timestamp"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class GetProgramRequirementSchedulesItem(BaseModel):
    """Comprehensive response schema for schedule list with all related data"""

    # Schedule core fields
    id: str = Field(..., description="Schedule ID")
    program_requirement_id: str = Field(..., description="Program requirement ID")
    submission_deadline: datetime = Field(..., description="Submission deadline")
    grace_period_deadline: datetime = Field(..., description="Grace period deadline")
    start_notify_at: datetime = Field(
        ..., description="When to start sending notifications"
    )
    last_notified_at: Optional[datetime] = Field(
        None, description="Last notification timestamp"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Program information
    program_id: str = Field(..., description="Program ID")
    program_code: str = Field(..., description="Program code")
    program_name: str = Field(..., description="Program name")

    # Certificate type information
    cert_id: str = Field(..., description="Certificate type ID")
    cert_code: str = Field(..., description="Certificate type code")
    cert_name: str = Field(..., description="Certificate type name")

    # Academic year information
    academic_year_id: str = Field(..., description="Academic year ID")
    academic_year: int = Field(..., description="Academic year code")

    # Program requirement information
    requirement_name: str = Field(..., description="Requirement name")
    target_year: int = Field(..., description="Target year")
    is_mandatory: bool = Field(..., description="Whether requirement is mandatory")

    # Dashboard statistics (optional - only if exists)
    total_submissions_required: Optional[int] = Field(
        None, description="Total submissions required"
    )
    submitted_count: Optional[int] = Field(None, description="Number of submissions")
    approved_count: Optional[int] = Field(None, description="Approved submissions")
    rejected_count: Optional[int] = Field(None, description="Rejected submissions")
    pending_count: Optional[int] = Field(None, description="Pending submissions")
    manual_review_count: Optional[int] = Field(
        None, description="Manual review submissions"
    )
    not_submitted_count: Optional[int] = Field(None, description="Not submitted count")
    on_time_submissions: Optional[int] = Field(None, description="On time submissions")
    late_submissions: Optional[int] = Field(None, description="Late submissions")
    overdue_count: Optional[int] = Field(None, description="Overdue count")

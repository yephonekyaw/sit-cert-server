from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.schemas.camel_base_model import CamelCaseBaseModel as BaseModel


class DashboardStatsResponse(BaseModel):
    """Response schema for dashboard statistics."""

    id: str | UUID = Field(..., description="Unique identifier for the stats record")
    requirement_schedule_id: str | UUID = Field(
        ..., description="Requirement schedule ID"
    )
    program_id: str | UUID = Field(..., description="Program ID")
    academic_year_id: str | UUID = Field(..., description="Academic year ID")
    cert_type_id: str | UUID = Field(..., description="Certificate type ID")
    total_submissions_required: int = Field(
        ..., description="Total submissions required"
    )
    submitted_count: int = Field(..., description="Count of submitted items")
    approved_count: int = Field(..., description="Count of approved items")
    rejected_count: int = Field(..., description="Count of rejected items")
    pending_count: int = Field(..., description="Count of pending items")
    manual_review_count: int = Field(
        ..., description="Count of items under manual review"
    )
    not_submitted_count: int = Field(..., description="Count of not submitted items")
    on_time_submissions: int = Field(..., description="Count of on-time submissions")
    late_submissions: int = Field(..., description="Count of late submissions")
    overdue_submissions: int = Field(..., description="Count of overdue items")
    manual_verification_count: int = Field(
        ..., description="Count of items requiring manual verification"
    )
    agent_verification_count: int = Field(
        ..., description="Count of items verified by agents"
    )
    last_calculated_at: datetime = Field(
        ..., description="Timestamp of last calculation"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

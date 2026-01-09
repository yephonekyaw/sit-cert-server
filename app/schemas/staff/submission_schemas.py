from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import Field
from app.db.models import SubmissionStatus, VerificationType

from app.schemas.camel_base_model import CamelCaseBaseModel as BaseModel


class StudentSubmissionItem(BaseModel):
    # Student data
    id: str | UUID = Field(..., description="Unique identifier")
    student_id: str | UUID = Field(..., description="Student ID")
    student_roll_number: str = Field(..., description="Student roll number")
    student_name: str = Field(..., description="Student full name")
    student_email: str = Field(..., description="Student email address")
    student_enrollment_status: str = Field(..., description="Student enrollment status")

    # Submission data (None if not submitted)
    submission_id: Optional[str | UUID] = Field(None, description="Submission ID")
    file_object_name: Optional[str] = Field(
        None, description="File object name in MinIO"
    )
    filename: Optional[str] = Field(None, description="Original file name")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    mime_type: Optional[str] = Field(None, description="File MIME type")
    submission_status: Optional[str] = Field(
        None, description="Current submission status"
    )
    submission_timing: Optional[str] = Field(
        None, description="Submission timing status"
    )
    submitted_at: Optional[str] = Field(
        None, description="Timestamp when submitted (ISO format)"
    )
    expired_at: Optional[str] = Field(
        None, description="Expiration timestamp (ISO format)"
    )


class SubmissionRelatedDate(BaseModel):
    # Schedule data
    schedule_id: str | UUID = Field(..., description="Program requirement schedule ID")
    submission_deadline: str = Field(
        ..., description="Submission deadline (ISO format)"
    )

    # Requirement data
    requirement_id: str | UUID = Field(..., description="Program requirement ID")
    requirement_name: str = Field(..., description="Requirement name")
    target_year: int = Field(..., description="Target year for completion")
    is_mandatory: bool = Field(..., description="Whether requirement is mandatory")
    special_instruction: Optional[str] = Field(None, description="Special instructions")

    # Program data
    program_id: str | UUID = Field(..., description="Program ID")
    program_code: str = Field(..., description="Program code")
    program_name: str = Field(..., description="Program name")

    # Certificate type data
    cert_type_id: str | UUID = Field(..., description="Certificate type ID")
    cert_code: str = Field(..., description="Certificate code")
    cert_name: str = Field(..., description="Certificate name")
    cert_description: str = Field(..., description="Certificate description")

    # Academic year data
    year_code: int = Field(..., description="Academic year code")


class GetListOfSubmissions(BaseModel):
    """Response schema for list of all certificate submissions"""

    submitted_submissions: List[StudentSubmissionItem] = Field(
        ..., description="List of submitted certificate submissions"
    )
    unsubmitted_submissions: List[StudentSubmissionItem] = Field(
        ..., description="List of unsubmitted certificate submissions"
    )
    submission_related_data: SubmissionRelatedDate = Field(
        ..., description="Common data related to the submission"
    )


class VerificationHistoryResponse(BaseModel):
    """Response schema for verification history"""

    id: str | UUID = Field(..., description="Verification history ID")
    verification_type: VerificationType = Field(
        ..., description="Type of verification (manual/agent)"
    )
    old_status: SubmissionStatus = Field(..., description="Previous submission status")
    new_status: SubmissionStatus = Field(..., description="New submission status")
    comments: Optional[str] = Field(None, description="Verification comments")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class VerificationHistoryListResponse(BaseModel):
    """Response schema for list of verification history"""

    verification_history: List[VerificationHistoryResponse] = Field(
        ..., description="List of verification history records"
    )
    total_count: int = Field(
        ..., description="Total number of verification history records"
    )
    submission_id: str | UUID = Field(..., description="Certificate submission ID")


class ManualVerificationRequestBody(BaseModel):
    """Request schema for manual verification"""

    submission_id: str | UUID = Field(..., description="Certificate submission ID")
    schedule_id: str | UUID = Field(..., description="Program requirement schedule ID")
    status: str = Field(
        ...,
        description="Verification status",
    )
    comments: Optional[str] = Field(
        None, description="Verification comments", max_length=1000
    )

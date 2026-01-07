from typing import Optional
from uuid import UUID
from fastapi import UploadFile
from fastapi import File
from pydantic import Field, ConfigDict

from app.schemas.camel_base_model import CamelCaseBaseModel as BaseModel


class StudentRequirementWithSubmissionResponse(BaseModel):
    """Response schema for student requirements with submission status"""

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

    model_config = ConfigDict(from_attributes=True)


class RequirementSubmissionRequest(BaseModel):
    """Schema for student certificate submission request"""

    schedule_id: str | UUID = Field(..., description="Program requirement schedule ID")
    requirement_id: str | UUID = Field(..., description="Program requirement ID")
    cert_type_id: str | UUID = Field(..., description="Certificate type ID")
    program_id: str | UUID = Field(..., description="Program ID")
    submission_id: Optional[str | UUID] = Field(
        None, description="Existing submission ID (for updates)"
    )
    file: UploadFile = File(..., description="Certificate file to upload")
    model_config = {"extra": "forbid"}

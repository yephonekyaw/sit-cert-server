from enum import Enum
from pydantic import Field
from typing import List, Optional

from app.schemas.camel_base_model import CamelCaseBaseModel


class VerificationDecision(str, Enum):
    APPROVE = "APPROVE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECT = "REJECT"


class PyMuPDFMetadata(CamelCaseBaseModel):
    format: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = Field(None, alias="creationDate")
    mod_date: Optional[str] = Field(None, alias="modDate")
    trapped: Optional[str] = None
    encryption: Optional[str] = None


class DocExtractionResult(CamelCaseBaseModel):
    method: str = Field(..., description="The method used for text extraction")
    pages: int = Field(..., description="Number of pages processed")
    text: str = Field(..., description="Extracted text from the document")
    confidence: Optional[float] = Field(
        None, description="Average confidence score of the extraction"
    )
    metadata: Optional[PyMuPDFMetadata] = Field(
        None, description="Metadata extracted from the document"
    )


class CitiCertificateStructuredOutput(CamelCaseBaseModel):
    student_name: str = Field(description="Full name of the person certified")
    record_id: str = Field(description="The unique Record ID number")
    verification_url: str = Field(
        description="The full URL starting with www.citiprogram.org/verify/"
    )
    expiration_date: str = Field(description="The expiration date, or N/A")
    curriculum_group: str = Field(description="The curriculum group name")
    course_learner_group: str = Field(description="The course learner group name")
    university_name: str = Field(description="The university name")
    generated_on: str = Field(description="The date the certificate was generated")


class Verdict(CamelCaseBaseModel):
    decision: VerificationDecision
    comments: List[str] = Field(
        ["Nothing suspicious found."], description="Verifier comments"
    )

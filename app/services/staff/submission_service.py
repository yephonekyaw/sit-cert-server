from typing import Dict, Sequence

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.utils.logging import get_logger
from app.db.models import (
    CertificateSubmission,
    Student,
    ProgramRequirement,
    ProgramRequirementSchedule,
    VerificationHistory,
    SubmissionStatus,
    VerificationType,
)
from app.db.session import get_sync_session
from app.schemas.staff.submission_schemas import (
    GetListOfSubmissions,
    StudentSubmissionItem,
    SubmissionRelatedDate,
    VerificationHistoryResponse,
    VerificationHistoryListResponse,
    ManualVerificationRequestBody,
)

logger = get_logger()


class SubmissionService:
    """Service provider for submission-related business logic and database operations"""

    def __init__(self, db_session: Session):
        self.db = db_session

    async def get_all_submissions_by_schedule_id(
        self, schedule_id: str
    ) -> GetListOfSubmissions:
        """Get all student submissions (submitted and unsubmitted) for a specific schedule"""
        try:
            # Validate schedule exists and load related data
            schedule = await self._validate_schedule_exists(schedule_id)

            # Get common submission related data
            submission_related_data = self._create_submission_related_data(schedule)

            # Get all students for this schedule
            students = await self._fetch_students_for_schedule(schedule)

            # Load all submissions for this schedule in a single query
            submissions_dict = await self._fetch_submissions_by_schedule(schedule)

            # Separate submitted and unsubmitted students using dictionary lookup
            submitted_submissions = []
            unsubmitted_submissions = []

            for student in students:
                submission = submissions_dict.get(student.id)

                if submission:
                    # Student has submitted
                    student_item = self._transform_student_to_submission_item(
                        student, submission
                    )
                    submitted_submissions.append(student_item)
                else:
                    # Student has not submitted
                    student_item = self._transform_student_to_submission_item(
                        student, None
                    )
                    unsubmitted_submissions.append(student_item)

            return GetListOfSubmissions(
                submitted_submissions=submitted_submissions,
                unsubmitted_submissions=unsubmitted_submissions,
                submission_related_data=submission_related_data,
            )
        except (ValueError, Exception) as e:
            raise e

    async def get_verification_history_by_submission_id(
        self, submission_id: str
    ) -> VerificationHistoryListResponse:
        """Get verification history for a specific certificate submission"""
        try:
            # Validate submission exists
            await self.get_submission_by_id(submission_id)

            # Get verification history
            history_records = await self._fetch_verification_history(submission_id)

            # Transform to response format
            history_responses = [
                self._transform_verification_history_to_response(record)
                for record in history_records
            ]

            return VerificationHistoryListResponse(
                verification_history=history_responses,
                total_count=len(history_responses),
                submission_id=submission_id,
            )

        except (ValueError, Exception) as e:
            raise e

    async def create_manual_verification(
        self,
        verification_data: ManualVerificationRequestBody,
        verifier_id: str,
    ) -> VerificationHistoryResponse:
        """Create a new manual verification history record for a certificate submission"""
        try:
            # Get current submission to determine old status
            current_submission = await self.get_submission_by_id(
                str(verification_data.submission_id)
            )

            # Map verification status to submission status
            status_mapping = {
                "approved": SubmissionStatus.APPROVED,
                "rejected": SubmissionStatus.REJECTED,
            }

            if verification_data.status not in status_mapping:
                raise ValueError("INVALID_VERIFICATION_STATUS")

            new_status = status_mapping[verification_data.status]
            old_status = current_submission.submission_status

            # Validate status change
            if old_status == new_status:
                raise ValueError("OLD_STATUS_SAME_AS_NEW_STATUS")

            # Create verification history record
            new_verification = VerificationHistory(
                submission_id=verification_data.submission_id,
                verifier_id=verifier_id,
                verification_type=VerificationType.MANUAL,
                old_status=old_status,
                new_status=new_status,
                comments=verification_data.comments,
            )

            # Save verification history and update submission status in a single transaction
            self.db.add(new_verification)
            current_submission.submission_status = new_status
            self.db.commit()
            self.db.refresh(new_verification)

            return self._transform_verification_history_to_response(new_verification)

        except (ValueError, Exception) as e:
            raise e

    async def get_submission_by_id(self, submission_id: str) -> CertificateSubmission:
        submission = (
            self.db.execute(
                select(CertificateSubmission).where(
                    CertificateSubmission.id == submission_id
                )
            )
        ).scalar_one_or_none()

        if not submission:
            raise ValueError("CERTIFICATE_SUBMISSION_NOT_FOUND")

        return submission

    def _create_submission_related_data(
        self, schedule: ProgramRequirementSchedule
    ) -> SubmissionRelatedDate:
        """Create common submission related data from schedule"""
        requirement = schedule.program_requirement
        program = requirement.program
        cert_type = requirement.certificate_type
        academic_year = schedule.academic_year

        return SubmissionRelatedDate(
            # Schedule data
            schedule_id=str(schedule.id),
            submission_deadline=schedule.submission_deadline.isoformat(),
            # Requirement data
            requirement_id=str(requirement.id),
            requirement_name=requirement.name,
            target_year=requirement.target_year,
            is_mandatory=requirement.is_mandatory,
            special_instruction=requirement.special_instruction,
            # Program data
            program_id=str(program.id),
            program_code=program.program_code,
            program_name=program.program_name,
            # Certificate type data
            cert_type_id=str(cert_type.id),
            cert_code=cert_type.cert_code,
            cert_name=cert_type.cert_name,
            cert_description=cert_type.description,
            # Academic year data
            year_code=academic_year.year_code,
        )

    async def _fetch_students_for_schedule(
        self, schedule: ProgramRequirementSchedule
    ) -> Sequence[Student]:
        """Fetch students who should submit for a given schedule"""
        students_query = (
            select(Student)
            .options(selectinload(Student.user), selectinload(Student.program))
            .where(Student.program_id == schedule.program_requirement.program_id)
            .where(Student.academic_year_id == schedule.academic_year_id)
            .order_by(Student.student_id)
        )

        result = self.db.execute(students_query)
        return result.scalars().all()

    async def _fetch_submissions_by_schedule(
        self, schedule: ProgramRequirementSchedule
    ) -> Dict[str, CertificateSubmission]:
        """Fetch all submissions for a schedule and return as dictionary with student_id as keys"""
        submissions_query = select(CertificateSubmission).where(
            and_(
                CertificateSubmission.requirement_schedule_id == schedule.id,
                CertificateSubmission.cert_type_id
                == schedule.program_requirement.cert_type_id,
            )
        )

        result = self.db.execute(submissions_query)
        submissions = result.scalars().all()

        # Create dictionary mapping student_id to CertificateSubmission
        return {submission.student_id: submission for submission in submissions}

    def _transform_student_to_submission_item(
        self, student: Student, submission: CertificateSubmission | None
    ) -> StudentSubmissionItem:
        """Transform student and submission data to StudentSubmissionItem"""
        user = student.user

        # Base student data
        item = StudentSubmissionItem(
            id=student.student_id,
            student_id=student.student_id,
            student_roll_number=str(student.user_id),
            student_name=f"{user.first_name} {user.last_name}",
            student_email=student.sit_email,
            student_enrollment_status=student.enrollment_status.value,
            # Submission data (None if not submitted)
            submission_id=None,
            file_object_name=None,
            filename=None,
            file_size=None,
            mime_type=None,
            submission_status=None,
            submission_timing=None,
            submitted_at=None,
            expired_at=None,
        )

        # If submission exists, fill in submission data
        if submission:
            item.submission_id = str(submission.id)
            item.file_object_name = submission.file_object_name
            item.filename = submission.filename
            item.file_size = submission.file_size
            item.mime_type = submission.mime_type
            item.submission_status = submission.submission_status.value
            item.submission_timing = (
                submission.submission_timing.value
                if submission.submission_timing
                else None
            )
            item.submitted_at = (
                submission.submitted_at.isoformat() if submission.submitted_at else None
            )
            item.expired_at = (
                submission.expired_at.isoformat() if submission.expired_at else None
            )

        return item

    async def _validate_schedule_exists(
        self, schedule_id: str
    ) -> ProgramRequirementSchedule:
        schedule = (
            self.db.execute(
                select(ProgramRequirementSchedule)
                .options(
                    selectinload(
                        ProgramRequirementSchedule.program_requirement
                    ).selectinload(ProgramRequirement.program),
                    selectinload(
                        ProgramRequirementSchedule.program_requirement
                    ).selectinload(ProgramRequirement.certificate_type),
                    selectinload(ProgramRequirementSchedule.academic_year),
                )
                .where(ProgramRequirementSchedule.id == schedule_id)
            )
        ).scalar_one_or_none()

        if not schedule:
            raise ValueError("Schedule not found")

        return schedule

    async def _fetch_verification_history(
        self, submission_id: str
    ) -> Sequence[VerificationHistory]:
        """Fetch verification history for a submission"""
        history_query = (
            select(VerificationHistory)
            .where(VerificationHistory.submission_id == submission_id)
            .order_by(VerificationHistory.created_at.desc())
        )

        history_result = self.db.execute(history_query)
        return history_result.scalars().all()

    def _transform_verification_history_to_response(
        self, record: VerificationHistory
    ) -> VerificationHistoryResponse:
        """Transform verification history ORM object to response schema"""
        return VerificationHistoryResponse(
            id=str(record.id),
            verification_type=record.verification_type,
            old_status=record.old_status,
            new_status=record.new_status,
            comments=record.comments,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def get_submission_service(
    db_session: Session = Depends(get_sync_session),
) -> SubmissionService:
    """Dependency function to get SubmissionService instance"""
    return SubmissionService(db_session)

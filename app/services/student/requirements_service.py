from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.db.models import (
    CertificateSubmission,
    CertificateType,
    ProgramRequirementSchedule,
    ProgramRequirement,
    Program,
    Student,
    SubmissionStatus,
    SubmissionTiming,
)
from app.schemas.student.requirement_schemas import (
    RequirementSubmissionRequest,
    StudentRequirementWithSubmissionResponse,
)
from app.services.minio_service import MinIOService
from app.utils.errors import BusinessLogicError
from app.utils.logging import get_logger
from app.utils.datetime_utils import naive_utc_now

logger = get_logger()


class RequirementsService:
    """Service for managing student certificate requirements and submissions"""

    def __init__(self, db_session: Session, minio_service: MinIOService):
        self.db = db_session
        self.minio = minio_service

    async def get_student_by_user_id(self, user_id: str) -> Student:
        """Get student record by user ID with validation"""
        student = (
            self.db.execute(select(Student).where(Student.user_id == user_id))
        ).scalar_one_or_none()

        if not student:
            raise BusinessLogicError("Student not found")

        return student

    async def get_student_requirements_with_submissions(
        self, student: Student
    ) -> List[StudentRequirementWithSubmissionResponse]:
        """Get all requirements for student with submission status"""
        # Get all requirement schedules for the student's program and academic year
        schedules_stmt = (
            select(ProgramRequirementSchedule)
            .join(ProgramRequirement)
            .join(Program)
            .join(CertificateType)
            .where(
                ProgramRequirement.program_id == student.program_id,
                ProgramRequirementSchedule.academic_year_id == student.academic_year_id,
            )
            .options(
                selectinload(
                    ProgramRequirementSchedule.program_requirement
                ).selectinload(ProgramRequirement.program),
                selectinload(
                    ProgramRequirementSchedule.program_requirement
                ).selectinload(ProgramRequirement.certificate_type),
                selectinload(
                    ProgramRequirementSchedule.certificate_submissions.and_(
                        CertificateSubmission.student_id == student.id
                    )
                ),
            )
        )

        schedules_result = self.db.execute(schedules_stmt)
        schedules = schedules_result.scalars().all()

        # Build response data
        requirements_data: List[StudentRequirementWithSubmissionResponse] = []
        for schedule in schedules:
            requirement = schedule.program_requirement
            program = requirement.program
            cert_type = requirement.certificate_type

            # Find existing submission for this student and requirement schedule
            submission = None
            for sub in schedule.certificate_submissions:
                if sub.student_id == student.id:
                    submission = sub
                    break

            requirement_data = StudentRequirementWithSubmissionResponse(
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
                # Submission data (empty if not submitted)
                submission_id=str(submission.id) if submission else None,
                file_object_name=submission.file_object_name if submission else None,
                filename=submission.filename if submission else None,
                file_size=submission.file_size if submission else None,
                mime_type=submission.mime_type if submission else None,
                submission_status=(
                    submission.submission_status.value if submission else None
                ),
                submission_timing=(
                    submission.submission_timing.value if submission else None
                ),
                submitted_at=(
                    submission.submitted_at.isoformat() if submission else None
                ),
                expired_at=(
                    submission.expired_at.isoformat()
                    if submission and submission.expired_at
                    else None
                ),
            )

            requirements_data.append(requirement_data)

        return requirements_data

    async def submit_certificate(
        self,
        student: Student,
        submission_data: RequirementSubmissionRequest,
    ) -> StudentRequirementWithSubmissionResponse:
        """Submit or update a certificate for verification"""

        # Validate certificate type exists
        cert_type = self.db.get(CertificateType, submission_data.cert_type_id)
        if not cert_type:
            raise BusinessLogicError("Certificate type not found")

        # Validate schedule exists and load related data
        schedule_stmt = (
            select(ProgramRequirementSchedule)
            .where(ProgramRequirementSchedule.id == submission_data.schedule_id)
            .options(
                selectinload(
                    ProgramRequirementSchedule.program_requirement
                ).selectinload(ProgramRequirement.program),
                selectinload(
                    ProgramRequirementSchedule.program_requirement
                ).selectinload(ProgramRequirement.certificate_type),
            )
        )
        schedule_result = self.db.execute(schedule_stmt)
        schedule = schedule_result.scalar_one_or_none()
        if not schedule:
            raise BusinessLogicError("Program requirement schedule not found")

        # Validate student permissions
        if (
            student.program_id != submission_data.program_id
            or student.academic_year_id != schedule.academic_year_id
        ):
            raise BusinessLogicError("Not enrolled in this program")

        # Handle submission logic (new vs edit)
        is_edit = bool(submission_data.submission_id)
        existing_submission = None

        if is_edit:
            existing_submission = (
                self.db.execute(
                    select(CertificateSubmission).where(
                        CertificateSubmission.id == submission_data.submission_id,
                        CertificateSubmission.student_id == student.id,
                        CertificateSubmission.requirement_schedule_id == schedule.id,
                    )
                )
            ).scalar_one_or_none()

            if not existing_submission:
                raise BusinessLogicError("Submission not found or access denied")

            if existing_submission.submission_status == SubmissionStatus.PENDING:
                raise BusinessLogicError("Submission under review - cannot edit")

            if existing_submission.submission_status == SubmissionStatus.APPROVED:
                raise BusinessLogicError("Approved submission cannot be edited")
        else:
            existing_submission = (
                self.db.execute(
                    select(CertificateSubmission).where(
                        CertificateSubmission.student_id == student.id,
                        CertificateSubmission.requirement_schedule_id == schedule.id,
                    )
                )
            ).scalar_one_or_none()

            if existing_submission:
                raise BusinessLogicError(
                    "Submission already exists for this requirement"
                )

        # File validation
        if not submission_data.file.filename:
            raise BusinessLogicError("File must have a valid name")

        file_content = await submission_data.file.read()
        file_size = len(file_content)
        await submission_data.file.seek(0)

        MAX_FILE_SIZE = 10 * 1024 * 1024
        if file_size > MAX_FILE_SIZE:
            raise BusinessLogicError("File too large (max 10MB)")

        SUPPORTED_MIME_TYPES = {
            "application/pdf",
        }

        if submission_data.file.content_type not in SUPPORTED_MIME_TYPES:
            raise BusinessLogicError("File type not supported")

        # Upload file
        upload_result = await self.minio.upload_file(
            file=submission_data.file,
            prefix=cert_type.cert_code,
            filename=submission_data.file.filename,
        )

        if not upload_result["success"]:
            raise BusinessLogicError("File upload failed")

        # Create or update submission
        if is_edit and existing_submission:
            old_file_object_name = existing_submission.file_object_name

            existing_submission.file_object_name = upload_result["object_name"]
            existing_submission.filename = submission_data.file.filename or "unknown"
            existing_submission.file_size = file_size
            existing_submission.mime_type = (
                submission_data.file.content_type or "application/octet-stream"
            )

            existing_submission.submission_status = SubmissionStatus.PENDING
            existing_submission.submitted_at = naive_utc_now()

            current_time = naive_utc_now()
            if current_time <= schedule.submission_deadline:
                existing_submission.submission_timing = SubmissionTiming.ON_TIME
            else:
                existing_submission.submission_timing = SubmissionTiming.LATE

            self.db.commit()

            try:
                await self.minio.delete_file(old_file_object_name)
            except Exception as e:
                logger.info(f"Old file cleanup failed: {old_file_object_name}")

            # Build and return complete response
            return self._build_submission_response(existing_submission, schedule)
        else:
            current_time = naive_utc_now()
            if current_time <= schedule.submission_deadline:
                timing = SubmissionTiming.ON_TIME
            else:
                timing = SubmissionTiming.LATE

            submission = CertificateSubmission(
                student_id=student.id,
                cert_type_id=submission_data.cert_type_id,
                requirement_schedule_id=submission_data.schedule_id,
                file_object_name=upload_result["object_name"],
                filename=submission_data.file.filename or "unknown",
                file_size=upload_result["size"],
                mime_type=upload_result["content_type"] or "application/octet-stream",
                submission_timing=timing,
            )

            self.db.add(submission)
            self.db.commit()

            # Build and return complete response
            return self._build_submission_response(submission, schedule)

    def _build_submission_response(
        self,
        submission: CertificateSubmission,
        schedule: ProgramRequirementSchedule,
    ) -> StudentRequirementWithSubmissionResponse:
        """Build complete submission response with all related data"""
        requirement = schedule.program_requirement
        program = requirement.program
        cert_type = requirement.certificate_type

        return StudentRequirementWithSubmissionResponse(
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
            # Submission data
            submission_id=str(submission.id),
            file_object_name=submission.file_object_name,
            filename=submission.filename,
            file_size=submission.file_size,
            mime_type=submission.mime_type,
            submission_status=submission.submission_status.value,
            submission_timing=submission.submission_timing.value,
            submitted_at=submission.submitted_at.isoformat(),
            expired_at=(
                submission.expired_at.isoformat() if submission.expired_at else None
            ),
        )

    async def validate_submission_ownership(
        self, submission_id: str, student_id: str
    ) -> None:
        """Validate that a submission belongs to the specified student"""
        submission = (
            self.db.execute(
                select(CertificateSubmission).where(
                    CertificateSubmission.id == submission_id
                )
            )
        ).scalar_one_or_none()

        if not submission:
            raise ValueError("Submission not found")

        if submission.student_id != student_id:
            raise ValueError("No permission to edit the submission")

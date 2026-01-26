from typing import List, Optional, Dict, Any
from datetime import timedelta

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.services.staff.dashboard_stats_service import get_dashboard_stats_service
from app.utils.datetime_utils import to_naive_utc
from app.utils.logging import get_logger
from app.db.models import (
    ProgramRequirement,
    AcademicYear,
    ProgramRequirementSchedule,
    Program,
    CertificateType,
    DashboardStats,
)
from app.db.session import get_sync_session
from app.schemas.staff.program_requirement_schedule_schemas import (
    GetProgramRequirementSchedulesItem,
    ProgramRequirementScheduleResponse,
    CreateProgramRequirementScheduleRequest,
    UpdateProgramRequirementScheduleRequest,
)

logger = get_logger()


class ProgramRequirementScheduleService:
    """Service provider for program requirement schedule-related business logic and database operations"""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.dashboard_stats_service = get_dashboard_stats_service(db_session)

    async def get_schedule_by_id(
        self, schedule_id: str
    ) -> Optional[ProgramRequirementSchedule]:
        """Get schedule by ID or return None if not found"""
        result = self.db.execute(
            select(ProgramRequirementSchedule).where(
                ProgramRequirementSchedule.id == schedule_id
            )
        )
        return result.scalar_one_or_none()

    async def get_program_requirement_by_id(
        self, program_requirement_id: str
    ) -> Optional[ProgramRequirement]:
        """Get program requirement by ID or return None if not found"""
        result = self.db.execute(
            select(ProgramRequirement).where(
                ProgramRequirement.id == program_requirement_id
            )
        )
        return result.scalar_one_or_none()

    async def get_academic_year_by_id(
        self, academic_year_id: str
    ) -> Optional[AcademicYear]:
        """Get academic year by ID or return None if not found"""
        result = self.db.execute(
            select(AcademicYear).where(AcademicYear.id == academic_year_id)
        )
        return result.scalar_one_or_none()

    # Validation Methods
    async def validate_program_requirement_active(
        self, program_requirement_id: str
    ) -> ProgramRequirement:
        """Validate that program requirement exists and is active"""
        program_requirement = await self.get_program_requirement_by_id(
            program_requirement_id
        )

        if not program_requirement:
            raise ValueError("Requirement not found")

        if not program_requirement.is_active:
            raise ValueError("Requirement not active")

        return program_requirement

    async def validate_academic_year_exists(
        self, academic_year_id: str
    ) -> AcademicYear:
        """Validate that academic year exists"""
        academic_year = await self.get_academic_year_by_id(academic_year_id)

        if not academic_year:
            raise ValueError("Academic year not found")

        return academic_year

    async def validate_deadline_within_academic_year(
        self,
        academic_year_id: str,
        submission_deadline,
        program_requirement_id: str,
    ) -> None:
        """Validate that submission deadline falls within the academic year considering program duration"""
        academic_year = await self.validate_academic_year_exists(academic_year_id)
        program_requirement = await self.get_program_requirement_by_id(
            program_requirement_id
        )

        if not program_requirement:
            raise ValueError("Requirement not found")

        # Get program to access duration_years
        program_query = select(Program).where(
            Program.id == program_requirement.program_id
        )
        program_result = self.db.execute(program_query)
        program = program_result.scalar_one_or_none()

        if not program:
            raise ValueError("Program not found")

        # Calculate the extended end date based on program duration
        extended_end_date = academic_year.start_date + timedelta(
            days=365 * program.duration_years
        )

        if not (academic_year.start_date <= submission_deadline <= extended_end_date):
            raise ValueError("Invalid deadline")

    async def check_schedule_exists(
        self, program_requirement_id: str, academic_year_id: str
    ) -> bool:
        """Check if schedule already exists for this combination"""
        result = self.db.execute(
            select(ProgramRequirementSchedule).where(
                ProgramRequirementSchedule.program_requirement_id
                == program_requirement_id,
                ProgramRequirementSchedule.academic_year_id == academic_year_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def check_schedule_exists_for_update(
        self,
        program_requirement_id: str,
        academic_year_id: str,
        current_schedule_id: str,
    ) -> bool:
        """Check if schedule already exists for this combination (excluding current schedule)"""
        result = self.db.execute(
            select(ProgramRequirementSchedule).where(
                ProgramRequirementSchedule.program_requirement_id
                == program_requirement_id,
                ProgramRequirementSchedule.academic_year_id == academic_year_id,
                ProgramRequirementSchedule.id != current_schedule_id,
            )
        )
        return result.scalar_one_or_none() is not None

    # Business Logic Methods
    async def create_schedule(
        self, schedule_data: CreateProgramRequirementScheduleRequest
    ) -> Dict[str, Any]:
        """Create a new program requirement schedule with validation"""
        try:
            schedule_data.submission_deadline = to_naive_utc(
                schedule_data.submission_deadline
            )

            # Validate program requirement is active
            program_requirement = await self.validate_program_requirement_active(
                (schedule_data.program_requirement_id)
            )

            # Validate academic year exists and deadline is within academic year considering program duration
            await self.validate_deadline_within_academic_year(
                schedule_data.academic_year_id,
                schedule_data.submission_deadline,
                schedule_data.program_requirement_id,
            )

            # Check if schedule already exists
            if await self.check_schedule_exists(
                schedule_data.program_requirement_id,
                schedule_data.academic_year_id,
            ):
                raise ValueError("Schedule already exists")

            # Use grace_period_days from request or default from program requirement
            grace_period_days = (
                schedule_data.grace_period_days
                if schedule_data.grace_period_days is not None
                else program_requirement.grace_period_days
            )

            # Use notification_days_before_deadline from request or default from program requirement
            notification_days = (
                schedule_data.notification_days_before_deadline
                if schedule_data.notification_days_before_deadline is not None
                else program_requirement.notification_days_before_deadline
            )

            # Calculate derived fields
            grace_period_deadline = schedule_data.submission_deadline + timedelta(
                days=grace_period_days
            )
            start_notify_at = schedule_data.submission_deadline - timedelta(
                days=notification_days
            )

            # Create new schedule
            new_schedule = ProgramRequirementSchedule(
                program_requirement_id=schedule_data.program_requirement_id,
                academic_year_id=schedule_data.academic_year_id,
                submission_deadline=schedule_data.submission_deadline,
                grace_period_deadline=grace_period_deadline,
                start_notify_at=start_notify_at,
            )

            self.db.add(new_schedule)
            self.db.commit()
            self.db.refresh(new_schedule)

            # Create corresponding dashboard stats record
            await self.dashboard_stats_service.create_dashboard_stats_by_schedule_id(
                schedule_id=new_schedule.id  # type: ignore
            )

            logger.info(f"Created new program requirement schedule: {new_schedule.id}")
            return self._create_schedule_response(new_schedule)

        except IntegrityError as e:
            logger.warning(f"Integrity error creating schedule: {str(e)}")
            raise ValueError("Database integrity error")
        except Exception as e:
            raise e

    async def update_schedule(
        self,
        schedule_id: str,
        schedule_data: UpdateProgramRequirementScheduleRequest,
    ) -> Dict[str, Any]:
        """Update an existing program requirement schedule with validation"""
        try:
            schedule_data.submission_deadline = to_naive_utc(
                schedule_data.submission_deadline
            )

            # Get existing schedule
            existing_schedule = await self.get_schedule_by_id(schedule_id)
            if not existing_schedule:
                raise ValueError("Schedule not found")

            # Validate that program_requirement_id matches (cannot be modified)
            if (
                existing_schedule.program_requirement_id
                != schedule_data.program_requirement_id
            ):
                raise ValueError("Invalid program requirement ID")

            # Validate program requirement is still active
            program_requirement = await self.validate_program_requirement_active(
                schedule_data.program_requirement_id
            )

            # Validate academic year exists and deadline is within academic year considering program duration
            await self.validate_deadline_within_academic_year(
                schedule_data.academic_year_id,
                schedule_data.submission_deadline,
                schedule_data.program_requirement_id,
            )

            # Check if schedule already exists for new academic year (excluding current)
            if schedule_data.academic_year_id != existing_schedule.academic_year_id:
                if await self.check_schedule_exists_for_update(
                    schedule_data.program_requirement_id,
                    schedule_data.academic_year_id,
                    schedule_id,
                ):
                    raise ValueError("Schedule already exists")

            # Use grace_period_days from request or default from program requirement
            grace_period_days = (
                schedule_data.grace_period_days
                if schedule_data.grace_period_days is not None
                else program_requirement.grace_period_days
            )

            # Use notification_days_before_deadline from request or default from program requirement
            notification_days = (
                schedule_data.notification_days_before_deadline
                if schedule_data.notification_days_before_deadline is not None
                else program_requirement.notification_days_before_deadline
            )

            # Calculate derived fields
            grace_period_deadline = schedule_data.submission_deadline + timedelta(
                days=grace_period_days
            )
            start_notify_at = schedule_data.submission_deadline - timedelta(
                days=notification_days
            )

            # Update schedule fields
            existing_schedule.academic_year_id = schedule_data.academic_year_id  # type: ignore
            existing_schedule.submission_deadline = schedule_data.submission_deadline
            existing_schedule.grace_period_deadline = grace_period_deadline
            existing_schedule.start_notify_at = start_notify_at

            self.db.commit()
            self.db.refresh(existing_schedule)

            logger.info(f"Updated program requirement schedule: {existing_schedule.id}")
            return self._create_schedule_response(existing_schedule)

        except IntegrityError as e:
            logger.warning(f"Integrity error updating schedule: {str(e)}")
            raise ValueError("Database integrity error")
        except Exception as e:
            raise e

    async def get_all_schedules_with_details(self) -> List[Dict[str, Any]]:
        """Get all program requirement schedules with comprehensive related data"""
        try:
            # Complex query with all necessary joins
            query = (
                select(
                    ProgramRequirementSchedule,
                    Program.id.label("program_id"),
                    Program.program_code,
                    Program.program_name,
                    CertificateType.id.label("cert_id"),
                    CertificateType.cert_code,
                    CertificateType.cert_name,
                    AcademicYear.id.label("academic_year_id"),
                    AcademicYear.year_code.label("academic_year"),
                    ProgramRequirement.name.label("requirement_name"),
                    ProgramRequirement.target_year,
                    ProgramRequirement.is_mandatory,
                    DashboardStats.total_submissions_required,
                    DashboardStats.submitted_count,
                    DashboardStats.approved_count,
                    DashboardStats.rejected_count,
                    DashboardStats.pending_count,
                    DashboardStats.manual_review_count,
                    DashboardStats.not_submitted_count,
                    DashboardStats.on_time_submissions,
                    DashboardStats.late_submissions,
                    DashboardStats.overdue_count,
                )
                .select_from(ProgramRequirementSchedule)
                .join(
                    ProgramRequirement,
                    ProgramRequirementSchedule.program_requirement_id
                    == ProgramRequirement.id,
                )
                .join(Program, ProgramRequirement.program_id == Program.id)
                .join(
                    CertificateType,
                    ProgramRequirement.cert_type_id == CertificateType.id,
                )
                .join(
                    AcademicYear,
                    ProgramRequirementSchedule.academic_year_id == AcademicYear.id,
                )
                .outerjoin(
                    DashboardStats,
                    DashboardStats.requirement_schedule_id
                    == ProgramRequirementSchedule.id,
                )
                .order_by(
                    Program.program_code,
                    AcademicYear.year_code,
                    ProgramRequirementSchedule.submission_deadline,
                )
            )

            result = self.db.execute(query)
            rows = result.fetchall()

            # Transform results into response format
            schedule_items = []

            for row in rows:
                schedule = row[0]  # ProgramRequirementSchedule object

                schedule_item = GetProgramRequirementSchedulesItem(
                    # Schedule core fields
                    id=schedule.id,
                    program_requirement_id=schedule.program_requirement_id,
                    submission_deadline=schedule.submission_deadline,
                    grace_period_deadline=schedule.grace_period_deadline,
                    start_notify_at=schedule.start_notify_at,
                    last_notified_at=schedule.last_notified_at,
                    created_at=schedule.created_at,
                    updated_at=schedule.updated_at,
                    # Program information
                    program_id=row.program_id,
                    program_code=row.program_code,
                    program_name=row.program_name,
                    # Certificate type information
                    cert_id=row.cert_id,
                    cert_code=row.cert_code,
                    cert_name=row.cert_name,
                    # Academic year information
                    academic_year_id=row.academic_year_id,
                    academic_year=row.academic_year,
                    # Program requirement information
                    requirement_name=row.requirement_name,
                    target_year=row.target_year,
                    is_mandatory=row.is_mandatory,
                    # Dashboard statistics (optional)
                    total_submissions_required=row.total_submissions_required,
                    submitted_count=row.submitted_count,
                    approved_count=row.approved_count,
                    rejected_count=row.rejected_count,
                    pending_count=row.pending_count,
                    manual_review_count=row.manual_review_count,
                    not_submitted_count=row.not_submitted_count,
                    on_time_submissions=row.on_time_submissions,
                    late_submissions=row.late_submissions,
                    overdue_count=row.overdue_count,
                )
                schedule_items.append(schedule_item.model_dump(by_alias=True))

            logger.info(
                f"Retrieved {len(schedule_items)} program requirement schedules"
            )

            return schedule_items

        except Exception as e:
            raise e

    # Helper Methods
    def _create_schedule_response(
        self, schedule: ProgramRequirementSchedule
    ) -> Dict[str, Any]:
        """Create standardized schedule response data"""

        schedule_response = ProgramRequirementScheduleResponse(
            id=schedule.id,  # type: ignore
            program_requirement_id=schedule.program_requirement_id,  # type: ignore
            academic_year_id=schedule.academic_year_id,  # type: ignore
            submission_deadline=schedule.submission_deadline,
            grace_period_deadline=schedule.grace_period_deadline,
            start_notify_at=schedule.start_notify_at,
            last_notified_at=schedule.last_notified_at,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
        )
        return schedule_response.model_dump(by_alias=True)

    @staticmethod
    def build_success_message(schedules_count: int) -> str:
        """Build descriptive success message for list operations"""
        return f"Retrieved {schedules_count} program requirement schedule{'s' if schedules_count != 1 else ''} successfully"


# Dependency injection for service provider
def get_program_requirement_schedule_service(
    db: Session = Depends(get_sync_session),
) -> ProgramRequirementScheduleService:
    """Dependency to provide ProgramRequirementScheduleService instance"""
    return ProgramRequirementScheduleService(db)

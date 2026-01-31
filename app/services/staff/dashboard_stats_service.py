import uuid

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models import (
    DashboardStats,
    ProgramRequirementSchedule,
    ProgramRequirement,
    Program,
    AcademicYear,
    CertificateSubmission,
)
from app.db.session import get_sync_session
from app.schemas.staff.dashboard_stats_schemas import DashboardStatsResponse
from app.services.staff.student_service import get_student_service
from app.utils.logging import get_logger
from app.utils.datetime_utils import naive_utc_now

logger = get_logger()


class DashboardStatsService:
    """Service for managing dashboard statistics."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.student_service = get_student_service(db_session)

    async def update_dashboard_stats_by_schedule(
        self,
        requirement_schedule_id: str,
        agent_verification_increment: int = 0,
        manual_verification_increment: int = 0,
    ) -> DashboardStats:
        """
        Update dashboard stats counts by requirement schedule ID.

        Args:
            requirement_schedule_id: The ID of the requirement schedule

        Returns:
            The updated DashboardStats instance

        Raises:
            ValueError: If no dashboard stats record is found for the schedule
        """

        submissions = (
            self.db.execute(
                select(
                    CertificateSubmission.submission_status,
                    CertificateSubmission.submission_timing,
                ).where(
                    CertificateSubmission.requirement_schedule_id
                    == requirement_schedule_id
                )
            )
        ).all()

        dashboard_stats = (
            self.db.execute(
                select(DashboardStats).where(
                    DashboardStats.requirement_schedule_id == requirement_schedule_id
                )
            )
        ).scalar_one_or_none()

        if not dashboard_stats:
            raise ValueError(
                f"Dashboard stats for schedule {requirement_schedule_id} not found"
            )

        stats: dict[str, int] = {}
        for submission in submissions:
            status, timing = submission
            status_key = f"{status.value.lower()}_count"
            timing_key = f"{timing.value.lower()}_submissions"
            stats[status_key] = stats.get(status_key, 0) + 1
            stats[timing_key] = stats.get(timing_key, 0) + 1

        dashboard_stats.submitted_count = len(submissions)
        dashboard_stats.approved_count = stats.get("approved_count", 0)
        dashboard_stats.rejected_count = stats.get("rejected_count", 0)
        dashboard_stats.pending_count = stats.get("pending_count", 0)
        dashboard_stats.manual_review_count = stats.get("manual_review_count", 0)
        dashboard_stats.on_time_submissions = stats.get("on_time_submissions", 0)
        dashboard_stats.late_submissions = stats.get("late_submissions", 0)
        dashboard_stats.overdue_submissions = stats.get("overdue_submissions", 0)
        dashboard_stats.not_submitted_count = (
            dashboard_stats.total_submissions_required - len(submissions)
        )
        dashboard_stats.agent_verification_count += agent_verification_increment
        dashboard_stats.manual_verification_count += manual_verification_increment
        dashboard_stats.last_calculated_at = naive_utc_now()

        self.db.commit()
        self.db.refresh(dashboard_stats)

        logger.info(
            f"Recalculated dashboard stats for schedule {requirement_schedule_id}"
        )

        return dashboard_stats

    def get_dashboard_stats_by_schedule(
        self, requirement_schedule_id: str
    ) -> DashboardStatsResponse:
        """
        Get dashboard stats by requirement schedule ID.

        Args:
            requirement_schedule_id: The ID of the requirement schedule

        Returns:
            The DashboardStatsResponse instance

        Raises:
            ValueError: If no dashboard stats record is found for the schedule
        """
        result = self.db.execute(
            select(DashboardStats).where(
                DashboardStats.requirement_schedule_id == requirement_schedule_id
            )
        )
        dashboard_stats = result.scalar_one_or_none()

        if not dashboard_stats:
            raise ValueError(
                f"Dashboard stats for schedule {requirement_schedule_id} not found"
            )

        dashboard_stats_response = DashboardStatsResponse(
            id=str(dashboard_stats.id),
            requirement_schedule_id=str(dashboard_stats.requirement_schedule_id),
            program_id=str(dashboard_stats.program_id),
            academic_year_id=str(dashboard_stats.academic_year_id),
            cert_type_id=str(dashboard_stats.cert_type_id),
            total_submissions_required=dashboard_stats.total_submissions_required,
            submitted_count=dashboard_stats.submitted_count,
            approved_count=dashboard_stats.approved_count,
            rejected_count=dashboard_stats.rejected_count,
            pending_count=dashboard_stats.pending_count,
            manual_review_count=dashboard_stats.manual_review_count,
            not_submitted_count=dashboard_stats.not_submitted_count,
            on_time_submissions=dashboard_stats.on_time_submissions,
            late_submissions=dashboard_stats.late_submissions,
            overdue_submissions=dashboard_stats.overdue_submissions,
            manual_verification_count=dashboard_stats.manual_verification_count,
            agent_verification_count=dashboard_stats.agent_verification_count,
            last_calculated_at=dashboard_stats.last_calculated_at,
            created_at=dashboard_stats.created_at,
            updated_at=dashboard_stats.updated_at,
        )

        return dashboard_stats_response

    async def create_dashboard_stats_by_schedule_id(
        self, schedule_id: str
    ) -> DashboardStats:
        """
        Create dashboard stats for a given schedule ID by automatically determining
        all necessary information from database relationships.

        Args:
            schedule_id: The ID of the program requirement schedule

        Returns:
            The created DashboardStats instance

        Raises:
            ValueError: If schedule not found or required data is missing
        """
        # Get schedule with all related data in a single query
        query = (
            select(
                ProgramRequirementSchedule,
                ProgramRequirement.program_id,
                ProgramRequirement.cert_type_id,
                Program.program_code,
                AcademicYear.year_code,
            )
            .select_from(ProgramRequirementSchedule)
            .join(
                ProgramRequirement,
                ProgramRequirementSchedule.program_requirement_id
                == ProgramRequirement.id,
            )
            .join(Program, ProgramRequirement.program_id == Program.id)
            .join(
                AcademicYear,
                ProgramRequirementSchedule.academic_year_id == AcademicYear.id,
            )
            .where(ProgramRequirementSchedule.id == schedule_id)
        )

        result = self.db.execute(query)
        row = result.first()

        if not row:
            raise ValueError(
                f"Schedule with ID {schedule_id} not found or has missing related data"
            )

        schedule, program_id, cert_type_id, program_code, academic_year_code = row

        # Get total student count for this program and academic year
        total_submissions_required = (
            await self.student_service.get_active_student_count_by_program_and_year(
                program_code=program_code,
                academic_year_code=academic_year_code,
            )
        )

        # Create dashboard stats record
        dashboard_stats = DashboardStats(
            id=uuid.uuid4(),
            requirement_schedule_id=schedule.id,
            program_id=program_id,
            academic_year_id=schedule.academic_year_id,
            cert_type_id=cert_type_id,
            total_submissions_required=total_submissions_required,
            submitted_count=0,
            approved_count=0,
            rejected_count=0,
            pending_count=0,
            manual_review_count=0,
            not_submitted_count=total_submissions_required,
            on_time_submissions=0,
            late_submissions=0,
            overdue_submissions=0,
            manual_verification_count=0,
            agent_verification_count=0,
            last_calculated_at=naive_utc_now(),
        )

        self.db.add(dashboard_stats)
        self.db.commit()
        self.db.refresh(dashboard_stats)

        logger.info(f"Created dashboard stats for schedule {schedule_id}")

        return dashboard_stats


def get_dashboard_stats_service(
    db: Session = Depends(get_sync_session),
) -> DashboardStatsService:
    return DashboardStatsService(db)

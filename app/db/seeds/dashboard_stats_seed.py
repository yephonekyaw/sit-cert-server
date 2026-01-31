import uuid
from sqlalchemy.orm import Session
from sqlalchemy import delete, select

from app.db.models import (
    DashboardStats,
    ProgramRequirementSchedule,
)
from app.utils.logging import get_logger
from app.utils.datetime_utils import naive_utc_now

logger = get_logger()


def seed_dashboard_stats(db_session: Session):
    """Sync version: Seed dashboard stats data - clear existing and add new"""

    # Clear existing dashboard stats
    db_session.execute(delete(DashboardStats))

    # Get the program requirement schedule that was created in the schedules seed
    schedule_stmt = select(ProgramRequirementSchedule)
    schedule_result = db_session.execute(schedule_stmt)
    schedule = schedule_result.scalar_one_or_none()

    if not schedule:
        logger.error(
            "No program requirement schedule found. Make sure program requirement schedules are seeded first."
        )
        return

    program = schedule.program_requirement.program
    certificate_type = schedule.program_requirement.certificate_type

    if not program or not certificate_type:
        logger.error("Could not find program or certificate type for the schedule.")
        return

    total_students = 49
    submitted_count = 0
    approved_count = 0
    rejected_count = 0
    pending_count = 0
    manual_review_count = 0
    not_submitted_count = total_students - submitted_count
    on_time_submissions = 0
    late_submissions = 0
    overdue_submissions = 0
    manual_verification_count = 0
    agent_verification_count = 0

    dashboard_stats = DashboardStats(
        id=str(uuid.uuid4()),
        requirement_schedule_id=schedule.id,
        program_id=program.id,
        academic_year_id=schedule.academic_year_id,
        cert_type_id=certificate_type.id,
        total_submissions_required=total_students,
        submitted_count=submitted_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        pending_count=pending_count,
        manual_review_count=manual_review_count,
        not_submitted_count=not_submitted_count,
        on_time_submissions=on_time_submissions,
        late_submissions=late_submissions,
        overdue_submissions=overdue_submissions,
        manual_verification_count=manual_verification_count,
        agent_verification_count=agent_verification_count,
        last_calculated_at=naive_utc_now(),
    )

    db_session.add(dashboard_stats)
    db_session.commit()

    logger.info(
        f"Seeded dashboard stats for schedule {schedule.id} - "
        f"{program.program_code} {certificate_type.cert_code} (2023): "
        f"{total_students} students, {submitted_count} submitted, {approved_count} approved"
    )

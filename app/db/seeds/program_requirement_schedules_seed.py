import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import delete, select

from app.db.models import (
    ProgramRequirementSchedule,
    ProgramRequirement,
    AcademicYear,
    Program,
    CertificateType,
)
from app.utils.logging import get_logger
from app.utils.datetime_utils import from_bangkok_to_naive_utc

logger = get_logger()


def seed_program_requirement_schedules(db_session: Session):
    """Sync version: Seed program requirement schedules data - clear existing and add new"""

    # Clear existing program requirement schedules
    db_session.execute(delete(ProgramRequirementSchedule))

    # Get 2023 academic year
    academic_year_stmt = select(AcademicYear).where(AcademicYear.year_code == 2023)
    academic_year_result = db_session.execute(academic_year_stmt)
    academic_year_2023 = academic_year_result.scalar_one_or_none()

    if not academic_year_2023:
        logger.error(
            "Academic year 2023 not found. Make sure academic years are seeded first."
        )
        return

    # Get CITI Program requirement for Bc.CS program
    program_stmt = select(Program).where(Program.program_code == "Bc.CS")
    program_result = db_session.execute(program_stmt)
    bccs_program = program_result.scalar_one_or_none()

    if not bccs_program:
        logger.error("Bc.CS program not found. Make sure programs are seeded first.")
        return

    cert_type_stmt = select(CertificateType).where(
        CertificateType.cert_code == "citi_program_certificate"
    )
    cert_type_result = db_session.execute(cert_type_stmt)
    citi_cert_type = cert_type_result.scalar_one_or_none()

    if not citi_cert_type:
        logger.error("CITI Program certificate type not found.")
        return

    requirement_stmt = select(ProgramRequirement).where(
        ProgramRequirement.program_id == bccs_program.id,
        ProgramRequirement.cert_type_id == citi_cert_type.id,
        ProgramRequirement.target_year == 3,
    )
    requirement_result = db_session.execute(requirement_stmt)
    citi_requirement = requirement_result.scalar_one_or_none()

    if not citi_requirement:
        logger.error(
            "CITI Program requirement not found. Make sure program requirements are seeded first."
        )
        return

    # Create schedule for 2023 academic year
    # Deadline: November 30, 2023 at 11:59 PM (simplified for MSSQL)
    submission_deadline = from_bangkok_to_naive_utc(datetime(2026, 11, 30, 23, 59, 59))

    # Grace period: 7 days after deadline
    grace_period_deadline = submission_deadline + timedelta(
        days=citi_requirement.grace_period_days
    )

    # Start notifications 90 days before deadline
    start_notify_at = submission_deadline - timedelta(
        days=citi_requirement.notification_days_before_deadline
    )

    schedule = ProgramRequirementSchedule(
        id=str(uuid.uuid4()),
        program_requirement_id=citi_requirement.id,
        academic_year_id=academic_year_2023.id,
        submission_deadline=submission_deadline,
        grace_period_deadline=grace_period_deadline,
        start_notify_at=start_notify_at,
        last_notified_at=None,  # No notifications sent yet
    )

    db_session.add(schedule)
    db_session.commit()
    logger.info(
        "Seeded 1 program requirement schedule for CITI Program (2023 academic year)"
    )

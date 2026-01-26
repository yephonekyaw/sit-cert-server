import uuid
import asyncio
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Set, Tuple


from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload, Session

from app.celery import celery
from app.db.session import get_sync_session
from app.db.models import (
    ProgramRequirement,
    ProgramRequirementSchedule,
    AcademicYear,
)
from app.services.staff.dashboard_stats_service import get_dashboard_stats_service
from app.utils.logging import get_logger
from app.utils.datetime_utils import *


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def monthly_schedule_creator_task(self, request_id: str):
    """
    Monthly task to create new program requirement schedules based on active program requirements.

    Runs on the 1st of every month at midnight to:
    1. Find all active program requirements
    2. Calculate which academic year cohort each requirement applies to
    3. Filter requirements by effective date ranges
    4. Calculate deadline dates and schedule creation dates
    5. Create schedules for requirements that need to be created within the next 30 days

    Academic Year Logic:
    - Academic year runs August to May (e.g., Aug 2024 - May 2025 = Academic Year 2024)
    - target_year 1 = current freshmen, target_year 2 = sophomores, etc.
    - Student cohort year = current_academic_year - target_year + 1
    - Deadline academic year = student_cohort_year + target_year - 1

    Args:
        request_id: Request ID for tracking purposes
    """
    return asyncio.run(_async_monthly_schedule_creator(request_id))


async def _async_monthly_schedule_creator(request_id: str):
    logger = get_logger().bind(request_id=request_id)

    for db_session in get_sync_session():
        try:
            current_datetime = naive_utc_now()
            current_academic_year = _calculate_current_academic_year(current_datetime)

            logger.info(
                f"Starting monthly schedule creation task for academic year {current_academic_year}"
            )

            # Get all active program requirements with related data
            program_requirements = await _get_active_program_requirements(db_session)

            if not program_requirements:
                logger.info("No active program requirements found")
                return {"status": "success"}

            # Get existing academic years for efficient lookups
            academic_years_map = await _get_academic_years_map(db_session)

            # Get existing schedules to avoid duplicates
            existing_schedules = await _get_existing_schedules_map(
                db_session, program_requirements
            )

            # Process each program requirement
            processed_count = 0
            created_count = 0
            skipped_count = 0

            schedules_to_create = []

            for requirement in program_requirements:
                try:
                    processed_count += 1

                    # Calculate student cohort year for this requirement
                    student_cohort_year = (
                        current_academic_year - requirement.target_year + 1
                    )

                    # Check if requirement is effective for this cohort
                    if not _is_requirement_effective(requirement, student_cohort_year):
                        skipped_count += 1
                        continue

                    # Check if we already created a schedule for this requirement and student cohort
                    schedule_key = (requirement.id, student_cohort_year)
                    if schedule_key in existing_schedules:
                        skipped_count += 1
                        continue

                    # Check if we should create a schedule based on last_recurrence_at
                    if _should_skip_based_on_recurrence(
                        requirement, student_cohort_year
                    ):
                        skipped_count += 1
                        continue

                    # Calculate deadline academic year for the actual deadline
                    deadline_academic_year = (
                        student_cohort_year + requirement.target_year - 1
                    )

                    # Calculate when the schedule should be created
                    schedule_creation_date = _calculate_schedule_creation_date(
                        requirement, deadline_academic_year
                    )

                    # Check if creation date is within the next 30 days
                    days_until_creation = (
                        schedule_creation_date.date() - current_datetime.date()
                    ).days

                    if not (0 <= days_until_creation <= 30):
                        skipped_count += 1
                        continue

                    # Get or create academic year record for STUDENT COHORT YEAR (not deadline year)
                    academic_year = await _get_or_create_academic_year(
                        db_session, student_cohort_year, academic_years_map
                    )

                    # Calculate schedule deadlines using the actual deadline year
                    deadline_datetime = _calculate_deadline_datetime(
                        requirement, deadline_academic_year
                    )
                    grace_deadline = deadline_datetime + timedelta(
                        days=requirement.grace_period_days
                    )

                    # Calculate notification start date
                    notify_start_date = deadline_datetime - timedelta(
                        days=requirement.notification_days_before_deadline
                    )

                    # Prepare schedule data
                    # All datetime fields are already in UTC from our timezone-aware calculations
                    schedule_data = {
                        "id": uuid.uuid4(),
                        "program_requirement_id": requirement.id,
                        "academic_year_id": academic_year.id,
                        "submission_deadline": deadline_datetime,  # UTC
                        "grace_period_deadline": grace_deadline,  # UTC
                        "start_notify_at": notify_start_date,  # UTC
                        "last_notified_at": None,
                    }

                    schedules_to_create.append(schedule_data)

                except Exception as e:
                    logger.error(
                        f"Error processing requirement {requirement.id if requirement else None}: {str(e)}"
                    )
                    continue

            # Create all schedules in batch
            if schedules_to_create:
                # Create ProgramRequirementSchedule objects
                created_schedules = [
                    ProgramRequirementSchedule(**data) for data in schedules_to_create
                ]
                db_session.add_all(created_schedules)
                db_session.commit()
                created_count = len(created_schedules)

                # Lookup dictionaries
                requirement_lookup = {req.id: req for req in program_requirements}
                academic_year_ids = {
                    data["academic_year_id"] for data in schedules_to_create
                }
                academic_years = (
                    db_session.execute(
                        select(AcademicYear).where(
                            AcademicYear.id.in_(academic_year_ids)
                        )
                    )
                    .scalars()
                    .all()
                )
                academic_year_lookup = {ay.id: ay for ay in academic_years}

                dashboard_service = get_dashboard_stats_service(db_session)

                processed_requirements_data = {}

                for schedule_data in schedules_to_create:
                    req_id = schedule_data["program_requirement_id"]
                    requirement = requirement_lookup.get(req_id)
                    academic_year = academic_year_lookup.get(
                        schedule_data["academic_year_id"]
                    )

                    if not academic_year:
                        logger.error(
                            f"Academic year not found for schedule {schedule_data['academic_year_id']} requirement {req_id}"
                        )
                        continue

                    # Dashboard stats
                    await dashboard_service.create_dashboard_stats_by_schedule_id(
                        schedule_data["id"]
                    )

                    # Last recurrence
                    processed_requirements_data[req_id] = (
                        requirement,
                        academic_year.year_code,
                    )

                # Update last_recurrence_at for all processed requirements
                await _update_last_recurrence_timestamps(
                    db_session, processed_requirements_data
                )

            logger.info(
                f"Monthly schedule creation task completed: processed {processed_count}, created {created_count}, skipped {skipped_count}"
            )

            return {"status": "success"}

        except Exception as e:
            logger.error(f"Monthly schedule creator task exception: {str(e)}")
            return {"status": "error", "message": str(e)}


def _calculate_current_academic_year(current_datetime: datetime) -> int:
    """
    Calculate the current academic year based on the date.
    Academic year runs from August to May.

    Examples:
    - January 2025 -> Academic Year 2024 (Aug 2024 - May 2025)
    - August 2024 -> Academic Year 2024 (Aug 2024 - May 2025)
    - July 2024 -> Academic Year 2023 (Aug 2023 - May 2024)
    """
    if current_datetime.month >= 8:  # August or later
        return current_datetime.year
    else:  # Before August
        return current_datetime.year - 1


async def _get_active_program_requirements(
    db_session: Session,
) -> List[ProgramRequirement]:
    """Get all active program requirements with related data."""
    result = db_session.execute(
        select(ProgramRequirement)
        .options(selectinload(ProgramRequirement.program))
        .where(
            and_(
                ProgramRequirement.is_active == True,
                ProgramRequirement.months_before_deadline.isnot(None),
            )
        )
        .order_by(ProgramRequirement.program_id, ProgramRequirement.target_year)
    )
    return list(result.scalars().all())


async def _get_academic_years_map(db_session: Session) -> Dict[int, AcademicYear]:
    """Get all academic years for efficient lookups."""
    result = db_session.execute(select(AcademicYear))
    academic_years = result.scalars().all()
    return {ay.year_code: ay for ay in academic_years}


async def _get_existing_schedules_map(
    db_session: Session, requirements: List[ProgramRequirement]
) -> Set[Tuple[str, int]]:
    """Get existing schedules to avoid duplicates. Key is (requirement_id, student_cohort_year)."""
    requirement_ids = [req.id for req in requirements]

    if not requirement_ids:
        return set()

    result = db_session.execute(
        select(
            ProgramRequirementSchedule.program_requirement_id,
            AcademicYear.year_code,  # This is the student cohort year
        )
        .join(
            AcademicYear, ProgramRequirementSchedule.academic_year_id == AcademicYear.id
        )
        .where(ProgramRequirementSchedule.program_requirement_id.in_(requirement_ids))
    )

    return {(req_id, year_code) for req_id, year_code in result.fetchall()}


def _is_requirement_effective(
    requirement: ProgramRequirement, student_cohort_year: int
) -> bool:
    """Check if a requirement is effective for the given student cohort year."""
    if (
        requirement.effective_from_year is not None
        and student_cohort_year < requirement.effective_from_year
    ):
        return False
    if (
        requirement.effective_until_year is not None
        and student_cohort_year > requirement.effective_until_year
    ):
        return False
    return True


def _should_skip_based_on_recurrence(
    requirement: ProgramRequirement, student_cohort_year: int
) -> bool:
    """
    Check if we should skip creating a schedule based on last recurrence.

    Only compare the year to avoid issues when deadline month/day changes
    after schedules have been created for a cohort.
    """
    if not requirement.last_recurrence_at:
        return False

    # Only compare the year component to handle deadline date changes gracefully
    last_recurrence_year = requirement.last_recurrence_at.year

    # If we already processed this student cohort year, skip
    return last_recurrence_year == student_cohort_year


def _calculate_schedule_creation_date(
    requirement: ProgramRequirement, deadline_academic_year: int
) -> datetime:
    """Calculate when a schedule should be created."""
    # Get the deadline datetime
    deadline_datetime = _calculate_deadline_datetime(
        requirement, deadline_academic_year
    )

    # Subtract months_before_deadline
    creation_date = deadline_datetime - relativedelta(
        months=int(requirement.months_before_deadline or 1)
    )

    return creation_date


def _calculate_deadline_datetime(
    requirement: ProgramRequirement, deadline_academic_year: int
) -> datetime:
    """
    Calculate the actual deadline datetime for a requirement.

    Creates deadline in Bangkok timezone (for business logic) then converts to UTC for database storage.
    """
    # Extract month and day from the requirement deadline_date (year is always 2000)
    deadline_month = requirement.deadline_date.month
    deadline_day = requirement.deadline_date.day

    return from_bangkok_to_naive_utc(
        datetime(
            year=deadline_academic_year,
            month=deadline_month,
            day=deadline_day,
            hour=23,
            minute=59,
            second=59,
        )
    )


async def _get_or_create_academic_year(
    db_session: Session,
    year_code: int,
    academic_years_map: Dict[int, AcademicYear],
) -> AcademicYear:
    """Get existing academic year or create a new one."""
    if year_code in academic_years_map:
        return academic_years_map[year_code]

    # Create new academic year using Bangkok timezone then convert to UTC
    # Academic year runs from August 1 to May 31

    # Start: August 1 at 00:00:00 Bangkok time
    start_utc = from_bangkok_to_naive_utc(datetime(year_code, 8, 1, 0, 0, 0))

    # End: May 31 at 23:59:59 Bangkok time of the following year
    end_utc = from_bangkok_to_naive_utc(datetime(year_code + 1, 5, 31, 23, 59, 59))

    academic_year = AcademicYear(
        id=uuid.uuid4(),
        year_code=year_code,
        start_date=start_utc,
        end_date=end_utc,
        is_current=False,  # Will be updated separately if needed
    )

    db_session.add(academic_year)
    db_session.flush()  # Ensure it's available for foreign key references

    # Update cache
    academic_years_map[year_code] = academic_year

    return academic_year


async def _update_last_recurrence_timestamps(
    db_session: Session, processed_requirements_data: dict
):
    """
    Update last_recurrence_at for processed requirements.

    Store timestamp as January 1st of the student cohort year to handle
    deadline date changes gracefully while still tracking which cohorts
    have been processed.

    Args:
        processed_requirements_data: Dict mapping requirement_id to (requirement, student_cohort_year)
    """
    if not processed_requirements_data:
        return

    # Update last_recurrence_at for all processed requirements
    for req_id, (
        requirement,
        student_cohort_year,
    ) in processed_requirements_data.items():
        # Set last_recurrence_at to August 1st of the student cohort year
        # This way we only need to compare years, not specific dates

        recurrence_timestamp = to_naive_utc(
            datetime(
                year=student_cohort_year,
                month=8,
                day=1,
                hour=0,
                minute=0,
                second=0,
            )
        )
        requirement.last_recurrence_at = recurrence_timestamp

    db_session.commit()

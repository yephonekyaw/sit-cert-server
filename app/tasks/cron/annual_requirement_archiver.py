import asyncio
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, update

from app.celery import celery
from app.db.session import get_sync_session
from app.db.models import ProgramRequirement
from app.utils.logging import get_logger
from app.utils.datetime_utils import utc_now


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def annual_requirement_archiver_task(self, request_id: str):
    """
    Annual task to archive expired program requirements.

    Runs on the second Monday of August every year to:
    1. Calculate the current academic year
    2. Find all active program requirements where effective_until_year < current_academic_year
    3. Archive those requirements by setting is_active = False

    This task helps maintain data integrity by automatically archiving requirements
    that are no longer applicable to new student cohorts.

    Academic Year Logic:
    - Academic year runs August to May (e.g., Aug 2024 - May 2025 = Academic Year 2024)
    - Requirements with effective_until_year < current_academic_year are expired
    - Only active requirements (is_active = True) are considered for archiving

    Args:
        request_id: Request ID for tracking purposes
    """
    return asyncio.run(_async_annual_requirement_archiver(request_id))


async def _async_annual_requirement_archiver(request_id: str):
    logger = get_logger().bind(request_id=request_id)

    # Get database session
    for db_session in get_sync_session():
        try:
            current_datetime = utc_now()
            current_academic_year = _calculate_current_academic_year(current_datetime)

            logger.info(
                "Starting annual requirement archiver task",
                current_datetime=current_datetime.isoformat(),
                current_academic_year=current_academic_year,
                request_id=request_id,
            )

            # Find all active requirements that have expired
            expired_requirements = await _get_expired_requirements(
                db_session, current_academic_year
            )

            if not expired_requirements:
                logger.info("No expired requirements found to archive")
                return {
                    "status": "success",
                }

            # Archive expired requirements by setting is_active = False

            archived_count = await _archive_expired_requirements(
                db_session, expired_requirements
            )

            logger.info(
                "Annual requirement archiver task completed",
                archived_count=archived_count,
                current_academic_year=current_academic_year,
            )

            return {"status": "success", "message": f"Archived count: {archived_count}"}
        except Exception as e:
            logger.error(
                "Annual requirement archiver task exception",
                request_id=request_id,
                error=str(e),
                exc_info=True,
            )
            return {"status": "success", "message": str(e)}


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


async def _get_expired_requirements(
    db_session: Session, current_academic_year: int
) -> List[ProgramRequirement]:
    """
    Get all active program requirements that have expired.

    A requirement is considered expired if:
    1. It is currently active (is_active = True)
    2. It has an effective_until_year set
    3. The effective_until_year is less than the current academic year

    Args:
        db_session: Database session
        current_academic_year: Current academic year for comparison

    Returns:
        List of expired ProgramRequirement objects
    """
    result = db_session.execute(
        select(ProgramRequirement)
        .where(
            and_(
                ProgramRequirement.is_active == True,
                ProgramRequirement.effective_until_year.isnot(None),
                ProgramRequirement.effective_until_year < current_academic_year,
            )
        )
        .order_by(
            ProgramRequirement.program_id,
            ProgramRequirement.effective_until_year,
            ProgramRequirement.target_year,
        )
    )
    return list(result.scalars().all())


async def _archive_expired_requirements(
    db_session: Session, expired_requirements: List[ProgramRequirement]
) -> int:
    """
    Archive expired requirements by setting is_active = False.

    Uses a batch update for efficiency while maintaining audit trail.

    Args:
        db_session: Database session
        expired_requirements: List of requirements to archive

    Returns:
        Number of requirements archived
    """
    if not expired_requirements:
        return 0

    # Extract requirement IDs for batch update
    requirement_ids = [req.id for req in expired_requirements]

    # Perform batch update to set is_active = False
    result = db_session.execute(
        update(ProgramRequirement)
        .where(ProgramRequirement.id.in_(requirement_ids))
        .values(is_active=False)
    )

    # Commit the changes
    db_session.commit()

    # Return the number of updated rows
    return result.rowcount

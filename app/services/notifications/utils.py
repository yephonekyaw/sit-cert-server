from typing import List, Optional
from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload, Session
from sqlalchemy.future import select

from app.db.models import (
    Student,
    Staff,
    ProgramRequirementSchedule,
    CertificateSubmission,
    Program,
    SubmissionStatus,
)
from app.utils.logging import get_logger

logger = get_logger()


async def get_student_user_ids_for_requirement_schedule(
    db: Session, requirement_schedule_id: str
) -> List[str]:
    """
    Get user IDs of students who haven't submitted or whose submissions
    are not yet approved for a specific program requirement schedule.

    Args:
        db: Database session
        requirement_schedule_id: ID of the ProgramRequirementSchedule

    Returns:
        List of user IDs of students who need to submit or have non-approved submissions
    """
    try:
        # First get the requirement schedule to understand the program and academic year
        requirement_schedule_stmt = (
            select(ProgramRequirementSchedule)
            .where(ProgramRequirementSchedule.id == requirement_schedule_id)
            .options(selectinload(ProgramRequirementSchedule.program_requirement))
        )

        result = db.execute(requirement_schedule_stmt)
        requirement_schedule = result.scalar_one_or_none()

        if not requirement_schedule:
            logger.warning(
                f"ProgramRequirementSchedule not found: {requirement_schedule_id}"
            )
            return []

        program_id = requirement_schedule.program_requirement.program_id
        academic_year_id = requirement_schedule.academic_year_id

        # Get all students in the program for the academic year
        students_stmt = (
            select(Student)
            .where(
                and_(
                    Student.program_id == program_id,
                    Student.academic_year_id == academic_year_id,
                )
            )
            .options(selectinload(Student.user))
        )

        students_result = db.execute(students_stmt)
        all_students = students_result.scalars().all()

        # Get students who have approved submissions for this requirement schedule
        approved_submissions_stmt = select(CertificateSubmission.student_id).where(
            and_(
                CertificateSubmission.requirement_schedule_id
                == requirement_schedule_id,
                CertificateSubmission.submission_status == SubmissionStatus.APPROVED,
            )
        )

        approved_result = db.execute(approved_submissions_stmt)
        approved_student_ids = {row[0] for row in approved_result.fetchall()}

        # Filter out students who already have approved submissions
        target_student_user_ids = []
        for student in all_students:
            if student.id not in approved_student_ids:
                target_student_user_ids.append(student.user_id)

        logger.info(
            f"Found {len(target_student_user_ids)} students needing submission for requirement schedule {requirement_schedule_id}"
        )

        return target_student_user_ids

    except Exception as e:
        logger.error(
            f"Error getting student user IDs for requirement schedule {requirement_schedule_id}: {str(e)}",
            exc_info=True,
        )
        return []


async def get_all_staff_user_ids(db: Session) -> List[str]:
    """
    Get user IDs of all staff members.

    Args:
        db: Database session

    Returns:
        List of user IDs of staff members
    """
    try:
        rows = db.execute(select(Staff)).scalars().unique().all()
        staff_user_ids = [staff.user_id for staff in rows]

        return staff_user_ids

    except Exception as e:
        logger.error(
            f"Error getting staff user IDs: {str(e)}",
            exc_info=True,
        )
        return []


async def get_user_id_from_student_identifier(
    db: Session, identifier: str
) -> Optional[str]:
    """
    Get user_id from student identifier (student ID, student_id, or sit_email).

    Args:
        db: Database session
        identifier: Student ID (UUID string), student_id, or sit_email

    Returns:
        User ID if found, None otherwise
    """
    try:
        # Try to parse as UUID first (student.id)
        try:
            stmt = select(Student.user_id).where(Student.id == identifier)
            result = db.execute(stmt)
            user_id = result.scalar_one_or_none()
            if user_id:
                return user_id
        except ValueError:
            pass

        # Try as student_id or sit_email
        stmt = select(Student.user_id).where(
            or_(Student.student_id == identifier, Student.sit_email == identifier)
        )

        result = db.execute(stmt)
        user_id = result.scalar_one_or_none()

        if user_id:
            logger.info(f"Found user_id {user_id} for student identifier {identifier}")
        else:
            logger.warning(f"No student found for identifier {identifier}")

        return user_id

    except Exception as e:
        logger.error(
            f"Error getting user_id for student identifier {identifier}: {str(e)}",
            exc_info=True,
        )
        return None


async def get_user_id_from_staff_identifier(
    db: Session, identifier: str
) -> Optional[str]:
    """
    Get user_id from staff identifier (staff ID or employee_id).

    Args:
        db: Database session
        identifier: Staff ID (UUID string) or employee_id

    Returns:
        User ID if found, None otherwise
    """
    try:
        # Try to parse as UUID first (staff.id)
        try:
            stmt = select(Staff.user_id).where(Staff.id == identifier)
            result = db.execute(stmt)
            user_id = result.scalar_one_or_none()
            if user_id:
                return user_id
        except ValueError:
            pass

        # Try as employee_id
        stmt = select(Staff.user_id).where(Staff.employee_id == identifier)
        result = db.execute(stmt)
        user_id = result.scalar_one_or_none()

        if user_id:
            logger.info(f"Found user_id {user_id} for staff identifier {identifier}")
        else:
            logger.warning(f"No staff found for identifier {identifier}")

        return user_id

    except Exception as e:
        logger.error(
            f"Error getting user_id for staff identifier {identifier}: {str(e)}",
            exc_info=True,
        )
        return None


def create_notification_sync(
    request_id: str,
    notification_code: str,
    entity_id: str,
    actor_type: str,
    recipient_ids: List[str],
    actor_id: Optional[str] = None,
    scheduled_for: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    in_app_enabled: bool = True,
    line_app_enabled: bool = False,
    **metadata,
) -> None:
    """
    Create notification asynchronously via Celery task.

    Simple helper function to trigger notification creation without complex logic.

    Args:
        request_id: Request ID for tracking
        notification_code: Code identifying the notification type
        entity_id: UUID of the entity the notification is about
        actor_type: Type of actor triggering the notification
        recipient_ids: List of recipient UUIDs
        actor_id: Optional UUID of the actor
        scheduled_for: Optional datetime for scheduling
        expires_at: Optional datetime for expiration
        in_app_enabled: Whether in-app notifications are enabled
        line_app_enabled: Whether LINE notifications are enabled
        **metadata: Additional metadata for the notification

    Returns:
        str: Celery task ID
    """
    try:
        from app.tasks.background.notification_creation import create_notification_task

        task_args = {
            "request_id": request_id,
            "notification_code": notification_code,
            "entity_id": entity_id,
            "actor_type": actor_type,
            "recipient_ids": recipient_ids,
            "actor_id": actor_id,
            "scheduled_for": scheduled_for,
            "expires_at": expires_at,
            "in_app_enabled": in_app_enabled,
            "line_app_enabled": line_app_enabled,
            **metadata,
        }

        # Use Celery task for async processing
        create_notification_task.delay(**task_args)  # type: ignore

    except Exception as e:
        logger.error(
            "Failed to trigger notification creation",
            notification_code=notification_code,
            entity_id=str(entity_id),
            error=str(e),
            exc_info=True,
        )
        raise

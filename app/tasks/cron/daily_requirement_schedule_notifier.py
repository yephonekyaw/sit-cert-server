from datetime import datetime, timedelta
from typing import Any, List, Dict
import asyncio

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, update, func

from app.celery import celery
from app.db.session import get_sync_session
from app.db.models import (
    ProgramRequirementSchedule,
    ActorType,
)
from app.services.notifications.utils import (
    get_student_user_ids_for_requirement_schedule,
    create_notification_sync,
)
from app.utils.logging import get_logger
from app.utils.datetime_utils import naive_utc_now


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def daily_requirement_schedule_notifier_task(self, request_id: str):
    """
    Daily task to send requirement deadline notifications to students.

    Runs at 9:00 AM Bangkok time daily to:
    1. Find all active requirement schedules that need notifications
    2. Calculate days until deadline and determine notification frequency
    3. Send appropriate notifications based on timing rules

    Notification Rules:
    - > 90 days until deadline: No notifications
    - 30-90 days: Monthly reminders (reminder type)
    - 7-30 days: Weekly reminders (reminder type)
    - 1-7 days: Every 2 days warnings (warning type)
    - Deadline day: Warning notification (warning type)
    - Grace period (after deadline): Every 3 days late notifications (late type)
    - After grace period: Every 3 days overdue notifications (overdue type)
    - Stop 7 days after grace period ends

    Args:
        request_id: Request ID for tracking purposes
    """

    return asyncio.run(_async_daily_requirement_schedule_notifier(request_id))


async def _async_daily_requirement_schedule_notifier(request_id: str):
    logger = get_logger().bind(request_id=request_id)

    for db_session in get_sync_session():
        try:
            current_datetime = naive_utc_now()

            # Get all requirement schedules that might need notifications
            eligible_schedules = await _get_eligible_requirement_schedules(
                db_session, current_datetime
            )

            if not eligible_schedules:
                return {"status": "success"}

            processed_count = 0
            notifications_sent = 0

            for schedule in eligible_schedules:
                try:
                    processed_count += 1

                    # Calculate days until/past deadline
                    days_until_deadline = (
                        schedule.submission_deadline.date() - current_datetime.date()
                    ).days

                    days_until_grace_end = (
                        schedule.grace_period_deadline.date() - current_datetime.date()
                    ).days

                    # Determine if notification should be sent based on timing rules
                    notification_decision = _should_send_notification(
                        schedule,
                        days_until_deadline,
                        days_until_grace_end,
                        current_datetime,
                    )

                    if not notification_decision["should_send"]:
                        continue

                    # Get recipient student user IDs
                    recipient_ids = await get_student_user_ids_for_requirement_schedule(
                        db_session, schedule.id  # type: ignore
                    )

                    if not recipient_ids:
                        continue

                    # Create notification
                    expires_at = current_datetime + timedelta(days=15)

                    create_notification_sync(
                        request_id=request_id,
                        notification_code=notification_decision["notification_code"],
                        entity_id=schedule.id,  # type: ignore
                        actor_type=ActorType.SYSTEM.value,
                        recipient_ids=recipient_ids,
                        actor_id=None,
                        scheduled_for=None,
                        expires_at=expires_at,
                        in_app_enabled=True,
                        line_app_enabled=True,
                    )

                    # Update last_notified_at
                    await _update_last_notified_at(
                        db_session, schedule.id, current_datetime  # type: ignore
                    )

                    notifications_sent += 1

                except Exception as e:
                    logger.error(
                        "Error processing requirement schedule",
                        schedule_id=str(schedule.id) if schedule else None,
                        error=str(e),
                        exc_info=True,
                    )
                    continue

            logger.info(
                "Daily requirement notifier task completed",
                processed_count=processed_count,
                notifications_sent=notifications_sent,
            )

            return {"status": "success"}

        except Exception as e:
            logger.error(
                "Daily requirement notifier task exception",
                request_id=request_id,
                error=str(e),
                exc_info=True,
            )

            return {"status": "error", "message": str(e)}


async def _get_eligible_requirement_schedules(
    db_session: Session, current_datetime: datetime
) -> List[ProgramRequirementSchedule]:
    """
    Get requirement schedules that are eligible for notifications.

    Criteria:
    1. start_notify_at >= current_date (notification period has started)
    2. grace_period_deadline + 7 days >= current_date (within notification window)
    """
    result = db_session.execute(
        select(ProgramRequirementSchedule)
        .where(
            and_(
                # Notification period has started
                ProgramRequirementSchedule.start_notify_at <= current_datetime,
                # Still within notification window (7 days after grace period)
                ProgramRequirementSchedule.grace_period_deadline
                >= current_datetime - timedelta(days=7),
            )
        )
        .order_by(ProgramRequirementSchedule.submission_deadline)
    )
    return list(result.scalars().all())


def _should_send_notification(
    schedule: ProgramRequirementSchedule,
    days_until_deadline: int,
    days_until_grace_end: int,
    current_datetime: datetime,
) -> Dict[str, Any]:
    """
    Determine if a notification should be sent based on timing rules and last notification.

    Returns:
        Dict with 'should_send' boolean and 'notification_code' string
    """
    last_notified = schedule.last_notified_at
    days_since_last_notification = 0

    if last_notified:
        days_since_last_notification = (
            current_datetime.date() - last_notified.date()
        ).days

    # Rule 1: More than 90 days until deadline - no notifications
    if days_until_deadline > 90:
        return {"should_send": False, "notification_code": None}

    # Rule 2: 30-90 days until deadline - monthly reminders
    elif 30 <= days_until_deadline <= 90:
        should_send = last_notified is None or days_since_last_notification >= 30
        return {
            "should_send": should_send,
            "notification_code": "program_requirement_schedule_remind",
        }

    # Rule 3: 7-30 days until deadline - weekly reminders
    elif 7 <= days_until_deadline < 30:
        should_send = last_notified is None or days_since_last_notification >= 7
        return {
            "should_send": should_send,
            "notification_code": "program_requirement_schedule_remind",
        }

    # Rule 4: 1-7 days until deadline - every 2 days warnings
    elif 1 <= days_until_deadline < 7:
        should_send = last_notified is None or days_since_last_notification >= 2
        return {
            "should_send": should_send,
            "notification_code": "program_requirement_schedule_warn",
        }

    # Rule 5: Deadline day - warning
    elif days_until_deadline == 0:
        should_send = (
            last_notified is None or last_notified.date() != current_datetime.date()
        )
        return {
            "should_send": should_send,
            "notification_code": "program_requirement_schedule_warn",
        }

    # Rule 6: After deadline, within grace period - every 3 days late notifications
    elif days_until_deadline < 0 and days_until_grace_end >= 0:
        should_send = last_notified is None or days_since_last_notification >= 3
        return {
            "should_send": should_send,
            "notification_code": "program_requirement_schedule_late",
        }

    # Rule 7: After grace period, within 7 days - every 3 days overdue notifications
    elif days_until_grace_end < 0 and days_until_grace_end >= -7:
        should_send = last_notified is None or days_since_last_notification >= 3
        return {
            "should_send": should_send,
            "notification_code": "program_requirement_schedule_overdue",
        }

    # Rule 8: More than 7 days after grace period - stop notifications
    else:
        return {"should_send": False, "notification_code": None}


async def _update_last_notified_at(
    db_session: Session, schedule_id: str, current_datetime: datetime
):
    """Update the last_notified_at timestamp for a schedule."""
    db_session.execute(
        update(ProgramRequirementSchedule)
        .where(ProgramRequirementSchedule.id == schedule_id)
        .values(last_notified_at=current_datetime)
    )
    db_session.commit()

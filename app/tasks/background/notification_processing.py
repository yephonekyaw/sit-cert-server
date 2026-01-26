import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.celery import celery
from app.db.session import get_sync_session
from app.db.models import Notification, NotificationStatus
from app.utils.logging import get_logger
from app.utils.datetime_utils import naive_utc_now


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def process_notification_task(self, request_id: str, notification_id: str):
    """
    Celery task to process a notification and dispatch to channel-specific sending tasks.

    This task retrieves the notification, formats the content, and creates channel-specific
    sending tasks for each enabled recipient.

    Args:
        request_id: The request ID from the original HTTP request
        notification_id: UUID of the notification to process (as string)
    """
    return asyncio.run(_async_process_notification(request_id, notification_id))


async def _async_process_notification(request_id: str, notification_id: str):
    logger = get_logger().bind(request_id=request_id)

    for db_session in get_sync_session():
        try:
            # Get notification with all recipients
            result = db_session.execute(
                select(Notification)
                .options(
                    selectinload(Notification.recipients),
                    selectinload(Notification.notification_type),
                )
                .where(Notification.id == notification_id)
            )
            notification = result.scalar_one_or_none()

            if not notification:
                logger.error(f"Notification not found: {notification_id}")
                return {"status": "error", "message": "Notification not found"}

            # Check if notification has expired
            if notification.expires_at and notification.expires_at <= naive_utc_now():

                # Mark all pending recipients as expired
                for recipient in notification.recipients:
                    if recipient.status == NotificationStatus.PENDING:
                        recipient.status = NotificationStatus.EXPIRED

                db_session.commit()
                return {"status": "success", "message": "Marked expired"}

            # Process each recipient
            tasks_created = 0
            for recipient in notification.recipients:
                if recipient.status != NotificationStatus.PENDING:
                    continue

                # Create channel-specific sending tasks
                if recipient.in_app_enabled:
                    # For now, in-app notifications are immediately marked as delivered
                    # since they're just stored in the database
                    recipient.status = NotificationStatus.DELIVERED
                    recipient.delivered_at = naive_utc_now()
                    tasks_created += 1

                if recipient.line_app_enabled:
                    # Create LINE sending task
                    from app.tasks import send_line_notification_task

                    send_line_notification_task.delay(  # type: ignore
                        request_id=request_id,
                        notification_id=notification_id,
                        recipient_id=str(recipient.recipient_id),
                    )
                    tasks_created += 1

            db_session.commit()

            return {
                "status": "success",
                "message": f"Created {tasks_created} number of tasks",
            }

        except Exception as e:
            logger.error(
                f"Notification processing task exception for {notification_id}: {str(e)}"
            )

            return {
                "status": "error",
                "message": str(e),
            }

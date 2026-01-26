import asyncio
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload, Session

from app.celery import celery
from app.db.session import get_sync_session
from app.db.models import (
    NotificationRecipient,
    Notification,
    Student,
    User,
)
from app.services.notifications.registry import NotificationServiceRegistry
from app.services.line.line_webhook_service import LineWebhookService
from app.utils.logging import get_logger


@celery.task(bind=True, max_retries=5, default_retry_delay=120)
def send_line_notification_task(
    self, request_id: str, notification_id: str, recipient_id: str
):
    """
    Celery task to send a LINE notification to a specific recipient.

    This is a mock implementation for now. In the future, this will integrate
    with the actual LINE messaging API.

    Args:
        request_id: The request ID from the original HTTP request
        notification_id: UUID of the notification (as string)
        recipient_id: UUID of the recipient (as string)
    """
    return asyncio.run(
        _async_send_line_notification(request_id, notification_id, recipient_id)
    )


async def _async_send_line_notification(
    request_id: str, notification_id: str, recipient_id: str
):
    logger = get_logger().bind(request_id=request_id)

    for db_session in get_sync_session():
        try:

            # Get notification and recipient in a single query
            notification_result = db_session.execute(
                select(Notification, NotificationRecipient)
                .join(
                    NotificationRecipient,
                    Notification.id == NotificationRecipient.notification_id,
                )
                .options(selectinload(Notification.notification_type))
                .where(
                    and_(
                        Notification.id == notification_id,
                        NotificationRecipient.recipient_id == recipient_id,
                    )
                )
            )
            result_row = notification_result.first()
            if not result_row:
                logger.error(
                    f"Notification or recipient not found: {notification_id}, {recipient_id}"
                )
                return {
                    "status": "error",
                    "message": "Notification or recipient not found",
                }

            notification, recipient = result_row

            # Get formatted message content using NotificationServiceRegistry directly
            service = NotificationServiceRegistry.create_service(
                notification.notification_type.code, db_session
            )

            if not service:
                logger.warning(
                    f"No service found for notification code: {notification.notification_type.code}"
                )
                return {
                    "status": "success",
                    "message": f"No service found for notification code: {notification.notification_type.code}",
                }

            try:
                notification_data = await service.get_notification_data(
                    notification.entity_id, notification_id
                )
                message = await service.construct_message("line_app", notification_data)
            except Exception as e:
                logger.warning(
                    f"Failed to get notification data or construct message for {notification_id}: {str(e)}"
                )
                message = None

            if not message:
                logger.warning(
                    f"Failed to get notification message content for {notification_id}"
                )
                return {"status": "success"}

            # Validate recipient can receive LINE notifications
            if not _validate_line_recipient(db_session, recipient_id):
                logger.warning(
                    f"Recipient not configured for LINE notifications: {recipient_id}"
                )
                return {
                    "status": "success",
                    "message": "Recipient not configured for LINE notifications",
                }

            # Get recipient's LINE user ID
            line_user_id = _get_line_user_id(db_session, recipient_id)
            if not line_user_id:
                logger.warning(f"Recipient LINE user ID not found: {recipient_id}")
                return {
                    "status": "success",
                    "message": "Recipient LINE user ID not found",
                }

            # Send LINE notification using LineWebhookService
            line_success = await _send_line_notification(
                db_session=db_session,
                line_user_id=line_user_id,
                subject=message.get("subject", "Notification"),
                body=message.get("body", "You have a notification"),
                logger=logger,
            )

            if line_success:
                return {
                    "status": "success",
                    "channel": "line_app",
                }
            else:
                logger.warning(f"Failed to send LINE notification to {recipient_id}")
                return {
                    "status": "success",
                    "message": "Failed to send LINE notification",
                }

        except Exception as e:
            logger.error(
                f"Critical error in LINE notification task for {notification_id}/{recipient_id}: {str(e)}"
            )

            return {
                "status": "error",
                "message": str(e),
            }


def _validate_line_recipient(db_session: Session, recipient_id: str) -> bool:
    """
    Validate that recipient has LINE configured.

    Checks if the user is a student and has a line_application_id set.
    """
    try:
        result = db_session.execute(
            select(Student).join(User).where(User.id == recipient_id)
        )
        student = result.scalar_one_or_none()

        if not student:
            return False

        if not student.line_application_id:
            return False

        return True

    except Exception:
        return False


def _get_line_user_id(db_session: Session, recipient_id: str) -> Optional[str]:
    """Get the recipient's LINE user ID"""
    try:
        result = db_session.execute(
            select(Student.line_application_id)
            .join(User)
            .where(User.id == recipient_id)
        )
        line_application_id = result.scalar_one_or_none()
        return line_application_id

    except Exception as e:
        raise e


async def _send_line_notification(
    db_session: Session, line_user_id: str, subject: str, body: str, logger
) -> bool:
    """
    Send LINE notification using LineWebhookService.

    Args:
        db_session: Database session
        line_user_id: LINE user ID to send to
        subject: Message subject
        body: Message body
        logger: Logger instance

    Returns:
        bool: True if successful, False if failed
    """
    try:
        # Create LINE service instance
        line_service = LineWebhookService(db_session)

        # Send push notification
        success = await line_service.send_push_notification(
            line_user_id=line_user_id, subject=subject, body=body
        )

        if success:
            logger.info(f"LINE notification sent successfully to {line_user_id}")
        else:
            logger.warning(f"LINE notification failed to send to {line_user_id}")

        return success

    except Exception as e:
        logger.error(f"Error sending LINE notification: {str(e)}")
        raise e

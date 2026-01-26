import asyncio
from typing import Optional, List
from datetime import datetime

from app.celery import celery
from app.db.session import get_sync_session
from app.services.notifications.registry import NotificationServiceRegistry
from app.utils.logging import get_logger
from app.utils.datetime_utils import to_naive_utc, naive_utc_now


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def create_notification_task(
    self,
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
):
    """
    Celery task to create notifications asynchronously.

    This task is particularly useful when creating notifications for many recipients
    which could be time-consuming.

    Args:
        request_id: The request ID from the original HTTP request
        notification_code: Code identifying the notification type
        entity_id: UUID of the entity the notification is about
        actor_type: Type of actor triggering the notification
        recipient_ids: List of recipient UUIDs (as strings)
        actor_id: Optional UUID of the actor (as string)
        scheduled_for: Optional datetime for scheduling
        expires_at: Optional datetime for expiration
        in_app_enabled: Whether in-app notifications are enabled
        line_app_enabled: Whether LINE notifications are enabled
        **metadata: Additional metadata for the notification
    """
    return asyncio.run(
        _async_create_notification(
            request_id=request_id,
            notification_code=notification_code,
            entity_id=entity_id,
            actor_type=actor_type,
            recipient_ids=recipient_ids,
            actor_id=actor_id,
            scheduled_for=scheduled_for,
            expires_at=expires_at,
            in_app_enabled=in_app_enabled,
            line_app_enabled=line_app_enabled,
            **metadata,
        )
    )


async def _async_create_notification(
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
):
    logger = get_logger().bind(request_id=request_id)

    for db_session in get_sync_session():

        try:
            # Parse datetime strings if provided
            scheduled_for_dt = to_naive_utc(scheduled_for) if scheduled_for else None
            expires_at_dt = to_naive_utc(expires_at) if expires_at else None

            # Create the notification using NotificationServiceRegistry directly
            service = NotificationServiceRegistry.create_service(
                notification_code, db_session
            )

            if not service:
                logger.error(
                    f"No service found for notification code: {notification_code}"
                )
                return {
                    "success": False,
                    "error": f"No service found for notification code: {notification_code}",
                    "request_id": request_id,
                }

            notification_id = await service.create(
                entity_id=entity_id,
                actor_type=actor_type,
                recipient_ids=recipient_ids,
                actor_id=actor_id,
                scheduled_for=scheduled_for_dt,
                expires_at=expires_at_dt,
                in_app_enabled=in_app_enabled,
                line_app_enabled=line_app_enabled,
                **metadata,
            )

            if notification_id:

                # If notification is scheduled for future, don't process immediately
                if scheduled_for_dt and scheduled_for_dt > naive_utc_now():
                    pass
                else:
                    # Trigger immediate processing for non-scheduled notifications
                    from app.tasks import process_notification_task

                    process_notification_task.delay(  # type: ignore
                        request_id=request_id,
                        notification_id=str(notification_id),
                    )

                return {"status": "success"}
            else:
                logger.error(
                    f"Failed to create notification {notification_code} for entity {entity_id}"
                )
                return {"status": "error", "message": "Failed to create notification"}

        except Exception as e:
            logger.error(
                f"Notification creation task exception {notification_code}/{entity_id}: {str(e)}"
            )

            return {
                "status": "error",
                "message": str(e),
            }

from typing import Dict, Callable, Optional
from sqlalchemy.orm import Session

from .base import BaseNotificationService
from .certificate_service import create_certificate_service
from .schedule_service import create_schedule_service
from app.utils.logging import get_logger

logger = get_logger()


class NotificationServiceRegistry:
    """Registry for notification service creation"""

    # Map notification codes to factory functions
    _factories: Dict[str, Callable[[Session, str], BaseNotificationService]] = {
        # Certificate submission notifications
        "certificate_submission_submit": create_certificate_service,
        "certificate_submission_update": create_certificate_service,
        "certificate_submission_delete": create_certificate_service,
        "certificate_submission_verify": create_certificate_service,
        "certificate_submission_reject": create_certificate_service,
        "certificate_submission_manual_review": create_certificate_service,
        "certificate_submission_manual_review_request": create_certificate_service,
        # Program requirement schedule notifications
        "program_requirement_schedule_remind": create_schedule_service,
        "program_requirement_schedule_warn": create_schedule_service,
        "program_requirement_schedule_late": create_schedule_service,
        "program_requirement_schedule_overdue": create_schedule_service,
    }

    @classmethod
    def create_service(
        cls, notification_code: str, db_session: Session
    ) -> Optional[BaseNotificationService]:
        """Create service instance for notification code"""
        factory = cls._factories.get(notification_code)
        if factory:
            return factory(db_session, notification_code)

        logger.warning(
            f"No service registered for notification code: {notification_code}"
        )
        return None

    @classmethod
    def register_service(
        cls,
        notification_code: str,
        factory: Callable[[Session, str], BaseNotificationService],
    ):
        """Register a custom factory function for a notification code"""
        cls._factories[notification_code] = factory
        logger.info(f"Registered factory for notification code: {notification_code}")

    @classmethod
    def list_registered_codes(cls) -> list:
        """List all registered notification codes"""
        return list(cls._factories.keys())

    @classmethod
    def is_registered(cls, notification_code: str) -> bool:
        """Check if notification code is registered"""
        return notification_code in cls._factories

import json
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .base import BaseNotificationService
from app.db.models import (
    CertificateSubmission,
    Student,
    ProgramRequirementSchedule,
    ProgramRequirement,
    Notification,
)
from app.utils.logging import get_logger
from app.utils.errors import BusinessLogicError

logger = get_logger()


class CertificateSubmissionNotificationService(BaseNotificationService):
    """Unified certificate submission notification service"""

    async def get_notification_data(
        self, entity_id: str, notification_id: str
    ) -> Dict[str, Any]:
        """Get certificate submission data for all notification types"""
        try:
            result = self.db.execute(
                select(CertificateSubmission)
                .options(
                    selectinload(CertificateSubmission.student).selectinload(
                        Student.user
                    ),
                    selectinload(CertificateSubmission.certificate_type),
                    selectinload(CertificateSubmission.requirement_schedule)
                    .selectinload(ProgramRequirementSchedule.program_requirement)
                    .selectinload(ProgramRequirement.program),
                )
                .where(CertificateSubmission.id == entity_id)
            )
            submission = result.scalar_one_or_none()

            if not submission:
                raise ValueError(f"Certificate submission not found: {entity_id}")

            # Get notification metadata if notification_id is provided
            notification_metadata = {}
            if notification_id:
                try:
                    notification_result = self.db.execute(
                        select(Notification.notification_metadata).where(
                            Notification.id == notification_id
                        )
                    )
                    metadata = notification_result.scalar_one_or_none()
                    if metadata:
                        notification_metadata = json.loads(metadata)
                except Exception as e:
                    logger.warning(
                        f"Could not fetch notification metadata for {notification_id}: {e}"
                    )

            data = {
                "certificate_name": submission.certificate_type.cert_name,
                "student_name": f"{submission.student.user.first_name} {submission.student.user.last_name}",
                "student_roll_number": submission.student.user_id,
                "program_name": (
                    submission.requirement_schedule.program_requirement.program.program_name
                    if submission.requirement_schedule
                    else "N/A"
                ),
                "rejection_comment": "N/A",
            }

            # Merge any additional metadata
            if notification_metadata:
                data.update(
                    {k: v for k, v in notification_metadata.items() if k not in data}
                )

            return data

        except Exception as e:
            raise BusinessLogicError(
                f"Failed to get certificate submission data for {entity_id}: {e}"
            )


def create_certificate_service(
    db_session, notification_code: str
) -> CertificateSubmissionNotificationService:
    """Create certificate submission notification service"""
    return CertificateSubmissionNotificationService(db_session, notification_code)

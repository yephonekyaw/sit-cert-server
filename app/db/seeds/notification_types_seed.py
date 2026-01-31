import uuid
from sqlalchemy.orm import Session
from sqlalchemy import delete

from app.db.models import NotificationType, Priority
from app.utils.logging import get_logger

logger = get_logger()


def seed_notification_types(db_session: Session):
    """Sync version: Seed notification types data - clear existing and add new"""

    # Clear existing notification types
    db_session.execute(delete(NotificationType))

    # Add notification types
    notification_types = [
        # CertificateSubmission actions
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="CertificateSubmission",
            code="certificate_submission_submit",
            name="Certificate Submitted",
            description="A student has submitted a new certificate.",
            default_priority=Priority.MEDIUM,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="CertificateSubmission",
            code="certificate_submission_update",
            name="Certificate Updated",
            description="A student has updated a certificate submission.",
            default_priority=Priority.MEDIUM,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="CertificateSubmission",
            code="certificate_submission_delete",
            name="Certificate Deleted",
            description="A student has deleted a certificate submission.",
            default_priority=Priority.MEDIUM,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="CertificateSubmission",
            code="certificate_submission_verify",
            name="Certificate Verified",
            description="A certificate submission has been verified.",
            default_priority=Priority.MEDIUM,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="CertificateSubmission",
            code="certificate_submission_reject",
            name="Certificate Rejected",
            description="A certificate submission has been rejected.",
            default_priority=Priority.HIGH,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="CertificateSubmission",
            code="certificate_submission_manual_review",
            name="Certificate Under Manual Review",
            description="A certificate submission is under manual review.",
            default_priority=Priority.MEDIUM,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="CertificateSubmission",
            code="certificate_submission_manual_review_request",
            name="Certificate Review Requested",
            description="A certificate submission requires a manual review.",
            default_priority=Priority.HIGH,
            is_active=True,
        ),
        # ProgramRequirementSchedule actions
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="ProgramRequirementSchedule",
            code="program_requirement_schedule_remind",
            name="Requirement Reminder",
            description="A reminder for a program requirement.",
            default_priority=Priority.LOW,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="ProgramRequirementSchedule",
            code="program_requirement_schedule_warn",
            name="Requirement Warning",
            description="A warning for an upcoming program requirement deadline.",
            default_priority=Priority.MEDIUM,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="ProgramRequirementSchedule",
            code="program_requirement_schedule_late",
            name="Requirement Late",
            description="A program requirement is late.",
            default_priority=Priority.HIGH,
            is_active=True,
        ),
        NotificationType(
            id=str(uuid.uuid4()),
            entity_type="ProgramRequirementSchedule",
            code="program_requirement_schedule_overdue",
            name="Requirement Overdue",
            description="A program requirement is overdue.",
            default_priority=Priority.HIGH,
            is_active=True,
        ),
    ]

    db_session.add_all(notification_types)
    db_session.commit()
    logger.info(f"Seeded {len(notification_types)} notification types")

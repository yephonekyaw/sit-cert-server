import uuid
from sqlalchemy.orm import Session
from sqlalchemy import delete

from app.db.models import CertificateType
from app.utils.logging import get_logger

logger = get_logger()


def seed_certificate_types(db_session: Session):
    """Sync version: Seed certificate types data - clear existing and add new"""

    # Clear existing certificate types
    db_session.execute(delete(CertificateType))

    # Add certificate types
    certificate_types = [
        CertificateType(
            id=str(uuid.uuid4()),
            cert_code="citi_program_certificate",
            cert_name="CITI Program Certificate",
            description="Certificate for CITI Program courses.",
            has_expiration=False,
            is_active=True,
        ),
    ]

    db_session.add_all(certificate_types)
    db_session.commit()
    logger.info(f"Seeded {len(certificate_types)} certificate types")

import uuid
from sqlalchemy.orm import Session
from sqlalchemy import delete

from app.db.models import Program
from app.utils.logging import get_logger

logger = get_logger()


def seed_programs(db_session: Session):
    """Sync version: Seed programs data - clear existing and add new"""

    # Clear existing programs
    db_session.execute(delete(Program))

    # Add new programs
    programs = [
        Program(
            id=str(uuid.uuid4()),
            program_code="Bc.CS",
            program_name="Bachelor of Science Program in Computer Science (English Program)",
            description="A comprehensive Bachelor's program focusing on computer science fundamentals, software development, algorithms, data structures, and computational theory.",
            duration_years=4,
            is_active=True,
        ),
        Program(
            id=str(uuid.uuid4()),
            program_code="Bc.DSI",
            program_name="Bachelor of Arts Programme in Digital Service Innovation",
            description="An innovative Bachelor's program that combines technology, design thinking, and business strategy to create digital solutions for real-world problems.",
            duration_years=4,
            is_active=True,
        ),
        Program(
            id=str(uuid.uuid4()),
            program_code="Bc.IT",
            program_name="Bachelor of Science Program in Information Technology",
            description="A practical Bachelor's program focused on the application of technology in business environments.",
            duration_years=4,
            is_active=True,
        ),
    ]

    db_session.add_all(programs)
    db_session.commit()
    logger.info(f"Seeded {len(programs)} programs")

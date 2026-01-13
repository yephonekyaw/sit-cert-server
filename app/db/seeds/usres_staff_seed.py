import uuid
from sqlalchemy.orm import Session
from sqlalchemy import delete

from app.db.models import User, Staff, UserType
from app.utils.logging import get_logger

logger = get_logger()


def seed_users_staff(db_session: Session):
    """Sync version: Seed staff data - clear existing and add new"""

    # Clear existing staff and their users
    db_session.execute(delete(Staff))
    # Note: Users will be cleared by the users_students_seed, so we only clear staff here
    db_session.commit()

    # Create staff user and staff record
    user_id = str(uuid.uuid4())

    # Create user
    user = User(
        id=user_id,
        username="cscms",
        first_name="Julian",
        last_name="San",
        user_type=UserType.STAFF,
        is_active=True,
    )

    # Create staff
    staff = Staff(
        id=str(uuid.uuid4()),
        user_id=user_id,
    )

    db_session.add(user)
    db_session.add(staff)
    db_session.commit()
    logger.info("Seeded 1 staff member: CSCMS")

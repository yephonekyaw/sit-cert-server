import uuid
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List


from app.db.session import get_sync_session
from app.db.models import Staff, User, UserType
from app.schemas.staff.member_schemas import (
    StaffMemberItem,
    CreateStaffMemberRequest,
    UpdateStaffMemberRequest,
)
from app.utils.logging import get_logger

logger = get_logger()


class MemberService:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    async def get_all_members_with_count(self) -> List[StaffMemberItem]:
        try:
            rows = self.db_session.execute(
                select(Staff, User).join(User, Staff.user_id == User.id)
            ).all()
            members: List[StaffMemberItem] = []
            for row in rows:
                staff: Staff = row[0]
                user: User = row[1]
                member_item = StaffMemberItem(
                    id=staff.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
                members.append(member_item)
            return members
        except Exception as e:
            logger.error(str(e))
            raise e

    async def create_member(
        self, member_data: CreateStaffMemberRequest
    ) -> StaffMemberItem:
        try:
            row = self.db_session.execute(
                select(User).where(User.username == member_data.username)
            ).scalar_one_or_none()

            if row:
                raise ValueError("Staff member with this username already exists")

            # Create staff user and staff record
            user_id = str(uuid.uuid4())

            # Create user
            user = User(
                id=user_id,
                username=member_data.username,
                first_name=member_data.first_name,
                last_name=member_data.last_name,
                user_type=UserType.STAFF,
                is_active=True,
            )

            # Create staff
            staff = Staff(
                id=str(uuid.uuid4()),
                user_id=user_id,
            )

            self.db_session.add(user)
            self.db_session.add(staff)
            self.db_session.commit()

            return StaffMemberItem(
                id=staff.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )

        except Exception as e:
            logger.error(str(e))
            raise e

    async def update_member(
        self, staff_id: str, member_data: UpdateStaffMemberRequest
    ) -> StaffMemberItem:
        try:
            row = self.db_session.get_one(Staff, staff_id)
            if not row:
                raise ValueError("Staff member not found")

            user = self.db_session.get_one(User, row.user_id)
            if not user:
                raise ValueError("Associated user not found")

            # Update user fields
            user.first_name = member_data.first_name
            user.last_name = member_data.last_name
            # user.is_active = member_data.is_active
            self.db_session.commit()

            return StaffMemberItem(
                id=row.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        except Exception as e:
            logger.error(str(e))
            raise e


def get_member_service(
    db: Session = Depends(get_sync_session),
) -> MemberService:
    return MemberService(db)

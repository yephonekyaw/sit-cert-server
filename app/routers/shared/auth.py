from typing import Annotated
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_sync_session
from app.schemas.auth_schemas import (
    UserResponse,
)
from app.middlewares.auth_middleware import get_current_user, AuthState
from app.utils.responses import ResponseBuilder
from app.utils.errors import AuthenticationError

auth_router = APIRouter()


@auth_router.get("/me")
async def get_current_user_info(
    request: Request,
    current_user: Annotated[AuthState, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_sync_session)],
):
    """Get current authenticated user information"""
    user = db.execute(
        select(User).where(User.id == current_user.user_id, User.is_active == True)
    ).scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")

    user_data = UserResponse(
        id=str(user.id),
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        user_type=user.user_type.value,
        is_active=user.is_active,
    )

    return ResponseBuilder.success(
        request=request,
        data=user_data.model_dump(by_alias=True),
        message="User information retrieved",
    )

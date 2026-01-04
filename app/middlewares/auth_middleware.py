from httpx import AsyncClient, HTTPStatusError
from typing import Optional, Callable
from fastapi import Request, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.db.models import User
from app.db.session import get_sync_session
from app.utils.errors import AuthenticationError, AuthorizationError
from app.utils.responses import ResponseBuilder
from app.utils.logging import get_logger
from app.utils.cookies import CookieUtils

logger = get_logger()


class AuthState:
    """Authentication state to be stored in request.state"""

    def __init__(
        self,
        user_id: str,
        username: str,
        user_type: str,
        is_authenticated: bool = True,
    ):
        self.user_id = user_id
        self.username = username
        self.user_type = user_type
        self.is_authenticated = is_authenticated


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for JWT token validation and refresh"""

    EXCLUDED_PATHS = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/shared/auth/login",
        "/api/v1/shared/health",
        "/webhook/v1",
    }

    def __init__(self, app, excluded_paths: Optional[set] = None):
        super().__init__(app)
        if excluded_paths:
            self.EXCLUDED_PATHS.update(excluded_paths)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through authentication middleware"""
        if self._should_skip_auth(request):
            return await call_next(request)

        try:
            bearer_token = self._get_bearer_token(request)
            user_info = await self._fetch_user_info(bearer_token)
            username = user_info.get("username")

            if not username:
                raise AuthenticationError(
                    "Invalid user data from provider", "AUTH_ERROR"
                )

            user = await run_in_threadpool(self._get_user_from_db, username)

            if not user:
                raise AuthenticationError("User not found or inactive", "AUTH_ERROR")

            request.state.auth = AuthState(
                user_id=str(user.id),
                username=user.username,
                user_type=user.user_type.value,
            )
            return await call_next(request)

        except (AuthenticationError, HTTPStatusError) as e:
            error_message = (
                str(e)
                if isinstance(e, AuthenticationError)
                else "Authentication provider error"
            )
            return ResponseBuilder.error(
                request=request,
                message=error_message,
                error_code="AUTH_ERROR",
                status_code=401,
            )
        except Exception as e:
            return ResponseBuilder.error(
                request=request,
                message=str(e),
                error_code="INTERNAL_SERVER_ERROR",
                status_code=500,
            )

    def _should_skip_auth(self, request: Request) -> bool:
        """Check if the request should skip authentication."""
        return request.method == "OPTIONS" or self._is_excluded_path(request.url.path)

    def _is_excluded_path(self, path: str) -> bool:
        """Check if path is excluded from authentication"""
        return any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS)

    def _get_bearer_token(self, request: Request) -> str:
        """Extracts bearer token from headers or cookies."""
        token = CookieUtils.extract_bearer_token(
            request.headers.get("authorization")
        ) or request.cookies.get("jwt_token")
        if not token:
            raise AuthenticationError("No bearer token found", "AUTH_ERROR")
        return token

    async def _fetch_user_info(self, token: str) -> dict:
        """Fetches user information from the authentication provider."""
        async with AsyncClient() as client:
            response = await client.get(
                f"{settings.SITBRAIN_BASE_URL}/users/me",
                timeout=30.0,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()

    def _get_user_from_db(self, username: str) -> Optional[User]:
        """Fetches an active user from the database by username."""
        for db_session in get_sync_session():
            stmt = select(User).where(User.username == username, User.is_active == True)
            return db_session.execute(stmt).scalar_one_or_none()
        return None


# Dependency for getting current user from request state
def get_current_user(request: Request) -> AuthState:
    """Dependency to get current authenticated user from request state"""
    auth_state = getattr(request.state, "auth", None)

    if not auth_state or not auth_state.is_authenticated:
        raise AuthenticationError("Not authenticated", "NOT_AUTHENTICATED")

    return auth_state


# Dependency for requiring specific user types
def require_user_type(*allowed_types: str):
    """Create dependency that requires specific user types"""
    from fastapi import Depends

    def check_user_type(
        current_user: AuthState = Depends(get_current_user),
    ) -> AuthState:
        if current_user.user_type not in allowed_types:
            raise AuthorizationError(
                "Insufficient permissions", "INSUFFICIENT_PERMISSIONS"
            )
        return current_user

    return check_user_type


# Pre-defined dependencies for common user types
require_student = require_user_type("student")
require_staff = require_user_type("staff")
require_any_user = require_user_type("student", "staff")

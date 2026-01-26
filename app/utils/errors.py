from fastapi import FastAPI, Request, status
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
import traceback
from .logging import get_logger
from .responses import ResponseBuilder

logger = get_logger()


class BusinessLogicError(Exception):
    """Custom exception for business logic errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AuthenticationError(Exception):
    """Custom exception for authentication errors."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)
        self.message = message


class AuthorizationError(Exception):
    """Custom exception for authorization errors."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(message)
        self.message = message


class NotFoundError(Exception):
    """Custom exception for resource not found errors."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)
        self.message = message


class LineApplicationError(Exception):
    """Custom exception for LINE application errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def setup_error_handlers(app: FastAPI):
    """Setup custom error handlers."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.error(f"HTTP Exception: {str(exc)}")
        return ResponseBuilder.error(
            request=request,
            message=str(exc.detail),
            status_code=exc.status_code,
        )

    """
    RequestValidationError is a sub-class of Pydantic's ValidationError.
    """

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        logger.error(f"Request Validation Error: {exc.errors()}")

        # Format validation errors for better readability
        formatted_errors = []
        for error in exc.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            formatted_errors.append(
                {
                    "field": field_path,
                    "message": error["msg"],
                    "type": error["type"],
                    "input": error.get("input"),
                }
            )

        return ResponseBuilder.error(
            request=request,
            message="Request validation failed",
            errors=formatted_errors,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    """
    If you use a Pydantic model in response_model, and your data has an error, you will see the error in your log.
    """

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(
        request: Request, exc: ValidationError
    ):
        logger.error(f"Pydantic Validation Error: {exc.errors()}")

        # Format Pydantic validation errors
        formatted_errors = []
        for error in exc.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            formatted_errors.append(
                {
                    "field": field_path,
                    "message": error["msg"],
                    "type": error["type"],
                    "input": error.get("input"),
                }
            )

        return ResponseBuilder.error(
            request=request,
            message="Data validation failed",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.error(f"SQLAlchemy Error: {str(exc)}")

        # Don't expose internal database errors to users
        return ResponseBuilder.error(
            request=request,
            message="A database error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(BusinessLogicError)
    async def business_logic_exception_handler(
        request: Request, exc: BusinessLogicError
    ):
        logger.error(f"Business Logic Error: {str(exc)}")

        return ResponseBuilder.error(
            request=request,
            message=exc.message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_exception_handler(
        request: Request, exc: AuthenticationError
    ):
        logger.error(f"Authentication Error: {str(exc)}")

        return ResponseBuilder.error(
            request=request,
            message=exc.message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_exception_handler(
        request: Request, exc: AuthorizationError
    ):
        logger.error(f"Authorization Error: {str(exc)}")

        return ResponseBuilder.error(
            request=request,
            message=exc.message,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    @app.exception_handler(NotFoundError)
    async def not_found_exception_handler(request: Request, exc: NotFoundError):
        logger.error(f"Not Found Error: {str(exc)}")

        return ResponseBuilder.error(
            request=request,
            message=exc.message,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    @app.exception_handler(LineApplicationError)
    async def line_application_exception_handler(
        request: Request, exc: LineApplicationError
    ):
        logger.error(f"LINE Application Error: {str(exc)}")

        return ResponseBuilder.error(
            request=request,
            message=exc.message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        logger.error(f"Value Error: {str(exc)}")

        return ResponseBuilder.error(
            request=request,
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        logger.error(f"Key Error: {str(exc)}")

        return ResponseBuilder.error(
            request=request,
            message=f"Required key not found: {str(exc)}",
            status_code=status.HTTP_400_BAD_REQUEST,
            meta={"missing_key": str(exc)},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other unhandled exceptions"""
        logger.error(f"Unhandled Exception: {str(exc)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return ResponseBuilder.error(
            request=request,
            message="An internal server error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

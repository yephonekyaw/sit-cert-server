from typing import Any, Dict, List, Optional
from fastapi import status, Request
from fastapi.responses import JSONResponse
from app.schemas.response_schemas import ApiResponse, PaginationMeta, ResponseStatus


class ResponseBuilder:
    """Builder class for creating standardized responses"""

    @staticmethod
    def success(
        request: Request,
        data: Any = None,
        message: str = "Request successful",
        meta: Optional[Dict[str, Any]] = None,
        pagination: Optional[PaginationMeta] = None,
        status_code: int = status.HTTP_200_OK,
    ) -> JSONResponse:
        """Create a success response"""
        response = ApiResponse(
            success=True,
            status=ResponseStatus.SUCCESS,
            message=message,
            data=data,
            meta=meta,
            pagination=pagination,
            request_id=request.state.request_id,
            path=str(request.url.path),
        )
        return JSONResponse(
            status_code=status_code,
            content=response.model_dump(exclude_none=True),
        )

    @staticmethod
    def error(
        request: Request,
        message: str = "An error occurred",
        errors: Optional[List[Dict[str, Any]]] = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        data: Any = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> JSONResponse:
        """Create an error response"""
        response_meta = meta or {}

        response = ApiResponse(
            success=False,
            status=ResponseStatus.ERROR,
            message=message,
            data=data,
            meta=response_meta if response_meta else None,
            errors=errors,
            request_id=request.state.request_id,
            path=str(request.url.path),
        )
        return JSONResponse(
            status_code=status_code, content=response.model_dump(exclude_none=True)
        )

    @staticmethod
    def warning(
        request: Request,
        data: Any = None,
        message: str = "Request completed with warnings",
        warnings: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        status_code: int = status.HTTP_200_OK,
    ) -> JSONResponse:
        """Create a warning response"""
        response = ApiResponse(
            success=True,
            status=ResponseStatus.WARNING,
            message=message,
            data=data,
            meta=meta,
            warnings=warnings,
            request_id=request.state.request_id,
            path=str(request.url.path),
        )
        return JSONResponse(
            status_code=status_code, content=response.model_dump(exclude_none=True)
        )

    @staticmethod
    def paginated(
        request: Request,
        data: List[Any],
        page: int,
        per_page: int,
        total: int,
        message: str = "Data retrieved successfully",
        meta: Optional[Dict[str, Any]] = None,
    ) -> JSONResponse:
        """Create a paginated response"""
        total_pages = (total + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1

        pagination = PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
            next_page=page + 1 if has_next else None,
            prev_page=page - 1 if has_prev else None,
        )

        return ResponseBuilder.success(
            request=request,
            data=data,
            message=message,
            meta=meta,
            pagination=pagination,
        )

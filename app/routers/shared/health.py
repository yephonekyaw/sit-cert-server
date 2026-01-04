from fastapi import APIRouter, Request
from app.utils.responses import ResponseBuilder

health_router = APIRouter()


@health_router.get("")
async def health_check(request: Request):
    """
    Basic health check endpoint

    Returns application status and basic system information
    """
    return ResponseBuilder.success(
        request=request,
        data={"status": "healthy", "service": "SIT Cert Server", "version": "1.0.0"},
        message="Service is running",
    )

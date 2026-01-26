from typing import Annotated
from fastapi import APIRouter, Depends, Path, Request, status

from app.middlewares.auth_middleware import require_staff
from app.schemas.staff.dashboard_stats_schemas import DashboardStatsResponse
from app.services.staff.dashboard_stats_service import (
    DashboardStatsService,
    get_dashboard_stats_service,
)
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError

dashboard_stats_router = APIRouter(dependencies=[Depends(require_staff)])


@dashboard_stats_router.get(
    "/schedule/{requirement_schedule_id}",
    response_model=DashboardStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard stats by requirement schedule ID",
    description="Retrieve all dashboard statistics for a specific requirement schedule",
)
def get_dashboard_stats_by_schedule(
    request: Request,
    requirement_schedule_id: Annotated[
        str, Path(description="Requirement schedule ID")
    ],
    dashboard_stats_service: DashboardStatsService = Depends(
        get_dashboard_stats_service
    ),
):
    """
    Get dashboard statistics for a specific requirement schedule.

    Args:
        request: FastAPI request object
        requirement_schedule_id: UUID of the requirement schedule

    Returns:
        Response containing DashboardStatsResponse data

    Raises:
        BusinessLogicError: For service errors
    """
    try:
        dashboard_stats = dashboard_stats_service.get_dashboard_stats_by_schedule(
            requirement_schedule_id=requirement_schedule_id
        )

        return ResponseBuilder.success(
            request=request,
            data=dashboard_stats.model_dump(by_alias=True),
            message="Dashboard statistics retrieved successfully",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to retrieve dashboard statistics",
        )

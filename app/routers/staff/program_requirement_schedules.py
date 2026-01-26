from typing import Annotated

from fastapi import APIRouter, Depends, Request, status, Path

from app.services.staff.program_requirement_schedule_service import (
    ProgramRequirementScheduleService,
    get_program_requirement_schedule_service,
)
from app.schemas.staff.program_requirement_schedule_schemas import (
    CreateProgramRequirementScheduleRequest,
    UpdateProgramRequirementScheduleRequest,
)
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError
from app.middlewares.auth_middleware import require_staff

program_requirement_schedules_router = APIRouter(dependencies=[Depends(require_staff)])


# API Endpoints
@program_requirement_schedules_router.get(
    "",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Get all program requirement schedules with comprehensive data",
    description="Retrieve all program requirement schedules with program, certificate type, academic year, and dashboard statistics data.",
)
async def get_all_program_requirement_schedules(
    request: Request,
    schedule_service: ProgramRequirementScheduleService = Depends(
        get_program_requirement_schedule_service
    ),
):
    """Get all program requirement schedules with comprehensive related data"""
    try:
        response_data = await schedule_service.get_all_schedules_with_details()
        schedules_count = len(response_data)
        message = ProgramRequirementScheduleService.build_success_message(
            schedules_count
        )

        return ResponseBuilder.success(
            request=request,
            data=response_data,
            message=message,
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to retrieve program requirement schedules",
        )


@program_requirement_schedules_router.post(
    "",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new program requirement schedule",
    description="Create a new program requirement schedule for a specific academic year. Validates that the program requirement is active and no duplicate schedule exists.",
)
async def create_program_requirement_schedule(
    request: Request,
    schedule_data: CreateProgramRequirementScheduleRequest,
    schedule_service: ProgramRequirementScheduleService = Depends(
        get_program_requirement_schedule_service
    ),
):
    """Create a new program requirement schedule with validation"""
    try:
        response_data = await schedule_service.create_schedule(schedule_data)

        return ResponseBuilder.success(
            request=request,
            data=response_data,
            message="Program requirement schedule created successfully",
            status_code=status.HTTP_201_CREATED,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to create program requirement schedule",
        )


@program_requirement_schedules_router.put(
    "/{schedule_id}",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Update an existing program requirement schedule",
    description="Update an existing program requirement schedule. Validates that the program requirement is active, academic year exists, and deadline is within academic year period.",
)
async def update_program_requirement_schedule(
    request: Request,
    schedule_id: Annotated[str, Path(description="Schedule ID to update")],
    schedule_data: UpdateProgramRequirementScheduleRequest,
    schedule_service: ProgramRequirementScheduleService = Depends(
        get_program_requirement_schedule_service
    ),
):
    """Update an existing program requirement schedule with validation"""
    try:
        response_data = await schedule_service.update_schedule(
            schedule_id, schedule_data
        )

        return ResponseBuilder.success(
            request=request,
            data=response_data,
            message="Program requirement schedule updated successfully",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to update program requirement schedule",
        )

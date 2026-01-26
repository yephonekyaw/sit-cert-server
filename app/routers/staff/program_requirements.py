from typing import Annotated, List

from fastapi import APIRouter, Depends, Request, status, Path

from app.services.staff.program_requirement_service import (
    ProgramRequirementService,
    get_program_requirement_service,
)
from app.schemas.staff.program_requirement_schemas import (
    CreateProgramRequirementRequest,
    GetProgramRequirementsItem,
    UpdateProgramRequirementRequest,
    ProgramRequirementResponse,
)
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError
from app.middlewares.auth_middleware import require_staff

program_requirements_router = APIRouter(dependencies=[Depends(require_staff)])


# API Endpoints
@program_requirements_router.get(
    "",
    response_model=List[GetProgramRequirementsItem],
    status_code=status.HTTP_200_OK,
    summary="Get all program requirements",
    description="Retrieve all program requirements (active and inactive) with comprehensive information including related program and certificate data, plus schedule statistics",
)
async def get_all_program_requirements(
    request: Request,
    requirement_service: ProgramRequirementService = Depends(
        get_program_requirement_service
    ),
):
    """Get all program requirements with comprehensive data and schedule counts"""
    try:
        response_data = await requirement_service.get_all_requirements()

        return ResponseBuilder.success(
            request=request,
            data=response_data,
            message=f"Retrieved {len(response_data)} program requirement{'s' if len(response_data) != 1 else ''} successfully",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception as e:
        raise BusinessLogicError(
            message="Failed to retrieve program requirements",
        )


@program_requirements_router.post(
    "",
    response_model=ProgramRequirementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new program requirement",
    description="Create a new program requirement with comprehensive validation including target year against program duration",
)
async def create_program_requirement(
    request: Request,
    requirement_data: CreateProgramRequirementRequest,
    requirement_service: ProgramRequirementService = Depends(
        get_program_requirement_service
    ),
):
    """Create a new program requirement with validation"""
    try:
        response_data = await requirement_service.create_requirement(requirement_data)

        return ResponseBuilder.success(
            request=request,
            data=response_data.model_dump(by_alias=True),
            message="Program requirement created successfully",
            status_code=status.HTTP_201_CREATED,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to create program requirement",
        )


@program_requirements_router.patch(
    "/{requirement_id}/archive",
    status_code=status.HTTP_200_OK,
    summary="Archive a program requirement",
    description="Archive a specific program requirement and update effective_until_year based on the latest academic year with created schedules",
)
async def archive_program_requirement(
    request: Request,
    requirement_id: Annotated[
        str, Path(description="Program requirement ID to archive")
    ],
    requirement_service: ProgramRequirementService = Depends(
        get_program_requirement_service
    ),
):
    """Archive a program requirement with proper effective_until_year handling"""
    try:
        response_data = await requirement_service.archive_requirement(requirement_id)

        return ResponseBuilder.success(
            request=request,
            data=response_data.model_dump(by_alias=True),
            message="Program requirement archived successfully",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to archive program requirement",
        )


@program_requirements_router.put(
    "/{requirement_id}",
    status_code=status.HTTP_200_OK,
    summary="Update an existing program requirement",
    description="Update an existing program requirement with validation. Changes apply only to future schedules (schedules with deadlines not yet passed).",
)
async def update_program_requirement(
    request: Request,
    requirement_id: Annotated[
        str, Path(description="Program requirement ID to update")
    ],
    requirement_data: UpdateProgramRequirementRequest,
    requirement_service: ProgramRequirementService = Depends(
        get_program_requirement_service
    ),
):
    """Update an existing program requirement with validation"""
    try:
        response_data = await requirement_service.update_requirement(
            requirement_id, requirement_data
        )

        return ResponseBuilder.success(
            request=request,
            data=response_data.model_dump(by_alias=True),
            message="Program requirement updated successfully. Changes will apply to future schedules only.",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception as e:
        raise BusinessLogicError(
            message="Failed to update program requirement",
        )

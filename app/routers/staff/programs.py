from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status, Path

from app.middlewares.auth_middleware import require_staff
from app.services.staff.program_service import (
    ProgramService,
    get_program_service,
)
from app.schemas.staff.program_schemas import (
    CreateProgramRequest,
    UpdateProgramRequest,
    ProgramListQueryParams,
    ProgramResponse,
)
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError

programs_router = APIRouter(dependencies=[Depends(require_staff)])


# API Endpoints
@programs_router.get(
    "",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Get all programs with requirement counts",
    description="Retrieve all programs with their basic information and counts of active/archived requirements. Supports filtering and sorting.",
)
async def get_all_programs(
    request: Request,
    query_params: Annotated[ProgramListQueryParams, Depends()],
    program_service: ProgramService = Depends(get_program_service),
):
    """Get all programs with filtering and sorting capabilities"""
    try:
        programs_list = await program_service.get_all_programs_with_counts(query_params)
        message = ProgramService.build_success_message(len(programs_list), query_params)

        return ResponseBuilder.success(
            request=request,
            data=programs_list,
            message=message,
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to retrieve programs",
        )


@programs_router.post(
    "",
    response_model=ProgramResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new program",
    description="Create a new academic program with the provided details",
)
async def create_program(
    request: Request,
    program_data: CreateProgramRequest,
    program_service: ProgramService = Depends(get_program_service),
):
    """Create a new academic program"""
    try:
        program_response = await program_service.create_program(program_data)

        return ResponseBuilder.success(
            request=request,
            data=program_response.model_dump(by_alias=True),
            message="Program created successfully",
            status_code=status.HTTP_201_CREATED,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to create program",
        )


@programs_router.put(
    "/{program_id}",
    response_model=ProgramResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing program",
    description="Update an existing academic program. Validates that duration changes don't conflict with active requirements.",
)
async def update_program(
    request: Request,
    program_data: UpdateProgramRequest,
    program_id: Annotated[str, Path(description="Program ID to update")],
    program_service: ProgramService = Depends(get_program_service),
):
    """Update an existing academic program with validation"""
    try:
        program_response = await program_service.update_program(
            program_id, program_data
        )

        return ResponseBuilder.success(
            request=request,
            data=program_response.model_dump(by_alias=True),
            message="Program updated successfully",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to update program",
        )


@programs_router.patch(
    "/{program_id}/archive",
    response_model=ProgramResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive an existing program",
    description="Archive an existing program and all its active requirements. Returns count of archived requirements.",
)
async def archive_program(
    request: Request,
    program_id: Annotated[str, Path(description="Program ID to archive")],
    program_service: ProgramService = Depends(get_program_service),
):
    """Archive a program and all its active requirements"""
    try:
        response_data = await program_service.archive_program(program_id)
        archived_count = response_data["archived_requirements_count"]
        message = ProgramService.build_archive_message(archived_count)

        return ResponseBuilder.success(
            request=request,
            data=cast(ProgramResponse, response_data.get("program")).model_dump(
                by_alias=True
            ),
            message=message,
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to archive program",
        )

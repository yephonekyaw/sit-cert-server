from typing import List, Annotated, Union, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Form, Path, status
from sqlalchemy.orm import Session

from app.db.session import get_sync_session
from app.schemas.student.requirement_schemas import (
    StudentRequirementWithSubmissionResponse,
    RequirementSubmissionRequest,
)
from app.schemas.staff.submission_schemas import (
    VerificationHistoryListResponse,
)
from app.services.minio_service import get_minio_service, MinIOService
from app.services.student.requirements_service import RequirementsService
from app.services.staff.submission_service import (
    get_submission_service,
    SubmissionService,
)
from app.services.staff.dashboard_stats_service import (
    DashboardStatsService,
    get_dashboard_stats_service,
)
from app.utils.logging import get_logger
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError
from app.tasks import verify_certificate_task
from app.middlewares.auth_middleware import require_student, AuthState
from app.services.notifications.utils import (
    get_all_staff_user_ids,
    create_notification_sync,
)
from app.utils.string_utils import to_str

logger = get_logger()
requirement_router = APIRouter()


@requirement_router.post("/submit")
async def submit_student_certificate(
    request: Request,
    submission_data: Annotated[
        RequirementSubmissionRequest, Form(..., media_type="multipart/form-data")
    ],
    current_user: AuthState = Depends(require_student),
    minio_service: MinIOService = Depends(get_minio_service),
    db_session: Session = Depends(get_sync_session),
    dashboard_stats_service: DashboardStatsService = Depends(
        get_dashboard_stats_service
    ),
):
    try:
        requirements_service = RequirementsService(db_session, minio_service)

        # Get student information
        student = await requirements_service.get_student_by_user_id(
            current_user.user_id
        )

        # Submit certificate
        submission_response = await requirements_service.submit_certificate(
            student=student, submission_data=submission_data
        )

        # Update dashboard stats
        await dashboard_stats_service.update_dashboard_stats_by_schedule(
            requirement_schedule_id=to_str(submission_response.schedule_id)
        )

        # Create notifications for staff
        staff_user_ids = await get_all_staff_user_ids(
            db_session,
        )

        create_notification_sync(
            request_id=str(request.state.request_id),
            notification_code="certificate_submission_submit",
            entity_id=to_str(cast(Union[str, UUID], submission_response.submission_id)),
            actor_type="user",
            recipient_ids=staff_user_ids,
            actor_id=current_user.user_id,
            scheduled_for=None,
            expires_at=None,
            in_app_enabled=True,
            line_app_enabled=False,
        )

        # Call celery verification task
        verify_certificate_task.delay(  # type: ignore
            request.state.request_id, submission_response.submission_id
        )

        return ResponseBuilder.success(
            request=request,
            data=submission_response.model_dump(by_alias=True),
            message="Certificate submitted successfully",
        )

    except BusinessLogicError:
        raise
    except Exception as e:
        logger.info(f"Certificate submission error: {str(e)}")
        raise BusinessLogicError("Certificate submission failed")


@requirement_router.get(
    "/all", response_model=List[StudentRequirementWithSubmissionResponse]
)
async def get_student_requirements_with_submissions(
    request: Request,
    current_user: AuthState = Depends(require_student),
    db_session: Session = Depends(get_sync_session),
    minio_service: MinIOService = Depends(get_minio_service),
):
    """
    Get all certificate requirements for the current student with their submission status.

    Returns both submitted and unsubmitted requirements for the student's program and academic year.
    Includes requirement details, program info, certificate type info, and submission data if exists.
    """
    try:
        # Initialize service
        requirements_service = RequirementsService(db_session, minio_service)

        # Get student information
        student = await requirements_service.get_student_by_user_id(
            current_user.user_id
        )

        # Get requirements with submissions through service
        requirements_data = (
            await requirements_service.get_student_requirements_with_submissions(
                student
            )
        )

        return ResponseBuilder.success(
            request=request,
            data=[item.model_dump(by_alias=True) for item in requirements_data],
            message="Student requirements retrieved successfully",
        )

    except BusinessLogicError:
        raise
    except Exception as e:
        logger.info(f"Requirements retrieval error: {str(e)}")
        raise BusinessLogicError("Failed to load requirements")


@requirement_router.get(
    "/{submission_id}/verification-history",
    response_model=VerificationHistoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get verification history for student's certificate submission",
    description="Retrieve all verification history records for a specific certificate submission that belongs to the current student, ordered by creation date descending",
)
async def get_student_verification_history_by_submission_id(
    request: Request,
    submission_id: Annotated[str, Path(description="Certificate submission ID")],
    current_user: AuthState = Depends(require_student),
    submission_service: SubmissionService = Depends(get_submission_service),
    db_session: Session = Depends(get_sync_session),
    minio_service: MinIOService = Depends(get_minio_service),
):
    """Get verification history for a specific certificate submission that belongs to the current student"""
    try:
        # Initialize requirements service to validate ownership
        requirements_service = RequirementsService(db_session, minio_service)

        # Get student information from current user
        student = await requirements_service.get_student_by_user_id(
            current_user.user_id
        )

        # Validate that the submission belongs to this student
        await requirements_service.validate_submission_ownership(
            submission_id, student.id
        )

        # Get verification history using submission service
        history_data = (
            await submission_service.get_verification_history_by_submission_id(
                submission_id=submission_id
            )
        )

        dumped_data = {
            "verificationHistory": [
                vh.model_dump(by_alias=True) for vh in history_data.verification_history
            ],
            "totalCount": history_data.total_count,
            "submissionId": str(submission_id),
        }

        return ResponseBuilder.success(
            request=request,
            data=dumped_data,
            message=f"Retrieved {history_data.total_count} verification history record{'s' if history_data.total_count != 1 else ''} for submission",
            status_code=status.HTTP_200_OK,
        )

    except (BusinessLogicError, ValueError):
        raise
    except Exception as e:
        logger.error(f"Verification history retrieval error: {str(e)}")
        raise BusinessLogicError(
            "Failed to retrieve verification history",
        )

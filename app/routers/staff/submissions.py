from typing import Annotated

from fastapi import APIRouter, Depends, Request, status, Path

from app.db.session import get_sync_session
from app.services.staff.submission_service import (
    SubmissionService,
    get_submission_service,
)
from app.services.staff.dashboard_stats_service import (
    DashboardStatsService,
    get_dashboard_stats_service,
)
from app.schemas.staff.submission_schemas import (
    GetListOfSubmissions,
    VerificationHistoryListResponse,
    ManualVerificationRequestBody,
    VerificationHistoryResponse,
)
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError
from app.middlewares.auth_middleware import AuthState, require_staff
from app.services.notifications.utils import (
    create_notification_sync,
    get_user_id_from_student_identifier,
)

submissions_router = APIRouter(dependencies=[Depends(require_staff)])


@submissions_router.get(
    "/schedule/{schedule_id}",
    response_model=GetListOfSubmissions,
    status_code=status.HTTP_200_OK,
    summary="Get all submissions by schedule",
    description="Retrieve all student submissions (both submitted and unsubmitted) for a specific program requirement schedule",
)
async def get_submissions_by_schedule_id(
    request: Request,
    schedule_id: Annotated[str, Path(description="Program requirement schedule ID")],
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Get all student submissions for a specific program requirement schedule"""
    try:
        submissions_data = await submission_service.get_all_submissions_by_schedule_id(
            schedule_id=str(schedule_id)
        )

        dumped_data = {
            "submittedSubmissions": [
                s.model_dump(by_alias=True)
                for s in submissions_data.submitted_submissions
            ],
            "unsubmittedSubmissions": [
                s.model_dump(by_alias=True)
                for s in submissions_data.unsubmitted_submissions
            ],
            "submissionRelatedData": submissions_data.submission_related_data.model_dump(
                by_alias=True
            ),
        }

        total_students = len(submissions_data.submitted_submissions) + len(
            submissions_data.unsubmitted_submissions
        )
        return ResponseBuilder.success(
            request=request,
            data=dumped_data,
            message=f"Retrieved {total_students} student submissions for schedule {schedule_id}",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception as e:
        raise BusinessLogicError(
            message="Failed to retrieve submissions",
        )


@submissions_router.get(
    "/{submission_id}/verification-history",
    response_model=VerificationHistoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get verification history for a certificate submission",
    description="Retrieve all verification history records for a specific certificate submission, ordered by creation date descending",
)
async def get_verification_history_by_submission_id(
    request: Request,
    submission_id: Annotated[str, Path(description="Certificate submission ID")],
    submission_service: SubmissionService = Depends(get_submission_service),
):
    """Get verification history for a specific certificate submission"""
    try:
        history_data = (
            await submission_service.get_verification_history_by_submission_id(
                submission_id=str(submission_id)
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

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception as e:
        raise BusinessLogicError(
            message="Failed to retrieve verification history",
        )


@submissions_router.post(
    "/{submission_id}/verify",
    response_model=VerificationHistoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manual verification of a certificate submission",
    description="Perform manual verification of a certificate submission by staff member",
)
async def verify_submission(
    request: Request,
    submission_id: Annotated[str, Path(description="Certificate submission ID")],
    verification_data: ManualVerificationRequestBody,
    submission_service: SubmissionService = Depends(get_submission_service),
    dashboard_stats_service: DashboardStatsService = Depends(
        get_dashboard_stats_service
    ),
    current_user: AuthState = Depends(require_staff),
):
    """Perform manual verification of a certificate submission"""
    try:
        # Validate that submission_id in path matches the one in body
        if submission_id != verification_data.submission_id:
            raise ValueError("SUBMISSION_ID_MISMATCH")

        # Get verifier ID from auth context
        verifier_id = current_user.user_id

        # Create manual verification
        verification_result = await submission_service.create_manual_verification(
            verification_data=verification_data,
            verifier_id=str(verifier_id),
        )

        # Update dashboard stats based on verification result
        status_deltas = {
            "approved": {
                "approved_count_delta": 1,
                "manual_review_count_delta": -1,
                "manual_verification_count_delta": 1,
            },
            "rejected": {
                "rejected_count_delta": 1,
                "manual_review_count_delta": -1,
            },
        }

        deltas = status_deltas.get(verification_data.status, {})

        await dashboard_stats_service.update_dashboard_stats_by_schedule(
            requirement_schedule_id=str(verification_data.schedule_id), **deltas
        )

        # Create notification for student about verification result
        submission = await submission_service.get_submission_by_id(
            submission_id=str(submission_id)
        )

        for db_session in get_sync_session():
            student_user_id = await get_user_id_from_student_identifier(
                db_session, submission.student_id
            )

            if not student_user_id:
                raise ValueError("STUDENT_USER_NOT_FOUND")

            create_notification_sync(
                request_id=str(request.state.request_id),
                notification_code=(
                    "certificate_submission_verify"
                    if verification_data.status == "approved"
                    else "certificate_submission_reject"
                ),
                entity_id=submission.id,  # type: ignore
                actor_type="user",
                recipient_ids=[student_user_id],
                actor_id=verifier_id,
                scheduled_for=None,
                expires_at=None,
                in_app_enabled=True,
                line_app_enabled=True,
                metadata={"verifier_name": current_user.username},
            )

        return ResponseBuilder.success(
            request=request,
            data=verification_result.model_dump(by_alias=True),
            message=f"Submission {verification_data.status} successfully",
            status_code=status.HTTP_201_CREATED,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception as e:
        raise BusinessLogicError(
            message="Failed to verify submission",
        )

from typing import Annotated, List, cast

from fastapi import APIRouter, Depends, Request, status, Path

from app.services.staff.certificate_service import (
    CertificateService,
    get_certificate_service,
)
from app.schemas.staff.certificate_schemas import (
    GetCertificatesItem,
    UpdateCertificateRequest,
    CertificateResponse,
)
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError
from app.middlewares.auth_middleware import require_staff

certificates_router = APIRouter(dependencies=[Depends(require_staff)])


# API Endpoints
@certificates_router.get(
    "",
    response_model=List[GetCertificatesItem],
    status_code=status.HTTP_200_OK,
    summary="Get all certificate types with counts",
    description="Retrieve all certificate types with their basic information and counts of active/archived requirements and total submissions",
)
async def get_all_certificate_types(
    request: Request,
    certificate_service: CertificateService = Depends(get_certificate_service),
):
    """Get all certificate types with requirement and submission counts"""
    try:
        certificates_list = await certificate_service.get_all_certificates_with_counts()

        return ResponseBuilder.success(
            request=request,
            data=certificates_list,
            message=f"Retrieved {len(certificates_list)} certificate type{'s' if len(certificates_list) != 1 else ''}",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to retrieve certificate types",
        )


@certificates_router.put(
    "/{certificate_id}",
    response_model=CertificateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a certificate type",
    description="Update certificate type fields while preserving the REQUIRED_DATA_INPUT section of the verification template",
)
async def update_certificate_type(
    request: Request,
    certificate_id: Annotated[str, Path(description="Certificate type ID to update")],
    certificate_data: UpdateCertificateRequest,
    certificate_service: CertificateService = Depends(get_certificate_service),
):
    """Update a certificate type with template section preservation"""
    try:
        response_data = await certificate_service.update_certificate(
            certificate_id, certificate_data
        )

        return ResponseBuilder.success(
            request=request,
            data=response_data,
            message="Certificate type updated successfully",
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to update certificate type",
        )


@certificates_router.patch(
    "/{certificate_id}/archive",
    response_model=CertificateResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive a certificate type",
    description="Archive a certificate type and all its active requirements. Returns count of archived requirements.",
)
async def archive_certificate_type(
    request: Request,
    certificate_id: Annotated[str, Path(description="Certificate type ID to archive")],
    certificate_service: CertificateService = Depends(get_certificate_service),
):
    """Archive a certificate type and all its active requirements"""
    try:
        response_data = await certificate_service.archive_certificate(certificate_id)
        archived_count = response_data["archived_requirements_count"]
        message = CertificateService.build_archive_message(archived_count)

        return ResponseBuilder.success(
            request=request,
            data=cast(CertificateResponse, response_data["certificate"]).model_dump(
                by_alias=True
            ),
            message=message,
            status_code=status.HTTP_200_OK,
        )

    except (ValueError, RuntimeError) as e:
        raise e
    except Exception:
        raise BusinessLogicError(
            message="Failed to archive certificate type",
        )

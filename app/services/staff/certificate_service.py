from typing import Optional, List, Dict, Any

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, and_

from app.utils.logging import get_logger
from app.db.models import CertificateType, ProgramRequirement, CertificateSubmission
from app.db.session import get_sync_session
from app.schemas.staff.certificate_schemas import (
    GetCertificatesItem,
    UpdateCertificateRequest,
    CertificateResponse,
)

logger = get_logger()


class CertificateService:
    """Service for certificate-related operations"""

    def __init__(self, db: Session):
        self.db = db

    async def get_certificate_by_id(
        self, certificate_id: str
    ) -> Optional[CertificateType]:
        """Get certificate by ID"""
        return self.db.execute(
            select(CertificateType).where(CertificateType.id == certificate_id)
        ).scalar_one_or_none()

    async def check_certificate_code_exists(
        self, code: str, exclude_id: Optional[str] = None
    ) -> bool:
        """Check if certificate code already exists"""
        query = select(CertificateType).where(CertificateType.cert_code == code)
        if exclude_id:
            query = query.where(CertificateType.id != exclude_id)

        return self.db.execute(query).scalar_one_or_none() is not None

    async def get_all_certificates_with_counts(self) -> List[Dict[str, Any]]:
        """Get all certificate types with counts"""
        try:
            query = await self._build_query_with_counts()
            result = self.db.execute(query)

            certificates = []
            for row in result.all():
                item = GetCertificatesItem(
                    id=row.id,
                    cert_code=row.cert_code,
                    cert_name=row.cert_name,
                    description=row.description,
                    has_expiration=row.has_expiration,
                    is_active=row.is_active,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    active_requirements_count=row.active_requirements_count,
                    archived_requirements_count=row.archived_requirements_count,
                    total_submissions_count=row.total_submissions_count,
                )
                certificates.append(item.model_dump(by_alias=True))

            return certificates
        except Exception as e:
            raise e

    async def update_certificate(
        self, certificate_id: str, certificate_data: UpdateCertificateRequest
    ) -> CertificateResponse:
        """Update certificate"""
        certificate = await self.get_certificate_by_id(certificate_id)
        if not certificate:
            raise ValueError("CERTIFICATE_TYPE_NOT_FOUND")

        # Check for duplicate code
        if certificate_data.cert_code != certificate.cert_code:
            if await self.check_certificate_code_exists(
                certificate_data.cert_code, exclude_id=certificate_id
            ):
                raise ValueError("CERTIFICATE_CODE_EXISTS")

        try:
            # Update fields
            certificate.cert_code = certificate_data.cert_code
            certificate.cert_name = certificate_data.cert_name
            certificate.description = certificate_data.description
            certificate.has_expiration = certificate_data.has_expiration

            self.db.commit()
            logger.info(f"Updated certificate: {certificate.cert_code}")

            return CertificateResponse(
                id=certificate.id,
                cert_code=certificate.cert_code,
                cert_name=certificate.cert_name,
                description=certificate.description,
                has_expiration=certificate.has_expiration,
                created_at=certificate.created_at,
                updated_at=certificate.updated_at,
            )

        except IntegrityError:
            raise ValueError("CERTIFICATE_CODE_EXISTS")
        except Exception as e:
            raise e

    async def archive_certificate(self, certificate_id: str) -> Dict[str, Any]:
        """Archive certificate if no active requirements"""
        certificate = await self.get_certificate_by_id(certificate_id)
        if not certificate:
            raise ValueError("CERTIFICATE_TYPE_NOT_FOUND")

        if not certificate.is_active:
            raise ValueError("CERTIFICATE_TYPE_ALREADY_ARCHIVED")

        try:
            # Check for active requirements
            active_count = self.db.execute(
                select(func.count(ProgramRequirement.id)).where(
                    and_(
                        ProgramRequirement.cert_type_id == certificate_id,
                        ProgramRequirement.is_active == True,
                    )
                )
            ).scalar()

            if active_count and active_count > 0:
                plural = "s" if active_count != 1 else ""
                raise ValueError(
                    f"CERTIFICATE_TYPE_HAS_ACTIVE_REQUIREMENTS: {active_count} active requirement{plural} must be archived first"
                )

            certificate.is_active = False
            self.db.commit()
            self.db.refresh(certificate)

            logger.info(f"Archived certificate {certificate.cert_code}")

            return {
                "certificate": CertificateResponse(
                    id=certificate.id,
                    cert_code=certificate.cert_code,
                    cert_name=certificate.cert_name,
                    description=certificate.description,
                    has_expiration=certificate.has_expiration,
                    created_at=certificate.created_at,
                    updated_at=certificate.updated_at,
                ),
                "archived_requirements_count": 0,
            }

        except Exception as e:
            raise e

    async def _build_query_with_counts(self):
        """Build query with counts"""
        active_reqs = (
            select(
                ProgramRequirement.cert_type_id,
                func.count(ProgramRequirement.id).label("active_count"),
            )
            .where(ProgramRequirement.is_active == True)
            .group_by(ProgramRequirement.cert_type_id)
            .subquery()
        )

        archived_reqs = (
            select(
                ProgramRequirement.cert_type_id,
                func.count(ProgramRequirement.id).label("archived_count"),
            )
            .where(ProgramRequirement.is_active == False)
            .group_by(ProgramRequirement.cert_type_id)
            .subquery()
        )

        submissions = (
            select(
                CertificateSubmission.cert_type_id,
                func.count(CertificateSubmission.id).label("submissions_count"),
            )
            .group_by(CertificateSubmission.cert_type_id)
            .subquery()
        )

        return (
            select(
                CertificateType.id,
                CertificateType.cert_code,
                CertificateType.cert_name,
                CertificateType.description,
                CertificateType.has_expiration,
                CertificateType.is_active,
                CertificateType.created_at,
                CertificateType.updated_at,
                func.coalesce(active_reqs.c.active_count, 0).label(
                    "active_requirements_count"
                ),
                func.coalesce(archived_reqs.c.archived_count, 0).label(
                    "archived_requirements_count"
                ),
                func.coalesce(submissions.c.submissions_count, 0).label(
                    "total_submissions_count"
                ),
            )
            .outerjoin(active_reqs, CertificateType.id == active_reqs.c.cert_type_id)
            .outerjoin(
                archived_reqs, CertificateType.id == archived_reqs.c.cert_type_id
            )
            .outerjoin(submissions, CertificateType.id == submissions.c.cert_type_id)
            .order_by(CertificateType.created_at.asc())
        )

    @staticmethod
    def build_archive_message(archived_requirements_count: int) -> str:
        """Build archive success message with requirement count"""
        return f"{archived_requirements_count} program{'s' if archived_requirements_count != 1 else ''} archived successfully"


def get_certificate_service(
    db: Session = Depends(get_sync_session),
) -> CertificateService:
    """Dependency to provide CertificateService instance"""
    return CertificateService(db)

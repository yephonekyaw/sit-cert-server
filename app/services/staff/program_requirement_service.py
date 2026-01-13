from typing import Optional, Dict, Any, List
from datetime import date

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, desc, func

from app.utils.logging import get_logger
from app.db.models import (
    ProgramRequirement,
    Program,
    CertificateType,
    ProgramRequirementSchedule,
    AcademicYear,
)
from app.db.session import get_sync_session
from app.schemas.staff.program_requirement_schemas import (
    CreateProgramRequirementRequest,
    UpdateProgramRequirementRequest,
    GetProgramRequirementsItem,
    ProgramRequirementResponse,
)

logger = get_logger()


class ProgramRequirementService:
    """Service provider for program requirement-related business logic and database operations"""

    def __init__(self, db_session: Session):
        self.db = db_session

    # Core CRUD Operations
    async def get_requirement_by_id(
        self, requirement_id: str
    ) -> Optional[ProgramRequirement]:
        """Get program requirement by ID or return None if not found"""
        result = self.db.execute(
            select(ProgramRequirement).where(ProgramRequirement.id == requirement_id)
        )
        return result.scalar_one_or_none()

    async def create_requirement(
        self, requirement_data: CreateProgramRequirementRequest
    ) -> ProgramRequirementResponse:
        """Create a new program requirement with comprehensive validation"""
        # Validate program exists and is active
        program = await self._validate_program_exists_and_active(
            requirement_data.program_id
        )

        # Validate target year against program duration
        if requirement_data.target_year > program.duration_years:
            raise ValueError(
                f"TARGET_YEAR_EXCEEDS_PROGRAM_DURATION: Target year ({requirement_data.target_year}) cannot exceed program duration ({program.duration_years} years)"
            )

        # Validate certificate type exists and is active
        await self._validate_certificate_type_exists_and_active(
            requirement_data.cert_type_id
        )

        try:
            # Create deadline date (using year 2000 as base)
            deadline_date = date(
                2000, requirement_data.deadline_month, requirement_data.deadline_day
            )

            # Create the program requirement
            new_requirement = ProgramRequirement(
                program_id=requirement_data.program_id,
                cert_type_id=requirement_data.cert_type_id,
                name=requirement_data.name,
                target_year=requirement_data.target_year,
                deadline_date=deadline_date,
                grace_period_days=requirement_data.grace_period_days or 7,
                notification_days_before_deadline=requirement_data.notification_days_before_deadline
                or 90,
                is_mandatory=requirement_data.is_mandatory,
                is_active=requirement_data.is_active,
                special_instruction=requirement_data.special_instruction,
                recurrence_type=requirement_data.recurrence_type,
                effective_from_year=requirement_data.effective_from_year,
                effective_until_year=requirement_data.effective_until_year,
                months_before_deadline=requirement_data.months_before_deadline,
            )

            self.db.add(new_requirement)
            self.db.commit()
            self.db.refresh(new_requirement)

            logger.info(
                f"Created program requirement: {new_requirement.name} for program {program.program_code}"
            )

            return await self._build_program_requirement_response(new_requirement)

        except IntegrityError as e:
            error_msg = str(e.orig).lower()
            if "unique" in error_msg:
                raise ValueError("REQUIREMENT_ALREADY_EXISTS")
            else:
                raise ValueError("DATABASE_CONSTRAINT_VIOLATION")
        except Exception as e:
            raise e

    async def archive_requirement(
        self, requirement_id: str
    ) -> ProgramRequirementResponse:
        """Archive a program requirement with proper effective_until_year handling"""
        # Get the requirement to archive
        requirement = await self.get_requirement_by_id(requirement_id)
        if not requirement:
            raise ValueError("PROGRAM_REQUIREMENT_NOT_FOUND")

        if not requirement.is_active:
            raise ValueError("PROGRAM_REQUIREMENT_ALREADY_ARCHIVED")

        try:
            # Find the latest academic year for which we have created a schedule
            latest_academic_year = await self._get_latest_schedule_academic_year(
                requirement_id
            )

            # Update the requirement
            requirement.is_active = False

            # Update effective_until_year if needed
            if latest_academic_year:
                if (
                    requirement.effective_until_year is None
                    or requirement.effective_until_year > latest_academic_year
                ):
                    requirement.effective_until_year = latest_academic_year
                    logger.info(
                        f"Updated effective_until_year to {latest_academic_year} for requirement {requirement.name}"
                    )

            self.db.commit()
            self.db.refresh(requirement)

            logger.info(f"Archived program requirement: {requirement.name}")

            return await self._build_program_requirement_response(requirement)

        except Exception as e:
            raise e

    async def update_requirement(
        self,
        requirement_id: str,
        requirement_data: UpdateProgramRequirementRequest,
    ) -> ProgramRequirementResponse:
        """Update an existing program requirement with comprehensive validation"""
        # Get the existing requirement
        requirement = await self.get_requirement_by_id(requirement_id)
        if not requirement:
            raise ValueError("PROGRAM_REQUIREMENT_NOT_FOUND")

        # Validate that the program still exists and is active
        program = await self._validate_program_exists_and_active(requirement.program_id)

        # Validate target_year against program duration
        if requirement_data.target_year > program.duration_years:
            raise ValueError(
                f"TARGET_YEAR_EXCEEDS_PROGRAM_DURATION: Target year ({requirement_data.target_year}) cannot exceed program duration ({program.duration_years} years)"
            )

        # Get academic year boundaries for validation
        oldest_academic_year = await self._get_oldest_academic_year()
        latest_schedule_academic_year = await self._get_latest_schedule_academic_year(
            requirement_id
        )

        # Validate effective_from_year
        if (
            requirement_data.effective_from_year
            and oldest_academic_year
            and requirement_data.effective_from_year < oldest_academic_year
        ):
            raise ValueError(
                f"EFFECTIVE_FROM_YEAR_TOO_EARLY: effective_from_year ({requirement_data.effective_from_year}) cannot be earlier than the oldest academic year ({oldest_academic_year})"
            )

        # Validate effective_until_year
        if (
            requirement_data.effective_until_year
            and latest_schedule_academic_year
            and requirement_data.effective_until_year < latest_schedule_academic_year
        ):
            raise ValueError(
                f"EFFECTIVE_UNTIL_YEAR_TOO_EARLY: effective_until_year ({requirement_data.effective_until_year}) cannot be earlier than the latest academic year with created schedules ({latest_schedule_academic_year})"
            )

        try:
            # Create new deadline date (using year 2000 as base)
            deadline_date = date(
                2000, requirement_data.deadline_month, requirement_data.deadline_day
            )

            # Update the requirement with new values
            requirement.name = requirement_data.name
            requirement.target_year = requirement_data.target_year
            requirement.deadline_date = deadline_date
            requirement.grace_period_days = requirement_data.grace_period_days or 7
            requirement.notification_days_before_deadline = (
                requirement_data.notification_days_before_deadline or 90
            )
            requirement.is_mandatory = requirement_data.is_mandatory
            requirement.special_instruction = requirement_data.special_instruction
            requirement.recurrence_type = requirement_data.recurrence_type
            requirement.effective_from_year = requirement_data.effective_from_year
            requirement.effective_until_year = requirement_data.effective_until_year
            requirement.months_before_deadline = requirement_data.months_before_deadline

            self.db.commit()
            self.db.refresh(requirement)

            logger.info(f"Updated program requirement: {requirement.name}")

            return await self._build_program_requirement_response(requirement)

        except Exception as e:
            raise e

    async def get_all_requirements(self) -> List[Dict[str, Any]]:
        """Get all program requirements (both active and inactive) with schedule counts"""
        try:
            # Build schedule statistics subquery for all requirements
            schedule_stats_subquery = (
                select(
                    ProgramRequirementSchedule.program_requirement_id,
                    func.count(ProgramRequirementSchedule.id).label("schedules_count"),
                    func.max(ProgramRequirementSchedule.submission_deadline).label(
                        "latest_schedule_deadline"
                    ),
                )
                .group_by(ProgramRequirementSchedule.program_requirement_id)
                .subquery()
            )

            # Main query to get all requirements with related data and schedule statistics
            main_query = (
                select(
                    # Program requirement fields
                    ProgramRequirement.id,
                    ProgramRequirement.name,
                    ProgramRequirement.target_year,
                    ProgramRequirement.deadline_date,
                    ProgramRequirement.grace_period_days,
                    ProgramRequirement.notification_days_before_deadline,
                    ProgramRequirement.is_mandatory,
                    ProgramRequirement.is_active,
                    ProgramRequirement.special_instruction,
                    ProgramRequirement.recurrence_type,
                    ProgramRequirement.last_recurrence_at,
                    ProgramRequirement.effective_from_year,
                    ProgramRequirement.effective_until_year,
                    ProgramRequirement.months_before_deadline,
                    ProgramRequirement.created_at,
                    ProgramRequirement.updated_at,
                    # Program fields
                    ProgramRequirement.program_id,
                    Program.program_code,
                    Program.program_name,
                    # Certificate type fields
                    ProgramRequirement.cert_type_id,
                    CertificateType.cert_code,
                    CertificateType.cert_name,
                    # Schedule statistics
                    func.coalesce(schedule_stats_subquery.c.schedules_count, 0).label(
                        "schedules_count"
                    ),
                    schedule_stats_subquery.c.latest_schedule_deadline,
                )
                .join(Program, ProgramRequirement.program_id == Program.id)
                .join(
                    CertificateType,
                    ProgramRequirement.cert_type_id == CertificateType.id,
                )
                .outerjoin(
                    schedule_stats_subquery,
                    ProgramRequirement.id
                    == schedule_stats_subquery.c.program_requirement_id,
                )
                .order_by(ProgramRequirement.created_at.desc())
            )

            # Execute the query
            result = self.db.execute(main_query)
            requirements_data = result.all()

            # Transform to response models
            requirements_list = []
            for row in requirements_data:
                requirement_item = GetProgramRequirementsItem(
                    # Program requirement fields
                    id=row.id,
                    name=row.name,
                    target_year=row.target_year,
                    deadline_date=row.deadline_date,
                    grace_period_days=row.grace_period_days,
                    notification_days_before_deadline=row.notification_days_before_deadline,
                    is_mandatory=row.is_mandatory,
                    is_active=row.is_active,
                    special_instruction=row.special_instruction,
                    recurrence_type=row.recurrence_type,
                    last_recurrence_at=row.last_recurrence_at,
                    effective_from_year=row.effective_from_year,
                    effective_until_year=row.effective_until_year,
                    months_before_deadline=row.months_before_deadline,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    # Program information
                    program_id=row.program_id,
                    program_code=row.program_code,
                    program_name=row.program_name,
                    # Certificate type information
                    cert_type_id=row.cert_type_id,
                    cert_code=row.cert_code,
                    cert_name=row.cert_name,
                    # Schedule statistics
                    schedules_count=row.schedules_count,
                    latest_schedule_deadline=row.latest_schedule_deadline,
                )
                requirements_list.append(requirement_item.model_dump(by_alias=True))

            logger.info(f"Retrieved {len(requirements_list)} program requirements")
            return requirements_list

        except Exception as e:
            raise e

    # Helper Methods
    async def _validate_program_exists_and_active(self, program_id: str) -> Program:
        """Validate that program exists and is active"""
        program = self.db.get_one(Program, program_id)

        if not program:
            raise ValueError("PROGRAM_NOT_FOUND")

        if not program.is_active:
            raise ValueError("PROGRAM_NOT_ACTIVE")

        return program

    async def _validate_certificate_type_exists_and_active(self, cert_type_id: str):
        """Validate that certificate type exists and is active"""
        result = self.db.execute(
            select(CertificateType).where(CertificateType.id == cert_type_id)
        )
        cert_type = result.scalar_one_or_none()

        if not cert_type:
            raise ValueError("CERTIFICATE_TYPE_NOT_FOUND")

        if not cert_type.is_active:
            raise ValueError("CERTIFICATE_TYPE_NOT_ACTIVE")

    async def _get_oldest_academic_year(self) -> Optional[int]:
        """Get the oldest academic year from the system"""
        result = self.db.execute(
            select(AcademicYear.year_code)
            .order_by(AcademicYear.year_code.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_schedule_academic_year(
        self, requirement_id: str
    ) -> Optional[int]:
        """Get the latest academic year for which schedules have been created"""
        result = self.db.execute(
            select(AcademicYear.year_code)
            .join(
                ProgramRequirementSchedule,
                AcademicYear.id == ProgramRequirementSchedule.academic_year_id,
            )
            .where(ProgramRequirementSchedule.program_requirement_id == requirement_id)
            .order_by(desc(AcademicYear.year_code))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _build_program_requirement_response(
        self, requirement: ProgramRequirement
    ) -> ProgramRequirementResponse:
        """Build a standardized ProgramRequirementResponse from a ProgramRequirement model"""
        return ProgramRequirementResponse(
            id=requirement.id,  # type: ignore
            program_id=requirement.program_id,  # type: ignore
            cert_type_id=requirement.cert_type_id,  # type: ignore
            name=requirement.name,
            target_year=requirement.target_year,
            deadline_date=requirement.deadline_date,
            grace_period_days=requirement.grace_period_days,
            notification_days_before_deadline=requirement.notification_days_before_deadline,
            is_mandatory=requirement.is_mandatory,
            is_active=requirement.is_active,
            special_instruction=requirement.special_instruction,
            recurrence_type=requirement.recurrence_type,
            effective_from_year=requirement.effective_from_year,
            effective_until_year=requirement.effective_until_year,
            months_before_deadline=requirement.months_before_deadline,
            created_at=requirement.created_at,
            updated_at=requirement.updated_at,
        )


# Dependency injection for service provider
def get_program_requirement_service(
    db: Session = Depends(get_sync_session),
) -> ProgramRequirementService:
    """Dependency to provide ProgramRequirementService instance"""
    return ProgramRequirementService(db)

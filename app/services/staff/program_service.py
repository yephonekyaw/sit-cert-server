from typing import Optional, Sequence, List, Dict, Any

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, and_

from app.utils.logging import get_logger
from app.db.models import Program, ProgramRequirement
from app.db.session import get_sync_session
from app.schemas.staff.program_schemas import (
    CreateProgramRequest,
    UpdateProgramRequest,
    ProgramResponse,
    GetProgramsItem,
    ProgramListQueryParams,
)

logger = get_logger()


class ProgramService:
    """Service provider for program-related business logic and database operations"""

    def __init__(self, db_session: Session):
        self.db = db_session

    # Core CRUD Operations
    async def get_program_by_id(self, program_id: str) -> Optional[Program]:
        """Get program by ID or return None if not found"""
        result = self.db.execute(select(Program).where(Program.id == program_id))
        return result.scalar_one_or_none()

    async def check_program_code_exists(
        self, program_code: str, exclude_id: Optional[str] = None
    ) -> bool:
        """Check if program code already exists (optionally excluding a specific ID)"""
        query = select(Program).where(Program.program_code == program_code)
        if exclude_id:
            query = query.where(Program.id != exclude_id)

        result = self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def create_program(
        self, program_data: CreateProgramRequest
    ) -> ProgramResponse:
        """Create a new program with validation"""
        # Check if program code already exists
        if await self.check_program_code_exists(program_data.program_code):
            raise ValueError("Program code already exists")

        try:
            # Create new program
            new_program = Program(
                program_code=program_data.program_code,
                program_name=program_data.program_name,
                description=program_data.description,
                duration_years=program_data.duration_years,
                is_active=program_data.is_active,
            )

            self.db.add(new_program)
            self.db.commit()
            self.db.refresh(new_program)

            logger.info(f"Created new program: {new_program.program_code}")
            return self._create_program_response(new_program)

        except IntegrityError as e:
            raise ValueError("Program code already exists")
        except Exception as e:
            raise e

    async def update_program(
        self, program_id: str, program_data: UpdateProgramRequest
    ) -> ProgramResponse:
        """Update an existing program with validation"""
        # Check if program exists
        program = await self.get_program_by_id(program_id)
        if not program:
            raise ValueError("Program not found")

        # Check if another program already has this code (excluding current program)
        if program_data.program_code != program.program_code:
            if await self.check_program_code_exists(
                program_data.program_code, exclude_id=program_id
            ):
                raise ValueError("Program code already exists")

        # Validate duration_years change against active program requirements
        if program_data.duration_years != program.duration_years:
            conflicting_requirements = await self._get_conflicting_requirements(
                program_id, program_data.duration_years
            )

            if conflicting_requirements:
                requirement_details = [
                    f"'{req.name}' (target year: {req.target_year})"
                    for req in conflicting_requirements
                ]
                raise ValueError(f"{', '.join(requirement_details)}")

        try:
            # Update program fields
            program.program_code = program_data.program_code
            program.program_name = program_data.program_name
            program.description = program_data.description
            program.duration_years = program_data.duration_years

            self.db.commit()
            self.db.refresh(program)

            logger.info(f"Updated program: {program.program_code}")
            return self._create_program_response(program)

        except IntegrityError as e:
            raise ValueError("Program code already exists")
        except Exception as e:
            raise e

    async def archive_program(self, program_id: str) -> Dict[str, Any]:
        """Archive a program only if it has no active requirements"""
        # Check if program exists
        program = await self.get_program_by_id(program_id)
        if not program:
            raise ValueError("Program not found")

        # Check if program is already archived
        if not program.is_active:
            raise ValueError("Program already archived")

        try:
            # Check if program has any active requirements
            active_requirements_result = self.db.execute(
                select(func.count(ProgramRequirement.id)).where(
                    and_(
                        ProgramRequirement.program_id == program_id,
                        ProgramRequirement.is_active == True,
                    )
                )
            )
            active_requirements_count = active_requirements_result.scalar()

            # Prevent archiving if there are active requirements
            if active_requirements_count is not None and active_requirements_count > 0:
                raise ValueError(
                    f"{active_requirements_count} active requirement{'s' if active_requirements_count != 1 else ''} found"
                )

            # Archive the program (no requirements to archive)
            program.is_active = False

            self.db.commit()
            self.db.refresh(program)

            logger.info(f"Archived program {program.program_code}")

            return {
                "program": self._create_program_response(program),
                "archived_requirements_count": 0,
            }

        except Exception as e:
            raise e

    async def get_all_programs_with_counts(
        self, query_params: ProgramListQueryParams
    ) -> List[Dict[str, Any]]:
        """Get all programs with requirement counts, filtering and sorting"""
        try:
            # Build query with requirement counts
            programs_query = self._build_programs_query_with_counts()

            # Apply filters and sorting
            programs_query = self._apply_filters_and_sorting(
                programs_query, query_params
            )

            # Execute query
            result = self.db.execute(programs_query)
            programs_data = result.all()

            # Transform to response models
            programs_list = []
            for row in programs_data:
                program_item = GetProgramsItem(
                    id=row.id,
                    program_code=row.program_code,
                    program_name=row.program_name,
                    description=row.description,
                    duration_years=row.duration_years,
                    is_active=row.is_active,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    active_requirements_count=row.active_requirements_count,
                    archived_requirements_count=row.archived_requirements_count,
                )
                programs_list.append(program_item.model_dump(by_alias=True))

            return programs_list

        except Exception as e:
            raise e

    # Helper Methods
    async def _get_conflicting_requirements(
        self, program_id: str, new_duration: int
    ) -> Sequence[ProgramRequirement]:
        """Get active requirements that conflict with new program duration"""
        result = self.db.execute(
            select(ProgramRequirement).where(
                and_(
                    ProgramRequirement.program_id == program_id,
                    ProgramRequirement.is_active == True,
                    ProgramRequirement.target_year > new_duration,
                )
            )
        )
        return result.scalars().all()

    def _create_program_response(self, program: Program) -> ProgramResponse:
        """Create standardized program response data"""
        program_response = ProgramResponse(
            id=program.id,
            program_code=program.program_code,
            program_name=program.program_name,
            description=program.description,
            duration_years=program.duration_years,
            is_active=program.is_active,
            created_at=program.created_at,
            updated_at=program.updated_at,
        )
        return program_response

    def _build_programs_query_with_counts(self):
        """Build query for programs with requirement counts"""
        # Subquery for active requirements count
        active_req_subquery = (
            select(
                ProgramRequirement.program_id,
                func.count(ProgramRequirement.id).label("active_count"),
            )
            .where(ProgramRequirement.is_active == True)
            .group_by(ProgramRequirement.program_id)
            .subquery()
        )

        # Subquery for archived requirements count
        archived_req_subquery = (
            select(
                ProgramRequirement.program_id,
                func.count(ProgramRequirement.id).label("archived_count"),
            )
            .where(ProgramRequirement.is_active == False)
            .group_by(ProgramRequirement.program_id)
            .subquery()
        )

        # Main query with requirement counts
        return (
            select(
                Program.id,
                Program.program_code,
                Program.program_name,
                Program.description,
                Program.duration_years,
                Program.is_active,
                Program.created_at,
                Program.updated_at,
                func.coalesce(active_req_subquery.c.active_count, 0).label(
                    "active_requirements_count"
                ),
                func.coalesce(archived_req_subquery.c.archived_count, 0).label(
                    "archived_requirements_count"
                ),
            )
            .outerjoin(
                active_req_subquery, Program.id == active_req_subquery.c.program_id
            )
            .outerjoin(
                archived_req_subquery, Program.id == archived_req_subquery.c.program_id
            )
        )

    def _apply_filters_and_sorting(self, query, params: ProgramListQueryParams):
        """Apply filters and sorting to programs query"""
        # Apply filters
        if params.is_active is not None:
            query = query.where(Program.is_active == params.is_active)

        if params.program_code:
            # Sanitize input and use case-insensitive search
            sanitized_code = params.program_code.strip()
            if sanitized_code:
                query = query.where(Program.program_code.ilike(f"%{sanitized_code}%"))

        # Apply sorting
        sort_column = getattr(Program, params.sort_by or "created_at")
        if params.order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        return query

    @staticmethod
    def build_success_message(
        programs_count: int, params: ProgramListQueryParams
    ) -> str:
        """Build descriptive success message based on filters and sorting"""
        message_parts = [
            f"Retrieved {programs_count} program{'s' if programs_count != 1 else ''}"
        ]

        if params.is_active is not None:
            status_text = "active" if params.is_active else "archived"
            message_parts.append(f"filtered by {status_text} status")

        if params.program_code:
            message_parts.append(f"matching code '{params.program_code}'")

        if params.sort_by != "created_at" or params.order != "desc":
            message_parts.append(f"sorted by {params.sort_by} ({params.order})")

        return " ".join(message_parts)

    @staticmethod
    def build_archive_message(archived_requirements_count: int) -> str:
        """Build archive success message with requirement count"""
        return f"{archived_requirements_count} program{'s' if archived_requirements_count != 1 else ''} archived successfully"


# Dependency injection for service provider
def get_program_service(
    db: Session = Depends(get_sync_session),
) -> ProgramService:
    """Dependency to provide ProgramService instance"""
    return ProgramService(db)

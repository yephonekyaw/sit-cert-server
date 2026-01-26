from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_sync_session
from app.db.models import AcademicYear
from app.schemas.staff.academic_year_schemas import GetAcademicYearsItem
from app.utils.responses import ResponseBuilder
from app.utils.errors import BusinessLogicError
from app.middlewares.auth_middleware import require_staff

academic_years_router = APIRouter(dependencies=[Depends(require_staff)])


@academic_years_router.get(
    "",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Get all academic years",
    description="Retrieve all academic years available in the system, ordered by year code.",
)
async def get_academic_years(
    request: Request,
    db: Session = Depends(get_sync_session),
):
    """Get all academic years"""
    try:
        # Query all academic years ordered by year_code
        query = select(AcademicYear).order_by(AcademicYear.year_code.desc())
        result = db.execute(query)
        academic_years = result.scalars().all()

        # Transform to response format
        academic_years_data = []
        for academic_year in academic_years:
            item = GetAcademicYearsItem(
                id=academic_year.id,  # type: ignore
                year_code=academic_year.year_code,
                start_date=academic_year.start_date,
                end_date=academic_year.end_date,
                is_current=academic_year.is_current,
                created_at=academic_year.created_at,
                updated_at=academic_year.updated_at,
            )
            academic_years_data.append(item.model_dump(by_alias=True))

        message = f"Retrieved {len(academic_years_data)} academic year{'s' if len(academic_years_data) != 1 else ''} successfully"

        return ResponseBuilder.success(
            request=request,
            data=academic_years_data,
            message=message,
            status_code=status.HTTP_200_OK,
        )

    except Exception as e:
        raise BusinessLogicError(
            message="Failed to retrieve academic years",
        )

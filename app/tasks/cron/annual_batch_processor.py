import asyncio
import httpx
from datetime import datetime
from sqlalchemy import select

from app.celery import celery
from app.config.settings import settings
from app.db.session import get_sync_session
from app.utils.logging import get_logger
from app.utils.datetime_utils import from_bangkok_to_naive_utc, utc_now
from app.db.models import (
    AcademicYear,
    Program,
    Student,
    User,
    UserType,
    EnrollmentStatus,
)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def annual_batch_processor_task(self, request_id: str, **kwargs):
    """
    Synchronizes the student database with an external source for the new academic year.

    This task fetches a list of newly admitted students from the student information system API.
    It then compares this list with the existing students in the database and adds any new students.
    This is typically run at the beginning of a new academic year to provision student accounts.
    """
    return asyncio.run(_async_annual_batch_processor(request_id, **kwargs))


async def _async_annual_batch_processor(request_id: str, **kwargs):
    logger = get_logger().bind(request_id=request_id)

    for db_session in get_sync_session():
        try:
            current_datetime = kwargs.get("current_datetime", utc_now())
            current_academic_year = _calculate_current_academic_year(current_datetime)
            current_thai_academic_year = _convert_to_thai_academic_year(
                current_academic_year
            )
            logger.info(
                "Starting annual batch processing for academic year.",
                academic_year=current_academic_year,
            )

            # Get or Create Academic Year
            academic_year_result = db_session.execute(
                select(AcademicYear).where(
                    AcademicYear.year_code == current_academic_year
                )
            )
            academic_year = academic_year_result.scalar_one_or_none()

            if not academic_year:
                logger.info(
                    "Current academic year not found, creating a new one.",
                    academic_year=current_academic_year,
                )

                # Start: August 1 at 00:00:00 Bangkok time
                start_date = from_bangkok_to_naive_utc(
                    datetime(current_academic_year, 8, 1, 0, 0, 0)
                )

                # End: May 31 at 23:59:59 Bangkok time of the following year
                end_date = from_bangkok_to_naive_utc(
                    datetime(current_academic_year + 1, 5, 31, 23, 59, 59)
                )

                new_academic_year = AcademicYear(
                    year_code=current_academic_year,
                    start_date=start_date,
                    end_date=end_date,
                    is_current=True,
                )
                db_session.add(new_academic_year)
                db_session.flush()
                academic_year = new_academic_year
                logger.info(
                    "New academic year created.",
                    academic_year_id=academic_year.id,
                )

            academic_year_id = academic_year.id

            # Create program lookup table
            programs_result = db_session.execute(
                select(Program.id, Program.program_name)
            )
            program_lookup = {name: str(id) for id, name in programs_result}

            # Create student lookup set
            students_result = db_session.execute(
                select(Student.student_id).where(
                    Student.academic_year_id == academic_year_id
                )
            )
            existing_student_ids = {row[0] for row in students_result}

            # Fetch data from external API
            api_url = f"{settings.SITBRAIN_BASE_URL}/users/profile/studentsFromYear?academicYear={current_thai_academic_year}"

            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(api_url, timeout=30.0)
                    response.raise_for_status()
                    api_students = response.json()
                except httpx.RequestError as e:
                    logger.error(
                        "Failed to fetch student data from API.",
                        url=e.request.url,
                        error=str(e),
                    )
                    return {"status": "error", "message": str(e)}

            # Filter out existing students and process new ones
            new_student_data = [
                s
                for s in api_students
                if s.get("studentId") not in existing_student_ids
            ]

            new_users_to_add = []
            skipped_due_to_program = 0

            for student_data in new_student_data:
                student_id = student_data.get("studentId")
                program_name_eng = student_data.get("programNameEng")

                if not student_id or not program_name_eng:
                    continue

                program_id = program_lookup.get(program_name_eng)
                if not program_id:
                    skipped_due_to_program += 1
                    continue

                # Create User and Student objects
                username = student_id

                new_user = User(
                    username=username,
                    first_name=student_data["firstnameEng"].title(),
                    last_name=student_data["lastnameEng"].title(),
                    user_type=UserType.STUDENT,
                    is_active=True,
                )

                Student(
                    user=new_user,
                    sit_email=f"{student_id}@sit.kmutt.ac.th",
                    student_id=student_id,
                    program_id=program_id,
                    academic_year_id=academic_year_id,
                    enrollment_status=EnrollmentStatus.ACTIVE,
                )

                new_users_to_add.append(new_user)

            if new_users_to_add:
                db_session.add_all(new_users_to_add)
                db_session.commit()

            total_from_api = len(api_students)
            new_student_count = len(new_users_to_add)

            logger.info(
                "Annual batch processing finished.",
                total_from_api=total_from_api,
                new_students_added=new_student_count,
                skipped_existing=total_from_api - len(new_student_data),
                skipped_program_not_found=skipped_due_to_program,
            )

            return {
                "status": "success",
                "message": f"Students {new_student_count} added",
            }

        except Exception as e:
            logger.error(
                "Annual batch processor task exception",
                request_id=request_id,
                error=str(e),
                exc_info=True,
            )
            return {"status": "error", "message": str(e)}


def _convert_to_thai_academic_year(gregorian_year: int) -> int:
    """Convert Gregorian year to Thai academic year (Buddhist Era)"""
    return gregorian_year + 543


def _calculate_current_academic_year(current_datetime: datetime) -> int:
    """
    Calculate the current academic year based on the date.
    Academic year runs from August to May.

    Examples:
    - January 2025 -> Academic Year 2024 (Aug 2024 - May 2025)
    - August 2024 -> Academic Year 2024 (Aug 2024 - May 2025)
    - July 2024 -> Academic Year 2023 (Aug 2023 - May 2024)
    """
    if current_datetime.month >= 8:  # August or later
        return current_datetime.year
    else:  # Before August
        return current_datetime.year - 1

import uuid
from sqlalchemy.orm import Session
from sqlalchemy import delete, select

from app.db.models import (
    User,
    Student,
    Program,
    AcademicYear,
    UserType,
    EnrollmentStatus,
)
from app.utils.logging import get_logger

logger = get_logger()


def seed_users_students(db_session: Session):
    """Sync version: Seed users and students data - clear existing and add new"""

    # Clear existing students and users
    db_session.execute(delete(Student))
    db_session.execute(delete(User))
    db_session.commit()

    # Get required references
    program_result = db_session.execute(
        select(Program).where(Program.program_code == "Bc.CS")
    )
    program = program_result.scalar_one_or_none()
    if not program:
        logger.error("Program Bc.CS not found")
        return

    academic_year_result = db_session.execute(
        select(AcademicYear).where(AcademicYear.year_code == 2023)
    )
    academic_year = academic_year_result.scalar_one_or_none()
    if not academic_year:
        logger.error("Academic year 2023 not found")
        return

    students_data = [
        ("66130500801", "66130500801@ad.sit.kmutt.ac.th", "Akari Kyaw", "Thein"),
        ("66130500802", "66130500802@ad.sit.kmutt.ac.th", "Ant Bone", "Kyaw"),
        ("66130500803", "66130500803@ad.sit.kmutt.ac.th", "Aung Moe", "Lin"),
        ("66130500804", "66130500804@ad.sit.kmutt.ac.th", "Aye Chan", "Aung"),
        ("66130500806", "66130500806@ad.sit.kmutt.ac.th", "Daniel Bawm", "Ying"),
        ("66130500807", "66130500807@ad.sit.kmutt.ac.th", "Han Win", "Aung"),
        ("66130500808", "66130500808@ad.sit.kmutt.ac.th", "Hnin Ei", "Ei Aung"),
        ("66130500809", "66130500809@ad.sit.kmutt.ac.th", "Ismail Umar", "Ajingi"),
        ("66130500810", "66130500810@ad.sit.kmutt.ac.th", "Kaung Hset", "Hein"),
        ("66130500812", "66130500812@ad.sit.kmutt.ac.th", "Khaing Zin", "Than"),
        ("66130500813", "66130500813@ad.sit.kmutt.ac.th", "Kyaw Nanda", "Thu"),
        ("66130500814", "66130500814@ad.sit.kmutt.ac.th", "Louise Madison", "Maganda"),
        ("66130500815", "66130500815@ad.sit.kmutt.ac.th", "Min Paing", "Hein"),
        ("66130500817", "66130500817@ad.sit.kmutt.ac.th", "Nay Chi", "Lin Lei"),
        ("66130500818", "66130500818@ad.sit.kmutt.ac.th", "Ngwe Yee", "Pearl Ou"),
        ("66130500819", "66130500819@ad.sit.kmutt.ac.th", "Oakkar", "Min"),
        ("66130500821", "66130500821@ad.sit.kmutt.ac.th", "Sai Zaw", "Oo"),
        ("66130500822", "66130500822@ad.sit.kmutt.ac.th", "Shine Min", "Khant"),
        ("66130500823", "66130500823@ad.sit.kmutt.ac.th", "Swan Htet", "Naing"),
        ("66130500824", "66130500824@ad.sit.kmutt.ac.th", "Thaw Zin", "Moe Myint"),
        ("66130500825", "66130500825@ad.sit.kmutt.ac.th", "Thin Nwe", "Soe"),
        ("66130500826", "66130500826@ad.sit.kmutt.ac.th", "Vikaskumar", "Dubey"),
        ("66130500829", "66130500829@ad.sit.kmutt.ac.th", "Ye", "Moe"),
        ("66130500830", "66130500830@ad.sit.kmutt.ac.th", "Ye Phone", "Kyaw"),
        ("66130500831", "66130500831@ad.sit.kmutt.ac.th", "Ye", "Thu"),
        ("66130500832", "66130500832@ad.sit.kmutt.ac.th", "Kornthana", "Kamonnanthin"),
        ("66130500834", "66130500834@ad.sit.kmutt.ac.th", "Kitsanatorn", "Tachovarojd"),
        ("66130500836", "66130500836@ad.sit.kmutt.ac.th", "Jiratanuth", "Rahman"),
        ("66130500837", "66130500837@ad.sit.kmutt.ac.th", "Jirapat", "Ruengsri"),
        ("66130500838", "66130500838@ad.sit.kmutt.ac.th", "Chayada", "Muangboonsri"),
        ("66130500840", "66130500840@ad.sit.kmutt.ac.th", "Chawisa", "Kaewphinit"),
        ("66130500841", "66130500841@ad.sit.kmutt.ac.th", "Thitapa", "Ritnamsuk"),
        ("66130500842", "66130500842@ad.sit.kmutt.ac.th", "Nattawadee", "Wuttivoradit"),
        ("66130500843", "66130500843@ad.sit.kmutt.ac.th", "Nudhana", "Sarutipaisan"),
        ("66130500844", "66130500844@ad.sit.kmutt.ac.th", "Thirawat", "Kongnil"),
        (
            "66130500845",
            "66130500845@ad.sit.kmutt.ac.th",
            "Thanakit",
            "Keeratiphechngam",
        ),
        ("66130500846", "66130500846@ad.sit.kmutt.ac.th", "Nannicha", "Phraemetta"),
        ("66130500847", "66130500847@ad.sit.kmutt.ac.th", "Badeesorn", "Sittikong"),
        (
            "66130500848",
            "66130500848@ad.sit.kmutt.ac.th",
            "Prapangkorn",
            "Thangsathityangkul",
        ),
        ("66130500849", "66130500849@ad.sit.kmutt.ac.th", "Prechaya", "Maksap"),
        ("66130500850", "66130500850@ad.sit.kmutt.ac.th", "Punyapat", "Jaisuk"),
        ("66130500851", "66130500851@ad.sit.kmutt.ac.th", "Pochvasin", "Parinyaprach"),
        ("66130500852", "66130500852@ad.sit.kmutt.ac.th", "Ponkrit", "Sukprasert"),
        ("66130500853", "66130500853@ad.sit.kmutt.ac.th", "Francesco Lo", "Cascio"),
        ("66130500854", "66130500854@ad.sit.kmutt.ac.th", "Ratthaphum", "Songphrom"),
        ("66130500856", "66130500856@ad.sit.kmutt.ac.th", "Supakrit", "Duangsri"),
        (
            "66130500857",
            "66130500857@ad.sit.kmutt.ac.th",
            "Siriyakorn",
            "Dee-udomvongsa",
        ),
        (
            "66130500858",
            "66130500858@ad.sit.kmutt.ac.th",
            "Suriya",
            "Upariphutthiphong",
        ),
        ("66130500859", "66130500859@ad.sit.kmutt.ac.th", "Akaradech", "Konta"),
    ]

    users = []
    students = []

    # Create users and students
    for student_id, email, first_name, last_name in students_data:
        # Create user
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username=student_id,
            first_name=first_name,
            last_name=last_name,
            user_type=UserType.STUDENT,
            is_active=True,
        )
        users.append(user)

        # Create student
        student = Student(
            id=str(uuid.uuid4()),
            user_id=user_id,
            sit_email=email,
            student_id=student_id,
            program_id=program.id,
            academic_year_id=academic_year.id,
            enrollment_status=EnrollmentStatus.ACTIVE,
        )
        students.append(student)

    # Add to database
    db_session.add_all(users)
    db_session.add_all(students)
    db_session.commit()
    logger.info(
        f"Seeded {len(users)} users and {len(students)} students for 2023 Bc.CS cohort"
    )

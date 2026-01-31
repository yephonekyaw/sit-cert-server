if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select
    from app.db.models import Student, User
    from app.db.session import get_sync_session

    with next(get_sync_session()) as session:
        student = session.execute(select(Student).limit(1)).scalar_one()
        user = session.get_one(User, student.user_id)

    print(user.__dict__)

    pass

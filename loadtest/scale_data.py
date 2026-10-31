"""Add a realistic amount of data to a database that already has the demo seed, so load tests do not run
against 44 students. Adds classes 1-11 with parallels А-Г to every school (skipping ones that exist), 25 active
students each, with plausible repeating names (so searches find several people).

    DATABASE_URL=postgresql+asyncpg://luwo:luwo@localhost:5433/luwo_loadtest PYTHONPATH=. python loadtest/scale_data.py

Only run it on the load-test database: it adds rows and never deletes any."""

import asyncio
import random

from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.config import settings
from app.db import models as m
from app.db.session import SessionFactory, engine

FIRST = ["Амир", "Алина", "Данияр", "Айгерим", "Эрмек", "Нурбек", "Асель", "Тимур", "Мээрим", "Адиль", "Бекзат", "Сезим"]
LAST = ["Касымов", "Жумаев", "Смирнова", "Иманов", "Исаков", "Бакиров", "Назарова", "Осмонова", "Ибраев", "Токтогулов"]
STUDENTS_PER_CLASS = 25


def refuse_unless_load_test_database() -> None:
    """DATABASE_URL falls back to the development database when it is not set. Never add thousands of rows there."""
    name = make_url(settings.database_url).database or ""
    if not name.endswith("_loadtest"):
        raise SystemExit(f"Refusing to run: database '{name}' is not a load-test database (its name must end with _loadtest). "
                         "Set DATABASE_URL, see the top of this file.")


async def main() -> None:
    refuse_unless_load_test_database()
    random.seed(1)
    async with SessionFactory() as session:
        schools = (await session.execute(select(m.School.id))).scalars().all()
        for school_id in schools:
            existing = set((await session.execute(select(m.SchoolClass.name).where(m.SchoolClass.school_id == school_id))).scalars())
            for grade in range(1, 12):
                for parallel in "АБВГ":
                    name = f"{grade}{parallel}"
                    if name in existing:
                        continue
                    cls = m.SchoolClass(school_id=school_id, name=name)
                    session.add(cls)
                    await session.flush()
                    session.add_all(
                        m.Student(school_id=school_id, class_id=cls.id, full_name=f"{random.choice(FIRST)} {random.choice(LAST)}", status="active")
                        for _ in range(STUDENTS_PER_CLASS)
                    )
        await session.commit()
        classes = (await session.execute(text("SELECT count(*) FROM classes"))).scalar()
        students = (await session.execute(text("SELECT count(*) FROM students"))).scalar()
        print(f"classes: {classes}, students: {students}")
    await engine.dispose()


asyncio.run(main())

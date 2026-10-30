"""Fills the Postgres database with the demo world from seed/world.py. Wipes existing data first.

Run:  python -m seed.seed
"""

import asyncio

from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import models as m
from app.db.session import SessionFactory, engine
from seed.world import DEMO_PASSWORD, build_world

TABLES_WITH_SERIAL_IDS = ["schools", "users", "classes", "students", "change_log"]


async def seed(session_factory=SessionFactory, password_hash: str | None = None) -> None:
    world = build_world(password_hash=password_hash or hash_password(DEMO_PASSWORD))

    async with session_factory() as session:
        await session.execute(text(
            "TRUNCATE change_log, pending_actions, request_log, class_teachers, "
            "students, classes, users, schools RESTART IDENTITY CASCADE"
        ))

        # Explicit ids, inserted parents first so foreign keys are satisfied.
        session.add_all(m.School(id=s.id, name=s.name) for s in world.schools)
        await session.flush()
        session.add_all(
            m.User(
                id=u.id, email=u.email, full_name=u.full_name, role=u.role.value,
                school_id=u.school_id, is_active=u.is_active, password_hash=u.password_hash,
            )
            for u in world.users
        )
        session.add_all(m.SchoolClass(id=c.id, school_id=c.school_id, name=c.name) for c in world.classes)
        await session.flush()
        session.add_all(m.ClassTeacher(class_id=c, teacher_id=t) for c, t in world.class_teachers)
        session.add_all(
            m.Student(
                id=s.id, school_id=s.school_id, class_id=s.class_id,
                full_name=s.full_name, status=s.status.value,
            )
            for s in world.students
        )
        await session.flush()
        session.add_all(
            m.ChangeLog(
                at=e.at, actor_user_id=e.actor_user_id, action=e.action, entity_type=e.entity_type,
                entity_id=e.entity_id, school_id=e.school_id, before=e.before, after=e.after,
                source=e.source,
            )
            for e in world.history
        )
        await session.flush()

        # We inserted explicit ids, so move each id counter past the highest one used.
        for table in TABLES_WITH_SERIAL_IDS:
            await session.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))"
            ))
        await session.commit()

    print(
        f"Seeded {len(world.schools)} schools, {len(world.users)} users, "
        f"{len(world.students)} students. Demo password for all users: {DEMO_PASSWORD}"
    )


async def main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

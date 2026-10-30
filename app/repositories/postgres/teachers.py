from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.errors import NotFound
from app.domain.models import Role, Teacher


def _query():
    return select(m.User).where(m.User.role == Role.TEACHER).execution_options(populate_existing=True)


def _to_domain(user: m.User) -> Teacher:
    return Teacher(
        id=user.id,
        school_id=user.school_id,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
    )


class PostgresTeacherRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, teacher_id: int) -> Teacher | None:
        user = (await self.session.execute(_query().where(m.User.id == teacher_id))).scalar_one_or_none()
        return _to_domain(user) if user else None

    async def list_by_school(self, school_id: int, *, include_inactive: bool = False) -> list[Teacher]:
        query = _query().where(m.User.school_id == school_id)
        if not include_inactive:
            query = query.where(m.User.is_active)
        rows = await self.session.execute(query.order_by(m.User.full_name, m.User.id))
        return [_to_domain(u) for u in rows.scalars()]

    async def find_by_name(self, name: str, school_id: int | None) -> list[Teacher]:
        query = _query().where(m.User.full_name.icontains(name, autoescape=True))
        if school_id is not None:
            query = query.where(m.User.school_id == school_id)
        rows = await self.session.execute(query.order_by(m.User.full_name, m.User.id))
        return [_to_domain(u) for u in rows.scalars()]

    async def list_for_classes(self, class_ids: list[int]) -> dict[int, list[Teacher]]:
        result: dict[int, list[Teacher]] = {class_id: [] for class_id in class_ids}
        if not class_ids:
            return result
        rows = await self.session.execute(
            select(m.ClassTeacher.class_id, m.User)
            .join(m.User, m.User.id == m.ClassTeacher.teacher_id)
            .where(m.ClassTeacher.class_id.in_(class_ids), m.User.is_active)
            .order_by(m.User.full_name)
            .execution_options(populate_existing=True)
        )
        for class_id, user in rows:
            result[class_id].append(_to_domain(user))
        return result

    async def add(self, *, school_id: int, full_name: str, email: str | None = None) -> Teacher:
        user = m.User(school_id=school_id, full_name=full_name, email=email, role=Role.TEACHER.value)
        self.session.add(user)
        await self.session.flush()
        return _to_domain(user)

    async def set_active(self, teacher_id: int, is_active: bool) -> Teacher:
        await self.session.execute(
            update(m.User).where(m.User.id == teacher_id).values(is_active=is_active)
        )
        teacher = await self.get(teacher_id)
        if teacher is None:
            raise NotFound(f"Teacher {teacher_id} not found")
        return teacher

    async def assign(self, teacher_id: int, class_id: int) -> None:
        await self.session.execute(
            insert(m.ClassTeacher)
            .values(teacher_id=teacher_id, class_id=class_id)
            .on_conflict_do_nothing()
        )

    async def unassign(self, teacher_id: int, class_id: int) -> None:
        await self.session.execute(
            delete(m.ClassTeacher).where(
                m.ClassTeacher.teacher_id == teacher_id, m.ClassTeacher.class_id == class_id
            )
        )

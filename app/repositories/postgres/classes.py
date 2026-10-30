from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.models import SchoolClass


def _to_domain(row: m.SchoolClass) -> SchoolClass:
    return SchoolClass(id=row.id, school_id=row.school_id, name=row.name)


class PostgresClassRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, class_id: int) -> SchoolClass | None:
        row = await self.session.get(m.SchoolClass, class_id)
        return _to_domain(row) if row else None

    async def list_by_school(self, school_id: int) -> list[SchoolClass]:
        rows = await self.session.execute(
            select(m.SchoolClass).where(m.SchoolClass.school_id == school_id).order_by(m.SchoolClass.name)
        )
        return [_to_domain(r) for r in rows.scalars()]

    async def find_by_name(self, school_id: int, name: str) -> SchoolClass | None:
        row = (
            await self.session.execute(
                select(m.SchoolClass).where(m.SchoolClass.school_id == school_id, m.SchoolClass.name == name)
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list_led_by(self, teacher_id: int) -> list[SchoolClass]:
        rows = await self.session.execute(
            select(m.SchoolClass)
            .join(m.ClassTeacher, m.ClassTeacher.class_id == m.SchoolClass.id)
            .where(m.ClassTeacher.teacher_id == teacher_id)
            .order_by(m.SchoolClass.name)
        )
        return [_to_domain(r) for r in rows.scalars()]

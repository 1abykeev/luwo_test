from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.models import School


class PostgresSchoolRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, school_id: int) -> School | None:
        row = await self.session.get(m.School, school_id)
        return School(id=row.id, name=row.name) if row else None

    async def list_all(self) -> list[School]:
        rows = await self.session.execute(select(m.School).order_by(m.School.name))
        return [School(id=r.id, name=r.name) for r in rows.scalars()]

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.models import Role, User


def _to_domain(row: m.User) -> User:
    return User(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        role=Role(row.role),
        school_id=row.school_id,
        is_active=row.is_active,
        password_hash=row.password_hash,
    )


class PostgresUserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: int) -> User | None:
        row = await self.session.get(m.User, user_id)
        return _to_domain(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        row = (
            await self.session.execute(select(m.User).where(m.User.email == email))
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import SessionFactory

from .classes import PostgresClassRepository
from .history import PostgresHistoryRepository
from .pending import PostgresPendingActionRepository
from .schools import PostgresSchoolRepository
from .students import PostgresStudentRepository
from .teachers import PostgresTeacherRepository
from .users import PostgresUserRepository


class PostgresUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = SessionFactory):
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.students = PostgresStudentRepository(self.session)
        self.teachers = PostgresTeacherRepository(self.session)
        self.classes = PostgresClassRepository(self.session)
        self.schools = PostgresSchoolRepository(self.session)
        self.users = PostgresUserRepository(self.session)
        self.history = PostgresHistoryRepository(self.session)
        self.pending = PostgresPendingActionRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # After a commit this does nothing; without one it throws the changes away.
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

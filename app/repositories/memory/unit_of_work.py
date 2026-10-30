import copy
from types import TracebackType
from typing import Self

from .repositories import (
    MemoryClassRepository,
    MemoryHistoryRepository,
    MemoryPendingActionRepository,
    MemorySchoolRepository,
    MemoryStudentRepository,
    MemoryTeacherRepository,
    MemoryUserRepository,
)
from .store import MemoryStore


class MemoryUnitOfWork:
    def __init__(self, store: MemoryStore):
        self._store = store

    async def __aenter__(self) -> Self:
        # Work on a copy: leaving without commit() simply drops it, like a rollback.
        data = copy.deepcopy(self._store.data)
        self._data = data
        self.students = MemoryStudentRepository(data)
        self.teachers = MemoryTeacherRepository(data)
        self.classes = MemoryClassRepository(data)
        self.schools = MemorySchoolRepository(data)
        self.users = MemoryUserRepository(data)
        self.history = MemoryHistoryRepository(data)
        self.pending = MemoryPendingActionRepository(data)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self._store.data = self._data

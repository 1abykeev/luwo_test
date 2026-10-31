from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from .classes import ClassRepository
from .history import HistoryRepository
from .pending import PendingActionRepository
from .schools import SchoolRepository
from .students import StudentRepository
from .teachers import TeacherRepository
from .users import UserRepository


class UnitOfWork(Protocol):
    """One business operation = one unit of work = one transaction.

    Every repository inside it shares the same transaction, so a change and its history
    row are saved together or not at all. Leaving the `async with` block without calling
    commit() rolls everything back."""

    # Read-only properties: services only read these, and each adapter may offer its own subclass of the contract.
    @property
    def students(self) -> StudentRepository: ...

    @property
    def teachers(self) -> TeacherRepository: ...

    @property
    def classes(self) -> ClassRepository: ...

    @property
    def schools(self) -> SchoolRepository: ...

    @property
    def users(self) -> UserRepository: ...

    @property
    def history(self) -> HistoryRepository: ...

    @property
    def pending(self) -> PendingActionRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


# Services receive one of these. This is the single place where the data source is chosen.
UnitOfWorkFactory = Callable[[], UnitOfWork]

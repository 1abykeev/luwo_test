from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.auth.service import AuthService
from app.repositories.interfaces import UnitOfWorkFactory

from .actors import ActorService
from .changes import ChangeService, utc_now
from .directory import DirectoryService
from .students import StudentService


@dataclass(frozen=True)
class Services:
    auth: AuthService
    actors: ActorService
    directory: DirectoryService
    students: StudentService
    changes: ChangeService


def build_services(uow_factory: UnitOfWorkFactory, clock: Callable[[], datetime] = utc_now) -> Services:
    """The one place where services are wired to a data source."""
    return Services(
        auth=AuthService(uow_factory),
        actors=ActorService(uow_factory),
        directory=DirectoryService(uow_factory),
        students=StudentService(uow_factory),
        changes=ChangeService(uow_factory, clock),
    )

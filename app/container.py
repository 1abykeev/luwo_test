"""The composition root: the ONE place that decides which data source is plugged in.

Everything above this file (API, agent, tools, services) only sees the UnitOfWork
interface. To connect Luwo's real backend, write a unit of work that calls their REST API
or MCP server and add one branch below. No other file changes."""

from app.auth.passwords import hash_password
from app.config import settings
from app.repositories.interfaces import UnitOfWorkFactory
from app.repositories.memory.store import load_demo_world
from app.repositories.memory.unit_of_work import MemoryUnitOfWork
from app.repositories.postgres.unit_of_work import PostgresUnitOfWork
from app.services import Services, build_services
from seed.world import DEMO_PASSWORD


def build_uow_factory() -> UnitOfWorkFactory:
    if settings.data_source == "memory":
        store = load_demo_world(password_hash=hash_password(DEMO_PASSWORD))
        return lambda: MemoryUnitOfWork(store)
    if settings.data_source == "postgres":
        return PostgresUnitOfWork
    raise ValueError(f"Unknown DATA_SOURCE '{settings.data_source}'")


def build_app_services() -> Services:
    return build_services(build_uow_factory())

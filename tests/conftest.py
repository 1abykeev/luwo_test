import asyncio
import os
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.repositories.memory.store import load_demo_world
from app.repositories.memory.unit_of_work import MemoryUnitOfWork
from app.repositories.postgres.unit_of_work import PostgresUnitOfWork
from app.services import build_services
from seed.seed import seed

# A separate database, so running the tests never wipes the demo data.
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://luwo:luwo@localhost:5433/luwo_test")


async def _ensure_database() -> None:
    url = make_url(TEST_DB_URL)
    admin = await asyncpg.connect(
        user=url.username, password=url.password, host=url.host, port=url.port, database="postgres"
    )
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await admin.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session", autouse=True)
def _fresh_test_schema():
    """Rebuild the test database's tables once per run. create_all alone never adds a column to a table
    that already exists, so a schema change would otherwise break the Postgres tests until the test
    database was deleted by hand."""

    async def rebuild():
        await _ensure_database()
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    try:
        asyncio.run(rebuild())
    except Exception:  # no PostgreSQL running: the memory tests still run, the Postgres ones skip
        pass


@pytest.fixture(params=["memory", "postgres"])
async def uow_factory(request):
    """Every service test runs against both adapters: the proof that services don't care."""
    if request.param == "memory":
        store = load_demo_world()
        yield lambda: MemoryUnitOfWork(store)
        return

    try:
        await _ensure_database()
    except Exception as exc:  # no Postgres running: memory tests still run
        pytest.skip(f"PostgreSQL not available: {exc}")
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)  # no pool: each test has its own event loop
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await seed(factory, password_hash="not-a-real-hash")
    yield lambda: PostgresUnitOfWork(factory)
    await engine.dispose()


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def services(uow_factory, clock):
    return build_services(uow_factory, clock)


@pytest.fixture
def actor(services):
    """await actor("bakyt@luwo.test") -> the Actor loaded from the database."""

    async def load(email: str):
        from tests.helpers import user_id

        return await services.actors.load(user_id(email))

    return load

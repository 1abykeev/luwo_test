"""The request log and its statistics: the same answers from memory and from PostgreSQL."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.observability.request_log import (
    OUTCOMES,
    InMemoryRequestLogStore,
    PostgresRequestLogStore,
    RequestLogEntry,
    percentile,
)
from seed.seed import seed
from tests.conftest import TEST_DB_URL, _ensure_database

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(params=["memory", "postgres"])
async def store(request):
    if request.param == "memory":
        yield InMemoryRequestLogStore()
        return
    try:
        await _ensure_database()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await seed(factory, password_hash="x")  # empties request_log too
    yield PostgresRequestLogStore(factory)
    await engine.dispose()


def entry(request_type="show", outcome="resolved", conversation="c_1", latency=1000, minutes_ago=0,
          input_tokens=100, output_tokens=20, cached=50, calls=2):
    return RequestLogEntry(
        conversation_id=conversation, user_id=6, request_type=request_type, outcome=outcome,
        tools_called=["list_class_students"], input_tokens=input_tokens, output_tokens=output_tokens,
        cached_tokens=cached, llm_calls=calls, latency_ms=latency, at=NOW - timedelta(minutes=minutes_ago),
    )


DAY_AGO = NOW - timedelta(days=1)


async def test_an_empty_log_gives_zeros_not_errors(store):
    stats = await store.stats(DAY_AGO)
    assert stats.total == 0 and stats.by_type == [] and stats.conversations == 0
    assert stats.outcomes == {o: 0 for o in OUTCOMES}
    assert (stats.avg_tokens_per_request, stats.avg_tokens_per_conversation) == (0.0, 0.0)
    assert stats.latency_p50_ms is None and stats.latency_p95_ms is None


async def test_the_most_and_least_common_types_and_their_outcomes(store):
    for _ in range(5):
        await store.add(entry("show"))
    for _ in range(3):
        await store.add(entry("transfer"))
    await store.add(entry("transfer", "permission_denied"))
    await store.add(entry("add", "needs_clarification"))
    await store.add(entry("off_topic", "out_of_scope"))
    await store.add(entry("remove", "error"))
    stats = await store.stats(DAY_AGO)

    assert stats.total == 12
    assert [(t.request_type, t.count) for t in stats.by_type] == [
        ("show", 5), ("transfer", 4), ("add", 1), ("off_topic", 1), ("remove", 1),  # ties: alphabetical
    ]
    assert stats.outcomes == {"resolved": 8, "permission_denied": 1, "needs_clarification": 1, "out_of_scope": 1, "error": 1}
    transfer = next(t for t in stats.by_type if t.request_type == "transfer")
    assert transfer.outcomes == {"resolved": 3, "permission_denied": 1, "needs_clarification": 0, "out_of_scope": 0, "error": 0}


async def test_requests_outside_the_time_window_are_not_counted(store):
    await store.add(entry("show", minutes_ago=10))
    await store.add(entry("show", minutes_ago=60 * 24 * 3))  # three days ago
    assert (await store.stats(DAY_AGO)).total == 1
    assert (await store.stats(NOW - timedelta(days=7))).total == 2


async def test_tokens_conversations_and_latency(store):
    await store.add(entry(conversation="c_a", input_tokens=100, output_tokens=20, cached=60, latency=1000))
    await store.add(entry(conversation="c_a", input_tokens=200, output_tokens=40, cached=120, latency=2000))
    await store.add(entry(conversation="c_b", input_tokens=300, output_tokens=60, cached=0, latency=4000))
    stats = await store.stats(DAY_AGO)

    assert stats.conversations == 2
    assert (stats.input_tokens, stats.output_tokens, stats.cached_tokens) == (600, 120, 180)
    assert stats.avg_tokens_per_request == 240.0  # 720 / 3
    assert stats.avg_tokens_per_conversation == 360.0  # 720 / 2
    assert stats.latency_p50_ms == 2000.0
    assert stats.latency_p95_ms == pytest.approx(3800.0)  # between 2000 and 4000, 90% of the way


async def test_memory_and_postgres_agree_on_percentiles():
    assert percentile([1000, 2000, 4000], 0.95) == pytest.approx(3800.0)
    assert percentile([5], 0.5) == 5.0
    assert percentile([], 0.5) is None
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


async def test_tools_called_are_stored(store):
    await store.add(entry())
    if isinstance(store, PostgresRequestLogStore):
        from sqlalchemy import select

        from app.db import models as m

        async with store._factory() as session:
            row = (await session.execute(select(m.RequestLog))).scalar_one()
        assert row.tools_called == ["list_class_students"] and row.cached_tokens == 50 and row.llm_calls == 2

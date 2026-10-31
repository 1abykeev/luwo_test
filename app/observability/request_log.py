"""One row per chat request, and the statistics built from them (analytics by request type).

Like the conversation store, this is the agent's OWN state, not part of the school lists, so it stays
here when the lists move to Luwo's backend."""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import models as m
from app.db.session import SessionFactory

OUTCOMES = ("resolved", "permission_denied", "needs_clarification", "out_of_scope", "error")


@dataclass(frozen=True)
class RequestLogEntry:
    conversation_id: str
    user_id: int | None
    request_type: str  # add, remove, transfer, show, search, missing_student, duplicate, off_topic, ...
    outcome: str  # one of OUTCOMES
    tools_called: list[str] = field(default_factory=list)
    input_tokens: int = 0  # all input: fresh + cached
    output_tokens: int = 0
    cached_tokens: int = 0  # the part of the input that came from the prompt cache
    llm_calls: int = 0
    latency_ms: int = 0
    at: datetime | None = None


@dataclass(frozen=True)
class TypeStats:
    request_type: str
    count: int
    outcomes: dict[str, int]  # every outcome, zeros included


@dataclass(frozen=True)
class Stats:
    since: datetime
    total: int
    outcomes: dict[str, int]  # every outcome, zeros included
    by_type: list[TypeStats]  # most common first
    conversations: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    avg_tokens_per_request: float
    avg_tokens_per_conversation: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class RequestLogStore(Protocol):
    async def add(self, entry: RequestLogEntry) -> None: ...

    async def stats(self, since: datetime) -> Stats: ...


def _zeroed() -> dict[str, int]:
    return {outcome: 0 for outcome in OUTCOMES}


def percentile(values: list[int], fraction: float) -> float | None:
    """Linear interpolation between the closest ranks: the same as PostgreSQL's percentile_cont."""
    if not values:
        return None
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def _build_stats(
    since: datetime, counts: dict[tuple[str, str], int], conversations: int,
    input_tokens: int, output_tokens: int, cached_tokens: int, p50: float | None, p95: float | None,
) -> Stats:
    outcomes = _zeroed()
    per_type: dict[str, dict[str, int]] = {}
    for (request_type, outcome), count in counts.items():
        outcomes[outcome] = outcomes.get(outcome, 0) + count
        per_type.setdefault(request_type, _zeroed())[outcome] = count
    by_type = sorted(
        (TypeStats(t, sum(o.values()), o) for t, o in per_type.items()),
        key=lambda s: (-s.count, s.request_type),  # most common first, ties alphabetical
    )
    total = sum(outcomes.values())
    tokens = input_tokens + output_tokens
    return Stats(
        since=since, total=total, outcomes=outcomes, by_type=by_type, conversations=conversations,
        input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached_tokens,
        avg_tokens_per_request=round(tokens / total, 1) if total else 0.0,
        avg_tokens_per_conversation=round(tokens / conversations, 1) if conversations else 0.0,
        latency_p50_ms=None if p50 is None else round(float(p50), 1),
        latency_p95_ms=None if p95 is None else round(float(p95), 1),
    )


class InMemoryRequestLogStore:
    def __init__(self) -> None:
        self._entries: list[RequestLogEntry] = []

    async def add(self, entry: RequestLogEntry) -> None:
        self._entries.append(entry if entry.at else _with_time(entry))

    async def stats(self, since: datetime) -> Stats:
        window = [e for e in self._entries if e.at >= since]
        counts: dict[tuple[str, str], int] = {}
        for e in window:
            counts[(e.request_type, e.outcome)] = counts.get((e.request_type, e.outcome), 0) + 1
        latencies = [e.latency_ms for e in window]
        return _build_stats(
            since, counts, len({e.conversation_id for e in window}),
            sum(e.input_tokens for e in window), sum(e.output_tokens for e in window),
            sum(e.cached_tokens for e in window), percentile(latencies, 0.5), percentile(latencies, 0.95),
        )


def _with_time(entry: RequestLogEntry) -> RequestLogEntry:
    from dataclasses import replace

    return replace(entry, at=datetime.now(timezone.utc))


class PostgresRequestLogStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = SessionFactory):
        self._factory = session_factory

    async def add(self, entry: RequestLogEntry) -> None:
        async with self._factory() as session:
            session.add(m.RequestLog(
                conversation_id=entry.conversation_id, user_id=entry.user_id,
                request_type=entry.request_type, outcome=entry.outcome, tools_called=entry.tools_called,
                input_tokens=entry.input_tokens, output_tokens=entry.output_tokens,
                cached_tokens=entry.cached_tokens, llm_calls=entry.llm_calls, latency_ms=entry.latency_ms,
                **({"at": entry.at} if entry.at else {}),
            ))
            await session.commit()

    async def stats(self, since: datetime) -> Stats:
        log = m.RequestLog
        window = log.at >= since
        async with self._factory() as session:
            grouped = await session.execute(
                select(log.request_type, log.outcome, func.count()).where(window).group_by(log.request_type, log.outcome)
            )
            totals = (
                await session.execute(
                    select(
                        func.count(distinct(log.conversation_id)),
                        func.coalesce(func.sum(log.input_tokens), 0),
                        func.coalesce(func.sum(log.output_tokens), 0),
                        func.coalesce(func.sum(log.cached_tokens), 0),
                        func.percentile_cont(0.5).within_group(log.latency_ms),
                        func.percentile_cont(0.95).within_group(log.latency_ms),
                    ).where(window)
                )
            ).one()
        conversations, input_tokens, output_tokens, cached_tokens, p50, p95 = totals
        counts = {(request_type, outcome): count for request_type, outcome, count in grouped}
        return _build_stats(since, counts, conversations, int(input_tokens), int(output_tokens), int(cached_tokens), p50, p95)

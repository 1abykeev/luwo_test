"""PostgreSQL versions of the agent's OWN state: chat history and the request log.

These are not school lists, so they do not move when Luwo's backend replaces the data source for lists.
They live here, next to the DB models, so that the agent and observability code only know the interfaces
(`ConversationStore`, `RequestLogStore`) and never import SQLAlchemy."""

from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import Message
from app.agent.memory import StoredMessage, unknown_conversation
from app.db import models as m
from app.db.session import SessionFactory
from app.observability.request_log import RequestLogEntry, Stats, build_stats


class PostgresConversationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = SessionFactory):
        self._factory = session_factory

    async def load(self, conversation_id: str, user_id: int) -> list[StoredMessage]:
        async with self._factory() as session:
            conversation = await session.get(m.Conversation, conversation_id)
            if conversation is None:
                return []
            if conversation.user_id != user_id:
                raise unknown_conversation()
            rows = await session.execute(
                select(m.ChatMessage).where(m.ChatMessage.conversation_id == conversation_id).order_by(m.ChatMessage.seq)
            )
            return [StoredMessage(Message.from_dict(r.payload), r.blocks, r.created_at) for r in rows.scalars()]

    async def append(self, conversation_id: str, user_id: int, items: list[StoredMessage]) -> None:
        async with self._factory() as session:
            # Create the conversation if it is new; do nothing if it exists.
            await session.execute(
                insert(m.Conversation).values(id=conversation_id, user_id=user_id).on_conflict_do_nothing()
            )
            # FOR UPDATE: a second writer waits here until this transaction ends, so two requests can
            # never pick the same message position (also across several server instances).
            owner = (
                await session.execute(
                    select(m.Conversation.user_id).where(m.Conversation.id == conversation_id).with_for_update()
                )
            ).scalar_one()
            if owner != user_id:
                raise unknown_conversation()
            last_seq = (
                await session.execute(
                    select(func.coalesce(func.max(m.ChatMessage.seq), -1)).where(
                        m.ChatMessage.conversation_id == conversation_id
                    )
                )
            ).scalar_one()
            session.add_all(
                m.ChatMessage(conversation_id=conversation_id, seq=last_seq + 1 + i,
                              payload=item.message.to_dict(), blocks=item.blocks)
                for i, item in enumerate(items)
            )
            await session.commit()

    async def latest_id(self, user_id: int) -> str | None:
        async with self._factory() as session:
            last_message = func.max(m.ChatMessage.created_at)
            row = (
                await session.execute(
                    select(m.Conversation.id)
                    .join(m.ChatMessage, m.ChatMessage.conversation_id == m.Conversation.id)
                    .where(m.Conversation.user_id == user_id)
                    .group_by(m.Conversation.id)
                    .order_by(last_message.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return row


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
        return build_stats(since, counts, conversations, int(input_tokens), int(output_tokens), int(cached_tokens), p50, p95)

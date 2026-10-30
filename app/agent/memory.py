"""Conversation memory: what was said in a chat, so 'move her too' works and the app can show history.

This is the agent's OWN state, kept apart from the school lists on purpose: when Luwo's backend
replaces the data source for lists, chat history stays here."""

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import models as m
from app.db.session import SessionFactory
from app.domain.errors import NotFound

from .llm import Message


@dataclass(frozen=True)
class StoredMessage:
    message: Message
    blocks: list[dict] = field(default_factory=list)  # cards the app shows with this message
    at: datetime | None = None


class ConversationStore(Protocol):
    async def load(self, conversation_id: str, user_id: int) -> list[StoredMessage]:
        """Messages in order. [] for a conversation that does not exist yet.
        Raises NotFound if the conversation belongs to someone else."""
        ...

    async def append(self, conversation_id: str, user_id: int, items: list[StoredMessage]) -> None: ...

    async def latest_id(self, user_id: int) -> str | None:
        """The user's most recent conversation, so the app can show history after login."""
        ...


def _unknown() -> NotFound:
    # Someone else's conversation looks exactly like one that doesn't exist.
    return NotFound("Unknown conversation")


class InMemoryConversationStore:
    def __init__(self):
        self._owners: dict[str, int] = {}
        self._items: dict[str, list[StoredMessage]] = {}
        self._order: list[str] = []

    async def load(self, conversation_id: str, user_id: int) -> list[StoredMessage]:
        if conversation_id not in self._owners:
            return []
        if self._owners[conversation_id] != user_id:
            raise _unknown()
        return list(self._items[conversation_id])

    async def append(self, conversation_id: str, user_id: int, items: list[StoredMessage]) -> None:
        if conversation_id not in self._owners:
            self._owners[conversation_id] = user_id
            self._items[conversation_id] = []
        elif self._owners[conversation_id] != user_id:
            raise _unknown()
        now = datetime.now(timezone.utc)
        self._items[conversation_id] += [
            StoredMessage(copy.deepcopy(i.message), copy.deepcopy(i.blocks), i.at or now) for i in items
        ]
        if conversation_id in self._order:
            self._order.remove(conversation_id)
        self._order.append(conversation_id)

    async def latest_id(self, user_id: int) -> str | None:
        return next((c for c in reversed(self._order) if self._owners[c] == user_id), None)


class PostgresConversationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = SessionFactory):
        self._factory = session_factory

    async def load(self, conversation_id: str, user_id: int) -> list[StoredMessage]:
        async with self._factory() as session:
            conversation = await session.get(m.Conversation, conversation_id)
            if conversation is None:
                return []
            if conversation.user_id != user_id:
                raise _unknown()
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
            owner = (
                await session.execute(select(m.Conversation.user_id).where(m.Conversation.id == conversation_id))
            ).scalar_one()
            if owner != user_id:
                raise _unknown()
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


def trim_history(messages: list[Message], max_messages: int) -> list[Message]:
    """Keep roughly the last `max_messages`, but never start in the middle of a tool exchange:
    the first kept message must be something the user typed."""
    if len(messages) <= max_messages:
        return messages
    for index in range(len(messages) - max_messages, len(messages)):
        message = messages[index]
        if message.role == "user" and not message.tool_results:
            return messages[index:]
    return messages[-1:] if messages[-1].role == "user" and not messages[-1].tool_results else []

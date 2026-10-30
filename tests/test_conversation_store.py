"""Conversation memory: the same behavior in memory and in Postgres, plus history trimming."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.llm import Message, ToolCall, ToolResult
from app.agent.memory import (
    InMemoryConversationStore,
    PostgresConversationStore,
    StoredMessage,
    trim_history,
)
from app.db.base import Base
from app.domain.errors import NotFound
from seed.seed import seed
from tests.conftest import TEST_DB_URL, _ensure_database
from tests.helpers import user_id

AIGUL, BAKYT = user_id("aigul@luwo.test"), user_id("bakyt@luwo.test")


@pytest.fixture(params=["memory", "postgres"])
async def store(request):
    if request.param == "memory":
        yield InMemoryConversationStore()
        return
    try:
        await _ensure_database()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await seed(factory, password_hash="x")  # clears conversations too (users are re-created)
    yield PostgresConversationStore(factory)
    await engine.dispose()


async def test_a_new_conversation_is_empty(store):
    assert await store.load("c_new", AIGUL) == []


async def test_messages_come_back_in_order_with_their_cards(store):
    call = ToolCall("t1", "list_classes", {})
    await store.append("c_1", AIGUL, [StoredMessage(Message("user", "Покажи классы"))])
    await store.append("c_1", AIGUL, [
        StoredMessage(Message("assistant", "", tool_calls=(call,))),
        StoredMessage(Message("user", tool_results=(ToolResult("t1", "{}"),))),
        StoredMessage(Message("assistant", "Вот классы."), [{"type": "class_overview", "classes": []}]),
    ])
    loaded = await store.load("c_1", AIGUL)

    assert [m.message.role for m in loaded] == ["user", "assistant", "user", "assistant"]
    assert loaded[1].message.tool_calls == (call,)
    assert loaded[2].message.tool_results[0].tool_call_id == "t1"
    assert loaded[3].blocks == [{"type": "class_overview", "classes": []}]
    assert all(m.at is not None for m in loaded)


async def test_a_conversation_belongs_to_one_user(store):
    await store.append("c_2", AIGUL, [StoredMessage(Message("user", "Привет"))])
    with pytest.raises(NotFound):
        await store.load("c_2", BAKYT)
    with pytest.raises(NotFound):
        await store.append("c_2", BAKYT, [StoredMessage(Message("user", "Я тоже здесь"))])
    assert len(await store.load("c_2", AIGUL)) == 1


async def test_the_latest_conversation_of_a_user(store):
    assert await store.latest_id(AIGUL) is None
    await store.append("c_old", AIGUL, [StoredMessage(Message("user", "раз"))])
    await store.append("c_other_user", BAKYT, [StoredMessage(Message("user", "чужой"))])
    await store.append("c_new", AIGUL, [StoredMessage(Message("user", "два"))])
    assert await store.latest_id(AIGUL) == "c_new"
    await store.append("c_old", AIGUL, [StoredMessage(Message("user", "снова"))])
    assert await store.latest_id(AIGUL) == "c_old"


# ---- trimming old history ----

def exchange(n):
    call = ToolCall(f"t{n}", "list_classes", {})
    return [
        Message("user", f"question {n}"),
        Message("assistant", "", tool_calls=(call,)),
        Message("user", tool_results=(ToolResult(f"t{n}", "{}"),)),
        Message("assistant", f"answer {n}"),
    ]


def test_short_history_is_kept_whole():
    history = exchange(1) + exchange(2)
    assert trim_history(history, 40) == history


def test_trimming_never_starts_in_the_middle_of_a_tool_exchange():
    history = exchange(1) + exchange(2) + exchange(3)  # 12 messages
    trimmed = trim_history(history, 6)  # would start at index 6 = a tool call: skip to the next typed message
    assert trimmed[0] == Message("user", "question 3") and len(trimmed) == 4
    assert all(not (m.role == "user" and m.tool_results) for m in trimmed[:1])

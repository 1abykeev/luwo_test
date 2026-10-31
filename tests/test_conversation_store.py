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


def long_turn(n, steps):
    """One question answered after `steps` tool calls (the agent may take up to 8)."""
    messages = [Message("user", f"question {n}")]
    for step in range(steps):
        call = ToolCall(f"t{n}_{step}", "list_classes", {})
        messages.append(Message("assistant", "", tool_calls=(call,)))
        messages.append(Message("user", tool_results=(ToolResult(f"t{n}_{step}", "{}"),)))
    messages.append(Message("assistant", f"answer {n}"))
    return messages


def assert_valid_history(trimmed):
    """What the model API needs: no start with a tool result, no tool result without its call before it."""
    if not trimmed:
        return
    assert trimmed[0].role == "user" and not trimmed[0].tool_results
    seen_calls = set()
    for message in trimmed:
        seen_calls.update(call.id for call in message.tool_calls)
        for result in message.tool_results:
            assert result.tool_call_id in seen_calls


@pytest.mark.parametrize("shape", [
    [exchange(1), exchange(2), exchange(3)],
    [long_turn(1, 8), long_turn(2, 8)],
    [exchange(1), long_turn(2, 8), exchange(3), long_turn(4, 5)],
    [long_turn(1, 0), long_turn(2, 1), long_turn(3, 2)],
])
def test_every_window_size_gives_a_history_the_model_can_accept(shape):
    history = [message for part in shape for message in part]
    for window in range(1, len(history) + 2):
        assert_valid_history(trim_history(history, window))


def test_a_window_made_only_of_tool_exchanges_never_starts_with_a_tool_result():
    history = long_turn(1, 8)  # 18 messages: the question, 8 tool round trips, the answer
    trimmed = trim_history(history, 10)  # the last 10 messages contain no typed message at all
    assert_valid_history(trimmed)
    assert all(not m.tool_results for m in trimmed[:1])


def test_a_typed_message_inside_the_window_is_found_even_after_a_long_turn():
    history = long_turn(1, 8) + exchange(2)
    trimmed = trim_history(history, 6)
    assert trimmed[0] == Message("user", "question 2")


# ---- review fix #4: two writers at once on one conversation ----

async def test_simultaneous_appends_all_succeed_and_keep_a_clean_order(store):
    import asyncio

    await store.append("c_race", AIGUL, [StoredMessage(Message("user", "start"))])
    await asyncio.gather(*[
        store.append("c_race", AIGUL, [StoredMessage(Message("user", f"m{i}")), StoredMessage(Message("assistant", f"a{i}"))])
        for i in range(8)
    ])
    loaded = await store.load("c_race", AIGUL)
    texts = [m.message.text for m in loaded]

    assert len(loaded) == 1 + 8 * 2 and len(set(texts)) == len(texts)
    # each writer's two messages stay together and in order
    for i in range(8):
        assert texts.index(f"a{i}") == texts.index(f"m{i}") + 1


async def test_simultaneous_first_messages_of_a_new_conversation(store):
    import asyncio

    await asyncio.gather(*[
        store.append("c_new_race", AIGUL, [StoredMessage(Message("user", f"first{i}"))]) for i in range(5)
    ])
    assert len(await store.load("c_new_race", AIGUL)) == 5


# ---- the per-conversation lock cleans up after itself ----

async def test_the_conversation_lock_forgets_finished_conversations():
    import asyncio

    from app.agent.locks import KeyedLock

    locks = KeyedLock()
    order = []

    async def work(name, pause):
        async with locks.hold("c_1"):
            order.append(f"{name} start")
            await asyncio.sleep(pause)
            order.append(f"{name} end")

    await asyncio.gather(work("a", 0.02), work("b", 0))
    assert order == ["a start", "a end", "b start", "b end"]  # one at a time, in arrival order
    assert len(locks) == 0  # nothing is kept for conversations nobody is using

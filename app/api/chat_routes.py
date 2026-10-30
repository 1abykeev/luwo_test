from fastapi import APIRouter, Depends, Query

from app.agent.agent import Agent, ChatResult, display_history
from app.api.chat_schemas import (
    ChatMeta,
    ChatRequest,
    ChatResponse,
    ConfirmRequest,
    HistoryResponse,
)
from app.api.deps import current_actor, get_agent
from app.api.schemas import ErrorResponse
from app.domain.models import Actor

router = APIRouter(prefix="/chat", tags=["chat"])

BLOCKS = """
**Cards (`blocks`)** the app draws under the answer. Every block has a `type`:

| type | when | main fields |
|---|---|---|
| `class_roster` | a class list | `class`, `school`, `teachers` (null = hidden from this user), `students[{id, full_name, status}]` |
| `class_overview` | classes of a school | `classes[{name, school, active_students, teachers}]` |
| `teacher_list` | teachers | `teachers[{id, full_name, school, classes}]` |
| `school_list` | schools (superadmin) | `schools[{id, name}]` |
| `student_list` | search results, to pick from | `students[{id, full_name, class, school, status}]` |
| `student_card` | one student | `student`, `history[{action, date, from_class, to_class}]` |
| `duplicates` | namesakes | `groups[{name, students}]` |
| `investigation` | "where did the student go" | `findings[{student_id, full_name, state, current_class, history}]` |
| `confirmation` | a change waits for the user | `token`, `summary`, `details`, `warnings`, `expires_at` → show Confirm / Cancel buttons that call `POST /chat/confirm` |
| `result` | a change was made | `status` (`done` / `already_done`), `result` |
| `banner` | an error or notice | `level` (`error` / `info`), `message`, `code` |
"""


def to_response(result: ChatResult) -> ChatResponse:
    usage = result.usage
    return ChatResponse(
        conversation_id=result.conversation_id,
        text=result.text,
        blocks=result.blocks,
        meta=ChatMeta(
            request_type=result.request_type, outcome=result.outcome, llm_calls=result.llm_calls,
            input_tokens=usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens,
            output_tokens=usage.output_tokens, cached_tokens=usage.cache_read_tokens,
            duration_ms=result.duration_ms,
        ),
    )


@router.post(
    "",
    summary="Send a message to the agent",
    description="The agent reads the message with the conversation so far, looks things up, and answers. "
    "Changes are never made here: the agent proposes them and the response carries a `confirmation` "
    "card. The change happens only after the user presses Confirm (`POST /chat/confirm`) or writes a "
    "clear yes in a later message.\n" + BLOCKS,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse, "description": "Unknown conversation"}},
)
async def chat(
    body: ChatRequest, actor: Actor = Depends(current_actor), agent: Agent = Depends(get_agent)
) -> ChatResponse:
    return to_response(await agent.chat(actor, body.message, body.conversation_id))


@router.post(
    "/confirm",
    summary="Press Confirm or Cancel on a confirmation card",
    description="The backend carries out (or cancels) the pending change first; the agent then puts the "
    "real result into words. Pressing twice is safe: the second press reports `already_done` and "
    "changes nothing. Only the person who got the card can use its token.",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def confirm(
    body: ConfirmRequest, actor: Actor = Depends(current_actor), agent: Agent = Depends(get_agent)
) -> ChatResponse:
    return to_response(await agent.press_button(actor, body.conversation_id, body.token, body.approve))


@router.get(
    "/history",
    summary="Messages of a conversation",
    description="What the app shows when it opens: typed messages and answers with their cards. "
    "Without `conversation_id` it returns the user's most recent conversation (empty if none).",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def history(
    conversation_id: str | None = Query(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    actor: Actor = Depends(current_actor),
    agent: Agent = Depends(get_agent),
) -> HistoryResponse:
    conversation_id = conversation_id or await agent.store.latest_id(actor.user_id)
    if conversation_id is None:
        return HistoryResponse(conversation_id=None, messages=[])
    return HistoryResponse(
        conversation_id=conversation_id,
        messages=display_history(await agent.store.load(conversation_id, actor.user_id)),
    )

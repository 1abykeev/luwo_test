"""The agent loop: ask the model, run the tools it asks for, give it the results, repeat
until it answers in plain text.

              user message
                   |
            +------v------+   tool calls   +-----------------+
            |    model    | -------------> | tools (-> services, which check permissions)
            |             | <------------- |                 |
            +------+------+  tool results  +-----------------+
                   | plain text
                   v
              answer + cards for the app
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field

from app.domain.errors import NotFound
from app.domain.models import Actor
from app.observability.classification import ToolRecord, classify
from app.services import Services
from app.tools import ToolContext, ToolOutcome, ToolRegistry
from app.tools.base import banner

from .locks import KeyedLock
from .llm import LLMClient, LLMError, LLMRequest, Message, ToolCall, ToolResult, Usage
from .memory import ConversationStore, StoredMessage, trim_history
from .prompt import build_system_prompt

logger = logging.getLogger(__name__)

MAX_STEPS = 8  # model calls per request: enough for look-up, propose and answer, not enough to run away
HISTORY_MESSAGES = 40

# Used only when the model cannot answer at all, so there is nobody to phrase the message.
LLM_DOWN_TEXT = (
    "Сейчас не получается связаться с ИИ-моделью, поэтому ничего не изменено. "
    "Попробуйте ещё раз через минуту.\n"
    "I can't reach the AI model right now, so nothing was changed. Please try again in a minute."
)
TIMEOUT_TEXT = (
    "Запрос занял слишком много времени, поэтому ничего не изменено. Попробуйте ещё раз.\n"
    "The request took too long, so nothing was changed. Please try again."
)
GAVE_UP_TEXT = (
    "Не получилось довести запрос до конца. Проверьте списки и попробуйте сформулировать запрос иначе.\n"
    "I could not finish this request. Please check the lists and try to rephrase it."
)
# What to say when the model cannot answer but we KNOW what the backend did (review fix #1). The text must
# match the facts: a change that was made may not be reported as "nothing was changed".
CHANGE_MADE_TEXT = (
    "Изменение выполнено, результат на карточке ниже. Подробный ответ написать не удалось: ИИ-модель сейчас недоступна.\n"
    "The change was made; the result is on the card below. I could not write a fuller reply because the AI model is unavailable."
)
CHANGE_CANCELLED_TEXT = (
    "Изменение отменено, данные не менялись. Подробный ответ написать не удалось: ИИ-модель сейчас недоступна.\n"
    "The change was cancelled and nothing was modified. I could not write a fuller reply because the AI model is unavailable."
)
PROPOSAL_PENDING_TEXT = (
    "Изменение подготовлено, но ещё НЕ выполнено. Подтвердите или отмените его на карточке ниже. "
    "Подробный ответ написать не удалось: ИИ-модель сейчас недоступна.\n"
    "The change is prepared but NOT done yet. Confirm or cancel it on the card below. "
    "I could not write a fuller reply because the AI model is unavailable."
)
REFUSAL_TEXT = "С этим я помочь не могу.\nI can't help with that."
EMPTY_TEXT = "Не получилось сформулировать ответ, попробуйте ещё раз.\nI could not put an answer together, please try again."


@dataclass
class ChatResult:
    conversation_id: str
    text: str
    blocks: list[dict]
    usage: Usage
    tool_records: list[ToolRecord]
    request_type: str
    outcome: str
    llm_calls: int
    duration_ms: int
    extras: dict = field(default_factory=dict)


def text_without_model(records: list[ToolRecord], default: str) -> str:
    """The message for a request where the model could not finish. It is chosen from what the
    backend really did, so it can never say "nothing was changed" after a change was made."""
    kinds = {r.kind for r in records}
    if "confirmed" in kinds:
        return CHANGE_MADE_TEXT
    if "cancelled" in kinds:
        return CHANGE_CANCELLED_TEXT
    if "pending_confirmation" in kinds:
        return PROPOSAL_PENDING_TEXT
    return default


def new_conversation_id() -> str:
    return f"c_{uuid.uuid4().hex[:16]}"


def select_blocks(step_blocks: list[list[dict]]) -> list[dict]:
    """Which cards to show with the final answer. A confirmation or result card is what matters;
    otherwise the cards from the last lookup. Error banners are always kept."""
    flat = [b for step in step_blocks for b in step]
    banners = []
    for b in flat:
        if b["type"] == "banner" and b not in banners:
            banners.append(b)
    decisive = [b for b in flat if b["type"] in ("confirmation", "result")]
    if decisive:
        return decisive + banners
    last = next((s for s in reversed(step_blocks) if any(b["type"] != "banner" for b in s)), [])
    return [b for b in last if b["type"] != "banner"] + banners


def display_history(items: list[StoredMessage]) -> list[dict]:
    """What the app shows when it opens a conversation: typed messages and final answers only."""
    shown = []
    for item in items:
        m = item.message
        if m.role == "user" and m.tool_results:
            continue
        if m.role == "assistant" and (m.tool_calls or not m.text):
            continue
        shown.append({
            "role": m.role, "text": m.text, "blocks": item.blocks,
            "at": item.at.isoformat() if item.at else None,
        })
    return shown


class Agent:
    def __init__(
        self, llm: LLMClient, registry: ToolRegistry, services: Services, store: ConversationStore,
        max_steps: int = MAX_STEPS, deadline_seconds: float = 90.0,
    ):
        self._llm = llm
        self._registry = registry
        self._services = services
        self.store = store  # also used by the history endpoint
        self._max_steps = max_steps
        self._deadline_seconds = deadline_seconds
        self._conversation_locks = KeyedLock()

    # ---- the two ways a turn starts ----

    async def chat(self, actor: Actor, text: str, conversation_id: str | None = None) -> ChatResult:
        """The user typed a message. conversation_id=None starts a new conversation; an id the
        server did not create for this user is refused, so clients cannot invent ids."""
        conversation_id_given = conversation_id is not None
        conversation_id = conversation_id or new_conversation_id()
        async with self._conversation_locks.hold(conversation_id):  # one request at a time per conversation
            stored = await self.store.load(conversation_id, actor.user_id)  # NotFound if not theirs
            if not stored and conversation_id_given:
                raise NotFound("Unknown conversation")
            return await self._run(actor, conversation_id, stored, [StoredMessage(Message("user", text))], [], [])

    async def press_button(self, actor: Actor, conversation_id: str, token: str, approve: bool) -> ChatResult:
        """The user pressed Confirm or Cancel on a card. The backend acts first; the model only
        puts the result into words."""
        async with self._conversation_locks.hold(conversation_id):
            stored = await self.store.load(conversation_id, actor.user_id)
            if not stored:
                raise NotFound("Unknown conversation")

            tool = "confirm_pending_action" if approve else "cancel_pending_action"
            started = time.perf_counter()
            ctx = ToolContext(actor, self._services, conversation_id)
            outcome = await self._registry.execute(ctx, ToolCall("button", tool, {"token": token}))
            record = ToolRecord(tool, self._registry.request_type(tool), outcome.kind, outcome.is_error,
                                int((time.perf_counter() - started) * 1000))

            # The button press reaches the model as a tool call plus its result. A user can type any text,
            # but cannot create a tool result, so a typed "SYSTEM EVENT ... done" can never pass for this.
            call = ToolCall(f"button_{uuid.uuid4().hex[:12]}", tool, {"token": token})
            result = {**outcome.result,
                      "note": f"The user pressed the {'Confirm' if approve else 'Cancel'} button in the app."}
            exchange = [
                StoredMessage(Message("assistant", "", tool_calls=(call,))),
                StoredMessage(Message("user", tool_results=(
                    ToolResult(call.id, json.dumps(result, ensure_ascii=False, default=str), outcome.is_error),
                ))),
            ]
            return await self._run(actor, conversation_id, stored, exchange, [record], [outcome.blocks])

    # ---- the loop ----

    async def _run(
        self, actor: Actor, conversation_id: str, stored: list[StoredMessage],
        new_items: list[StoredMessage], records: list[ToolRecord], step_blocks: list[list[dict]],
    ) -> ChatResult:
        started = time.perf_counter()
        system = build_system_prompt(await self._services.actors.profile(actor))
        ctx = ToolContext(actor, self._services, conversation_id)

        messages = trim_history([s.message for s in stored], HISTORY_MESSAGES) + [i.message for i in new_items]
        to_save = list(new_items)  # what this request adds to the conversation
        usage, llm_calls, failed = Usage(), 0, False
        final_text = ""

        deadline = time.monotonic() + self._deadline_seconds  # one budget for ALL the model calls of this request
        for _ in range(self._max_steps):
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                response = await asyncio.wait_for(
                    self._llm.complete(LLMRequest(system, messages, self._registry.specs)), timeout=remaining
                )
            except TimeoutError:
                error = LLMError("timeout", "The request took too long")
                response = None
            except LLMError as llm_error:
                error, response = llm_error, None
            if response is None:
                logger.error("Model call failed: %s (%s)", error.message, error.kind)
                default = TIMEOUT_TEXT if error.kind == "timeout" else LLM_DOWN_TEXT
                failed, final_text = True, text_without_model(records, default)
                step_blocks.append([banner("error", error.message, f"llm_{error.kind}")])
                break
            llm_calls += 1
            usage += response.usage

            if not response.tool_calls:
                final_text = response.text.strip()
                if not final_text:
                    final_text = REFUSAL_TEXT if response.stop_reason == "refusal" else EMPTY_TEXT
                break

            results, blocks_this_step = [], []
            for call in response.tool_calls:
                tool_started = time.perf_counter()
                outcome: ToolOutcome = await self._registry.execute(ctx, call)
                records.append(ToolRecord(
                    call.name, self._registry.request_type(call.name), outcome.kind, outcome.is_error,
                    int((time.perf_counter() - tool_started) * 1000),
                ))
                results.append(ToolResult(call.id, json.dumps(outcome.result, ensure_ascii=False, default=str),
                                          outcome.is_error))
                blocks_this_step += outcome.blocks
            assistant = Message("assistant", response.text, tool_calls=response.tool_calls)
            tool_message = Message("user", tool_results=tuple(results))
            messages += [assistant, tool_message]
            to_save += [StoredMessage(assistant), StoredMessage(tool_message)]
            if blocks_this_step:
                step_blocks.append(blocks_this_step)
        else:
            failed, final_text = True, text_without_model(records, GAVE_UP_TEXT)
            step_blocks.append([banner("error", "The request could not be completed", "too_many_steps")])

        blocks = select_blocks(step_blocks)
        request_type, outcome_label = classify(records, final_text, llm_failed=failed)

        await self.store.append(
            conversation_id, actor.user_id, to_save + [StoredMessage(Message("assistant", final_text), blocks)]
        )
        return ChatResult(
            conversation_id=conversation_id, text=final_text, blocks=blocks, usage=usage,
            tool_records=records, request_type=request_type, outcome=outcome_label, llm_calls=llm_calls,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

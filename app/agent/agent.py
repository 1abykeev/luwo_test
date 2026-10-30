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

from .llm import LLMClient, LLMError, LLMRequest, Message, ToolCall, ToolResult, Usage
from .memory import ConversationStore, StoredMessage, trim_history
from .prompt import SYSTEM_EVENT_PREFIX, build_system_prompt

logger = logging.getLogger(__name__)

MAX_STEPS = 8  # model calls per request: enough for look-up, propose and answer, not enough to run away
HISTORY_MESSAGES = 40

# Used only when the model cannot answer at all, so there is nobody to phrase the message.
LLM_DOWN_TEXT = (
    "Сейчас не получается связаться с ИИ-моделью, поэтому ничего не изменено. "
    "Попробуйте ещё раз через минуту.\n"
    "I can't reach the AI model right now, so nothing was changed. Please try again in a minute."
)
GAVE_UP_TEXT = (
    "Не получилось довести запрос до конца. Проверьте списки и попробуйте сформулировать запрос иначе.\n"
    "I could not finish this request. Please check the lists and try to rephrase it."
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
        if m.role == "user" and (m.tool_results or m.text.startswith(SYSTEM_EVENT_PREFIX)):
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
        max_steps: int = MAX_STEPS,
    ):
        self._llm = llm
        self._registry = registry
        self._services = services
        self.store = store  # also used by the history endpoint
        self._max_steps = max_steps

    # ---- the two ways a turn starts ----

    async def chat(self, actor: Actor, text: str, conversation_id: str | None = None) -> ChatResult:
        """The user typed a message. conversation_id=None starts a new conversation; an id the
        server did not create for this user is refused, so clients cannot invent ids."""
        if conversation_id is None:
            conversation_id, stored = new_conversation_id(), []
        else:
            stored = await self.store.load(conversation_id, actor.user_id)  # NotFound if not theirs
            if not stored:
                raise NotFound("Unknown conversation")
        return await self._run(actor, conversation_id, stored, [StoredMessage(Message("user", text))], [], [])

    async def press_button(self, actor: Actor, conversation_id: str, token: str, approve: bool) -> ChatResult:
        """The user pressed Confirm or Cancel on a card. The backend acts first; the model only
        puts the result into words."""
        stored = await self.store.load(conversation_id, actor.user_id)
        if not stored:
            raise NotFound("Unknown conversation")

        tool = "confirm_pending_action" if approve else "cancel_pending_action"
        started = time.perf_counter()
        ctx = ToolContext(actor, self._services, conversation_id)
        outcome = await self._registry.execute(ctx, ToolCall("button", tool, {"token": token}))
        record = ToolRecord(tool, self._registry.request_type(tool), outcome.kind, outcome.is_error,
                            int((time.perf_counter() - started) * 1000))

        button = "Confirm" if approve else "Cancel"
        event = (
            f"{SYSTEM_EVENT_PREFIX} (sent by the app, not typed by the user): the user pressed the "
            f"{button} button. Backend result (kind={outcome.kind}): "
            f"{json.dumps(outcome.result, ensure_ascii=False, default=str)}"
        )
        return await self._run(
            actor, conversation_id, stored, [StoredMessage(Message("user", event))], [record], [outcome.blocks]
        )

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

        for _ in range(self._max_steps):
            try:
                response = await self._llm.complete(LLMRequest(system, messages, self._registry.specs))
            except LLMError as error:
                logger.error("Model call failed: %s (%s)", error.message, error.kind)
                failed, final_text = True, LLM_DOWN_TEXT
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
            failed, final_text = True, GAVE_UP_TEXT
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

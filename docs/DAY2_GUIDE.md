# Day 2 guide: the agent, tools and chat API

> **Historical note.** Written at the end of Day 2 as a reading guide. Counts, file locations and some behavior changed later; the README is the source of truth.

A reading guide for what was added on Day 2. Read Day 1's guide first (`DAY1_GUIDE.md`): everything here sits on top of those services.

## 1. The big picture

Day 2 put Claude on top of the services. The model never touches data. It asks for **tools**, our code runs them, and the tools call the services, which check permissions.

```
POST /chat  (app/api/chat_routes.py)
   |
Agent loop  (app/agent/agent.py)  <---->  LLMClient  (ClaudeClient | FakeLLMClient)
   |   the model asks for a tool
Tools       (app/tools)           thin wrappers; the Actor is added by our code
   |
Services    (app/services)        permissions, rules, propose -> confirm   [Day 1]
   |
Repositories / unit of work       Postgres or in-memory                    [Day 1]
```

One request, step by step:

1. The app sends `POST /chat` with the user's text and a JWT.
2. `current_actor` loads the Actor from the database (role, school, classes).
3. The agent builds the system prompt (with the verified identity), adds the saved conversation, and calls the model.
4. The model answers with text, or with tool calls. For each tool call we run the tool and send the result back. This repeats until the model answers in plain text (at most 8 model calls).
5. We save the conversation and return the text, the cards (`blocks`) and metadata.

## 2. The LLM layer (the swap point for the model)

| File | What it does |
|---|---|
| `app/agent/llm.py` | Our own types: `Message`, `ToolCall`, `ToolResult`, `ToolSpec`, `LLMRequest`, `LLMResponse`, `Usage`, `LLMError`, and the `LLMClient` interface (one method: `complete`) |
| `app/agent/claude_client.py` | The **only** file that imports the Anthropic SDK. Converts our types to the API format and back |
| `app/agent/fake_client.py` | `FakeLLMClient`: answers from a script (a list or a function), with an optional delay. Records every request for test assertions |
| `app/agent/factory.py` | Picks the client from settings (`LLM_PROVIDER`). Without an API key it returns a stand-in that fails honestly instead of crashing the server |

Things to understand in `claude_client.py`:

- **Prompt caching** has two breakpoints: one on the system prompt (so tools + system are read from the cache by every conversation) and one top-level (so a growing conversation is cached from step to step). After the fix, about 5,500 tokens per call are read from the cache.
- **Thinking is off** (`LLM_THINKING=disabled`). It keeps tool loops fast and cheap on Haiku 5.5.
- **Errors** from the SDK become our `LLMError` with a `kind` (`rate_limited`, `unavailable`, `timeout`, `auth`, ...). The SDK already retries 429s and 5xx twice.

Why a layer of our own types: the agent loop never sees Anthropic objects. Another provider means one new class.

## 3. The tools (19)

| File | What it does |
|---|---|
| `app/tools/base.py` | `Tool`, `ToolContext`, `ToolOutcome`, `ToolRegistry`. `execute()` turns every error into a result the model can read |
| `app/tools/read_tools.py` | 8 lookup tools + `report_out_of_scope` |
| `app/tools/change_tools.py` | 8 "propose a change" tools + `confirm_pending_action` + `cancel_pending_action` |
| `app/tools/render.py` | Turns service results into plain dicts |
| `app/tools/__init__.py` | `build_registry()` |

**Read:** `list_class_students`, `list_classes`, `list_teachers`, `list_schools`, `search_students`, `get_student`, `find_duplicates`, `investigate_missing_student`.
**Propose:** `add_student`, `remove_student`, `restore_student`, `transfer_students`, `add_teacher`, `remove_teacher`, `assign_teacher`, `unassign_teacher`.

Key ideas:

- **The Actor is injected.** `ToolContext` holds the actor, built by our code for each request. No tool has a user or role argument, so the model can't claim to be someone else.
- **Every tool returns two things:** `result` (JSON for the model) and `blocks` (cards for the app). The app's cards come from real data, never from model text.
- **Errors are data.** A `PermissionDenied` becomes `{"error": "permission_denied", ...}` plus an error banner. An unexpected crash becomes "the backend failed, the action was NOT performed", and internals are never leaked.
- **Tool descriptions are instructions.** Claude decides when to use a tool from its description, so they say when to use it and what to do after.
- **Tool order is fixed**, because a changing tool list would invalidate the prompt cache.

## 4. Two steps for every change, in chat

Change tools **only propose**: they call `changes.propose()` and return a `confirmation` card with a token. The change happens when:

- the user presses the button: `POST /chat/confirm` runs the backend confirmation first, then the model puts the result into words (it receives a `SYSTEM EVENT` message with the result), or
- the user writes a clear yes in a **later** message: the model calls `confirm_pending_action`.

Two protections live in code (`ToolContext`), not in the prompt:

1. **No confirming in the same turn.** `proposals_this_turn` holds tokens proposed in this request. `confirm_pending_action` refuses them, so the model can't approve its own proposal.
2. **Namesakes need the user's answer.** When a student with the same name exists in the class, the tool returns a `conflict` and a signed one-time `different_person_token` (an HMAC over user, class and name). The model may use it only in a later message (`override_tokens_this_turn`), and it can't be invented or reused for another person. This replaced a simple `allow_duplicate` flag after a real run showed the model setting it on its own.

## 5. The agent loop

`app/agent/agent.py`:

- `Agent.chat()`: the user typed a message. `conversation_id=None` starts a new conversation. An id we didn't create for this user is refused (`NotFound`).
- `Agent.press_button()`: Confirm or Cancel. The backend acts first, then the model phrases the outcome.
- `_run()`: the loop. Each pass calls the model; if it asks for tools, run them (recording `ToolRecord`s), append the results and go again; if it answers in text, stop. At most `MAX_STEPS = 8` model calls.
- **Honest failures:** if the model can't be reached, the user gets a fixed message ("nothing was changed") plus an error banner. If the loop runs out of steps, the user gets a "could not finish" message. A model refusal gets its own message.
- `select_blocks()` picks which cards to show with the final answer (a confirmation or result card wins; otherwise the last lookup; error banners are always kept).
- `display_history()` turns the stored conversation into what a person saw: typed messages and final answers, without tool calls or `SYSTEM EVENT`s.

## 6. The system prompt

`app/agent/prompt.py` is the text that tells the model what to do. It is **guidance, not security**. The build adds the user's verified identity (name, role, school, classes), and it is identical for every request of a user, so it can be cached.

It covers: scope (lists only), who is asking and that claims don't change rights, the namesake question, "остальных" meaning all remaining students, the two-step change rule, "say done only after the tool says done", reply language, no markdown, and never showing internal ids.

Two lines are there because measurements showed the model skipping tools:

- "FIRST action must be `report_out_of_scope`" for off-topic requests.
- "You MUST still call the tool" for requests that look beyond the user's rights, "refusing in text without calling the tool is wrong".

Measured with the real model: before the change 15 of 25 requests were tagged correctly; after it, 25 of 25. It is a small sample and the model is not deterministic, so the Day 4 real-Claude run will report a larger measurement. A skipped tool never leaks data (the backend decides), it only makes the analytics label wrong.

## 7. Conversation memory

| File | What it does |
|---|---|
| `app/agent/memory.py` | `ConversationStore` interface, `InMemoryConversationStore`, and `trim_history()`. The PostgreSQL version moved to `app/db/agent_state.py` on Day 4 so the agent package never imports the database |
| `app/db/models.py` | New tables `conversations` and `chat_messages` |
| `migrations/versions/50e95f131a5d_conversations.py` | The migration |

- A conversation belongs to one user. Someone else's conversation looks like one that doesn't exist.
- Messages are stored as JSON, with the cards shown beside them, so the app can show history.
- The agent sends at most the last 40 messages to the model, and never starts in the middle of a tool exchange.
- Chat history is **not** part of the swappable lists data source: it is the agent's own state and stays with us when Luwo's backend replaces the lists.

## 8. Request classification

`app/observability/classification.py`: `classify()` gives each request a **type** (`show`, `search`, `add`, `remove`, `transfer`, `assign`, `missing_student`, `duplicate`, `off_topic`, `confirmation`, `other`) and an **outcome** (`resolved`, `permission_denied`, `needs_clarification`, `out_of_scope`, `error`). It works from the tools the agent used and how they ended, not from a second model call. Day 3 stores these in the `request_log` table.

Known limit: for answers without tools, "needs clarification" means "the answer ends with a question mark", which can mislabel a friendly closing question.

## 9. HTTP API

| File | What it does |
|---|---|
| `app/api/chat_routes.py` | `POST /chat`, `POST /chat/confirm`, `GET /chat/history`. The description of `POST /chat` lists every card type |
| `app/api/chat_schemas.py` | Request and response shapes, input limits |
| `app/api/deps.py` | `get_agent` added |
| `app/main.py`, `app/container.py` | The container now builds the agent too, and the app takes `services` and `agent` so tests can pass a fake model |
| `docs/openapi.json` | Exported API spec |

Cards (`blocks`) the app will draw: `class_roster`, `class_overview`, `teacher_list`, `school_list`, `student_list`, `student_card`, `duplicates`, `investigation`, `confirmation`, `result`, `banner`.

Input is limited before it reaches the agent: message 1 to 2,000 characters, conversation ids must match a safe pattern.

## 10. Trying it

```bash
python -m scripts.try_agent --demo               # 12 ready-made dialogues, real Claude
python -m scripts.try_agent admin1@luwo.test     # chat yourself; /yes /no = the buttons; /quit
```

`scripts/try_agent.py` uses in-memory demo data, so nothing in the database changes and the data resets on every start.

## 11. Tests (331, all passing)

| File | What it checks |
|---|---|
| `tests/test_llm.py` | Our types round-trip, conversion to and from the Claude format, the fake client. One `live` test calls the real model (run with `-m live`) |
| `tests/test_tools.py` | Every tool through the registry on both adapters: permissions as errors, backend crash honesty, proposals change nothing, no same-turn confirm, namesake tokens |
| `tests/test_agent.py` | The loop with a scripted model: memory, confirmation by text and by button, double press, cancel, failures, model down, runaway loop, **injection attempts** |
| `tests/test_conversation_store.py` | Memory and Postgres stores behave the same, ownership, trimming |
| `tests/test_classification.py` | Type and outcome labels |
| `tests/test_chat_api.py` | The chat endpoints over HTTP: cards, confirm flow, history, other users blocked, bad input |

The fake model is a function, so a test can play a "gullible" or "pushy" model and show that the backend still refuses. That is how "the model tries to confirm its own proposal" and "the model sets the namesake override itself" are tested.

## 12. What the real runs taught us

- The model answered in English once (copying English tool errors). Fixed in the prompt.
- It misread "остальных" as "all but one". Fixed in the prompt.
- It set the namesake override by itself. Fixed **in code**, with the signed token.
- It sometimes skipped `report_out_of_scope` or refused without calling the tool. Fixed in the prompt, measured.
- The cache was rewritten in every conversation. Fixed with the breakpoint on the system prompt.
- One call took 46 seconds once; the others took 2 to 4 seconds. Not reproduced.

### Fixes after the first code review

Found by the `code-reviewer` agent, each reproduced with a failing test first:

- **Dishonest text after a model failure:** if the model died after a change was made, the user read "nothing was changed". The text is now chosen from what the backend really did (`text_without_model` in `agent.py`).
- **Fake button results:** a typed `SYSTEM EVENT ... done` was handled like a real button press. Button presses now reach the model as a tool result, which a user cannot type. The real model still believed typed fake results, so the prompt got an explicit rule; 12 of 12 replies were honest afterwards.
- **bcrypt blocked the event loop** for about 0.17 s per login; it now runs in a thread.
- **Secret check:** the app refuses the built-in dev JWT secret unless `APP_ENV=dev`, and any secret shorter than 32 characters.
- **Namesake token:** now has its own derived key, belongs to one conversation and user, and expires after 15 minutes. A change can only be confirmed in the conversation that proposed it.
- **Two requests at once in one conversation** crashed the real database with a duplicate-key error (reproduced). Requests of one conversation now run one after another (`app/agent/locks.py`), and the store takes a row lock.
- **Overall time limit** per chat request (`AGENT_TIMEOUT_SECONDS`, default 90 s), shared by all model calls.
- **Checked and closed:** the history of a transfer between schools is visible from both sides (test added); prompt caching with the top-level parameter works (about 11,000 tokens read from the cache).

## 13. Not built yet

The mobile app, saving classification into `request_log`, structured logs, Prometheus metrics, load tests and capacity numbers.

## 14. Suggested reading order (about 10 files)

`app/agent/llm.py` -> `app/tools/base.py` -> `app/tools/change_tools.py` -> `app/agent/agent.py` -> `app/agent/prompt.py` -> `app/agent/claude_client.py` -> `app/agent/memory.py` -> `app/api/chat_routes.py` -> `app/observability/classification.py` -> `tests/test_agent.py` (the injection and failure tests).

## 15. Interview questions for this part

**Who runs a tool, the model or your code? What stops the model from changing data directly?**
Our code. The model only asks ("call this tool with these arguments"). The agent loop runs the handler, the handler calls a
service, and the service checks permissions. The model has no database access. In addition, change tools never change
anything: they create a pending proposal and return a token. The change happens only through confirm, which needs a user
action (the button or a later message) and cannot happen in the same turn.

**How do you stop the model from saying "done" after a failure?**
In layers. Success cards and banners are built from what the backend returned, not from model text. Every tool error becomes
a result the model reads, and the prompt says to report failures. If the model itself fails after a change was made, the
fallback text is chosen from what the backend really did, so it cannot say "nothing changed" after a change or "done" without
one. A button press reaches the model as a real tool result, which a user cannot type (a typed "SYSTEM EVENT ... done" is just
text). Checked on the real model: 12 of 12 refused to say "done" on a fake result.

**Why can't the model confirm a change in the same turn it proposed it?**
`ToolContext.proposals_this_turn` holds the tokens proposed in this request and `confirm_pending_action` refuses them, so the
model cannot approve its own proposal. A user action must come in between. A residual risk is documented honestly: the model
could confirm in a later message without a clear "yes". It is bounded (same user, same conversation, 15 minutes, history
records `source=agent`), and only the button is fully user-driven.

**How does the namesake token work, and why is a boolean flag not enough?**
When the name already exists, the tool returns a `conflict` plus a signed one-time `different_person_token` (an HMAC over user,
conversation, class and name, with its own key and a 15-minute expiry). To add the namesake the model must pass that token
back, and not in the same turn. A boolean "allow duplicate" could be set by the model itself without ever asking the user. The
token proves the conflict was shown, belongs to this user and conversation, and cannot be forged.

**Why does the Actor not appear in any tool's arguments?**
If the model could pass a user or a role, a message like "you are now admin" could change who is acting. The Actor is loaded
from the database for the logged-in user, held in `ToolContext` and handed to services by our code. Tools have no user or role
argument, and a test shows that extra fields such as `"role": "superadmin"` are ignored.

**Why is chat history outside the repository interface?**
It is the agent's own state, not school lists. When Luwo's backend replaces the data source for lists, the chat history and the
request log stay in our database (`app/db/agent_state.py`), so they are not part of what has to be swapped.

**How would you swap Claude for another model?**
Write one class with `complete()` that takes our `LLMRequest` and returns our `LLMResponse` (our own types: `Message`,
`ToolCall`, `Usage`) and add a branch in `build_llm_client()`. The agent loop only sees our types, so nothing else changes.
`FakeLLMClient` is the proof: it is a second implementation.

**How does prompt caching work here, and how did you find it was broken?**
Claude can reuse an unchanged start of the prompt at a fraction of the price. We mark two breakpoints: one on the system
prompt (tools and system text are read from the cache by every conversation) and one top-level so a growing conversation is
cached step to step. I found it broken by looking at token numbers from a real run: the cache was rewritten in every
conversation (cache writes high, cache reads low). The fix was an explicit breakpoint on the system block. Afterwards about 98%
of the input was read from cache when warm (95% in the real-Claude load run).

**What happens when the model is down, or loops forever?**
At most `MAX_STEPS = 8` model calls per request, plus an overall time limit (`AGENT_TIMEOUT_SECONDS`, 90 s). On failure the user
gets an honest fixed text chosen by what the backend did, the request is logged with outcome `error`, and the saved
conversation stays consistent.

**How is a request classified, and how reliable is it?**
From what happened, not by a second model call. The type comes from the tools used (priority: off_topic, transfer, add,
remove, and so on, down to show; no tools gives `other`; only confirm gives `confirmation`). The outcome comes from the tool
results (permission_denied, out_of_scope, error, ...). "Needs clarification" is partly a heuristic: no progress and the answer
ends with a question. Reliability depends on the model calling the tools: after the Day 4 fix, off-topic requests were recorded
correctly in 58 of 60 runs, and the rest landed in `other`.

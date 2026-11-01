# Day 3 guide: the mobile app, analytics, logs and metrics

> **Historical note.** Written at the end of Day 3 as a reading guide. Counts, file locations and some behavior changed later; the README is the source of truth.

Read `DAY1_GUIDE.md` and `DAY2_GUIDE.md` first. Day 3 added two things on top of them: a phone app, and the
ability to see what the agent does (analytics, logs, metrics).

## 1. Review fixes done before the app

The first code review found problems; they were fixed with a failing test first each time (details in
`DAY2_GUIDE.md`, "Fixes after the first code review"). Two things worth knowing:

- Fix #2 (a typed fake "backend result") was only fully proven on the real model: the scripted test passed,
  but the real Claude still believed the fake text until the prompt got an explicit rule.
- `app/main.py` no longer builds the application when imported (`app` is created on first access), so tests and
  tools can import it without side effects.

## 2. The mobile app (`mobile/`)

Expo SDK 58, React Native, TypeScript (strict), Expo Router. Two screens: login and chat.

| File | What it does |
|---|---|
| `src/app/_layout.tsx` | Loads fonts, keeps the splash screen until we know who is signed in, and protects routes with `Stack.Protected` (signed out → login) |
| `src/app/login.tsx`, `src/app/index.tsx` | The two screens. Login has one-tap demo users |
| `src/api/client.ts`, `types.ts` | The only place that calls the backend; typed errors; Russian messages for people |
| `src/session.tsx`, `src/storage.ts` | Sign in/out, saved session (secure storage on the phone, `localStorage` in the browser) |
| `src/chat/state.ts` | **The chat state as a pure reducer** (no UI), so it can be tested directly |
| `src/chat/useChat.ts` | A hook that connects the reducer to the server |
| `src/components/cards/` | One component per card type the backend sends (`CardRenderer` picks it) |
| `src/components/` | Bubbles, composer with suggestion chips, header, the user switcher sheet, empty state |
| `src/format.ts`, `src/theme.ts`, `src/suggestions.ts`, `src/demo.ts` | Text helpers, design tokens, role-based suggestion chips, demo accounts |

Decisions to be able to explain:

- **Cards come from structured blocks, not model text.** The list of students is drawn from real data, so the model
  cannot invent a name on a card. An unknown block type is skipped instead of crashing.
- **A confirmation card's state is derived from data.** "Confirmed" is decided by a `result` card carrying the same
  token (so a reloaded history shows used confirmations correctly). A reply WITHOUT a result card for that token counts
  as a failure, never as success. The backend change that made this possible: result cards now carry the `token`.
- **Messages that fail to send stay in the chat** with a "Повторить" button. A rejected token (401) sends the person to
  login and wipes the session; an unreachable server keeps the saved session and says there is no connection.
- **Server error texts are English; people see Russian.** The app maps error codes to Russian text (`bannerText`).
- **Design from luwo.ai**: its own colors (navy, cyan), fonts (Oswald, Inter) and pill shapes, taken from its stylesheet.
  A mockup is in `docs/design/mockup.html`.

Real-run findings that led to changes (found by looking at the app, not by reading logs):

| Problem seen in the screenshots | Fix |
|---|---|
| The agent answered in English (7 of 36 runs) and wrote an English "thinking aloud" line before correct answers | Language rule moved to the top of the prompt; one-sentence preamble before tools forbidden; a small guard (`app/agent/language.py`) removes a leading English paragraph if it still happens. Result: 0 of 72 |
| The text repeated the list the card already shows (6 of 6) | Prompt: never write list rows again. Result: 0 of 12 for rosters |
| No "which student?" picker, because the model asked in text without searching (6 of 6) | Prompt: always call `search_students` before asking which one, with an example. Result: 0 of 12 |
| A rights question answered in text without calling the backend (no red banner, wrong analytics label), 6 of 32 | Examples in the prompt. Result: 1 of 32 |
| The red banner showed the backend's English message | Error codes mapped to Russian in the app |

## 3. Analytics, logs, metrics (`app/observability/`)

The agent knows only an **`Observer`** and calls it at four moments: a conversation starts, a tool finishes, a model
call finishes, a request finishes. `Telemetry` (the real observer) turns each into a log line, Prometheus metrics, and a
row in `request_log`. `NullObserver` does nothing (tests). Monitoring can never break a chat: every method swallows and
logs its own failures (tested with a broken request log).

| File | What it does |
|---|---|
| `request_log.py` | `RequestLogStore` (interface and memory version; the Postgres version is in `app/db/agent_state.py`), one row per chat request, and the statistics: counts by type and outcome, tokens, p50/p95 |
| `classification.py` | Type and outcome of a request, derived from the tools used (Day 2) |
| `telemetry.py` | The `Observer` interface, `NullObserver`, `Telemetry` |
| `logging.py` | structlog set up so our logs and library logs are all JSON, with ids from `contextvars` |
| `metrics.py` | The Prometheus metrics, the HTTP middleware, the database timing hook, the process collector (psutil) |
| `app/api/analytics_routes.py` | `GET /analytics/requests` (superadmin only) |
| `monitoring/`, `docker-compose.yml` | Prometheus config, Grafana provisioning, the dashboard (24 panels), the `observability` profile |

Things to be able to explain:

- **Cardinality.** Metric labels only take values from small fixed sets (route template, request type, tool name).
  A user id or conversation id as a label would create a new time series for each one. A test checks this, and unknown
  URLs share one label (`unmatched`) so a scanner cannot flood the metrics.
- **Histograms, not averages.** p50/p95 are computed by Prometheus from histogram buckets (`histogram_quantile`).
- **Database time without touching repositories.** One SQLAlchemy engine event hook measures every statement, so the
  repository layer stays free of monitoring code.
- **Tokens per conversation** from two counters (`luwo_llm_tokens_total / luwo_conversations_started_total`), and exactly
  per conversation from `request_log`.
- **Context ids in logs.** `conversation_id` and `user_id` are bound once per request (`request_scope`) and appear on
  every line, including logs from libraries; they are cleared afterwards (tested: no leaking into the next request).
- **Privacy.** `LOG_USER_TEXT=false` keeps message text and tool arguments out of the logs.
- **`/metrics` token.** `METRICS_TOKEN` makes Prometheus send a bearer token.

## 4. Numbers seen so far (one real run, not the load test)

About 12,000 model tokens per chat request and about 15,600 per conversation; 57% of input tokens served from the prompt
cache in the first run and 98% once warm; agent p50 about 2.5 s and p95 about 4.7 s; one Claude call p50 about 1.4 s; one SQL statement about 1 ms;
process memory about 160 MB. These are from a short warm-up, not a capacity measurement: the proper numbers
come from the load test.

## 5. Tests

| Where | What |
|---|---|
| `tests/test_observability.py` (26 test cases) | Analytics permissions and answers; metrics counted correctly; label cardinality; `/metrics` format and token; DB timing (Postgres); log content and levels; no id leaking between requests; broken monitoring does not break the chat |
| `tests/test_request_log.py` | The statistics, identical on memory and Postgres (percentiles included) |
| `tests/test_language.py`, `tests/test_agent.py` | The language guard |
| `tests/test_tools.py`, `tests/test_chat_api.py` | Result cards carry the token; CORS |
| `mobile/src/__tests__/` (77 tests) | API client (errors, timeout), chat reducer, formatting, card components (buttons, states, picker) |

The mobile tests were checked by breaking the app on purpose: two deliberate mistakes (a "done" card keeping its buttons;
an answer without a result counted as success) made 3 and 1 tests fail.

## 6. Interview questions for this part

**Why are the cards drawn from blocks and not from the model's text?**
Blocks are structured data built by our backend from tool results (class roster, confirmation, student card, ...). The app
draws real data, so the model cannot invent a student or a button, and the numbers on a card are always the backend's. The
model's text is only the commentary, and the prompt forbids writing the list out again. It also lets the app draw a
Confirm/Cancel card with a real token.

**How does the app know a confirmation was already used after you reload the chat?**
The state is derived from data, not stored in the app. History returns messages together with their cards, and a confirmation
card counts as used when a later `result` card carries the same token. Even if someone pressed it again, the server is
idempotent: it answers "already done" and changes nothing.

**What happens in the app when the server is down? When the token is rejected?**
Server unreachable: the message stays in the chat with a "Повторить" button, the saved login is kept, and a friendly "no
connection" message is shown. Token rejected (401): the session is wiped and the app goes back to the login screen.

**What is label cardinality and where could it have gone wrong here?**
A Prometheus label creates a separate time series for every distinct value. If metrics were labeled with a user id, a
conversation id or the raw URL, the number of series would grow without limit and memory would blow up. Our labels come from
small fixed sets (route template, request type, tool name), unknown URLs share one `unmatched` label so a scanner cannot flood
the metrics, and a test checks this.

**How do you get p95 database time without changing any repository?**
A SQLAlchemy engine event hook times every statement (before and after cursor execute) and feeds a histogram. The repositories
know nothing about it (on Day 4 the hook moved to `app/db/instrumentation.py`, so upper layers stay free of database code).
Prometheus then computes p95 from the histogram.

**How do you get "tokens per conversation" without a conversation-id label?**
Two counters with no per-conversation label: total tokens and conversations started. Tokens per conversation is
`increase(tokens) / increase(conversations started)` over the selected time range, which is what the dashboard panel computes.
There is also a histogram of tokens per request.

**What do you log, and how would you keep personal data out of the logs?**
One JSON line per event, with the conversation id, user id and request id: conversation started, each tool call, the request
summary (type, outcome, tools, tokens, duration) and the HTTP line. Message text and tool arguments are logged only when
`LOG_USER_TEXT` is on (default on in development, off elsewhere), and confirmation tokens are redacted. Messages can contain
children's names, so a real deployment should keep it off.

**How do you make sure monitoring cannot take the chat down?**
The `Telemetry` observer wraps every method so an exception inside it is swallowed, the request-log write is best effort, the
HTTP metrics use a light ASGI middleware, and Prometheus and Grafana are separate optional containers. If monitoring breaks,
chats keep working.

**What did you find by looking at the real app that tests had not found?**
Using the real model and the app: English replies, lists written out again under the card, a missing student picker, rights
questions answered without calling the backend (wrong analytics label), the cache being rewritten every conversation, and an
English banner. Each was fixed with a prompt rule, the language guard or a structural change, and measured on the real model
(for example rights questions answered without the backend went from 6 of 32 to 1 of 32).

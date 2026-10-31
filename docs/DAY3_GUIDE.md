# Day 3 guide: the mobile app, analytics, logs and metrics

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
| `request_log.py` | `RequestLogStore` (memory and Postgres), one row per chat request, and the statistics: counts by type and outcome, tokens, p50/p95 |
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

1. Why are the cards drawn from blocks and not from the model's text?
2. How does the app know a confirmation was already used after you reload the chat?
3. What happens in the app when the server is down? When the token is rejected?
4. What is label cardinality and where could it have gone wrong here?
5. How do you get p95 database time without changing any repository?
6. How do you get "tokens per conversation" without a conversation-id label?
7. What do you log, and how would you keep personal data out of the logs?
8. How do you make sure monitoring cannot take the chat down?
9. What did you find by looking at the real app that tests had not found?

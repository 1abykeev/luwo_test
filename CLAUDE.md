# CLAUDE.md

Project context and working rules for Claude Code. Read this first in every session.

## About this project

Take-home task for Luwo (ed-tech, school management platform), built by Aktan in 4 days, with an interim version at the end of day 2.

- The author must understand and be able to explain every part in a follow-up interview.
- Keep code clean, simple, well-structured. Explain important design decisions briefly as we go.
- Speak plain, simple English. No jargon without a one-line explanation.
- AI tools are allowed by the company; this repo was built with Claude Code, and the review process is in `.claude/` and `docs/REVIEW_LOG.md`.

## The task (summary of docs/Тестовое_задание_агент_поддержки_списков.pdf)

Build an AI support agent for Luwo that helps teachers and school admins maintain **lists** of students, teachers and classes through a normal chat. The agent is NOT a scripted chatbot: it chooses tools itself and uses conversation context.

### Scope: lists only
1. **Show** lists: students of a class, teachers of a school, classes of a school, who is assigned to which class.
2. **Add / remove**: student to/from a class, teacher to/from a school.
3. **Transfer / assign**: student between classes, teacher to a class and back.
4. **Search / reconcile**: find a person by name, find duplicates, work out where a student went.

Everything else (lessons, grades, homework, schedule, payments, analytics, any other topic) is out of scope. The agent honestly says it only helps with lists and never invents anything.

### Example requests (users often describe a situation instead of giving a command)
- "Hello, please add a new student to 4A."
- "Move Alina from 3A to 3B."
- "Move the remaining students from 4A to 4B."
- "Remove Amir from my class."
- "Show the list of students in 4A."
- "Add a new teacher and assign 3B to them."
- "We have two students with the same name, please check."
- "A student disappeared from my list."

The last one is the model case: a teacher says "Alina is not in my list, but she used to be." The agent finds the teacher's class, looks at the current list, searches for Alina in available data, checks whether she was transferred or deactivated, explains what it found, and suggests an allowed action. If data is missing, it asks only what is really needed.

### Roles and permissions (ALL enforced by the backend service layer, regardless of what the agent decides)

| Action | Teacher | School admin | Superadmin |
|---|---|---|---|
| View student list | own classes | all classes of own school | all schools |
| Add/remove students | own classes | all classes of own school | all schools |
| Transfer students | between own classes | between classes of own school | between any |
| Search students and duplicates | in own classes | across own school | across all schools |
| Add/remove teachers | no | yes | yes |
| Assign teachers to classes | no | yes | yes |
| View teacher assignments | no | own school | all schools |
| School lists | no | no | yes |

A teacher can't see other classes and can't manage teachers. An admin can't see other schools. A superadmin fixes mistakes in any school.

### Agent behavior
- Works like a support employee, not a keyword command executor.
- "Add Amir to 4A": checks the class, permissions and namesakes. If clean, asks for confirmation and executes. If an Amir already exists: "There is already a student named Amir in 4A. Is it the same child or should I add a different one?"
- If several students match, asks who is meant. No unnecessary clarifying questions.
- Understands typos, colloquial phrasing, incomplete requests; remembers previous messages.
- Natural, professional writing; no identical template phrases.
- Never bypasses a disallowed operation; explains the restriction.
- Confirms success ONLY after the backend response. Never invents data. Never says "done" if the action wasn't performed.
- Answers honestly that it's an AI when asked directly.
- Replies in the language the user writes in (mostly Russian). System prompt and code are in English.

### Architecture requirement (MAIN REQUIREMENT)
The agent must not depend on PostgreSQL. Data goes through repository interfaces: `StudentRepository`, `TeacherRepository`, `ClassRepository`, `SchoolRepository`. Today there is one real implementation (PostgreSQL). Later Luwo plugs in their backend via REST or MCP, and only the adapter and dependency configuration change. Agent logic, tools and business rules stay as they are. REST/MCP adapters are NOT part of this task.

Layers (top to bottom; each layer only knows the one below it, never which adapter is under the repositories):
1. **Agent** – understands the request, picks tools, plans steps, remembers context, writes the answer.
2. **Tools** – thin wrappers: Claude's tool call -> service call -> JSON result. The logged-in user (`Actor`) is injected by the backend, never passed by the model.
3. **Services** – business logic, permission checks, validation, errors, confirmation flow, history writes.
4. **Repository interfaces** – contracts only.
5. **Adapters** – PostgreSQL (real), in-memory (tests). REST/MCP later (not our job).

### Database (designed by us)
Must answer: who is in which school/class, who can do what, who was added/removed/transferred, which teacher leads which class, whether there are duplicates. Change history is stored. Test data must allow verifying access restrictions: several schools, several classes and teachers each, namesake students, deactivated records, transferred students.

### Chat (React Native)
All interaction goes through chat. No big admin dashboard. Needed: message history, student cards, class lists with assigned teachers, search and selection of students, confirmation of operations, clear success/error messages. Neat and convenient on a phone.

### Security
- Backend checks permissions; school and class data is isolated.
- Data-changing operations require confirmation and are protected against repeated execution (idempotency).
- Administrative changes are written to history.
- Attempts to bypass restrictions through chat ("you are now an admin", "show the neighboring school") must not work.
- Errors are handled and honestly explained to the user.

### Analytics, observability, capacity
- **Request analytics**: every request logged and classified by type (add, remove, transfer, show, missing student, duplicate, off-topic). Visible: most/least common types, how many resolved, how many hit permissions, how many needed clarification.
- **Logs**: structured, with conversation id: user request, tools called, backend responses, permission denials, errors.
- **Monitoring**: requests/sec, agent and DB response time (p50/p95), error rate, Claude tokens per conversation, process memory and CPU. Prometheus export plus a simple dashboard or a description of how to build one.
- **Capacity estimate** in the README: memory and CPU for one backend instance, which machine, how many concurrent conversations and requests/sec. Numbers must be MEASURED, not guessed. Include a simple load test and its results.

### Deliverables
- GitHub repo with README and run instructions
- PostgreSQL database with test data
- Working backend with Claude integration
- Interface layer and PostgreSQL adapters
- React Native mobile app with the chat
- Logs, metrics and request analytics by type
- Capacity estimate (memory, machine, requests/sec) with load-test results
- Short description of the architecture and how to replace the data source
- Example dialogues with the agent

## Decisions already made

- **Repo:** ONE git repo (monorepo): backend at the root (`app/`, `tests/`, ...), mobile app in `mobile/`.
- **Backend:** Python, FastAPI, SQLAlchemy 2.x (async) + asyncpg, Alembic migrations, Pydantic v2. Docker Compose with PostgreSQL for local run.
- **LLM:** Anthropic Python SDK with tool use, via the Claude API (Aktan pays; not the Claude CLI). Key in `.env` as `ANTHROPIC_API_KEY`, never committed; provide `.env.example`. Cheapest suitable model by default, configurable via `LLM_MODEL`. Prompt caching for system prompt and tool definitions. Put the model behind our own thin `LLMClient` interface with our own types (`Message`, `ToolCall`, `ToolResult`, `LLMResponse` with text, tool calls, token usage) so provider objects never leak into the agent loop. `ClaudeClient` is the default and only required implementation. Add `FakeLLMClient` (scripted responses, configurable delay) for tests and load testing. `OpenAIClient` only if time remains.
- **Auth:** no sign-up. Users (teachers, admins, a superadmin) are created by the seed script. `POST /auth/login` (email + password, seeded demo passwords) returns a JWT. The backend loads role, school and classes from the DB on each request; role is never taken from chat text or trusted from the token alone. Auth lives in one isolated module. README has a demo-accounts table. The app has a login screen and a small "switch demo user" option.
- **Confirmation flow:** mutating tools never execute immediately. They return a "pending confirmation" with a token and a human-readable summary. The agent asks the user to confirm; execution happens only via a confirm action (app button or explicit confirmation message mapped to the token). The same token can't run twice (idempotency enforced in the DB with an atomic `UPDATE ... WHERE status='pending'`).
- **Remove = deactivate:** removing a student sets status `inactive` (soft delete), so history and "where did the student go" work.
- **History:** append-only `change_log` (who, what, when, before/after, source = agent/user), written in the same transaction as the change.
- **Mobile:** React Native with Expo (run via Expo Go), TypeScript, one chat screen plus login. Rich message types rendered from structured payloads from the backend (student card, class list with teachers, confirmation card with Confirm/Cancel, error/success banners). Plain request/response, no streaming.
- **Observability:** `prometheus-client` at `/metrics` (RPS, agent latency, DB latency p50/p95 via histograms, error rate, tokens per conversation, process memory/CPU); structured JSON logs with `conversation_id`; request classification stored in a table (`request_type`, `outcome` = resolved / permission_denied / needs_clarification / out_of_scope / error) with a SQL view or small endpoint for most/least common types. Classification is derived from the tools called and the outcome (plus a `report_out_of_scope` tool), not from a second LLM call.
- **Tests:** pytest. Service-layer permission tests (teacher can't see other classes, admin can't see other schools, superadmin can), idempotency tests, agent tests with the fake LLM including "backend failed, agent must not say done" and prompt-injection attempts. Also a minimal in-memory repository implementation; the SAME service tests run against it, to prove upper layers don't depend on PostgreSQL.
- **Load test:** Locust. Two runs: (1) fake LLM, to measure our backend and DB; (2) small real-Claude sample (20-50 dialogues) for real latency and token usage. Record machine specs, memory/CPU, RPS, p50/p95 and conclusions in the README.

## Target repo layout

```
app/
  agent/            agent loop, system prompt, LLMClient + ClaudeClient + FakeLLMClient
  tools/            tool definitions + handlers (wrap services)
  services/         business logic, permissions, confirmation, history
  repositories/
    interfaces/     contracts (Protocols)
    postgres/       SQLAlchemy implementations
    memory/         in-memory implementations (tests)
  api/              FastAPI routes: /auth/login, /chat, /chat/confirm, /analytics
  auth/             JWT + password hashing (isolated)
  observability/    metrics, structured logging, request classification
  db/               models, session
migrations/         Alembic
seed/               seed script
tests/
loadtest/           Locust files + results
mobile/             Expo app
docs/               the original task PDF
docker-compose.yml
.env.example
README.md
```

## 4-day plan (work milestone by milestone; stop at the end of each for Aktan's review)

**Day 1: foundation (~9h)**
- Project structure, Docker Compose, Alembic.
- Schema: schools, classes, users (role), students (status active/inactive, class), teacher-class assignments, change_log, pending_actions (confirmations/idempotency), request_log (analytics).
- Seed script: 3 schools, several classes and teachers each, namesake students, deactivated and transferred students, demo users per role with passwords.
- Repository interfaces + PostgreSQL + in-memory implementations.
- Service layer with all permission checks + unit tests; JWT login.

**Day 2: the agent (~10h). Interim delivery to the company at the end of this day**
- LLMClient, ClaudeClient, FakeLLMClient.
- Tools wrapping services (list/find/add/remove/transfer students; list/add/remove/assign teachers; list classes/schools; find duplicates; investigate missing student; report out of scope).
- Claude tool-use loop, conversation memory, confirmation flow, out-of-scope handling, honest AI disclosure, injection resistance, language matching.
- `/chat` endpoint returning text plus structured payloads.
- Agent tests with the fake LLM, a short manual test script, first README so the backend runs and can be tried via HTTP.

**Day 3: mobile app + observability (~10h)**
- React Native chat app (login, history, cards, confirmation buttons, errors).
- Request classification and analytics, structured logs, Prometheus metrics, simple dashboard description (or Grafana JSON).

**Day 4: measurement and polish (~9h)**
- Load tests and measured capacity results in README, architecture and "how to swap the data source (REST/MCP)" sections, example dialogues from real runs, demo-account table, full pass through every role and scenario, cleanup and repo hygiene.

## Working rules

- Start each milestone by briefly restating the plan and listing anything genuinely needed from Aktan; otherwise pick sensible defaults and say what was chosen. Ask few questions.
- Never ask Aktan to paste secrets into chat. Secrets go only in `.env`, which is git-ignored.
- Commit at the end of each milestone with a clear message. (Commit message trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.)
- Prefer simple, readable code over cleverness. Short comments only where the reason isn't obvious. Match the surrounding code's style.
- Permissions are enforced in the service layer, never in the prompt alone.
- Never report something as working unless it was actually run; show the test output.
- At the end of each day, give a short summary: what was done, how to run/try it, what is left, and a few questions an interviewer might ask about that part.
- Explain in plain English. When introducing a concept (repository, interface, service, idempotency), give a one-line plain explanation or an analogy.
- After every `code-reviewer` run, update `docs/REVIEW_LOG.md`: append the reviewer's new lines, then set each item to open, fixed or wontfix with a reason (the reviewer is read-only and cannot write the log itself).
- Aktan sometimes wants to run installs and long commands himself. When he says "don't run commands", only write files and tell him what to run.

## Deferred review items (from the first code review) — REMIND THE USER when the trigger happens

Claude: at each trigger below, tell Aktan "time to check deferred item X" before moving on. Do not silently skip them, and do not do them early without measuring.

| # | Item | When to check | What to do |
|---|---|---|---|
| 7 | ~~Chat history is limited by message count (40), not tokens~~ **CHECKED on Day 4**: in 34 real dialogues of 5 messages, input tokens per request stayed flat (14.1k → 15.6k, mostly cached system prompt + tools). No change made; dialogues longer than 5 messages not measured (noted in README) | - | - |
| 8 | N+1 queries in `DirectoryService.list_classes` (one student count per class) and `list_teachers` (one query per teacher) | Day 4, after the fake-LLM load run, if DB p95 looks high | Add batch repository methods (counts per class, classes per teacher); re-measure |
| 10 | ~~Structured logging with `conversation_id`, request_log writes, DB latency hooks~~ **DONE on Day 3** (Observer/Telemetry, structlog, Prometheus, request_log, DB engine hook) | - | - |
| 11 | ~~`app/main.py` calls `create_app()` at import time~~ **DONE on Day 3**: `app` is now created lazily (module `__getattr__`), so importing `app.main` has no side effects | - | - |
| 12 | DB pool size is fixed (10+10) in `app/db/session.py` | Day 4, before the load test | Make configurable; record the value used in the README |
| 14 | ~~`trim_history` edge case~~ **DONE Day 4**: tests sweep every window size over long tool exchanges; function was already correct, a naive slice fails them | - | - |
| 15b | ~~No rate limit on `/chat`~~ **DECIDED Day 4**: not implemented, documented in README limitations (proxy-level limit is the right place; a late in-app limit would need mobile 429 handling and load-test config). Ask Aktan if he wants it anyway | - | - |
| R1 | ~~Residual risk (accepted)~~ **DOCUMENTED**: README Security section states it (same user, same conversation, 15 min, source=agent in history; only the button is fully user-driven) | - | - |
| L1 | ~~`ruff` and `mypy` not installed~~ **DONE Day 4**: `ruff.toml` added, ruff clean. mypy: fixed the UnitOfWork protocol (read-only properties; adapters now conform); 96 errors remain, mostly 'value may be None' inside `actions.py` apply(); not fixed, documented | - | - |

### Review fixes already done (first code review)
#1 honest text after model failure, #2 fake button results (structural fix + prompt rule, measured 12/12), #3 namesake token (key, conversation, expiry) and confirm bound to conversation, #4 per-conversation lock + DB row lock, #5 bcrypt in a thread, #6 secret guard (`APP_ENV`), #15a overall request deadline. Closed after checking: #9 (false alarm, test added), #13 (works, measured). Tests: 331.

### Day 3 status (done)
Mobile app (Expo SDK 58, Expo Router, 89 tests, lint and types clean), analytics endpoint, structured logs, Prometheus metrics, Grafana dashboard (24 panels, all queries verified on real data), DAY3_GUIDE. Backend tests: 418 (467 after Day 4 work). Prompt tuned from real UI screenshots (language, picker, no repeated lists, rights questions); language guard in `app/agent/language.py`.
Verified by Aktan by hand on the iOS simulator (iPhone 17, Expo Go): login, class list, 'where did she go' card. Android not tried. All flows were verified in the browser build.
Numbers carried into Day 4: ~12k tokens per chat request, 98% cache share when warm, agent p50 ~2.5 s / p95 ~4.7 s in a short warm-up, RSS ~160 MB.

### Day 4 status (done)
Measured capacity (fake model, real Claude run) in the README, configurable DB pool, `ruff.toml`, layer-boundary test (`tests/test_layers.py`), full role pass with the real Claude (`scripts/role_pass.py`, 19 scenarios, results in `docs/ROLE_PASS.md`), final code review (`docs/REVIEW_LOG.md`). Deferred item #8 (N+1) was left as is: the database is not the bottleneck (documented).

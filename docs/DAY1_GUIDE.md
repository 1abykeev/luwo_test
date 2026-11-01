# Day 1 guide: what was built and where

> **Historical note.** Written at the end of Day 1 as a reading guide. Counts, file locations and some behavior changed later; the README is the source of truth.

A reading guide for the foundation of the Luwo list-support agent. Read the sections in order, then open the files they name.

## 1. The big picture

Day 1 built the **bottom layers** of the system, plus login. The agent (Claude) sits on top of them from Day 2.

```
HTTP API  (app/api, app/main.py)                       only login for now
   |
Services  (app/services)                               rules, permissions, confirmation
   |
Repository interfaces (app/repositories/interfaces)    contracts only
   |
Adapters: postgres/  and  memory/                      the actual storage
```

Each layer talks only to the one below it. Services never import SQLAlchemy.

## 2. Project setup

| File | What it does |
|---|---|
| `docker-compose.yml` | Runs Postgres 16 in Docker on host port **5433** |
| `.env.example` / `.env` | Settings; `.env` is git-ignored |
| `app/config.py` | Reads settings from `.env` (database URL, JWT secret, `DATA_SOURCE`) |
| `requirements.txt`, `.gitignore`, `pytest.ini` | Dependencies, ignored files, test config |
| `CLAUDE.md` | Project rules and plan for Claude Code; not part of the app |

## 3. The database

| File | What it does |
|---|---|
| `app/db/models.py` | The 8 tables: `schools`, `users`, `classes`, `class_teachers`, `students`, `change_log`, `pending_actions`, `request_log` |
| `app/db/base.py`, `app/db/session.py` | SQLAlchemy base class; database connection |
| `alembic.ini`, `migrations/env.py`, `migrations/versions/*` | Alembic keeps the schema in versioned files. Two migrations: initial schema, then `users.email` made nullable |

Things to understand in `models.py`:

- **Constraints live in the database** (valid roles, valid statuses). Bad data is rejected even if the code has a bug.
- A **deactivated student keeps their `class_id`**, so we can say where they were.
- `change_log` is the history. `pending_actions` holds unconfirmed changes. `request_log` is for Day 3 analytics.

## 4. Domain types

| File | What it does |
|---|---|
| `app/domain/models.py` | Plain dataclasses: `Student`, `Teacher`, `User`, `Actor`, `Scope`, `ChangeEntry`, `PendingAction`, `Role` |
| `app/domain/errors.py` | `PermissionDenied`, `NotFound`, `InvalidRequest`, `Conflict`, `AuthenticationFailed` |

Two types matter most:

- **`Actor`**: "who is making this request". Built from the database for every request, never from chat text.
- **`Scope`**: "what data a search may look at". The service builds it from the Actor and the repository filters by it.

## 5. Repositories (the swap point)

| Folder | What it does |
|---|---|
| `app/repositories/interfaces/` | **Contracts only**: `StudentRepository`, `TeacherRepository`, `ClassRepository`, `SchoolRepository`, plus `UserRepository`, `HistoryRepository`, `PendingActionRepository`, `UnitOfWork` |
| `app/repositories/postgres/` | Real SQL implementations, plus `unit_of_work.py` |
| `app/repositories/memory/` | Same contracts with Python dicts (`store.py`, `repositories.py`, `unit_of_work.py`) |

**Unit of work** (`interfaces/unit_of_work.py`): one business operation uses one transaction. A change and its history row are saved together or not at all. Leaving the `async with` block without `commit()` rolls everything back. `UnitOfWorkFactory` is the single place where the data source is chosen.

**`pending.claim()`** (`postgres/pending.py`) is the idempotency mechanism. It is one `UPDATE ... WHERE status='pending'`, so the database picks exactly one winner.

## 6. Demo data

| File | What it does |
|---|---|
| `seed/world.py` | Builds the demo world as plain objects: 3 schools, 9 classes, 12 users, 44 students, namesakes, deactivated students, 2 transfers, 1 removed teacher |
| `seed/seed.py` | Writes that world into Postgres: `python -m seed.seed` |

The in-memory adapter loads from the same `world.py`, so the same tests run on identical data.

## 7. Services (where the real logic is)

Read these in this order:

1. **`services/permissions.py`**: the permission table from the task as code (`scope_for`, `can_access_class`, `can_access_student`, ...).
2. **`services/names.py`**: handles Latin "4A" vs Cyrillic "4А", "3B" meaning 3Б, and name validation.
3. **`services/actors.py`**: `load(user_id)` builds the Actor from the database and rejects removed accounts.
4. **`services/directory.py`**: class rosters, class lists, teacher lists, school lists, and resolving "4А" plus a school name to a class.
5. **`services/students.py`**: search, student card, duplicates, and `investigate_missing_student` ("where did she go?").
6. **`services/actions.py`**: the 8 changes (add, remove, restore, transfer students; add, remove, assign, unassign teachers). Each has `plan()` (check and describe) and `apply()` (do it and write history).
7. **`services/changes.py`**: `propose()` stores a pending action and changes nothing. `confirm()` claims the token, re-checks, applies, writes history and commits, all in one transaction.
8. `services/views.py`, `services/common.py`, `services/__init__.py`: result dataclasses, a small helper, and the container that wires services together.

Policies built in:

- **Hidden destination.** A teacher learns that a student left their class, but not the new class if it isn't theirs.
- **Out-of-scope ids return "not found"**, not "forbidden", so ids can't be used to probe other schools.
- **Same name in the same class blocks the request** until the user decides. The same name elsewhere is only a warning.
- **Double confirm.** A second confirm returns the first result with `already_applied=True`.

## 8. Auth and API

| File | What it does |
|---|---|
| `app/auth/passwords.py` | bcrypt hashing |
| `app/auth/tokens.py` | JWT with only the user id inside; role is loaded from the database every time |
| `app/auth/service.py` | Login; every failure gives the same message |
| `app/api/deps.py` | `current_actor`: token, then user id, then Actor from the database |
| `app/api/auth_routes.py`, `app/api/schemas.py`, `app/api/errors.py` | `/auth/login`, `/auth/me`, request/response shapes, error-to-HTTP-code mapping |
| `app/main.py` | Creates the FastAPI app; also serves `/health` and `/docs` |
| `app/container.py` | **The composition root**: picks the data source. To plug in Luwo's REST backend, add a branch here |

## 9. Tests (139, all passing)

| File | What it checks |
|---|---|
| `tests/conftest.py` | Runs each service test on both memory and a real Postgres test database (`luwo_test`) |
| `tests/helpers.py` | Looks up ids by name in the demo world |
| `tests/test_names.py` | Class names, name cleaning |
| `tests/test_permissions_read.py` | Permission table for reads and the missing-student cases |
| `tests/test_changes.py` | Propose/confirm, double confirm, 5 simultaneous confirms, expiry, rights for writes, history |
| `tests/test_auth.py` | Login, forged/expired/unsigned tokens, removed accounts |

## 10. One request end to end

A teacher moves a student between two of her classes:

1. `propose("transfer_students", {...})` runs `actions.TransferStudents.plan()`. It checks she leads both classes and the student is active, saves a pending row and returns a token and details. **Nothing has changed yet.**
2. `confirm(token)` runs `claim()`, which flips pending to confirmed. Then `plan()` runs again, `apply()` moves the student and writes history, and `commit()` saves it all.
3. Confirming again returns the first result with `already_applied=True`.

## 11. Suggested reading order (about 10 files)

`domain/models.py` -> `repositories/interfaces/unit_of_work.py` -> `services/permissions.py` -> `services/actions.py` (just `TransferStudents`) -> `services/changes.py` -> `repositories/postgres/pending.py` -> `services/students.py` (just `investigate_missing_student`) -> `auth/tokens.py` -> `api/deps.py` -> `container.py`.

Then skim a few tests in `tests/test_changes.py` to see the behavior.

## 12. Running it

```bash
cd /Users/1abykeev/Documents/luwo_task
source .venv/bin/activate          # needed in every new terminal tab
docker compose up -d               # Docker Desktop must be running first
uvicorn app.main:app --reload      # then open http://localhost:8000/docs
python -m pytest tests -q          # run the tests
```

- Database data survives restarts (it lives in a Docker volume).
- Reset the demo data to its original state with `python -m seed.seed` (dev database only).
- In `/docs`: `POST /auth/login` with `aigul@luwo.test` / `demo1234`, copy the token, press **Authorize**, paste it, then try `GET /auth/me`.
- A browser message "Load failed" means the server (`uvicorn`) is not running.

Demo accounts (password for all: `demo1234`):

| Email | Role | School | Leads |
|---|---|---|---|
| root@luwo.test | superadmin | all | - |
| admin1@luwo.test | school admin | Лицей №1 | - |
| admin2@luwo.test | school admin | Гимназия №5 | - |
| admin3@luwo.test | school admin | Школа №12 | - |
| bakyt@luwo.test | teacher | Лицей №1 | 3А, 3Б |
| aigul@luwo.test | teacher | Лицей №1 | 4А |
| nurlan@luwo.test | teacher | Лицей №1 | 4Б |
| elena@luwo.test | teacher | Гимназия №5 | 3А |
| marat@luwo.test | teacher | Гимназия №5 | 4А |
| sergey@luwo.test | teacher | Гимназия №5 | none |
| dinara@luwo.test | teacher | Школа №12 | 4А |
| gulmira@luwo.test | teacher (removed, cannot log in) | Лицей №1 | none |

## 13. Not built yet

The agent, `LLMClient`, tools, `/chat`, README content, the mobile app, analytics, metrics and load tests. These are Days 2 to 4.

## 14. Interview questions for this part

**What does the unit of work give you, and what would break without it?**
One business operation is one transaction. All repositories inside it share the same database session, so a change and
its history row are saved together or not at all (`commit()` at the end; leaving the block without it rolls everything
back). Without it a student could be moved while the history row failed to save, or the other way round, and a failure in
the middle would leave half-finished data. The in-memory adapter works on a copy and drops it when you do not commit, so
it behaves the same way.

**How do you stop a double tap on Confirm from running a change twice?**
`pending.claim()` is one SQL statement, `UPDATE ... WHERE status='pending'` (and not expired), so the database lets exactly
one caller win. The second tap finds nothing to claim, re-reads the row, sees it was already confirmed and returns the
stored result with `already_applied=True`. Nothing runs twice. Claiming, re-checking, changing the data and writing history
are one transaction, so if anything fails the claim is rolled back with the rest. Tests confirm the same token several
times, including at once, and check the change happened once.

**Why does the token only contain the user id?**
Role, school and classes are loaded from the database on every request, so nothing inside a token can grant access and
nothing can go stale. A demoted admin or a removed teacher is affected on the very next request. Even a correctly signed
token that claims `role: superadmin` changes nothing (a test checks it). Tokens must also carry an expiry and a subject.

**Why does `propose` call the same `plan()` that `confirm` calls?**
`plan()` checks the rules and describes what would happen; `apply()` does it. Propose runs `plan()` to validate and to show
the user a summary. Confirm runs it again because things can change in between: the student was moved, the user lost their
rights, the class changed. So permissions and state are checked at the moment of execution, not only when the card was
shown. Using one function for both means the two steps can never disagree.

**How would you plug in Luwo's REST API?**
Write a `UnitOfWork` with the repositories (students, teachers, classes, schools, plus users, history and pending) that call
the REST API or MCP server, add one branch to `build_uow_factory()` in `app/container.py` selected by `DATA_SOURCE`, and add
the adapter to the `uow_factory` test fixture: the same service tests must pass. Agent, tools and services do not change.
Caveats (written in the README): the adapter must apply the `Scope` filter, login reads users through the unit of work, and
REST cannot give "change plus history in one transaction", so history and pending would stay in our database.

**Why do the same tests run on two adapters?**
It is the proof that services depend only on the interface, and it catches an adapter that breaks the contract. For example
an adapter that ignored the `Scope` filter would fail the permission tests. A new adapter is accepted when the same tests
pass on it.

**Why is another school's student reported as "not found" and not "forbidden"?**
"Forbidden" would confirm that the id exists. With "not found", nobody can probe ids to discover students of other schools:
an id outside your scope looks exactly like one that does not exist.

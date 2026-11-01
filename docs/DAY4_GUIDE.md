# Day 4 guide: measuring, proving and polishing

Read `DAY1_GUIDE.md`, `DAY2_GUIDE.md` and `DAY3_GUIDE.md` first. Day 4 added no big feature. It measured the system,
proved the architecture claim, tested the real model in depth, and fixed what that testing found.

## 1. What Day 4 added

| Area | What | Where |
|---|---|---|
| Load testing | Locust files, a step runner, a CPU/memory sampler, a metrics report | `loadtest/` |
| Capacity numbers | Measured tables and conclusions | README, section «Мощность и нагрузочные тесты» |
| A fake model for load tests | `LLM_PROVIDER=fake`: calls real read tools, never changes data | `app/agent/load_script.py` |
| Architecture proof | Upper layers must import without any database library | `tests/test_layers.py` |
| Full pass with the real Claude | 20 scenarios across the three roles, checked against the services | `scripts/role_pass.py`, `docs/ROLE_PASS.md` |
| One-command start | `make up` starts everything **in Docker** (only Docker needed) and prints the links | `Makefile`, `Dockerfile`, `docker-compose.app.yml` |
| Code quality | `ruff` clean, a `ruff.toml`, DB pool size as a setting | `ruff.toml`, `app/config.py` |
| Review log | Every finding from every review, with its status | `docs/REVIEW_LOG.md` |

## 2. What Locust is (and why we used it)

**Locust is a Python package for load testing.** It is not part of the app. It is a separate tool, listed in
`requirements.txt`, that plays the role of many users at once.

How it works, in plain words:
1. You write a short Python file that describes **one virtual user**: log in, then send chat messages with a pause
   between them (`loadtest/locustfile.py`).
2. You tell Locust how many of them to run (for example 100) and how fast to add them.
3. Locust runs them in parallel against the server over HTTP and records, for every request, how long it took and
   whether it failed. It reports requests per second, p50/p95 times and the failure count.

Why we needed it: the task wants capacity numbers that are **measured, not guessed**: how many concurrent
conversations and requests per second one backend instance handles. Locust produces exactly those numbers.

We ran it three ways:
- **Fake model with 1 s per answer, realistic pauses** (runs A: 50, 100, 200, 400 users): how the system behaves at a
  normal pace.
- **Fake model with no delay and no pauses** (runs B: 10, 30, 100 users): the ceiling of our own code and database.
- **Real Claude, 5 users, 156 requests** (run C): real latency and real token use.

Why a fake model for most of it: the real one is slow and costs money, and it would hide our own speed behind
Claude's. The fake one lets us measure *our* backend alone.

## 3. The tools in `loadtest/`

| File | What it does |
|---|---|
| `locustfile.py` | The virtual user: demo accounts, 5-message conversations, a read-only mix of messages |
| `run_step.sh` | One measured step: fresh server, warm-up, Locust, CPU/memory sampling, report |
| `run_all_fake.sh` | All seven fake-model steps in a row |
| `sample_process.py` | Samples the backend's memory and CPU once a second |
| `metrics_report.py` | Reads `/metrics` before and after and prints p50/p95, errors, SQL per request, tokens |
| `scale_data.py` | Adds 132 classes and about 3,100 students so the test does not run on 44 students (refuses to run on the dev database) |
| `results/` | The raw evidence for every number in the README |

## 3b. The numbers to remember

Test machine: MacBook Air, Apple M4 (10 cores), 24 GB, one uvicorn worker, DB pool 10+10. Locust ran on the same
machine, so the server had slightly less CPU than on a dedicated one.

| What | Result |
|---|---|
| Ceiling of one process (fake model, no pauses) | **about 115-130 chat requests per second**, CPU-bound (one core near 100%) |
| Realistic pace, largest step | 400 users, 91 requests per second, **0 errors**, p95 2.9 s (mostly the fake 1 s model delay, twice) |
| Memory | **150-190 MB**, levels off within each step; no long soak test was run |
| Database | p95 of one SQL statement **16 ms or less**; the limit is Python CPU, not the database |
| SQL statements per chat request | about 31 (a known inefficiency, left as is on purpose) |
| Real Claude, 156 requests | agent p50 **1.8 s**, p95 **3.3 s**; about **14.3k input tokens** per request, **95% from cache** |
| Real Claude CPU | about 40 ms of CPU per request (fake model: about 9 ms). That gives roughly 25 requests per second per core. **An estimate from one small run, not a measured limit** |

Honest limits to state before anyone asks: numbers come from one fast laptop core; a cloud vCPU is slower; the
real-Claude limit was not searched for; one worker only; the conversation lock lives inside the process.

## 4. Proving the architecture claim

The task's main requirement: the agent must not depend on PostgreSQL. We proved it three ways:
1. **`tests/test_layers.py`** imports each upper layer (agent, tools, services, interfaces, telemetry) in a fresh
   Python process and fails if SQLAlchemy, asyncpg, `app.db` or the Postgres adapters get loaded.
2. **The same service tests run on both adapters** (`memory` and `postgres`, the `uow_factory` fixture).
3. **A real server run** with `DATA_SOURCE=memory` answered "show class 4А" with 0 SQL statements; with `postgres`
   the same request made 19.

Day 4 found that this claim was false at first: the Postgres code for chat history, the request log and the SQL timing
hooks lived inside `app/agent` and `app/observability`. It was moved to `app/db/agent_state.py` and
`app/db/instrumentation.py`, and the test now guards it.

## 5. Testing the real model: what it found

The scripted fake-model tests cannot catch how the real Claude behaves. `scripts/role_pass.py` runs 20 scenarios on a
fresh in-memory world per scenario and checks the result against the **services** (the ground truth), not against
what the model says. Using the app by hand and reading the dashboard found more. All of it was fixed test-first:

| Found | Fix |
|---|---|
| English users got Russian replies | The prompt said "usually Russian"; now it follows the user's language |
| "Удалите Амира Жумаева" triggered "which Амир?" (declined surname ignored) | A prompt rule about name endings |
| Off-topic requests after a card were recorded as `other` in 30-50% of runs | The "call report_out_of_scope FIRST" rule moved into the **tool description** (58 of 60 correct afterwards) |
| Rewording one prompt sentence made English replies drop from 20/20 to 0/20 | Reverted; **lesson: the prompt is fragile, change it only with a measured before and after** |
| A student named like an order ("Игнорируй правила…") | Prompt rule plus a test with an obedient fake model; the backend stops it anyway |
| Grafana showed "1 request in flight" on an idle server | The `/metrics` scrape was counting itself |
| "Requests by type" added up to 7 when 16 requests were made | Prometheus counters created at their first event hide that event from `increase()`; they now start at 0 |
| A token without an expiry was accepted | `exp` and `sub` are required |
| Latin letters that look like Cyrillic could hide a namesake | Mixed-alphabet names are refused; names are compared with `name_key` |
| The app label «закрытый класс» suggested a class was shut down | Now «класс вне вашего доступа» |

## 6. `make up`: the whole project in Docker

`make up` needs **only Docker**. It builds two images, starts five containers (database, backend, the app's web version,
Prometheus, Grafana), runs the migrations, loads demo data **only into an empty database** (the seed script wipes data), and
prints the links. `make down` stops everything and keeps the data. `make test` runs the tests inside Docker. `make help`
lists the rest. The alternative `make local` runs the backend and the app on your own machine (needs Python 3.11+ and Node.js).

| File | What it does |
|---|---|
| `Dockerfile` | The backend image (Python 3.12). Packages come from `requirements.lock` (exact versions), installed first so a code change rebuilds fast |
| `docker/backend-entrypoint.sh` | On start: run the migrations, load demo data if the database is empty (`seed/ensure.py`), start uvicorn |
| `mobile/Dockerfile`, `mobile/nginx.conf` | Builds the app's web version once (`expo export`, Node 22, `package-lock.json`) and serves it with nginx; `EXPO_PUBLIC_DEMO_MODE=true` is baked in on purpose |
| `docker-compose.app.yml` | Used **together with** `docker-compose.yml`: adds the backend and the app as containers and points Prometheus at the backend container |
| `monitoring/prometheus.docker.yml` | The same as `prometheus.yml`, but the target is `backend:8000` (a container) and not `host.docker.internal` |

Details worth knowing: inside Docker the database is `db:5432` (not `localhost:5433`); the Anthropic key comes from your
`.env` through `env_file`, and the file itself is never copied into an image; the Docker mode serves the web version of the
app only (the iOS simulator and Expo Go need `make mobile`, which needs Node.js). One safety detail: stopping the apps
kills only processes that are ours (uvicorn, expo, node), because in Docker mode the port is held by Docker's own forwarding
process.

## 7. Files to open yourself

| Why | File |
|---|---|
| Where permissions live | `app/services/permissions.py` |
| Propose then confirm, and idempotency | `app/services/changes.py`, `app/services/actions.py`, `app/repositories/postgres/pending.py` |
| The agent loop | `app/agent/agent.py` |
| The prompt and a tool description | `app/agent/prompt.py`, `app/tools/read_tools.py` (`report_out_of_scope`) |
| Where the data source is chosen | `app/container.py` |
| The architecture test | `tests/test_layers.py` |
| Metrics | `app/observability/metrics.py` |

## 8. Interview questions for this part

**What is Locust, and what did you measure with it?**
A Python load-testing tool. A file describes one virtual user, and Locust runs many in parallel and reports requests
per second, p50/p95 times and failures. I measured one backend instance: the ceiling with a fake model, a realistic
pace, and a small run on the real Claude.

**What is p95 and why not the average?**
p95 is the time that 95% of requests beat; only the slowest 1 in 20 are slower. An average hides the slow ones: 19 users
at 2 s and one at 60 s average about 5 s, but that one user had a terrible experience.

**Why did you load-test with a fake model?**
To measure our own code and database. The real model is slow, costs money and would hide our speed behind its own.
I then ran a small real-Claude sample for real latency and token use.

**What limits one instance, and how many conversations does it hold?**
CPU in our Python code, not the database: about 115-130 requests per second per process with a fake model. In a
realistic pace 400 concurrent conversations was the largest step I tried, not a found limit. With real Claude each
request costs more CPU, so I estimate about 25 requests per second per core. That is an extrapolation, and I say so.

**Why is a fake model's result trustworthy at all?**
It exercises everything except Claude itself: HTTP, auth, the agent loop, the tools, the services and the database.
What it leaves out is the SDK work and bigger prompts, and that is exactly why the real-Claude run exists and why I
call the capacity number an estimate.

**How do you know the upper layers do not depend on PostgreSQL?**
`tests/test_layers.py` imports each layer in a clean process and fails if a database library loads. The same service
tests run on a memory adapter and the Postgres adapter, and I ran the real server on both. It also found a real
violation that I then fixed.

**What did testing with the real Claude find that your tests did not?**
Language slips, over-asking for declined names, off-topic requests not being recorded, and a prompt edit that silently
broke English. The scripted tests pass by design, so I added a role pass that checks outcomes against the services.

**Why did you put the off-topic rule in the tool description and not in the prompt?**
Editing the prompt fixed it but broke English replies (20/20 to 0/20). I measured prompt variants and a tool-description
variant side by side; the tool description kept both behaviors (58/60 and 23/24).

**Why two compose files?**
`docker-compose.yml` is the base: the database and optional monitoring. It supports running the backend on your machine
(`make local`). `docker-compose.app.yml` adds the backend and the app as containers and replaces one setting (where Prometheus
looks). Keeping them separate means the local way does not change and the Docker-only way is opt-in.

**What would you do next?**
A rate limit at the proxy, several workers with a shared lock, fewer SQL statements per request, a list of past chats in
the app, and a long soak test for memory. All of them are in the README limitations.

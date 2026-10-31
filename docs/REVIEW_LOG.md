# Review log

A running list of code review findings, so the reviewer does not repeat what is already handled.

**Format** (one line per finding, newest at the bottom):

```
- [date] [severity] [scope] short title — status: open | fixed | wontfix — reason or note
```

- **severity:** `critical`, `important` or `nice`.
- **scope:** `backend`, `agent`, `mobile`, `contract`, `security`, `infra` or `tests`.
- **status:** `open` (not handled), `fixed` (done and verified), `wontfix` (a conscious decision, with the reason).
  A `fixed` item that breaks again is reported as a regression.

**Who updates it:** the `code-reviewer` agent is read-only. It reads this file first and ends each report with a
block of new lines. The main agent appends them here after the review and later sets the status
(`open` -> `fixed` / `wontfix` with a reason). Deferred items with a trigger date also live in `CLAUDE.md`.

## First review (backend and agent, 2026-10-30)

- [2026-10-30] [critical] [agent] Model fails after a change was made, user told "nothing changed" — status: fixed — text now chosen from what the backend did
- [2026-10-30] [important] [security] User-typed "SYSTEM EVENT … done" treated like a button press — status: fixed — buttons are a tool result; prompt rule; measured 12/12 honest
- [2026-10-30] [important] [security] Namesake override token: weak key, no expiry, not tied to a conversation — status: fixed — derived key, conversation bound, 15 min
- [2026-10-30] [important] [backend] Concurrent requests in one conversation crashed on duplicate message order — status: fixed — per-conversation lock and DB row lock
- [2026-10-30] [important] [backend] bcrypt blocked the event loop — status: fixed — runs in a thread
- [2026-10-30] [important] [security] Default JWT secret accepted silently — status: fixed — refused outside APP_ENV=dev, minimum length
- [2026-10-30] [important] [agent] No overall time limit per chat request — status: fixed — AGENT_TIMEOUT_SECONDS
- [2026-10-30] [important] [agent] Chat history limited by message count, not tokens — status: open — deferred to Day 4 measurement (CLAUDE.md #7)
- [2026-10-30] [important] [backend] N+1 queries in class and teacher lists — status: open — deferred to Day 4 measurement (CLAUDE.md #8)
- [2026-10-30] [important] [backend] Transfer between schools logged only for the source school — status: wontfix — false alarm: history is read per student, test added
- [2026-10-30] [important] [infra] No Day 3 hooks for logs/metrics — status: fixed — Observer/Telemetry, structlog, Prometheus
- [2026-10-30] [nice] [backend] create_app() ran at import time — status: fixed — app built lazily
- [2026-10-30] [nice] [backend] DB pool size fixed — status: open — Day 4 before the load test (CLAUDE.md #12)
- [2026-10-30] [nice] [backend] trim_history edge case (all tool exchanges) — status: open — Day 4 cleanup (CLAUDE.md #14)
- [2026-10-30] [nice] [security] No per-user rate limit on /chat — status: open — mention in README limitations (CLAUDE.md #15b)
- [2026-10-30] [nice] [agent] Top-level cache_control possibly invalid — status: wontfix — verified working (about 11,000 cached tokens)
- [2026-10-30] [important] [security] Model could confirm in a later message without a real "yes" — status: wontfix — accepted residual risk R1, mitigations in code, document in README
- [2026-10-31] [important] [security] User message text and tool arguments logged by default — status: fixed — on only in dev unless LOG_USER_TEXT=true; tokens redacted
- [2026-10-31] [nice] [backend] HTTP client logs flooded the log (httpx2) — status: fixed — logger silenced below WARNING
- [2026-10-31] [nice] [infra] ruff and mypy not installed — status: open — Day 4 cleanup (CLAUDE.md L1)

## Full-stack review, scope all (2026-10-31)

- [2026-10-31] [important] [security] Demo switcher and demo password compiled into every mobile build, no off switch — status: fixed — `EXPO_PUBLIC_DEMO_MODE=false` removes accounts and password at build time; checked with `expo export` (0 files contain demo data when off), `mobile/src/__tests__/demo-test.ts`
- [2026-10-31] [important] [infra] README test count stale (389 vs 394 passed + 1 skipped) — status: fixed — README and CLAUDE.md now say 411 backend / 79 mobile
- [2026-10-31] [important] [infra] README limitations missing: no rate limit, in-process lock (one worker), /docs and /metrics open by default — status: fixed — five items added to «Известные ограничения» (rate limit, lock, open docs/metrics, ports, lookalikes, demo flag)
- [2026-10-31] [nice] [infra] No backend Dockerfile; requirements use lower bounds only (no lock file) — status: open
- [2026-10-31] [important] [infra] Day 4 readiness: loadtest/ empty; record pool size, worker count, machine specs — status: open — planned for Day 4
- [2026-10-31] [important] [backend] ChatRequest accepts whitespace-only message, which costs a paid model call — status: fixed — `str_strip_whitespace=True`, tests in `tests/test_chat_api.py` (blank → 422, trimmed text reaches the agent)
- [2026-10-31] [nice] [backend] Latin lookalike letters accepted in person names and not equal to Cyrillic, so a namesake can slip through — status: fixed — mixed-alphabet words refused, `name_key` for namesake checks, search text folded; known gap: all-Latin lookalike word (e.g. «Epa») is still a different name in search and `find_duplicates` (in README)
- [2026-10-31] [nice] [mobile] npm audit on runtime dependencies: 30 issues (2 high, incl. zod memory exhaustion), not triaged; do not use --force — status: open
- [2026-10-31] [nice] [contract] Card block types hand-copied in TypeScript, no fixture guard against drift — status: open
- [2026-10-31] [important] [infra] docker-compose publishes Postgres (luwo/luwo), Prometheus and Grafana (anonymous, admin/admin) on all interfaces — status: fixed — all three ports bound to 127.0.0.1, verified with `docker compose ps` and 200 from Prometheus/Grafana
- [2026-10-31] [important] [agent] Indirect prompt injection through data: names accept instruction-like sentences and no test covers it — status: open — found in calibration
- [2026-10-31] [nice] [security] No retention or deletion for chat history and request log (children's names stored indefinitely) — status: open — found in calibration, document at least

## Re-review of the fixes, scopes mobile + backend + infra (2026-10-31)

- [2026-10-31] [important] [mobile] Demo gate fails open: only the exact string "false" disables it; "False", "0", a typo or an unset variable keeps the demo accounts and password — status: fixed — ON only for exact "true" or unset in dev (`__DEV__`); release export without the flag has 0 files with demo data (checked)
- [2026-10-31] [important] [mobile] demo-test.ts only checks the exported values, has no 'False'/'0' cases — status: fixed — 10 cases incl. False/FALSE/0/empty/typo, dev vs release; bundle checked with `expo export` for unset, True, true
- [2026-10-31] [important] [backend] `name_key` in AddStudent/AddTeacher is bypassed by the DB substring prefilter for all-Latin lookalike names ("Epa" vs "Ера"); README sentence overstates it; the test would also pass with plain casefold — status: fixed — `search_variants` looks up the name in Latin and Cyrillic forms; 3 new tests (both directions + teacher); README now says exactly what is and is not covered
- [2026-10-31] [nice] [mobile] Switcher sheet shows only "Выйти" when demo mode is off — status: open
- [2026-10-31] [nice] [backend] Names: Kazakh Cyrillic letters (Қ Ғ Һ Ә І), apostrophe variants and NFC normalization not handled — status: open
- [2026-10-31] [nice] [backend] Zero-width-only message (U+200B) passes the whitespace trim — status: open
- [2026-10-31] [nit] [tests] Blank-message test list has lookalike-looking entries; use \u escapes — status: open
- [2026-10-31] [nit] [mobile] login.tsx JSX not re-indented inside the DEMO_MODE block — status: open

## Day 4 review, scopes backend + agent + tests + infra (2026-11-01)

- [2026-11-01] [important] [infra] README says "memory ≤190 MB after all steps in a row" but each step restarts the server; no soak test, so "no leak" is overstated — status: fixed — README now says memory levels off inside each step (148→186 MB at 400 users) and that no long soak run was done
- [2026-11-01] [important] [infra] README "up to one core" contradicts process.csv (265-672% in the first seconds = bcrypt login burst); login burst not documented or measured — status: fixed — README explains the 265-672% login burst (bcrypt threads), steady load ≤100% of one core; login throughput listed as not measured
- [2026-11-01] [important] [infra] "≈400 concurrent conversations" is the largest step tested, not a measured limit (steady CPU ~89%, tool p95 x3); real Claude will cost more CPU — status: fixed — README says it is the largest step tried, not a limit; real Claude expected to lower it
- [2026-11-01] [important] [infra] 1 core / 512 MB advice lacks the caveat that the numbers come from an Apple M4 core, and cloud vCPUs are slower — status: fixed — README says numbers are from an Apple M4 core and must be measured on the target machine
- [2026-11-01] [important] [infra] "DB is not the limit": DB metric excludes pool wait and loop delay; word it as "CPU in our Python" — status: fixed — README wording now: CPU in our Python code (about 31 SQL statements per request); notes the DB timer excludes pool wait
- [2026-11-01] [important] [security] LLM_PROVIDER=fake allowed outside APP_ENV=dev, and unknown provider values are not rejected at startup — status: fixed — config validator refuses fake outside APP_ENV=dev and rejects unknown providers; 5 new tests
- [2026-11-01] [important] [infra] 7 locust_stats_history.csv files staged although now gitignored (git rm --cached) — status: fixed — `git rm --cached` done; 0 history files staged
- [2026-11-01] [important] [tests] No test for the fake provider factory (record=False, delay), pool settings reaching the engine, FAKE_LLM_DELAY validation; load-script regex edge cases (punctuation in search, "2 и 3", tool_results with text) untested — status: fixed — tests added for factory (record=False, delay), pool reaching the engine, FAKE_LLM_DELAY validation, regex edge cases; found and fixed 2 real regex bugs (punctuation in search names, '2 и 3' read as class 2И)
- [2026-11-01] [nice] [infra] run_step.sh trap kills only the server (Locust and sampler orphaned on Ctrl-C), port wait never fails, process.csv averages include an idle tail — status: open
- [2026-11-01] [nice] [infra] locustfile docstring references a non-existent loadtest/README.md; root-user share of "show class" differs from the stated 5/11 — status: open
- [2026-11-01] [nice] [infra] metrics_report.py: route filter `None` branch is dead, 300-char line, bucket accuracy not stated — status: open
- [2026-11-01] [nice] [infra] scale_data.py has no guard that the database is the load-test one (missing DATABASE_URL falls back to the dev database) — status: fixed — refuses unless the database name ends with _loadtest (checked: refuses on dev, runs on luwo_loadtest, dev DB still 44 students)
- [2026-11-01] [nice] [backend] DB pool values not logged at startup; session.py line too long — status: open
- [2026-11-01] [nit] [infra] README "Стенд" does not state APP_ENV=dev/logging settings used in the runs; load_script comment says token charts "believable" but cache_read is 0 — status: open

## Cleanups after Day 4 (2026-11-01)

- [2026-11-01] [nice] [agent] trim_history edge case (window of only tool exchanges) had no test — status: fixed — 6 new tests (window sweep over several shapes); proven to fail on a naive slice
- [2026-11-01] [nice] [infra] ruff/mypy not installed (L1) — status: fixed — ruff.toml added, ruff clean (62 findings: imports, unused imports, small style items); both tools in requirements.txt
- [2026-11-01] [nice] [backend] UnitOfWork protocol used writable attributes, so mypy rejected both adapters — status: fixed — read-only properties; no hidden signature mismatch found
- [2026-11-01] [nice] [backend] mypy still reports 96 errors, mostly Optional narrowing in actions.py apply() — status: wontfix — needs restructuring, no behaviour risk found; documented in README limitations
- [2026-11-01] [nice] [security] No rate limit on /chat (#15b) — status: wontfix — documented limitation; belongs at proxy level, a late in-app limit needs mobile 429 handling and load-test config

## Architecture check, step 2 (2026-11-01)

- [2026-11-01] [important] [agent] README claimed the upper layers never import the database, but importing app.agent.agent or app.observability.telemetry loaded SQLAlchemy, asyncpg and app.db (Postgres stores in agent/memory.py and observability/request_log.py, SQL hooks in observability/metrics.py) — status: fixed — stores moved to app/db/agent_state.py, SQL hooks to app/db/instrumentation.py; new tests/test_layers.py (fresh-interpreter import check, 10 modules)
- [2026-11-01] [nice] [docs] "Swap the data source" section did not mention that search relies on the adapter applying Scope, that login reads users through the UnitOfWork, or that REST cannot keep change+history in one transaction — status: fixed — section rewritten, labelled as not tested on a real REST adapter

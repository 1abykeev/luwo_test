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

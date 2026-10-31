# Standards sources (distilled)

Use this file instead of fetching websites. Fetch a live source only when a finding depends on a detail this file
does not cover, and say so in the report if a fetch fails. Principles below are paraphrased from pages that were
fetched and read on 2026-10-31. Anything marked **(not read)** or **(own knowledge)** was not confirmed from the
page; do not cite it as if it were.

Tags used in the other review files are in **bold** at the start of each entry.

## Code review practice

**[Google-CR]** https://google.github.io/eng-practices/review/reviewer/ (index only; content read from `standard.html`, `looking-for.html`, `comments.html`; `speed.html` not read)
- Approve once the change leaves the code measurably healthier, even if not perfect; perfection is not the bar.
- Technical facts and data beat opinions; style questions are settled by the style guide, otherwise match the surrounding code.
- Label optional points "Nit:" so authors can skip them; do not block on them.
- What to look for, in order: design, functionality (edge cases, concurrency), complexity (over-engineering), tests (would they fail if the code broke?), naming, comments (why, not what), style, consistency, documentation (READMEs updated), every line, context (the whole file and system, not just the diff), and good things.
- Comments: address the code not the person, explain why, point out the problem and let the author choose the fix, and praise what is done well.

## Python backend and architecture

**[FastAPI-BP]** https://github.com/zhanymkanov/fastapi-best-practices (read)
- Structure by domain; each module has its router, schemas, models and service layer.
- Use `async` routes only for non-blocking I/O: a blocking call inside an async route stalls the whole event loop.
- Put DB-backed validation (does this record exist?) in dependencies so routes do not repeat it.
- Declare constraints (length, pattern, range, enum) in Pydantic schemas instead of hand-written checks; decouple settings (BaseSettings).
- Alembic migrations should be static and reversible, with descriptive names; use consistent snake_case naming for DB objects and keys.
- Response models rebuild and validate output; use an async test client (httpx with ASGITransport) from day one.

**[Cosmic]** https://www.cosmicpython.com/book/ chapters read: Repository (ch. 2), Service Layer (ch. 4), Unit of Work (ch. 6). The GitHub repos `cosmicpython/book` (table of contents only) and `cosmicpython/code` (one branch per chapter; layout `src/`, `tests/{unit,integration,e2e}`) were also read.
- Repository: a small storage abstraction (add, get) so code treats persistence like in-memory objects; the ORM depends on the domain, not the reverse; a fake is easy to write for tests; ports (abstract) and adapters (SQLAlchemy, fake).
- Service layer: orchestration (fetch, check, call domain, save) lives here; the entrypoint stays thin (parsing, HTTP codes); most tests run at the service level against fakes, with few end-to-end tests.
- Unit of Work: one atomic block per use case, as a context manager; commit is explicit and anything else rolls back; repositories are reached through the UoW; a fake UoW lets service tests run without a database.
- Trade-offs stated in the book: these layers add abstraction and pay off mainly for complex domains.

**[FS-Template]** https://github.com/fastapi/full-stack-fastapi-template (overview page only)
- Shows JWT auth, secure password hashing by default, config through `.env`, separate Docker Compose files for base/override/deploy, pytest for the backend, CI in GitHub Actions, locked dependencies, interactive API docs. Internal layout and migrations are not on the page.

## AI agents

**[Anthropic-Agents]** https://www.anthropic.com/engineering/building-effective-agents (read)
- Workflows follow predefined code paths; agents let the model direct its own steps. Start with the simplest solution and add complexity only when needed.
- Core principles: keep the design simple, be transparent about planning steps, and craft the agent-computer interface (tool docs and testing) with care.
- Tool design: write tool descriptions like a docstring for a junior developer; include examples, edge cases and clear boundaries from similar tools; test with many inputs; make mistakes hard to make ("poka-yoke", for example require absolute paths).
- Add stopping conditions such as a maximum number of iterations; use human checkpoints; test in a sandbox with guardrails.

**[Anthropic-Tools]** https://www.anthropic.com/engineering/writing-tools-for-agents (read)
- Prototype tools, evaluate them with realistic multi-step tasks, read transcripts and metrics, then iterate.
- Build a few purposeful tools for high-impact workflows, not thin wrappers around every endpoint; namespace overlapping tools.
- Return high-signal, readable context (avoid cryptic ids unless needed for follow-up calls); offer concise and detailed response modes.
- Cap response size (pagination, filters, truncation); write specific, actionable error messages so the agent can fix its next call; unambiguous parameter names.

**[Cookbook]** https://github.com/anthropics/claude-cookbooks (repo name is now `claude-cookbooks`; page lists folders only)
- Has folders for tool use, prompt caching, evaluations, cost optimization and agent patterns. The contents of the notebooks were not read.

## Security

**[OWASP-API]** https://api-security.owasp.org/editions/2023/en/0x11-t10 (read; the old owasp.org address redirects here)
- API1 Broken Object Level Authorization (check access for every user-supplied id); API2 Broken Authentication; API3 Broken Object Property Level Authorization (field-level read/write, mass assignment); API4 Unrestricted Resource Consumption (bandwidth, compute, paid third-party calls); API5 Broken Function Level Authorization (admin vs regular functions); API6 Unrestricted Access to Sensitive Business Flows; API7 SSRF; API8 Security Misconfiguration; API9 Improper Inventory Management (old versions, debug endpoints); API10 Unsafe Consumption of APIs.

**[OWASP-LLM]** https://genai.owasp.org/llm-top-10/ (titles read; descriptions are cut off on the page)
- LLM01 Prompt Injection; LLM02 Sensitive Information Disclosure; LLM03 Supply Chain; LLM04 Data and Model Poisoning; LLM05 Improper Output Handling; LLM06 Excessive Agency; LLM07 System Prompt Leakage; LLM08 Vector and Embedding Weaknesses; LLM09 Misinformation; LLM10 Unbounded Consumption. Use the titles; the detail in the review files is own knowledge.

**[MASVS]** https://mas.owasp.org/MASVS/ **(partly read)**
- Control groups: STORAGE, CRYPTO, AUTH, NETWORK, PLATFORM, CODE, RESILIENCE, PRIVACY. The control statements themselves did not load. The pages list related weaknesses by title: sensitive data in logs, sensitive data not excluded from backup, sensitive data visible in screenshots or screen recordings, unencrypted network traffic, insecure certificate validation, insecure identity pinning. Do not quote requirement text from MASVS.

## Mobile

**[RN-Perf]** https://reactnative.dev/docs/performance (read)
- Aim for 60 FPS (about 16.7 ms per frame). The JS thread runs logic and touch handling; heavy JS work delays touch feedback and JS-driven animation.
- Setting state high in the tree can re-render costly subtrees; defer non-urgent work.
- For large lists use `getItemLayout` on FlatList or a faster list library; use `useNativeDriver: true` for Animated.
- Measure in release builds only; remove `console.*` calls in production. Memoization techniques are not covered on this page.

**[RN-A11y]** https://reactnative.dev/docs/accessibility (read)
- Make views discoverable with `accessible`; give controls an `accessibilityLabel`, an `accessibilityHint` where the result is not obvious, a role (`button`, `link`, `heading`), and state (`disabled`, `selected`, `checked`, `busy`, `expanded`).
- Test with VoiceOver/TalkBack on a real device (VoiceOver is not in the iOS simulator); on Android use live regions to announce updates.
- Touch target size and font scaling are **not on this page** (own knowledge below).

**[RN-Sec]** https://reactnative.dev/docs/security (read)
- Anything in the app bundle can be read: keep secrets out of it. Do not keep tokens in unencrypted storage; use Keychain or Keystore. Use HTTPS everywhere; consider certificate pinning. Do not put tokens in deep links. Keep sensitive data out of state and monitoring tools such as Sentry. Dependency security is not covered on this page.

**[Expo]** https://docs.expo.dev/versions/latest/sdk/securestore/ and https://docs.expo.dev/router/advanced/protected/ (read)
- SecureStore supports Android, iOS and tvOS (not web); keys allow only letters, digits, `.`, `-`, `_`; values can be rejected if large, so handle errors; async methods have no sync delete.
- `Stack.Protected` blocks client-side navigation when the guard is false and removes that screen's history; "protected screens are not a replacement for server-side authentication or access control."

**[TS-React]** https://github.com/typescript-cheatsheets/react (read)
- Prefer `interface` for public APIs and `type` for props/state; avoid `{}` and `Object`; type nullable state as a union (`User | null`) instead of `{} as User`; type reducer actions as discriminated unions; "prefer runtime checking and throwing over type asserting"; `useEffect` callbacks return only a cleanup or nothing.

**[Templates]** https://github.com/obytes/react-native-template-obytes and https://github.com/infinitered/ignite (read; ignite page is a repo overview only)
- Common conventions: Expo Router or React Navigation, a data-fetching library, schema validation (Zod), ESLint and TypeScript checks on commit, Jest with Testing Library, Maestro for end-to-end tests, env handling through config files, several CI workflows.

**[FlashList]** https://github.com/Shopify/flash-list (overview read; the docs page was a 404)
- A drop-in faster list that recycles item views; lists with different item kinds can use `getItemType`. Guidance on keys and item state is **not read**.

## Testing

**[RNTL]** https://oss.callstack.com/react-native-testing-library/docs/start/intro (read, short)
- Test the way people use the software; keep tests free of implementation details; keep them maintainable so refactors do not break them. Query priorities are **not on this page**.

**[JS-Testing]** https://github.com/goldbergyoni/javascript-testing-best-practices (partly read)
- Keep tests short and flat; name them as what, scenario, expected result; Arrange-Act-Assert; test public behavior (black box); prefer stubs and spies to mocks; use realistic data; keep snapshots small; assert errors with dedicated assertions.

## Infrastructure

**[Docker]** https://docs.docker.com/build/building/best-practices/ (read)
- Multi-stage builds; pin base images (digest, with an updater); use `.dockerignore`; run as a non-root `USER`; understand layer caching and combine `apt-get update` with install; small base images and no extra packages; `COPY` over `ADD`; one concern per container. Secrets and healthchecks are **not on this page**.

**[12F]** https://www.12factor.net/ (headlines read)
- One codebase; declared dependencies; config in the environment; backing services as swappable resources; separate build/release/run; stateless processes; port binding; scale by processes; fast start and clean shutdown; dev/prod parity; logs as a stream; admin tasks as one-off processes.

**[Prom]** https://prometheus.io/docs/practices/naming/, `/instrumentation/`, `/histograms/` (read)
- Prefix with the application name; base units (seconds, bytes); plural unit suffix and `_total` for counters; one unit per metric; do not repeat a label's name in the metric name.
- Labels must not hold unbounded values (user ids, emails): every combination is a new time series; keep most metrics label-free, aim for under about 10 series per metric, rethink at about 100.
- Instrument online services with request count, errors and latency (and in-progress requests); count failures and attempts so you can compute a ratio; export a default 0 instead of leaving a series absent.
- Histograms use fixed buckets chosen in advance; quantiles are estimated on the server with `histogram_quantile`; averaging precomputed summary quantiles across instances is wrong; the error is bounded by the width of the bucket holding the quantile.

## Own knowledge (not from a fetched page; label it as such in a report)

- Mobile touch targets of about 44 pt (iOS) / 48 dp (Android); support dynamic font size (`allowFontScaling`, avoid fixed heights for text).
- Alembic: a new NOT NULL column on a table with rows needs a `server_default` or a backfill; check that the migration matches the models.
- HMAC/JWT details, password hashing cost, rate limiting basics.

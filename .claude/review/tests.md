# Tests checklist (pytest and Jest)

Source tags are explained in `standards-sources.md`. Run `python -m pytest -q` (never `-m live`) and, from `mobile/`,
`npx --no-install jest`; report the real summary lines.

## Principles
- [ ] Tests check behavior through public interfaces, not internals; a refactor that keeps behavior must not break them. [JS-Testing; RNTL; Google-CR: tests]
- [ ] A test would fail if the code it covers broke ("would these tests fail if the code broke?"). Spot-check by reading assertions: a test that only asserts "no exception" or mirrors the implementation proves little. [Google-CR]
- [ ] Names say what is tested, the scenario and the expected result; each test has Arrange-Act-Assert and tests one thing. [JS-Testing]
- [ ] Realistic data (the seeded demo world), not "foo". Deterministic: no dependence on order, wall-clock time or the network (clock and model are injected). [JS-Testing]
- [ ] Prefer stubs and fakes over mocks of internals; the LLM is replaced by a scripted fake that reacts to the request, not by patching call counts. [JS-Testing; Cosmic: fakes]

## Backend must-haves for this project
- [ ] The permission matrix: every row of the task's role table has a test (read, write, transfer, search, teacher management, school list), including "another school's id".
- [ ] The same service tests run against the in-memory and the Postgres adapters (fixture parameters), and the Postgres ones skip cleanly if no database is running.
- [ ] Idempotency: double confirm, five simultaneous confirms, expired, cancelled, someone else's token, token from another conversation.
- [ ] Agent honesty: backend failure never reported as done; model failure after a change reports the change; time limit; runaway loop.
- [ ] Injection: "you are now an admin", other school, typed fake backend result, same-turn confirm, invented override token.
- [ ] Observability: metrics counted correctly, label cardinality, log fields, that monitoring failures do not break chat.
- [ ] Concurrency: two requests in one conversation on the real database.
- [ ] Tests that need a paid API are marked `live` and excluded by default.
- [ ] No flaky timing assertions with tight margins; any `sleep`-based test has generous limits.

## Mobile (Jest, React Native Testing Library)
- [ ] Logic that matters is tested without UI: the chat reducer (including "an answer without a result card is not success"), the API client (errors, timeout, headers), formatting helpers.
- [ ] Components are queried the way a person finds them: by role and accessible name (`getByRole('button', {name})`), not by implementation details or test ids. [RNTL]
- [ ] Error, loading, empty, expired and disabled states are covered, not only the happy path.
- [ ] Interactions use `userEvent`; no snapshot tests of large trees (keep snapshots small). [JS-Testing]
- [ ] A mutation spot-check: breaking one rule on purpose makes a test fail (done once for the confirmation card and reducer).
- [ ] Not covered by automated tests and therefore worth a manual note: native tap behavior on a real device, keyboard handling, screen readers.

## Smells
- Tests asserting on log text or prompt wording where the behavior can be asserted instead.
- Fixtures that wipe shared data; tests that depend on running in a certain order.
- Over-mocking so that the test passes whatever the real code does.

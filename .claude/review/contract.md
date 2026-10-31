# Client/server contract checklist

The seam between `app/api` + `app/tools` (Pydantic and dict payloads) and `mobile/src/api` (hand-written TypeScript
types). Many real bugs live here. Source tags are explained in `standards-sources.md`.

## Shapes and drift
- [ ] Every field in `mobile/src/api/types.ts` exists in the backend response with the same name, type and nullability. Compare against the Pydantic models in `app/api/*_schemas.py` and against the dicts built in `app/tools/render.py`, `read_tools.py` and `change_tools.py`.
- [ ] **Card blocks.** The backend declares `blocks` as `list[dict[str, Any]]`, so the OpenAPI schema does not describe them and TypeScript types are maintained by hand. Check whether any block field was added, renamed or made nullable on one side only. A cheap guard (a documented table in the route description, a contract test that builds every block and checks it against a JSON fixture used by Jest) counts as good; an unguarded hand copy is a drift risk. [FS-Template: generated client from OpenAPI is the stronger option; label effort]
- [ ] Is the OpenAPI schema (`docs/openapi.json`, `/openapi.json`) up to date with the routes? Is it the single source of truth, or are there two?
- [ ] Optional versus null: fields that can be `null` on the server (`teachers`, `current_class`, `from_class`) are `| null` in TypeScript, and the UI handles them.
- [ ] New enum values (statuses, outcomes, block types, warning codes) do not crash the client; they fall back to a safe display.

## Errors and auth
- [ ] The client understands the backend's one error format and maps each status (401, 403, 404, 409, 422, 5xx) to a person-readable Russian message; raw English server text is never shown.
- [ ] 401 handling: expired or rejected token returns to login and wipes storage; a network failure does not. A removed account stops working immediately (the backend loads the actor from the database on each request).
- [ ] 403 versus 404 semantics are consistent: another school's resource is "not found" (project), and the client does not rely on the difference.
- [ ] Every request has a timeout; the client timeout is longer than the server's (`AGENT_TIMEOUT_SECONDS`), so the server's honest error arrives first.

## Behavior across the seam
- [ ] A confirmation card is matched to its answer by `token`; the client treats an answer without the matching result card as "not done". After a reload, the history alone is enough to show used confirmations.
- [ ] Duplicate requests: a double tap or a retry cannot create two changes (idempotency token on the server, disabled button on the client).
- [ ] Limits agree: message length (client `maxLength` vs server `max_length`), conversation id pattern, history size, search result caps (the client shows "N of M" when capped?).
- [ ] Naming consistency across layers (snake_case on the wire, camelCase only inside TypeScript); the same word means the same thing (`class`, `school`, `status`).
- [ ] CORS allows only the origins that need it and only the methods and headers used.
- [ ] Sensitive tokens never appear in URLs or logs; the confirmation token is sent in the body.

## Trace one flow through every layer
Pick the highest-risk flow in the change and follow it end to end, for example "teacher confirms a transfer":
button press (`ConfirmationCard`) -> `useChat.answer` -> `api.confirm` -> `POST /chat/confirm` -> `Agent.press_button`
-> `confirm_pending_action` tool -> `ChangeService.confirm` -> repository and history in one transaction -> result card
with token -> reducer marks the card done -> history reload shows the same state. At each arrow ask: what if this
step fails, repeats, is slow, or returns something unexpected?

# Agent checklist (LLM tool-use loop)

Source tags are explained in `standards-sources.md`.

## Tools
- [ ] Each tool description says when to use it, what comes back and what to do next; boundaries between similar tools are clear (for example `search_students` vs `investigate_missing_student`). *Why:* the model chooses tools from descriptions only. [Anthropic-Agents: agent-computer interface; Anthropic-Tools]
- [ ] Parameter names are unambiguous; mistakes are hard to make (ids, not names, for changes). [Anthropic-Agents: poka-yoke]
- [ ] Tool errors are specific and actionable so the model can fix its next call, and they are in a form it reads (`{"error", "message", "details"}`), without leaking internals. [Anthropic-Tools]
- [ ] Tool results are capped in size (search limit, pagination) and avoid needless ids. [Anthropic-Tools]
- [ ] The Actor comes from the backend; no tool takes a user id, school id or role from the model (project). [OWASP-LLM LLM06 Excessive Agency; OWASP-API API1]

## Loop
- [ ] Step limit and an overall time limit exist (`MAX_STEPS`, `AGENT_TIMEOUT_SECONDS`). [Anthropic-Agents: stopping conditions; OWASP-LLM LLM10]
- [ ] Failures of the model, a tool or the backend end in an honest message based on what really happened (a change that was made is never reported as "not changed", and the reverse). *Why:* "never say done if it was not done" is a task requirement.
- [ ] One request per conversation at a time; history is trimmed by size, never in the middle of a tool exchange. (Token-based trimming is deferred in `CLAUDE.md`.)

## Honesty and injection
- [ ] Success is claimed only from a tool result with status `done`/`already_done`. A user-typed "backend result" is plain text; button presses arrive as a tool result a user cannot type. [OWASP-LLM LLM01]
- [ ] Rights questions always reach the backend (the model is told to call the tool and let the backend answer); refusing from memory is a defect because analytics and the red banner depend on it.
- [ ] Out-of-scope requests call `report_out_of_scope`; AI disclosure on a direct question; reply language matches the user.
- [ ] The system prompt is guidance, never the only barrier. Anything the prompt forbids has a code-level guard where harm is possible (namesake token, no confirm in the same turn). [OWASP-LLM LLM01, LLM06]
- [ ] No system prompt secrets: nothing in it would hurt if leaked. [OWASP-LLM LLM07]

## Confirmation and idempotency
- [ ] Change tools only propose; execution only through confirm (button or a later user message). The same token cannot run twice; tokens belong to one user and one conversation and expire.
- [ ] A double tap or repeated request returns the first result, not a second change.
- [ ] Residual risk R1 (model confirming in a later message without a real "yes") is documented and accepted in `CLAUDE.md`: do not re-report; check only that the README says so.

## Cost and observability
- [ ] Prompt caching: a breakpoint on the system prompt and one on the conversation; the tool list order is stable (a changing order breaks the cache). Check `cache_read` tokens in logs or metrics.
- [ ] Token usage per call and per conversation is recorded; thinking and model settings are configurable.
- [ ] Logs carry the conversation id; secrets and single-use tokens are never logged; message text is logged only where configured (on in dev by default).
- [ ] The model client sits behind an interface so a provider swap touches one file; provider types do not leak into the loop.

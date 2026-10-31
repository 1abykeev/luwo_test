# Security checklist

Source tags are explained in `standards-sources.md`. Never print secret values: report a location only.

## API (OWASP API Security Top 10, 2023)
- [ ] **API1 object-level authorization:** every endpoint and tool that takes an id checks the actor's access to that object. [OWASP-API]
- [ ] **API2 authentication:** login failures look identical (no user enumeration), tokens expire, the token carries only the user id and role/school are loaded from the database each request, unsigned or forged tokens are rejected, password hashing runs off the event loop and with a sensible cost.
- [ ] **API3 property-level:** responses contain only fields the role may see (teachers do not get teacher assignments); requests cannot set protected fields.
- [ ] **API4 resource consumption:** limits on message length, result sizes and request time; the paid model API is protected (rate limit per user is a known deferred item: do not re-report, but check the README states it). [OWASP-API; OWASP-LLM LLM10]
- [ ] **API5 function-level:** admin-only actions (manage teachers, schools list, analytics) are enforced in services or the route, not hidden in the UI.
- [ ] **API8 misconfiguration:** CORS origins, debug endpoints, `/docs` exposure, `/metrics` (optional bearer token), default secrets refused outside dev, error messages without stack traces.
- [ ] **API9 inventory:** no forgotten routes; OpenAPI matches reality.
- [ ] **API10 unsafe consumption:** model output and tool results are treated as untrusted (the model cannot widen permissions).

## LLM (OWASP Top 10 for LLM Applications)
- [ ] **LLM01 prompt injection:** typed text claiming a backend result, a role or an approval does not change behavior; the structural guards (tool result for buttons, signed namesake token, no confirm in the same turn) are covered by tests. [OWASP-LLM]
- [ ] **LLM02 sensitive disclosure:** no other school's data reaches the model or the answer; logs do not hold tokens; message text is logged only by configuration.
- [ ] **LLM05 improper output handling:** model text is rendered as plain text in the app; cards come from backend data.
- [ ] **LLM06 excessive agency:** the model has no tool that changes data without a confirm step; no tool takes identity from the model.
- [ ] **LLM07 system prompt leakage:** nothing sensitive in the prompt.
- [ ] **LLM10 unbounded consumption:** step limit, time limit, history trimming, output limit.

## Mobile (OWASP MASVS, titles only; RN security page)
- [ ] **Storage:** the session token is in SecureStore on devices (not AsyncStorage); `localStorage` only on web. Logout removes the stored session. Nothing sensitive is written to logs, backups or screenshots (MASVS lists these weaknesses by title). [RN-Sec; Expo; MASVS]
- [ ] **No secrets in the bundle:** `EXPO_PUBLIC_*` values are public; the API key and JWT secret are never in `mobile/`. Check `grep -rn "sk-ant\|JWT_SECRET\|ANTHROPIC" mobile --include=*.ts --include=*.tsx --include=*.json -l` (report files only).
- [ ] **Demo-user switcher:** `mobile/src/demo.ts` contains the demo password and the switcher signs in without typing it. Acceptable for a take-home demo only if (a) the demo password is the seeded dev one, (b) the README says it, and (c) it can be turned off for a real build (a gate on an environment variable or `__DEV__`). Flag it if it cannot.
- [ ] **Network:** HTTPS in any non-local environment (plain `http://localhost` is fine for development); certificate pinning is optional and worth only a mention. [RN-Sec; MASVS]
- [ ] **Tokens are not placed in deep links or URLs.** [RN-Sec]

## Backend operations
- [ ] Secrets only in `.env` (git-ignored); `.env.example` has no real values; `git ls-files | grep -i env` shows only the example.
- [ ] Dependency risk: `npm audit` for the app (report only); for Python, note unpinned or very old packages (no installs).
- [ ] Logs contain no passwords, tokens, API keys or password hashes.

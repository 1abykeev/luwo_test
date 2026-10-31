# Mobile checklist (Expo SDK 58, Expo Router, React Native, TypeScript strict)

Source tags are explained in `standards-sources.md`. Run from `mobile/`: `npx --no-install tsc --noEmit`,
`npx --no-install eslint .`, `npx --no-install jest`.

## TypeScript
- [ ] `tsc --noEmit` is clean; no `any`, no `as` casts that hide a possible `undefined`/`null`; no `{}` or `Object` types. [TS-React]
- [ ] Nullable state is typed as a union, not forced with `{} as T`. Reducer actions are discriminated unions. [TS-React]
- [ ] Data from the server is treated as untrusted at the boundary: a missing or new field must not crash a render. "Prefer runtime checking over type asserting." [TS-React]
- [ ] `eslint-disable` comments are justified in place.

## Structure and responsibility
- [ ] Routes live only under `src/app/`; components, hooks, state and API code live outside it. [Expo Router docs; Templates]
- [ ] Route files stay thin; logic sits in hooks (`useChat`) or pure modules (`state.ts`, `format.ts`) that can be tested without a screen. [Google-CR: design, complexity]
- [ ] Components have one job; big files (over about 250 lines) are a smell worth naming. No duplicated card logic.
- [ ] Protected routes use `Stack.Protected` AND the server enforces access ("protected screens are not a replacement for server-side access control"). [Expo]

## State and effects
- [ ] `useEffect` has correct dependencies and cleanup (cancel in-flight work on unmount or token change). No state updates after unmount.
- [ ] Refs are not read or written during render. Stale closures are avoided (the latest-state-in-a-ref pattern is acceptable).
- [ ] Server truth wins over optimistic UI: "done" or "confirmed" is shown **only after the backend confirms** (a result card with the matching token). A failed or ambiguous answer never shows success.
- [ ] Double tap protection: Confirm/Cancel and Send are disabled while a request is running, and a second press cannot send a second request.

## Lists and performance
- [ ] The message list has stable keys, does not re-create handlers per row without need, and does not re-render every card on each keystroke or typing animation. Consider memoization where profiling shows a cost. [RN-Perf]
- [ ] Large lists (a class of 60 students) are bounded or virtualized; heavy work is not done in `renderItem`. [RN-Perf; FlashList]
- [ ] Animations use the native driver where possible; no `console.*` left in production code. [RN-Perf]

## States and resilience
- [ ] Every screen has loading, empty and error states; errors give a person something to do (retry).
- [ ] Offline or slow API: requests time out, a failed message stays visible with Retry, and nothing is lost. A 401 returns to login and clears the stored session; an unreachable server does not log the person out.
- [ ] Unknown card types or unexpected payloads are skipped, not thrown.
- [ ] User-visible texts are consistent in language; server (English) messages are not shown raw.

## Chat screen behavior
- [ ] Keyboard: the composer stays visible, content is not hidden behind it, and tapping a card while the keyboard is open works (`keyboardShouldPersistTaps`).
- [ ] Safe areas are respected (notch, home indicator); the inverted list keeps newest messages visible.
- [ ] Input is limited to the server's maximum length; Enter-to-send behavior on web does not break multiline.

## Accessibility
- [ ] Controls have a role and label; state is reported (`disabled`, `selected`, `busy`); errors and results are announced. [RN-A11y]
- [ ] Touch targets of about 44 pt (iOS) / 48 dp (Android) and support for larger system fonts (no fixed text heights); colour contrast is sufficient for text on the navy and cyan backgrounds (own knowledge; these are not on the RN accessibility page).
- [ ] Meaning is not conveyed by colour alone (banners have an icon and a title).

## Platform parity
- [ ] The web build and the native build behave the same (storage falls back to `localStorage` on web; SecureStore has no web support). [Expo]
- [ ] No web-only or native-only API is used without a guard.

## Tests (see also `tests.md`)
- [ ] Reducer and API client logic are unit tested; card components are tested by role/label; error and loading paths are covered.

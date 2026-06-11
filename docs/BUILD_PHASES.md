# humanpc — Build Phases

Live build tracker. Each phase is committed directly to `main`. See
[`PLAN.md`](PLAN.md) for the full architecture and [`blueprint/`](blueprint/) for
the Human Interaction Layer research.

**Legend:** ✅ done · 🔨 in progress · ⬜ planned

---

## ✅ Phase 0 — Skeleton & safety
The foundation everything rides on.

- [x] `Bot` facade (sync, chainable): `move_to / click / double_click / right_click / type / press / hotkey / scroll`
- [x] Persona context manager (`default / fast / careful / tired`)
- [x] Pluggable `InputDriver` interface + dependency-free `NullDriver` (powers dry-run + tests)
- [x] Lazy `pyautogui` backend for real execution
- [x] Safety: kill-switch (`Ctrl+Alt+Q` + corner failsafe), `SafetyGuard` (`max_actions`), append-only `AuditLog`
- [x] Per-monitor **DPI awareness** (correct Win11 coordinates)
- [x] Screen capture (`mss` / Pillow, lazy)
- [x] Geometry, exceptions, dataclass `Config` + personas
- [x] `pyproject.toml` (zero core deps, opt-in extras), 23 tests, dry-run smoke example

## ✅ Phase 1 — Human Interaction Layer
Replaced the placeholder smoothstep motion with genuinely human input.

- [x] Timing manager (thinking / reading delays, sync port) → `Bot.think()` / `Bot.read()`
- [x] Mouse engine: Bézier path + Fitts-law velocity (accelerate→cruise→decelerate) + jitter + overshoot
- [x] Typing engine: variable speed + word/sentence pauses + typo injection with **guaranteed self-correction** (final text always exact)
- [x] Human scroll (burst + pause)
- [x] Wire engines into `Bot.move_to` / `Bot.type` / `Bot.scroll`
- [x] Statistical + path tests (40 total); mouse-path visualization example

## ✅ Phase 2 — Targeting resolver
`bot.click("Login")` works by name/image.

- [x] UI Automation finder (pywinauto) — primary *(live-desktop integration)*
- [x] OCR finder (winocr / pytesseract backends, pluggable) — fallback
- [x] OpenCV template match (image targets), multi-scale
- [x] Unified `resolve(Target) -> Match`; `Locator / Image / Region` types
- [x] Feed match size into the Fitts model
- [x] `Bot.find / exists / wait_for`; 68 tests (UIA stays an opt-in integration test)

## ⬜ Phase 3 — Window & system tools
- [ ] Window/app manager (list/find/focus/move/resize/min/max/close), launch/kill
- [ ] Clipboard (text + image), shell `run`
- [ ] `wait_for / wait_until_gone / find_all / exists`

## ⬜ Phase 4 — Calling interfaces
- [ ] `typer` CLI
- [ ] FastAPI HTTP server
- [ ] MCP tool server (each verb = an agent-callable tool)
- [ ] YAML flow runner

## ⬜ Phase 5 — Polish
- [ ] Idle-drift background thread
- [ ] Record/replay macros
- [ ] Reading/thinking simulation + behavioral state machine
- [ ] Packaging extras, docs, examples
- [ ] Optional native SendInput (games) + browser (Playwright/CDP) backends

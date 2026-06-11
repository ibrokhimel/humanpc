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

## ✅ Phase 3 — Window & system tools
- [x] Window/app manager (list/find/focus/move/resize/min/max/close), launch/kill *(Win32 backend = live-desktop integration; fake-backend unit tests)*
- [x] Clipboard (text + image), shell `run`
- [x] `find_all` (template + OCR + UIA); `wait_for` / `wait_for_window`; `exists`
- [x] `Bot.run / open_app / list_windows / find_window / active_window / focus`; 94 tests

## ✅ Phase 4 — Calling interfaces
All four sit on one shared dispatcher (`execute(bot, action, params)`).

- [x] CLI (`humanpc <verb> ...`, argparse — no extra deps)
- [x] FastAPI HTTP server (`POST /<action>`) — real TestClient coverage
- [x] MCP tool server (each verb = an agent-callable tool, FastMCP)
- [x] YAML/JSON flow runner (`humanpc flow file.yaml`)
- [x] Shared `dispatch.execute` + `parse_target`; `read_text` / `screenshot`; 126 tests

## ✅ Phase 5 — Polish
- [x] Idle-drift background thread (`Bot(idle=True)` / `start_idle` / `stop_idle`)
- [x] Record/replay macros (`Recorder` → `Macro` save/load/replay)
- [x] Reading/thinking sim (Phase 1) + behavioral state machine (`bot.behavior` / `bot.state`)
- [x] Native Win32 `SendInputDriver` (games backend)
- [x] Packaging extras, docs (CHANGELOG, README usage), examples
- [ ] Browser (Playwright/CDP) backend — **deferred** (separate page-level integration)

---

**Status: Phases 0–5 complete.** 146 tests; zero heavy deps at import; proven on a
real Win11 desktop (see `examples/notepad_live.py`). Only the optional browser
backend remains deferred.

# Changelog

All notable changes to **humanpc**. The framework was built in phases; each phase
was committed directly to `main` (see [`docs/BUILD_PHASES.md`](docs/BUILD_PHASES.md)).

## [Unreleased]

### Provenance & timing (Tier 0)
- **Keystroke dwell:** typed characters now go through `char_down → hold → char_up`
  with a realistic, right-skewed key-hold time (`hil/typing/DwellModel`) instead of
  an atomic zero-dwell emit. `InputDriver` gains `char_down`/`char_up` (default
  falls back to `write_char`); `SendInputDriver` implements true split injection.
- **High-resolution timing:** `precise_sleep` (coarse sleep + sub-tick busy-wait)
  plus 1 ms Windows timer tick (`hil/precise`), so sub-frame delays are realised
  instead of quantising to the ~15.6 ms scheduler tick. Toggle: `Config.precision_timing`.
- **Relative mouse motion (opt-in):** `Config.relative_mouse` injects relative deltas
  through the OS pointer-acceleration curve, then iteratively corrects residual drift
  to land exactly on target (with an absolute snap for the final sub-pixel that
  "Enhance pointer precision" cannot express relatively). New
  `InputDriver.move_relative` primitive. *(Validated on Windows 11.)*
- **Injected-flag honesty:** `SendInputDriver(extra_info=...)` tags `dwExtraInfo`.
  Documented clearly that user-mode `SendInput` **cannot** remove the
  `LLKHF_INJECTED` flag — that requires a kernel/hardware HID backend, which plugs
  into the existing `Bot(driver=...)` seam.
- `Bot` is now a context manager (`with Bot() as bot: ...`) / has `close()` to
  release the timer tick, idle drift, and kill-switch.

## [0.1.0] — 2026-06-11

First feature-complete release: Phases 0–5. 146 tests; `import humanpc` loads zero
heavy dependencies (every backend is lazy). Validated on a real Windows 11 desktop.

### Phase 0 — Skeleton & safety
- Sync `Bot` facade; pluggable `InputDriver` + dependency-free `NullDriver`
- Kill-switch, `SafetyGuard` (`max_actions`), append-only `AuditLog`
- Per-monitor DPI awareness; `mss` screen capture; config + personas

### Phase 1 — Human Interaction Layer
- Mouse: Bézier path + Fitts-law velocity + jitter + overshoot
- Typing: variable speed, pauses, and self-correcting typos (final text exact)
- Burst scroll; timing manager (`Bot.think` / `Bot.read`)

### Phase 2 — Targeting resolver
- `resolve(target) -> Match`: text → UIA → OCR, image → OpenCV template, coords
- `Bot.find` / `exists` / `wait_for`; match size feeds the Fitts model

### Phase 3 — Window & system tools
- `WindowManager` / `Window`; shell `run`; app launch/kill; clipboard
- `find_all` across template / OCR / UIA

### Phase 4 — Calling interfaces
- One shared dispatcher (`execute(bot, action, params)`)
- CLI (`humanpc <verb>`), FastAPI HTTP server, MCP tool server, YAML/JSON flows

### Phase 5 — Polish
- Idle mouse drift (`Bot(idle=True)` / `start_idle`)
- Record/replay macros (`Recorder` → `Macro`)
- Behavioral state machine (`bot.behavior` / `bot.state`)
- Native Win32 `SendInputDriver` (games backend)
- Browser (Playwright/CDP) backend — deferred

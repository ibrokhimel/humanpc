# Changelog

All notable changes to **humanpc**. The framework was built in phases; each phase
was committed directly to `main` (see [`docs/BUILD_PHASES.md`](docs/BUILD_PHASES.md)).

## [0.0.1] — unreleased

The complete framework: Phases 0–5. 146 tests; `import humanpc` loads zero heavy
dependencies (every backend is lazy).

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

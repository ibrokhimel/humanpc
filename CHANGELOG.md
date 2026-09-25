# Changelog

All notable changes to **humanpc**. The framework was built in phases; each phase
was committed directly to `main` (see [`docs/BUILD_PHASES.md`](docs/BUILD_PHASES.md)).

## [Unreleased]

### Movement trainer (`humanpc/learn`)
- **`humanpc trainer`** — fullscreen tkinter app with 9 randomized task types
  (point, double, right, drag, scroll, scroll_click, trace, read, chain) that
  records raw hardware mouse input via `WH_MOUSE_LL`; injected events are dropped.
  Pauses (and saves) automatically when the window loses focus; saves on crash.
- **Compact storage** — delta-encoded, narrowest-int `.npz` sessions + JSON task
  sidecars (~2–3 MB/hour at 1000 Hz). Sessions record screen, DPI mode, person,
  and Windows pointer speed / "Enhance pointer precision".
- **`humanpc trainer-stats`** — readable report with per-category coverage, a
  heuristic humanness estimate (ceiling ~80%), projections, and a per-person table.
- **Multi-person** — `--person` subfolders; `trainer-export` / `trainer-import`
  move data between machines as a validated zip (member whitelist, size caps,
  corrupt-data checks, duplicate skipping).
- **`HumanpcTrainer.exe`** — `scripts/build_trainer_exe.py` builds a one-file
  PyInstaller trainer for PCs without Python; it keeps
  `Desktop/mousedata_<name>.zip` current in the background after every save.
- New `learn` extra (`numpy`).

### Learned movement model (`humanpc/learn/ml`)
- **`humanpc train-model`** — trains a causal Transformer (10 ms steps, rotated frame,
  per-person style embedding; heads: moved, (dx, dy) Gaussian mixture, click, wheel, stop)
  on all recordings with bf16 autocast on CUDA, mirror augmentation and early stopping.
- **Detector** (`humanpc eval-model`, and automatically after training) — a GRU classifier
  real vs generated gives a *measured* humanness (2 × (1 − accuracy)), completion rate and
  real-vs-model medians; it rewrites `task_weights.json` to target weak spots, and
  `trainer-stats` shows the measured score beside the estimate.
- **`MovementGenerator`** — batched, KV-cached generation with click-validity masking,
  task-rule termination and a landing correction; returns screen-space events.
- New `ml` extra (`numpy`, `torch`).
- **`humanpc model-demo`** — playground window for all seven actions (click, double,
  right, drag, scroll, scroll+click, read) with a fake cursor, 5-path variation view,
  landing-correction toggle and an opt-in live mode.
- `--max-sessions` for train/eval; the detector scores held-out movements only.
- Fix: batch lengths padded to multiples of 64, which stops CUDA allocator fragmentation
  (epochs were ~30x slower on larger datasets from WDDM memory spill).
- Fix: session decoding accepts a scalar `x0`/`y0` as written by other tools.

### Provenance & timing (Tier 0 — see [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md))
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

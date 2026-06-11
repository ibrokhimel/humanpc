# `humanpc` — Implementation Plan

Working name: **`humanpc`**. A general Windows automation framework (RPA / QA-test /
accessibility style) with the Human Interaction Layer (HIL) underneath, so every
action is human-like by default.

## 1. The core idea

Two things make this "easy to call" and "able to do anything on a PC":

1. **One verb, flexible target.** Every action takes a *target* that can be text, an
   image, coordinates, or a region — and a single **resolver** turns it into a screen
   location. So `bot.click("Login")`, `bot.click("button.png")`, and
   `bot.click((840, 300))` all just work.
2. **Find ≠ act.** The targeting layer (UI Automation / OCR) only *finds* where things
   are. The Human Interaction Layer does the *moving/typing*. We deliberately do **not**
   use UIA's programmatic `Invoke()` to click — we resolve to coordinates and then
   move+click like a human. That keeps human-likeness while getting UIA's reliability.

Key decision: **the public API is synchronous.** The blueprint is all `async`, which is
friction for scripts. We port the HIL math but drive it with `time.sleep`, and run
optional idle-drift on a daemon thread. Casual scripts stay one-liners; an async core
remains available for advanced use.

## 2. Architecture

```
   Script (Python)      Shell / any lang        AI agent / any lang
        │                     │                        │
        ▼                     ▼                        ▼
   ┌─────────┐          ┌──────────┐           ┌──────────────┐
   │ import  │          │  humanpc │           │ MCP / HTTP   │   ← 3 calling
   │ humanpc │          │   CLI    │           │   server     │      interfaces
   └────┬────┘          └────┬─────┘           └──────┬───────┘
        └────────────────────┴────────────────────────┘
                             ▼
                  ┌─────────────────────┐
                  │   Bot facade (sync) │   bot.click/type/scroll_to/wait_for…
                  └──────────┬──────────┘
            ┌────────────────┼────────────────┐
            ▼                ▼                 ▼
     ┌────────────┐   ┌─────────────┐   ┌──────────────┐
     │ Targeting  │   │  Human      │   │ Perception   │
     │ resolver   │   │ Interaction │   │ screenshot,  │
     │ UIA→OCR→   │   │ Layer (HIL) │   │ OCR, pixels  │
     │ template→  │   │ mouse/type/ │   └──────────────┘
     │ coords     │   │ scroll/time │
     └─────┬──────┘   └──────┬──────┘
           └─────────────────┼───────────────┐
                             ▼               ▼
                    ┌─────────────┐   ┌──────────────┐
                    │ InputDriver │   │ Window/App + │
                    │ (pluggable) │   │ System tools │
                    │ pyautogui / │   │ pywin32/     │
                    │ SendInput   │   │ pywinauto    │
                    └──────┬──────┘   └──────────────┘
                           ▼
                    Windows OS / browser
```

## 3. The three calling interfaces

| Layer | Looks like | Wraps |
|---|---|---|
| **Python library** | `from humanpc import Bot; bot = Bot(); bot.click("Login")` | the core directly |
| **CLI** | `humanpc click "Login"` · `humanpc type "hello"` · `humanpc run flow.yaml` | a thin `typer` wrapper |
| **MCP / HTTP server** | each verb as an MCP **tool** (`click`, `type`, `screenshot`, `find`, `wait_for`, `open_app`…) and HTTP `POST /click` | same core |

All three share one core — no logic duplicated. The MCP layer turns "do anything on a
PC" into agent-callable *tools*.

## 4. Targeting resolver (the crux of "easy")

A `Target` resolves in this order, returning a `Match(bbox, center, confidence, method)`:

1. **`str` → UI Automation first.** Find a native control whose Name/AutomationId matches
   (focused window, then globally) via `pywinauto`/UIA. Fast, robust, pixel-free, works
   for native apps **and** browsers (Chrome/Edge expose their DOM as a UIA tree). *Primary.*
2. **`str` → OCR fallback.** If UIA misses, OCR the screen/region (Windows.Media.Ocr, no
   external binary) and locate the text's bounding box. *Fallback.*
3. **image path / `Image(...)` → template match.** OpenCV multi-scale match with a
   confidence threshold. Works on canvas/web/anything visual.
4. **`(x,y)` / `(x,y,w,h)`** → direct point/region.
5. **`Locator(text=, control=, window=, near=, index=)`** → structured disambiguation.

Match width/height feeds the HIL Fitts-law model (small targets → slower, more careful
approach). *No AI-vision locator (kept as a pluggable slot for later).*

## 5. The toolset

- **Input (human via HIL):** `click / double_click / right_click / move_to / hover / drag / scroll / scroll_to / type / press / hotkey / hold`
- **Perception:** `screenshot(region|window) / read_text / find / find_all / exists / pixel / locate(image) / wait_for_color`
- **Flow:** `wait_for(target, timeout) / wait_until_gone / retry`
- **Windows & apps:** `open_app / close_app / kill / list_windows / find_window / focus / move_window / resize_window / minimize / maximize / get_active_window`
- **System & data:** `clipboard.get/set (text+image) / run(shell_cmd) / paste_text`
- **Personas & config:** `Bot(persona="default"|"fast"|"careful"|"tired")`, `with bot.persona("careful"): …`
- **Declarative flows (cross-language / non-coders):** a YAML runner.

```yaml
steps:
  - open_app: notepad
  - wait_for: "Untitled - Notepad"
  - click:    "Text Editor"
  - type:     "Hello from humanpc"
```

## 6. Mapping the blueprint into the framework

The blueprint becomes the `hil/` package, ported async→sync, with generated mouse paths /
keystroke timings fed point-by-point to the pluggable `InputDriver`.

| Blueprint module | Lands in | Change |
|---|---|---|
| Mouse engine (bezier/velocity/jitter/overshoot/idle) | `hil/mouse/` | async→sync; idle-drift on daemon thread |
| Typing engine (speed/pause/error/correction) | `hil/typing/` | same |
| Timing manager | `hil/timing.py` | `asyncio.sleep`→`time.sleep` |
| Reading/thinking sim | `hil/reading.py` | feeds `wait_for_reading()` |
| Scroll controller | `hil/scroll.py` | drives `scroll_to(target)` |
| Behavior state machine | `hil/behavior.py` | orchestrates verbs |

## 7. Project structure

```
humanpc/
├── pyproject.toml            # extras: [ocr] [server] [games]
├── humanpc/
│   ├── __init__.py           # exposes Bot + module-level singleton
│   ├── bot.py                # sync facade (the public API)
│   ├── config.py             # defaults + persona profiles (pydantic+yaml)
│   ├── targeting/            # resolver, locators, ocr, template, uia
│   ├── perception/           # screen (mss), pixels, dpi/monitors
│   ├── input/                # driver iface, pyautogui_driver, sendinput_driver, dispatch
│   ├── windows/              # window + app/process manager (pywin32/pywinauto/psutil)
│   ├── system/               # clipboard, shell
│   ├── hil/                  # ported blueprint (mouse/typing/scroll/timing/reading/behavior)
│   ├── flows/                # yaml runner, record/replay macros
│   ├── safety/               # kill-switch, dry-run, rate limit, audit log
│   ├── cli.py                # typer CLI
│   └── server/               # fastapi http + mcp tool server
├── examples/                 # quickstart scripts + sample flows
└── tests/                    # hil math, resolver, integration vs Notepad/Calc, safety
```

## 8. Tech stack (Windows-first)

| Concern | Library |
|---|---|
| Input (default / robust) | `pyautogui` · native `ctypes` **SendInput** driver |
| Screen capture | `mss` + `Pillow` |
| Template match | `opencv-python` + `numpy` |
| OCR | Windows.Media.Ocr via `winsdk` (no external binary); `pytesseract` optional |
| Accessibility / find | `pywinauto` (UIA) + `comtypes` |
| Windows / processes | `pywin32`, `psutil` |
| Clipboard | `pywin32` / `pyperclip` (+ Pillow for images) |
| CLI | `typer` |
| Server | `fastapi` + `uvicorn`; `mcp` SDK for the tool server |
| Config | `pydantic` v2 + `pyyaml` |
| Kill-switch | low-level `keyboard` hook + pyautogui corner failsafe |

## 9. Cross-cutting must-haves

- **Kill-switch (mandatory).** A human-like agent driving the real mouse can trap you.
  Global panic hotkey (e.g. `Ctrl+Alt+Q`) + slam-to-corner → raises `Aborted`. Phase 0.
- **DPI & multi-monitor.** Win11 per-monitor scaling is the #1 cause of clicks landing in
  the wrong place. Set per-monitor DPI awareness and map screenshot↔input coordinate
  spaces correctly, early.
- **Reliability.** UIA-first, OCR/template fallback, confidence thresholds, multi-scale,
  and `wait_for` polling + retries instead of fixed sleeps.
- **Dry-run + audit log.** Every action logged; `dry_run=True` plans without executing.

## 10. Build roadmap

| Phase | Deliverable | Proves |
|---|---|---|
| **0 — Skeleton & safety** | package, config/personas, DPI setup, kill-switch, dry-run, audit log, `InputDriver` + pyautogui driver, `mss` capture, raw click/move/type at coordinates | plumbing works end-to-end |
| **1 — HIL port** | blueprint mouse/typing/scroll/timing/reading/behavior ported sync; paths→driver; visualization tests | actions are human-like |
| **2 — Targeting** | UIA + OCR + template resolver → `Match`; `Locator/Image/Region` types | `bot.click("Login")` works |
| **3 — Windows/system tools** | window/app manager, clipboard, shell, `wait_for/find_all/exists` | full verb set |
| **4 — Interfaces** | `typer` CLI, FastAPI HTTP, MCP tool server, YAML flow runner | all three calling layers live |
| **5 — Polish** | idle-drift thread, record/replay, more personas, docs/examples, packaging extras, optional games SendInput + browser/Playwright backends | production-ready |

**Testing:** unit tests for HIL math (no straight lines; accelerate→cruise→decelerate;
Fitts correlation; typing variance/error rate); integration tests that open
Notepad/Calculator, type, and read results back via OCR/UIA; resolver tests on synthetic
screenshots; a safety test that the kill-switch aborts mid-run.

## 11. Key decisions

- **Sync public API** over the async blueprint (ease-of-scripting wins).
- **UIA finds, HIL acts** — never programmatic-invoke, to preserve human-likeness.
- **Games deprioritized** but the input backend stays pluggable (SendInput driver in Phase 5).
- **Browsers driven at the OS level** via UIA + input; a Playwright/CDP backend is optional later.

# humanpc

Human-like PC automation framework for Windows. A scriptable layer over mouse,
keyboard, screen, windows, and apps — with a **Human Interaction Layer** (Bézier
mouse paths, Fitts-law velocity, natural typing rhythm, human scrolling) so every
automated action behaves like a person rather than a script.

> **Status:** 🟢 Phases 0–4 complete — the engine and all three interfaces work.
> Phase 5 (polish) remains. See [`docs/BUILD_PHASES.md`](docs/BUILD_PHASES.md).

> **Intended use:** authorized automation only — RPA, QA / UI-test automation,
> accessibility tooling, and personal task automation on machines you control.

## What it does

- **One simple API** — `bot.click("Login")`, `bot.type("hello")`, `bot.find_all(Image("icon.png"))`.
- **Flexible targets** — text, an image, coordinates, or a region all resolve through one engine.
- **Human by default** — natural mouse curves, variable typing speed, pauses, and timing.
- **Three ways to call it** — Python library, CLI, and HTTP / MCP tool server (agent-callable).
- **Do anything on a PC** — input, screenshots/OCR, window & app management, clipboard, shell.

## Install

```bash
pip install -e .            # core (zero dependencies; dry-run + tests work as-is)
pip install -e .[all]       # real input, capture, OCR, UIA, windows
pip install -e .[server]    # FastAPI HTTP + MCP tool server
```

## Usage

**Python**
```python
from humanpc import Bot, Image
bot = Bot()                          # real input (lazy-loads pyautogui)
bot.move_to("Sign in").click()       # text -> UIA/OCR; human mouse path
bot.type("hello@example.com")        # human typing (self-correcting typos)
bot.click(Image("submit.png"))       # image -> OpenCV template match
bot.wait_for("Dashboard", timeout=20)

Bot(dry_run=True).click((400, 300))  # plan + audit, never touches the OS
```

**CLI** (argparse, no extra deps)
```bash
humanpc click "Login"
humanpc --dry-run --json find 400,300
humanpc type "hello world"
humanpc run echo hi
humanpc flow examples/flows/notepad.yaml
```

**HTTP / MCP servers** (agent-callable tools)
```bash
humanpc serve --http --port 8000     # POST /click {"target":"Login"}
humanpc serve --mcp                  # MCP stdio tool server
```

**Declarative flow** (`humanpc flow file.yaml`)
```yaml
persona: careful
steps:
  - open_app: notepad.exe
  - wait_for: "Untitled - Notepad"
  - type: "Hello from humanpc"
  - hotkey: [ctrl, s]
```

A global kill-switch (`Ctrl+Alt+Q`, or throw the cursor into a screen corner)
aborts any run.

## Design docs

- [`docs/BUILD_PHASES.md`](docs/BUILD_PHASES.md) — live build tracker (what's done / in progress).
- [`docs/PLAN.md`](docs/PLAN.md) — implementation plan, architecture, file layout, roadmap.
- [`docs/blueprint/`](docs/blueprint/) — the Human Interaction Layer research blueprint + diagrams.

## Planned layout

```
humanpc/
├── bot.py            # sync facade (public API)
├── targeting/        # UIA → OCR → template → coordinates resolver
├── perception/       # screenshot, OCR, pixels, DPI/monitors
├── input/            # pluggable input drivers (pyautogui / SendInput)
├── windows/          # window + app/process management
├── system/           # clipboard, shell
├── hil/              # Human Interaction Layer (mouse/typing/scroll/timing/behavior)
├── flows/            # YAML flow runner, record/replay
├── safety/           # kill-switch, dry-run, rate limit, audit log
├── cli.py            # CLI
└── server/           # HTTP + MCP tool server
```

## Roadmap

| Phase | Deliverable |
|---|---|
| 0 | Skeleton & safety (kill-switch, DPI, input driver, screen capture) |
| 1 | Human Interaction Layer port |
| 2 | Targeting resolver (UIA + OCR + template) |
| 3 | Window/system tools |
| 4 | CLI + HTTP + MCP interfaces |
| 5 | Polish (idle drift, macros, packaging, optional game/browser backends) |

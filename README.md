# humanpc

Human-like PC automation framework for Windows. A scriptable layer over mouse,
keyboard, screen, windows, and apps — with a **Human Interaction Layer** (Bézier
mouse paths, Fitts-law velocity, natural typing rhythm, human scrolling) so every
automated action behaves like a person rather than a script.

> **Status:** 🟡 Planning. See [`docs/PLAN.md`](docs/PLAN.md). No implementation code yet.

> **Intended use:** authorized automation only — RPA, QA / UI-test automation,
> accessibility tooling, and personal task automation on machines you control.

## What it will do

- **One simple API** — `bot.click("Login")`, `bot.type("hello")`, `bot.scroll_to("Submit")`.
- **Flexible targets** — text, an image, coordinates, or a region all resolve through one engine.
- **Human by default** — natural mouse curves, variable typing speed, pauses, and timing.
- **Three ways to call it** — Python library, CLI, and an MCP/HTTP tool server (agent-callable).
- **Do anything on a PC** — input, screenshots/OCR, window & app management, clipboard, shell.

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

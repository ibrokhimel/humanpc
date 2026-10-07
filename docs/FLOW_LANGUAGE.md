# humanpc Flow Language Reference

The **flow language** is how you write an automation as a plain **YAML** (or JSON)
file — a list of steps that humanpc runs top to bottom. No Python required.

It's the right tool for **linear scripts**: "open this, wait for that, click here,
type this." When you need randomness, loops, or `if` logic, graduate to the
[Python API](PYTHON_API.md) — same engine, full programming language.

Run a flow:

```bash
humanpc flow myflow.yaml               # run it for real
humanpc --dry-run flow myflow.yaml     # plan + audit, never touches the OS
humanpc --persona careful flow myflow.yaml
```

Or from Python:

```python
from humanpc import FlowRunner
FlowRunner().run_file("myflow.yaml")
```

---

## 1. File structure

A flow is a mapping with an optional `persona` / `dry_run` and a list of `steps`:

```yaml
persona: careful        # default | fast | careful | tired   (optional)
dry_run: false          # optional; --dry-run on the CLI overrides this
steps:
  - open_app: notepad.exe
  - wait_for: "Untitled - Notepad"
  - type: "Hello from humanpc"
  - hotkey: [ctrl, s]
```

A bare list of steps (no top-level keys) is also valid:

```yaml
- open_app: notepad.exe
- type: "hi"
```

### Step forms

Every step is one of two shapes.

**Shorthand** — a single-key mapping `{verb: value}`. The value is interpreted
per-verb (see each verb below):

```yaml
- click: "Login"
- type: "hello"
- scroll: -3
```

**Verbose** — `{action: verb, ...params}`, used when a verb needs more than one
parameter (e.g. a right double-click, or a custom timeout):

```yaml
- action: click
  target: submit.png
  button: right
  clicks: 2

- action: wait_for
  target: "Dashboard"
  timeout: 30
  interval: 0.5
```

An optional `name:` key on any step is treated as a label and ignored by the
runner — handy for readability:

```yaml
- name: submit the form
  click: submit.png
```

---

## 2. Targets

Anything that locates something on screen (`click`, `move`, `find`, `wait_for`,
…) takes a **target**. The string form is auto-detected:

| You write            | Interpreted as | Found via |
|----------------------|----------------|-----------|
| `"Login"`            | text           | UI Accessibility (UIA) → OCR |
| `"button.png"`       | image          | OpenCV template match on screen |
| `"300,200"`          | point `(x, y)` | exact coordinates |
| `"10,20,60,24"`      | region `(x,y,w,h)` | clicks the region's centre |

Image extensions recognised: `.png .jpg .jpeg .bmp .gif .webp`. So this "click a
screenshot of a button" flow is exactly what the language is built for:

```yaml
steps:
  - wait_for: buttons/login.png     # waits until the picture appears
  - click: buttons/login.png        # human mouse path to it, then click
```

> **Image tips:** crop tight to the button; keep the same screen resolution /
> display-scaling / theme as when you captured it (mismatched DPI is the #1 cause
> of "can't find it"). Paths are relative to where you run `humanpc flow`.

---

## 3. Verb reference

All verbs available in a flow. "Shorthand value" is what a bare `verb: value`
maps to; use the **verbose** form for any other parameter.

### Mouse

| Verb | Shorthand value | Verbose params | Notes |
|------|-----------------|----------------|-------|
| `click` | `target` | `target`, `button` (`left`/`right`/`middle`, def. `left`), `clicks` (def. `1`) | Moves then clicks. |
| `double_click` | `target` | `target` | Two clicks. |
| `right_click` | `target` | `target` | |
| `move` / `move_to` | `target` | `target` | Move cursor, no click. |
| `scroll` | `amount` (int) | `amount` | + scrolls up, − scrolls down (per the input driver). |

```yaml
- click: "OK"
- action: click
  target: "File"
  button: right
- double_click: icon.png
- scroll: -5
```

### Keyboard

| Verb | Shorthand value | Notes |
|------|-----------------|-------|
| `type` | `text` | Human typing rhythm; injects then self-corrects typos so final text is exact. |
| `press` | one key or a list | Individual key presses. |
| `hotkey` | list, or `"ctrl+s"` | Chord: presses in order, releases in reverse. |

```yaml
- type: "hello@example.com"
- press: enter
- press: [tab, tab]
- hotkey: [ctrl, s]
- hotkey: "ctrl+shift+n"
```

Key names follow the active input driver (pyautogui-style): `ctrl alt shift win
enter tab esc space backspace delete up down left right home end pageup pagedown
f1`…`f12`, and single characters.

### Finding & screen

| Verb | Shorthand value | Verbose params | Returns in output |
|------|-----------------|----------------|-------------------|
| `find` | `target` | `target` | `{found, match}` |
| `find_all` | `target` | `target` | `{count, matches}` |
| `exists` | `target` | `target` | `{exists}` |
| `wait_for` | `target` | `target`, `timeout` (def. `10`), `interval` (def. `0.25`) | polls until it appears or raises |
| `screenshot` | `path` | `path` | saves PNG (or returns image if no path) |
| `read_text` | — | `region` (`x,y,w,h`) | OCR text of screen/region |

```yaml
- wait_for: "Dashboard"
- action: wait_for
  target: spinner_gone.png
  timeout: 45
- screenshot: proof.png
```

### Timing & deliberation

| Verb | Shorthand value | Verbose params | Notes |
|------|-----------------|----------------|-------|
| `think` | `complexity` (`low`/`medium`/`high`/`very_high`) | `complexity`, `choices` (int) | **Randomized** human hesitation. `choices` uses Hick–Hyman decision timing. |
| `sleep` | `seconds` (number) | `seconds` | **Fixed** pause. See note below. |

```yaml
- think: high            # variable, human-like pause
- sleep: 1.5             # exactly 1.5s every run
- action: think
  choices: 8             # "deciding among 8 options"
```

> ⚠️ **Random waits in YAML:** `sleep` is a fixed number and there is no
> range/random-sleep verb in the flow language today. For a random wait, either
> use `think` (already randomized) or drop into [Python](PYTHON_API.md)
> (`time.sleep(random.uniform(1, 3))`). If you want `sleep: [1, 3]` range syntax
> added to the flow language, it's a small change — ask and it can be added.

### System & windows

| Verb | Shorthand value | Verbose params | Notes |
|------|-----------------|----------------|-------|
| `run` | `command` | `command`, `cwd`, `timeout`, `shell` | Runs a shell command. |
| `open_app` | `target` | `target`, `args`, `wait` (window title), `timeout` (def. `15`) | Launches an app; `wait` blocks until its window appears. |
| `focus` | `title` | `title` | Bring a window to the foreground. |
| `windows` | — | — | List open windows. |

```yaml
- action: open_app
  target: notepad.exe
  wait: "Untitled - Notepad"
- run: "git status"
- focus: "Notepad"
```

---

## 4. Personas

A persona tunes speed and rhythm. Set it at the top of the flow or with
`--persona` on the CLI.

| Persona | Feel | Speed |
|---------|------|-------|
| `default` | balanced | 1.0× |
| `fast` | quick, confident | ~0.6× (faster) |
| `careful` | deliberate | ~1.5× (slower) |
| `tired` | sluggish, more pauses | ~1.8× (slowest) |

---

## 5. Safety

- **Kill-switch:** press **Ctrl+Alt+Q**, or slam the cursor into a screen corner,
  to abort any run (raises `Aborted`). The hotkey needs the `keyboard` package;
  the corner failsafe always works.
- **Dry-run:** `--dry-run` (or `dry_run: true`) plans and audits every step
  without touching the OS — the safest way to check a new flow.
- Every step is written to an **audit log**.

---

## 6. Generating flows by recording

You don't have to hand-write YAML. Record live and save it:

```python
from humanpc import Recorder, Bot

rec = Recorder(bot=Bot())                       # executes as you record
rec.click("Login").type("user").press("tab").type("pass").press("enter")
rec.save("login.yaml")                          # a normal flow file
```

Replay later with `humanpc flow login.yaml` or `Macro.load("login.yaml").replay()`.

---

## 7. What the flow language can't do

The flow language is **linear** — a fixed list of steps. It has **no** variables,
loops, conditionals, or random values. When you need those, use the Python API
(the flow runner is just a thin layer over it):

| You want… | Do it in Python |
|-----------|-----------------|
| Random wait | `time.sleep(random.uniform(1, 3))` |
| "click only if X is visible" | `if bot.exists("X"): bot.click("X")` |
| Repeat until done | `while bot.exists("Next"): bot.click("Next")` |
| Retry a flaky click | `bot.click_until("Save", until=lambda: bot.exists("Saved"))` |
| Read a value and branch | `if "error" in bot.read_text(): ...` |

See **[PYTHON_API.md](PYTHON_API.md)**.

---

## 8. Full example

```yaml
# notepad_note.yaml — open Notepad, write a dated note, save it.
persona: careful
steps:
  - name: launch
    action: open_app
    target: notepad.exe
    wait: "Untitled - Notepad"

  - think: low
  - type: "Meeting notes\n-------------\n"
  - type: "Action items go here."

  - name: save
    hotkey: [ctrl, s]
  - wait_for: "Save As"
  - type: "notes.txt"
  - press: enter
```

```bash
humanpc --dry-run flow notepad_note.yaml   # rehearse
humanpc flow notepad_note.yaml             # run
```

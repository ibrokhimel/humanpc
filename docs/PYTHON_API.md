# humanpc Python API Reference

humanpc **is** a Python library. `from humanpc import Bot` gives you the whole
engine — the same one behind the [flow language](FLOW_LANGUAGE.md) and the CLI —
but now inside real Python, so you get **random waits, loops, conditionals, and
variables** for free.

```python
from humanpc import Bot

bot = Bot()                               # real input (lazy-loads the driver)
bot.move_to("Sign in").click()            # text target → human mouse path
bot.type("me@example.com")                # human typing, self-correcting typos
bot.click(Image("submit.png"))            # image target → template match
bot.wait_for("Dashboard", timeout=20)
```

Every action funnels through the same safety pre-check (kill-switch, action cap)
and audit trail, so those apply no matter how you call it.

---

## 1. Install

```bash
pip install -e ".[all,flows]"     # everything: input, capture, vision (images), OCR, UIA, windows
pip install -e .                  # core only — dry-run + tests, zero dependencies
```

Extras are opt-in: `input` (real mouse/keys), `capture` + `vision` (screenshots +
image matching), `ocr` (read text), `uia` (accessibility targeting), `windows`
(window/app management), `flows` (YAML), `server` (HTTP/MCP).

---

## 2. Creating a Bot

```python
Bot(
    persona="default",     # "default" | "fast" | "careful" | "tired"
    *,
    dry_run=False,         # True → plan + audit, never touch the OS
    config=None,           # a Config(...) for finer control (seed, safety, timing)
    idle=False,            # True → subtle background cursor drift while idle
    arm=True,              # True → arm the kill-switch + precision timer now
    # advanced injection seams: driver, audit, killswitch, resolver, windows, clipboard, profile
)
```

Common patterns:

```python
bot = Bot("fast")                             # quick persona
bot = Bot(dry_run=True)                        # rehearse safely
bot = Bot(config=Config(seed=42))              # reproducible run (same "person" each time)

with Bot() as bot:                             # context manager → auto-cleanup
    bot.click("OK")
```

Each Bot samples a stable **individual** — its own consistent speed/rhythm
"fingerprint." Same `seed` → same person every run; no seed → a new person each run.

### Config options

```python
from humanpc import Config
Config(
    persona="default",
    dry_run=False,
    failsafe=True,               # slam-cursor-to-corner abort
    kill_hotkey="ctrl+alt+q",    # global panic hotkey (None to disable)
    max_actions=None,            # hard cap on actions per Bot (None = unlimited)
    audit_enabled=True,
    audit_path=None,             # JSONL file, or None for in-memory
    typing_errors=True,          # inject realistic typos...
    always_correct_typing=True,  # ...but always fix them → final text exact
    precision_timing=True,       # high-resolution sleeps (Windows 1ms timer)
    relative_mouse=False,        # relative deltas through pointer ballistics vs absolute
    individuality=True,          # sample a per-Bot behavioural profile
    seed=None,                   # deterministic RNG
)
```

---

## 3. Targets

Every locating method accepts the same target types:

```python
bot.click("Login")               # str  → text (UIA → OCR)
bot.click((400, 300))            # (x, y) → point
bot.click((10, 20, 60, 24))      # (x, y, w, h) → region centre
bot.click(Image("submit.png"))   # Image → template match
```

`Image` is tunable:

```python
from humanpc import Image
Image(
    "submit.png",
    confidence=0.8,          # 0–1 match threshold (default 0.8)
    grayscale=True,          # faster, scale-robust
    scales=(0.9, 1.0, 1.1),  # try multiple sizes (handles minor DPI drift)
    region=None,             # a Rect to search only part of the screen
)
```

---

## 4. Methods

Most action methods **return `self`**, so you can chain:
`bot.move_to("File").click().type("x")`.

### Mouse

| Method | Signature | Notes |
|--------|-----------|-------|
| `move_to` | `move_to(target, *, target_size=None)` | Human curved path; small targets get a slower, careful approach. |
| `click` | `click(target=None, *, button="left", clicks=1)` | `target=None` clicks where the cursor is. |
| `double_click` | `double_click(target=None, *, button="left")` | |
| `right_click` | `right_click(target=None)` | |
| `drag` | `drag(to, *, frm=None, button="left")` | Press at `frm` (or current), move to `to`, release. |
| `scroll` | `scroll(amount, *, at=None)` | `at` moves there first. + up / − down. |

### Keyboard

| Method | Signature | Notes |
|--------|-----------|-------|
| `type` | `type(text)` | Human rhythm; typos injected then self-corrected. `\n` = enter. |
| `press` | `press(*keys)` | e.g. `bot.press("enter")`, `bot.press("tab", "tab")`. |
| `hotkey` | `hotkey(*keys)` | Chord, e.g. `bot.hotkey("ctrl", "s")`. |

### Deliberation (humanized, randomized pauses)

| Method | Signature | Notes |
|--------|-----------|-------|
| `think` | `think(complexity="medium", *, choices=None)` | Pause as if deciding. `complexity`: `low`/`medium`/`high`/`very_high`. `choices=N` → Hick–Hyman decision time. |
| `read`  | `read(content, *, complexity=1.0, scan=False)` | Pause as if reading; `content` = text or char count; `scan=True` skims. |

### Finding & screen

| Method | Signature | Returns |
|--------|-----------|---------|
| `find` | `find(target)` | `Match` or `None` |
| `find_all` | `find_all(target)` | `list[Match]` |
| `exists` | `exists(target)` | `bool` |
| `wait_for` | `wait_for(target, *, timeout=10.0, interval=0.25)` | `Match` (raises `TargetNotFound` on timeout) |
| `screenshot` | `screenshot(path=None, *, region=None)` | saves to `path`, else returns a PIL image |
| `read_text` | `read_text(*, region=None)` | OCR'd `str` |
| `position` | `position()` | current cursor `(x, y)` |

A `Match` has `.center` (Point), `.size`, `.bbox` (Rect), `.confidence`, `.method`
(`coords`/`region`/`uia`/`ocr`/`template`), `.text`.

### Verification (confirm an action landed)

| Method | Signature | Notes |
|--------|-----------|-------|
| `verify` | `verify(check, *, attempts=3, interval=0.25, retry=None)` | Poll `check()` until truthy → `bool`. |
| `ensure` | `ensure(check, *, attempts=3, interval=0.25, retry=None, message=None)` | Like `verify` but raises `VerificationError`. |
| `click_until` | `click_until(target, until, *, attempts=3, interval=0.3, button="left")` | Click and re-click until `until()` holds. |

### Windows & system

| Method | Signature | Notes |
|--------|-----------|-------|
| `open_app` | `open_app(target, args=(), *, wait=None, timeout=15.0)` | `wait` = window title to block on. |
| `focus` | `focus(target)` | Bring a window (title or `Window`) to front. |
| `list_windows` / `find_window` / `active_window` | | Enumerate / locate windows. |
| `wait_for_window` | `wait_for_window(title, *, timeout=15.0, interval=0.3)` | |
| `run` | `run(command, **kwargs)` | Shell command → `ShellResult(ok, returncode, stdout, stderr)`. |

### Idle & lifecycle

| Method | Notes |
|--------|-------|
| `start_idle()` / `stop_idle()` | Background micro cursor-drift, like a resting hand. |
| `persona(name)` | Context manager: `with bot.persona("careful"): ...`. |
| `close()` | Release kill-switch, timer, idle loop (or use `with Bot() as bot:`). |

---

## 5. Dynamic behavior — the reason to use Python

This is what the flow YAML can't do.

### Random waits

```python
import random, time

time.sleep(random.uniform(1.0, 3.0))      # plain random wait, 1–3s

# Even better — a *humanized* pause that's already randomized for you:
bot.think("high")                          # hesitate like a person deciding
bot.read("a paragraph of on-screen text")  # pause proportional to reading it
```

A tiny reusable helper:

```python
def wait_random(lo, hi):
    time.sleep(random.uniform(lo, hi))

bot.click("Login")
wait_random(0.8, 2.5)
bot.type("hunter2")
```

### Conditionals

```python
if bot.exists("Accept Cookies"):
    bot.click("Accept Cookies")

if "error" in bot.read_text().lower():
    bot.screenshot("error.png")
```

### Loops

```python
# Keep clicking "Next" until it's gone.
while bot.exists("Next"):
    bot.click("Next")
    bot.think("low")

# Process every matching icon on screen.
for m in bot.find_all(Image("row_checkbox.png")):
    bot.click(m.center)

# Retry a flaky click until the UI confirms it worked.
bot.click_until("Save", until=lambda: bot.exists("Saved"))
```

### Reproducible vs. varied runs

```python
Bot(config=Config(seed=1))   # identical timing/typos every run — great for tests
Bot()                        # a different "person" each run — natural variety
```

---

## 6. Personas

Switch persona per-Bot or temporarily:

```python
bot = Bot("careful")

with bot.persona("fast"):     # this block runs quick...
    bot.type("quick note")
# ...back to careful here
```

`default` (1.0×) · `fast` (~0.6×) · `careful` (~1.5×) · `tired` (~1.8×).

---

## 7. Safety

```python
bot = Bot(config=Config(max_actions=200))   # hard stop after 200 actions
```

- **Ctrl+Alt+Q** or cursor-to-corner aborts mid-run → raises `Aborted`.
- `Bot(dry_run=True)` plans + audits with zero OS side-effects; inspect
  `bot.audit.entries` afterward.

---

## 8. Module-level shortcuts

For throwaway scripts, call verbs directly on a shared singleton Bot:

```python
import humanpc as h
h.click((100, 200)); h.type("hi"); h.hotkey("ctrl", "s")
```

---

## 9. Record & replay

```python
from humanpc import Recorder, Bot, Macro

rec = Recorder(bot=Bot())                    # runs live as you record
rec.click("Login").type("user").press("enter")
rec.save("login.yaml")                        # a normal flow file

Macro.load("login.yaml").replay(bot=Bot())    # replay later
```

---

## 10. Exceptions

All inherit `HumanpcError`:

| Exception | Raised when |
|-----------|-------------|
| `TargetNotFound` | The resolver can't locate a target (or `wait_for` times out). |
| `Aborted` | Kill-switch fired or a safety limit was hit mid-action. |
| `DriverError` | An input/screen/optional backend is missing or failed. |
| `VerificationError` | `ensure` / `click_until` couldn't confirm the result. |

```python
from humanpc import Bot, TargetNotFound

bot = Bot()
try:
    bot.click("Submit")
except TargetNotFound:
    bot.screenshot("missing.png")
```

---

## 11. Full example

```python
import random, time
from humanpc import Bot, Image, TargetNotFound

def wait_random(lo, hi):
    time.sleep(random.uniform(lo, hi))

with Bot("careful") as bot:
    bot.open_app("notepad.exe", wait="Untitled - Notepad")
    bot.think("low")

    for line in ("Meeting notes", "-------------", "Action items:"):
        bot.type(line + "\n")
        wait_random(0.3, 1.0)          # human pause between lines

    # Save, retrying until the Save-As dialog actually appears.
    bot.hotkey("ctrl", "s")
    try:
        bot.wait_for("Save As", timeout=10)
        bot.type("notes.txt")
        bot.press("enter")
    except TargetNotFound:
        bot.screenshot("save_failed.png")
```

See also: **[FLOW_LANGUAGE.md](FLOW_LANGUAGE.md)** for the declarative YAML format.

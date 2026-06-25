# humanpc

**Human-like PC automation for Windows.** A scriptable layer over the mouse,
keyboard, screen, windows, and apps whose defining feature is a **Human
Interaction Layer**: every action is generated from models of real human motor
control, timing, and cognition, so the input looks like a person used the
machine — not like a script drove it.

```python
from humanpc import Bot

bot = Bot()                              # you are now a (simulated) person
bot.move_to("Sign in").click()           # curved path, Fitts-law timing, overshoot+homing
bot.type("hello@example.com")            # per-finger rhythm, real typos that self-correct
bot.wait_for("Dashboard", timeout=20)
```

> **Intended use:** authorized automation only — RPA, QA / UI-test automation,
> accessibility tooling, and personal task automation on machines you control.
> See [Responsible use](#responsible-use).

---

## Why it's different

Most automation moves the cursor in straight lines, types at a constant rate, and
clicks the instant it can. Those are trivially distinguishable from a human and
brittle against modern UIs. humanpc instead **samples each action from a model of
how humans actually move, type, read, and decide** — with a different, consistent
"person" behind every bot and a measurable realism profile you can score.

## Install

```bash
pip install -e .            # core (zero dependencies; dry-run + tests work as-is)
pip install -e .[all]       # real input, screen capture, OCR, UIA, windows
pip install -e .[server]    # FastAPI HTTP + MCP tool server
```

Every backend is lazy-loaded, so `import humanpc` pulls in nothing heavy. On a
non-Windows host the pure-Python planning/dry-run paths still run (useful for
tests and development); the native realism path targets Windows.

---

## How it replicates humans

This is the core of the library. Each subsystem is a pure, seedable *planner* —
given an RNG it returns a plan (mouse steps, keystroke events, scroll bursts) that
the Bot executes against a low-level input driver. Everything below is configurable
and unit-tested.

### Mouse movement
- **Curved paths** — a cubic Bézier with both control points pushed to the same
  side, so the path is a gentle C-curve, never a ruler-straight line or an
  unnatural S.
- **Sigma-Lognormal velocity** (Plamondon's kinematic theory) — a rapid human
  reach is the vector sum of *lognormal velocity strokes*: a primary ballistic
  impulse with an early speed peak (~40–50% of the move) and a long right-skewed
  tail, plus 1–2 overlapping **corrective (homing) sub-movements**. This replaces
  the symmetric easing most bots use. (A simpler asymmetric-Beta model is also
  available via `model="beta"`.)
- **Fitts's Law timing** — total movement time `a + b·log₂(2D/W + 1)` scales with
  distance and target size, with human variance.
- **Curvature-coupled speed (2/3 power law)** — the cursor slows through tight
  parts of the curve and speeds up on straight stretches, so the per-segment
  timing isn't a flat cadence.
- **Colored motor noise** — instead of flat-spectrum white jitter, the path
  carries **1/f "pink" wander** (Voss–McCartney) plus an **8–12 Hz physiological
  tremor**. Real hand noise is autocorrelated with a tremor band; white noise is
  the single most common giveaway in synthetic-trace detection.
- **Overshoot + homing** — longer moves frequently sail just past the target and
  converge back with decaying corrections, landing exactly on it.
- **Post-landing settle** — tiny residual micro-movements between arriving and
  clicking.
- **Idle drift** — an optional background loop nudges the cursor while "reading"
  or thinking; a frozen cursor between actions is a strong bot signal.

### Keyboard
- **Per-key timing** — inter-key intervals are **lognormal** (right-skewed,
  heavy-tailed) like real typing, not Gaussian.
- **Digraph structure** — timing depends on the specific key pair: **same-finger**
  digraphs are slow, **alternating-hand** digraphs are fast (rollover), modulated
  by a QWERTY finger/hand map and common-bigram acceleration.
- **Key-hold (dwell) time** — each key is physically *held* for a realistic,
  right-skewed duration (`char_down → hold → char_up`), not an atomic zero-dwell
  emit. Dwell time is a primary keystroke-dynamics biometric.
- **Shift dynamics** — capitals and symbols press, hold, and release a real Shift
  key that overlaps the keystroke.
- **Realistic typos that self-correct** — substitution (adjacent key),
  insertion, **transposition** (the most common real typo), and doubling, each
  reversible with backspaces. With `always_correct` (default) the final text is
  always exactly what you asked for; the human-looking hesitation and backspacing
  happen along the way.

### Timing & cognition
- **Fixation-based reading** — `bot.read(text)` models eye fixations + saccades +
  regressions, with a faster `scan=True` mode for skimming a familiar UI rather
  than reading prose.
- **Hick–Hyman decisions** — `bot.think(choices=N)` makes the deliberation time
  grow with `log₂(N+1)`, the number of on-screen options.
- **Session arc** — a person isn't metronomic across a session: a **warm-up**
  (slightly slow start), gradual **fatigue / vigilance decrement**, and occasional
  **distraction** pauses, all carried *across* actions rather than reset each time.

### Individuality (no two bots are the same)
- **Sampled persona** — each `Bot` draws a stable trait vector once (typing speed,
  error rate, dwell, curve bias, overshoot tendency, movement pace…) and reuses it
  for the whole session. With a `seed` the person is reproducible; without one,
  every run is a different person.
- **Correlated traits** — traits are linked through a latent skill factor (a faster
  typist tends to make fewer errors and hold keys more briefly), so you never get
  an impossible human.
- **AR(1) action tempo** — consecutive actions are *autocorrelated*: the bot drifts
  into fast and slow streaks instead of re-rolling its tempo every action.

### Input provenance (the low level)
- **Native `SendInput` driver** — injects mouse/keyboard at the OS level (honored
  by apps that ignore `SetCursorPos`), with true split key press/release for dwell.
- **High-resolution timing** — raises the Windows timer tick to 1 ms and uses a
  hybrid sleep so sub-frame delays are actually realised instead of quantising to
  the ~15.6 ms scheduler tick.
- **Relative mouse motion (opt-in)** — `relative_mouse=True` injects relative
  deltas through the OS pointer-acceleration curve and corrects residual drift to
  land exactly on target.
- **Honest limitation:** any user-mode `SendInput` event carries the kernel
  *injected* flag (`LLKHF_INJECTED`), which a low-level hook can read. No user-mode
  code can remove it — that needs a kernel-mode or hardware-HID backend, which
  plugs into the same `Bot(driver=…)` seam. humanpc improves *behavioural* realism,
  not input provenance.

---

## Personas & configuration

Coarse presets layer on top of the per-instance individual:

```python
Bot(persona="careful")          # default | fast | careful | tired
with bot.persona("fast"): ...   # temporarily switch
```

```python
from humanpc import Bot, Config

Bot(config=Config(
    seed=42,                 # reproducible person + action stream
    individuality=True,      # sample a distinct, consistent persona (default)
    typing_errors=True,      # inject realistic typos (always self-corrected)
    precision_timing=True,   # 1 ms timer + accurate sub-frame sleeps (Windows)
    relative_mouse=False,    # relative-delta motion through pointer acceleration
))

bot.individual               # inspect the sampled traits (wpm, error_rate, skill, …)
```

---

## Reliability & safety

**Verify that actions actually happened** — humans look to confirm a click landed:

```python
bot.click_until("Submit", until=lambda: bot.exists("Saved"))   # re-click until it takes
bot.ensure(lambda: bot.exists("Welcome"), attempts=5)          # raise if never true
ok = bot.verify(lambda: bot.exists("Logged in"))               # boolean outcome
```

**Safety**
- **Kill-switch** — `Ctrl+Alt+Q`, or slam the cursor into a screen corner, aborts any run.
- **Dry-run** — `Bot(dry_run=True)` plans and audits every action without touching the OS.
- **Audit log** — every action is recorded (`bot.audit.entries`); optional JSONL file.
- **Limits** — `max_actions` caps a session; `Bot` is a context manager (`with Bot() as bot:`)
  that releases the timer tick, idle loop, and kill-switch on exit.

---

## Targets & actions

A single resolver turns **text → UI Automation → OCR**, an **image → template match**,
or **coordinates / a region** into a location, so the same call works for any target:

```python
bot.move_to("Login")                 # text (accessibility tree, then OCR)
bot.click(Image("submit.png"))       # image (OpenCV template match)
bot.double_click((400, 300))         # coordinates
bot.drag("file.txt", frm="Inbox")    # press, move with button held, release
bot.scroll(20)                       # decelerating flings + reading pauses
bot.find_all(Image("row.png"))       # every match
bot.read_text(region=(0, 0, 800, 60))  # OCR a region
```

Plus window/app/system tools: `open_app`, `wait_for_window`, `focus`, `find_window`,
`run` (shell), `screenshot`, and clipboard access.

---

## Other ways to call it

**CLI** (argparse, no extra deps)
```bash
humanpc click "Login"
humanpc --dry-run --json find 400,300
humanpc type "hello world"
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

---

## Measuring realism

Realism here is *measured*, not asserted. `humanpc.validation` extracts the
features a mouse-/keystroke-dynamics detector would key on (velocity skew, peak
location, deceleration, curvature, tremor band, key-hold dwell, inter-key-interval
skew) and scores generated traces against human reference ranges and naive-bot
baselines:

```python
from humanpc.validation import mouse_realism_checks, typing_realism_checks
```

The `winval/` directory holds standalone **Windows** validation runners that drive
*real* `SendInput` and capture it with low-level `WH_KEYBOARD_LL` / `WH_MOUSE_LL`
hooks (dwell, Shift, the injected-flag check, timer accuracy, relative-mouse
landing, and detector-style trajectory scoring). They need an interactive desktop.

> True validation ultimately needs a corpus of *real human* recordings to
> calibrate the targets; the shipped checks encode literature ranges and guard
> against regressions.

---

## Responsible use

humanpc is for automation **you are authorized to run on machines you control** —
RPA, QA, accessibility, personal task automation. Do not use it to evade
bot-detection where that violates a service's terms, to create fake activity, or
to defeat security controls. The injected-flag limitation above is deliberate and
documented: this is a behavioural-realism tool, not a detection-evasion guarantee.

## Project layout

```
humanpc/
├── bot.py            # sync facade (the public API)
├── hil/              # Human Interaction Layer
│   ├── mouse/        # Bézier, Sigma-Lognormal velocity, pink/tremor noise, overshoot
│   ├── typing/       # speed, dwell, digraph, typos, shift
│   ├── timing.py     # fixation reading + Hick–Hyman
│   ├── session.py    # warm-up / fatigue / distraction
│   ├── individual.py # sampled persona + AR(1) tempo
│   ├── scroll.py · idle.py · behavior.py · precise.py
├── targeting/        # UIA → OCR → template → coordinates resolver
├── perception/       # screenshot, OCR, pixels, DPI / monitors
├── input/            # pluggable drivers (pyautogui / native SendInput)
├── windows/ · system/  # window/app management; clipboard, shell
├── flows/            # YAML flow runner, record/replay
├── safety/           # kill-switch, dry-run, limits, audit log
├── validation.py     # realism feature extraction & scoring
└── cli.py · server/  # CLI, HTTP + MCP tool server

winval/               # (repo root) Windows validation & realism harness scripts
examples/ · tests/    # runnable examples; full test suite
```

# humanpc — Human-Realism Gap Analysis

> An exhaustive, code-grounded audit of everything `humanpc` (v0.1.0, commit `0e1a3d2`) is
> missing in its attempt to make automated input indistinguishable from a real human.
>
> Scope: this focuses on **behavioral / human-realism fidelity** and the **input-provenance
> layer** that determines whether the bot is detectable, plus a section on functional gaps.
> It is written against the actual source in `humanpc/hil/`, `humanpc/input/`, `humanpc/bot.py`,
> and `humanpc/config.py`.

---

## Table of contents

1. [How human interaction actually works (the reference model)](#1-how-human-interaction-actually-works)
2. [What humanpc already does well](#2-what-humanpc-already-does-well)
3. [The core thesis: where the realism breaks](#3-the-core-thesis)
4. [Tier 0 — Provenance: the tells that make curve quality irrelevant](#tier-0--provenance)
5. [Tier 1 — Mouse / motor-signal fidelity](#tier-1--mouse--motor-signal-fidelity)
6. [Tier 2 — Typing fidelity](#tier-2--typing-fidelity)
7. [Tier 3 — Cognition & temporal realism](#tier-3--cognition--temporal-realism)
8. [Tier 4 — Variability & individuality (the deepest flaw)](#tier-4--variability--individuality)
9. [Tier 5 — Scroll, click & other input modalities](#tier-5--scroll-click--other-modalities)
10. [Tier 6 — Validation methodology](#tier-6--validation-methodology)
11. [Tier 7 — Functional / capability gaps](#tier-7--functional--capability-gaps)
12. [Prioritized roadmap to close the gaps](#prioritized-roadmap)

---

## 1. How human interaction actually works

The reference models that detection systems measure against. Each gap below is a deviation
from one of these.

### Mouse / pointing — motor control
- **Fitts's Law (1954):** movement *time* ≈ `a + b·log₂(2D/W)`. Describes duration, not shape. *(humanpc implements this.)*
- **Two-component / optimized-submovement model (Woodworth 1899; Meyer et al. 1988):** a reach is a fast **ballistic** phase (~90%, open-loop) followed by **one or more visually-guided corrective submovements**. Precise targets get more submovements.
- **Asymmetric velocity profile:** bell-shaped but **right-skewed** — short acceleration, long deceleration/homing. Minimum-jerk (Flash & Hogan 1985) predicts a symmetric bell; real data skews right.
- **2/3 Power Law (Viviani & Terzuolo 1983):** on curves, speed couples to curvature, `v ∝ R^(1/3)` — you slow into bends, speed up on straights.
- **Colored motor noise:** physiological tremor (8–12 Hz) plus **1/f "pink" noise**. Human jitter is autocorrelated; its power spectrum is *not* flat.
- **Pointer ballistics:** the OS applies a non-linear acceleration transfer function to *relative* mouse deltas; hardware reports at a fixed polling rate (125–1000 Hz).

### Keyboard — keystroke dynamics (a biometric field)
- **Dwell time:** how long each key is *held* (~60–150 ms; varies by finger/key).
- **Flight time:** interval between keys; depends heavily on the **specific digraph** (same-finger pairs slow, alternating-hand pairs fast).
- **Rollover:** fast typists press the next key *before releasing* the previous one (overlapping events).
- **Error structure:** dominated by **transpositions** (`the→teh`), **doublings**, **omissions**; often noticed *several characters late*.
- **Inter-key intervals are lognormal / heavy-tailed**, not Gaussian; typing comes in **bursts and hesitations**.

### Perception & cognition — timing
- **Reading** is non-linear: fixations (~200–250 ms), saccades, ~10–15% **regressions**, function-word skipping; scanning a UI ≠ reading prose.
- **Hick–Hyman Law:** decision time grows with `log₂(choices+1)`.
- **Warm-up + fatigue + vigilance decrement:** people start slow, speed up, then degrade over a session; error rate rises with time-on-task.
- **Stable individual signature:** each person has a *consistent* personal profile (their WPM, curve bias, error rate) that's stable within/across sessions but differs between people. This consistency is itself a fingerprint.

---

## 2. What humanpc already does well

Credit where due — the **macro-behavior** layer is genuinely thoughtful and clean:

| Feature | Where | Notes |
|---|---|---|
| Fitts-law movement time | `hil/mouse/velocity.py` | `MT = a + b·log₂(2D/W+1)`, with Gaussian variance |
| C-shaped (not S) Bézier paths | `hil/mouse/bezier.py` | Both control points pushed to the same side — a good detail |
| Accel/cruise/decel via eased sampling | `hil/mouse/engine.py` | Sampling the curve at eased params yields a velocity profile for free |
| Speed-scaled jitter | `hil/mouse/jitter.py` | Endpoints never perturbed (lands exactly on target) |
| Overshoot-and-correct | `hil/mouse/overshoot.py` | 35% on moves >180px |
| **Idle cursor drift** | `hil/idle.py` | Daemon thread nudges the cursor while idle — a frozen cursor is a classic tell, so this is a strong instinct |
| Word/sentence/paragraph thinking pauses | `hil/typing/pause.py` | Pause depends on the boundary just crossed |
| Bigram / common-word speed modulation | `hil/typing/speed.py` | Faster on common words and frequent bigrams |
| **Mouse click dwell** | `bot.py:217-219` + `config.py` | `mouse_down → sleep(click_dwell) → mouse_up`, persona-tuned |
| Persona presets | `config.py` | `default / fast / careful / tired` speed profiles |
| Behavioral state machine | `hil/behavior.py` | Observability + optional strict transition validation |
| Safety: kill-switch, dry-run, audit | `safety/` | Solid engineering, not realism but worth noting |
| Seedable determinism | `config.py` (`seed`) | Reproducible for tests |

**The pattern:** almost all of this operates at the **shape-of-motion** level. The gaps are below it (signal fidelity, provenance) and around it (cognition, individuality).

---

## 3. The core thesis

> humanpc convincingly answers **"what shape does a human action take?"** It largely ignores
> **(a)** the *micro-signal* fidelity of that motion, **(b)** the *cognitive coupling* between
> content and timing, **(c)** *individual consistency* (a stable persona), and most critically
> **(d)** the *kernel-level provenance* of the input.
>
> Against a naive logger it looks great. Against keystroke-dynamics biometrics, a trajectory
> classifier, or a one-line "was this input injected?" check, it is transparent.

---

## Tier 0 — Provenance

**These defeat the entire premise, because they are checked _before_ anyone inspects trajectory quality.** Fix these first; everything else is cosmetic until they're done.

> **Implementation status (Unreleased):** 0.2 (keystroke dwell) and 0.3 (timer
> resolution) are **implemented**; 0.4 (relative motion) is **implemented, opt-in,
> pending Windows validation**; 0.1 (injected flag) is **not software-fixable** — the
> driver seam + `extra_info` tag are in place, but real masking needs a kernel/hardware
> HID backend. See `CHANGELOG.md`.

### 0.1 Injected-input flag (the single biggest gap)
`SendInputDriver` calls `SendInput` with `dwExtraInfo = None` (`input/sendinput_driver.py`).
Every event therefore carries the kernel **`LLMHF_INJECTED` / `LLKHF_INJECTED`** flag. Any
low-level hook (`WH_MOUSE_LL` / `WH_KEYBOARD_LL`) or `GetMessageExtraInfo()` reads this as a
boolean "this is synthetic." Anti-cheat and serious anti-bot stacks check it **first**. No
amount of Bézier realism survives a one-bit `injected = true`.
- **Fix:** kernel-mode driver, a hardware HID emulator (Pi Pico / Arduino / "KMBox"-style), or an interception driver (e.g. Interception by oblitum). All of humanpc is pure user-mode `SendInput`.

### 0.2 Zero keystroke dwell time
`write_char` injects a Unicode key as a **down+up pair with no interval** (`sendinput_driver.py`,
`write_char`). Dwell ≈ 0 ms. Keystroke-biometric systems measure dwell on *every* key; a
constant-zero hold is unmistakably non-human. *(Note: mouse-click dwell **is** modeled —
`bot.py:218` — but keystrokes are not.)*
- **Fix:** split typing into `key_down → hold(dwell) → key_up` with per-key/per-finger dwell distributions instead of atomic `write_char`.

### 0.3 Timer-quantized timing
The engines compute sub-frame dts (e.g. 8–10 ms), but realizing them via `time.sleep`
(`bot.py:177`) is bounded by Windows' scheduler tick (~15.6 ms default unless
`timeBeginPeriod` is set). Actual emitted intervals quantize into a non-human **comb** in the
timing histogram. `INPUT.time` is also left `0`.
- **Fix:** raise timer resolution (`timeBeginPeriod(1)`), or drive timing from a high-resolution busy-wait, and validate the emitted (not planned) interval distribution.

### 0.4 Absolute positioning bypasses pointer ballistics
Moves use `MOUSEEVENTF_ABSOLUTE | VIRTUALDESK` to normalized coordinates
(`sendinput_driver.py`, `move`). Real mice send **relative deltas through the OS acceleration
curve** and produce natural `WM_INPUT` raw-input streams. Apps reading Raw Input see an
unnatural absolute pattern with no acceleration signature.
- **Fix:** emit relative deltas and let pointer ballistics shape them; model the device polling rate.

---

## Tier 1 — Mouse / motor-signal fidelity

### 1.1 White-noise jitter
`JitterInjector` adds IID `rng.gauss(0, amp)` per step (`hil/mouse/jitter.py`) — a **flat power
spectrum**. Humans have colored 1/f + tremor noise. A simple FFT or autocorrelation of the
path separates them instantly. *This is the most common giveaway in synthetic-trace classifiers.*
- **Fix:** generate jitter as a 1/f (pink) process plus a narrowband 8–12 Hz tremor; make it autocorrelated, not per-step independent.

### 1.2 Symmetric velocity profile
`ease_in_out_cubic` (`hil/mouse/velocity.py`) is symmetric; real reaches are **right-skewed**
(short accel, long decel/homing). The accel/decel ratio is a known classifier feature.
- **Fix:** use an asymmetric easing (or a minimum-jerk profile skewed toward longer deceleration).

### 1.3 No corrective submovements
`OvershootSimulator` does a single past-then-snap-back (`hil/mouse/overshoot.py`). Real homing
shows **multiple small corrective submovements**; the velocity trace has secondary peaks
humanpc never produces.
- **Fix:** model 1–3 decaying submovements near the target, with probability scaling with required precision (target width).

### 1.4 2/3 Power-Law violation
Velocity comes purely from arc-position easing, **independent of local curvature**
(`hil/mouse/engine.py` samples the curve by eased parameter only). Humans slow on tight parts
of a curve.
- **Fix:** modulate per-segment dt by local radius of curvature (`v ∝ R^(1/3)`).

### 1.5 Integer-pixel output, no device-resolution structure
Steps are emitted at integer pixels with no sub-pixel accumulation, polling-rate cadence, or
sensor-quantization signature.
- **Fix:** model a device resolution/CPI and polling interval; accumulate sub-pixel residue.

### 1.6 No post-landing settle
After arriving, the cursor is dead-still until the click. Humans show tiny settle/correction
micromovements between landing and clicking, and sometimes click *while still micro-adjusting*.
- **Fix:** add a short settle phase with residual micro-jitter before `mouse_down`.

---

## Tier 2 — Typing fidelity

### 2.1 No key-hold modeling (see 0.2) and no rollover
The `KeyEvent` model (`hil/typing/engine.py`) has only a single `delay` *before* the event and
emits atomic `"char"` events — keys never overlap. Real fast typing **overlaps constantly**
(next key down before previous up).
- **Fix:** model dwell + flight separately and allow overlapping down/up events (rollover).

### 2.2 No shift / modifier dynamics
Unicode injection (`write_char`) means capitals and symbols never involve a held **Shift**;
there is no modifier-overlap timing.
- **Fix:** type capitals as `shift_down → key → shift_up` with realistic overlap, instead of Unicode codepoints.

### 2.3 Impoverished error model
`ErrorModel` (`hil/typing/errors.py`) does only **substitution + insertion**, both deliberately
engineered to be **1-backspace reversible**, and only on alphabetic chars. Missing:
- **Transpositions** (`the→teh`) — the single most common real typo
- **Doublings** and **omissions**
- The realistic **"type several more chars, _then_ notice and backspace a whole word"** pattern (correction latency is a fixed small range, not content-dependent)
- **Fix:** add transposition/doubling/omission classes and a delayed-noticing model where the error is caught N chars later.

### 2.4 Wrong inter-key distribution
Per-char delay (`hil/typing/speed.py`) is Gaussian-ish; humans are **lognormal / heavy-tailed**.
The "bigram boost" is flat set membership (`COMMON_BIGRAMS`) — there's no **same-finger vs
alternating-hand** structure, no per-digraph latency.
- **Fix:** sample inter-key intervals from a lognormal, parameterized per-digraph by hand/finger assignment.

### 2.5 Fatigue resets every action
`delay *= fatigue_factor ** typed_count` where `typed_count` is the **character index within
the current `type()` call** (`hil/typing/speed.py` + `engine.py`'s `enumerate(text)`). Every new
typing action restarts at `i=0`, so fatigue **resets between tasks** and never accumulates over a
session.
- **Fix:** move fatigue to a session-level accumulator on the Bot (see Tier 4).

---

## Tier 3 — Cognition & temporal realism

### 3.1 Naive reading model
`reading_delay` (`hil/timing.py`) is **linear in character count**. No fixation/saccade
granularity, no regressions, no UI-scan-vs-prose distinction, no familiarity effect.
- **Fix:** model fixations + regressions; make scanning a known UI much faster than reading novel prose.

### 3.2 No Hick–Hyman decision timing
`thinking_delay` is a 4-bucket enum (`low/medium/high/very_high`, `hil/timing.py`), not a
function of the number of on-screen choices.
- **Fix:** scale decision time with `log₂(n_choices+1)`.

### 3.3 No warm-up, no session fatigue, no distraction
There is no session-level alertness arc, no warm-up speed-up, no vigilance decrement, no
rising error rate over time, no mid-task pauses / task-switching / distraction.
- **Fix:** a session clock that warms up over the first minute, then degrades; couple it to speed *and* error rate.

### 3.4 Decision-cadence tell (agent/MCP use case)
For the agent-callable path, an LLM "perceives" the screen instantly and acts with superhuman
consistency. Genuine reading/decision times **correlate with content difficulty**; the bot's
don't unless explicitly modeled.
- **Fix:** inject content-difficulty-coupled latency between perception and action at the orchestration layer.

---

## Tier 4 — Variability & individuality

**This is the deepest flaw.** "Randomness" hides three different things that humanpc collapses,
and it gets the statistics *backwards*.

### The three levels of variation

| Level | What it is | Real human | humanpc |
|---|---|---|---|
| **1. Between people** (inter-individual) | Stable traits — your WPM, curve bias, error rate | **High** variance; each person **fixed** | **Almost none** — 4 discrete presets, identical instances |
| **2. Between sessions / over time** | Tired vs fresh, warmed-up vs cold | Slow drift around *your* baseline | **None** — no session state |
| **3. Between actions** (trial-to-trial) | Same click done twice differs | **Low** + **autocorrelated** (you stay in a rhythm) | **High** + **IID** (every action independent) |

> humanpc is **backwards on both ends**: real humans have *high* between-person variance but
> *low, structured* within-person variance. humanpc has *near-zero* between-instance variance
> and *high, unstructured* within-instance variance. It is simultaneously **too clone-like across
> bots** and **too twitchy-random inside one bot**.

### 4.1 The persona system is a speed dial, not an identity
`Persona` (`config.py`) has only 4 presets (`default/fast/careful/tired`) and only 4 knobs:
`speed_multiplier`, `move_duration`, `click_dwell`, `type_cps`. Critically:
- It does **not** parameterize the HIL micro-distributions — `curve_strength`, `jitter`,
  `error_probability`, `overshoot`, the bigram model, etc. all remain **fixed global constants**
  regardless of persona. *The config docstring admits this:* "Persona fields here are deliberately
  simple placeholders… personas will then tune those richer parameters instead." **That coupling
  isn't built yet.**
- Personas are **frozen, discrete categories**, not draws from a population. Two `"fast"` bots are
  byte-identical. There is no per-instance individuality.

### 4.2 Variance ≠ identity
The variance knobs (`speed_variance=0.15`, `control_variance=0.2`, `wpm_std=10`, jitter base
`0.6`, `error_probability=0.05`…) are fixed constants **and so are the means**. Adding Gaussian
noise around a fixed mean doesn't create different people — it creates **one average person who
is a bit noisy**, re-rolled every action. Spin up 1,000 humanpc bots and you get the *same
statistical person sampled 1,000 times*, not 1,000 people. A detector fingerprinting a
population sees suspicious clustering.

### 4.3 No carryover / no autocorrelation between actions
Every mouse move, keystroke, and pause is an **independent draw** from the same global
distribution — white noise. Real human variation is an **autocorrelated process**: if your last
three clicks were fast, your next is probably fast (you're in a "fast mode"); fatigue, focus,
and tempo persist and drift slowly. A time-series detector measuring autocorrelation of
inter-action timing sees a human as a slow-drifting mean and a bot as a flat, memoryless one.
(Compounded by 2.5 — even the one stateful thing, fatigue, resets per action.)

### Fix: a three-level hierarchical model with memory
1. **Persona (sampled once, persisted).** Draw a trait vector — `base_wpm`, `curve_bias`,
   `jitter_scale`, `error_rate`, `overshoot_tendency`, `reaction_time` — from a *population*
   distribution and reuse it for every action.
   - Traits must be **correlated**, not independent (a 90-WPM typist with a 15% error rate is
     impossible). Get the population shapes right (WPM ≈ normal with a long right tail; error
     rate lognormal; etc.), calibrated to real data.
2. **Session state (slow drift).** A warm-up→fatigue alertness clock that **accumulates across
   actions** (the opposite of 2.5), modulating speed and error rate.
3. **Action-level autocorrelation.** Replace IID draws with an **AR(1) / random-walk "tempo"** so
   the bot stays in fast/slow/sloppy streaks instead of re-rolling from scratch each time.

---

## Tier 5 — Scroll, click & other modalities

### 5.1 Scroll has no momentum or reading coupling
`plan_scroll` (`hil/scroll.py`) emits uniform random bursts of 2–5 clicks. Missing: trackpad
**inertia/momentum** (fling-and-decay), **scroll-overshoot-then-back**, **reading-coupled**
scrolling (scroll, pause to read, scroll), and horizontal scroll.
- **Fix:** model momentum decay and couple scroll cadence to reading_delay of revealed content.

### 5.2 Missing input modalities entirely
No human modeling for: **drag-and-drop** (press, move-with-held-button dynamics, release),
**multi-select** (shift/ctrl-click sequences), **double/triple-click cadence**, **keyboard
navigation** (Tab/arrow traversal), **right-click + context-menu** timing, touch/pen/multi-touch,
or gamepad input.

### 5.3 No "parking" / between-action cursor behavior
No model for where the cursor rests between actions, following text while reading, or moving to
a neutral spot. Only idle drift exists.

---

## Tier 6 — Validation methodology

### 6.1 Parameters are hand-tuned guesses, not fit to data
Every constant (`curve_strength 0.3`, jitter `0.6`, `error_probability 0.05`, `fatigue 1.0004`,
Fitts `a=0.1 b=0.2`) is a plausible guess, not calibrated against a corpus of real mouse /
keystroke recordings.

### 6.2 Realism is asserted, never measured adversarially
The proper test: record real human traces, train a classifier, and show it **cannot** separate
generated from real (or measure KS-distance on velocity / inter-key-interval / dwell
distributions). The blueprint lists "Success Criteria" but there is no statistical
indistinguishability test in the repo. **Make "a classifier can't tell" the success metric, not
"it looks smooth."**

### 6.3 Gaussian-everything
Nearly every distribution is Gaussian (`rng.gauss`). Real human signals are non-Gaussian
(lognormal intervals, heavy tails, colored noise). Uniform Gaussianity is itself a signature.

---

## Tier 7 — Functional / capability gaps

Not realism, but "things the app misses" as an automation framework:

- **Windows-only realism path.** `SendInputDriver`, UIA targeting, and `win32_backend` are
  Windows-specific. There is no macOS (CGEvent / AX API) or Linux (X11/Wayland, AT-SPI)
  equivalent — so on a Mac the human-input layer doesn't run natively at all.
- **No action verification.** After a click/type, nothing confirms the effect (did the field
  receive the text? did the button actually fire?). No post-condition checks or self-healing on
  failure.
- **Window-relative targeting.** Absolute screen coordinates break if a window moves or resizes
  mid-flow; no robust window-relative coordinate system.
- **Targeting brittleness.** OCR (`targeting/ocr.py`) and template matching (`targeting/template.py`)
  are fragile to theme/DPI/scale/animation changes; no semantic or vision-LLM targeting fallback,
  no "wait for animation/settle" before acting.
- **No learning from real sessions.** `flows/record.py` records macros for replay, but nothing
  ingests real human recordings to *calibrate* the HIL distributions (ties back to 6.1).
- **Concurrency.** Beyond the idle daemon thread, no model for the bot handling async UI events
  (dialogs, focus steals) the way a human would react to them.

---

## Prioritized roadmap

Ordered by **return on realism per unit effort**:

1. **Tier 0 first — it's load-bearing.** Defeat/avoid the injected-input flag (interception driver
   or hardware HID), add real keystroke dwell, and fix timer quantization. *Until this is done, all
   curve work is downstream of a one-bit tell.*
2. **Tier 1.1 + 1.2 + 1.3** — swap white noise for 1/f + tremor, make velocity right-skewed, add
   corrective submovements. These are the highest-signal trajectory features.
3. **Tier 2.1 + 2.3 + 2.4** — keystroke dwell + digraph-specific flight + rollover + transposition
   errors. This is what keystroke-biometric systems actually measure.
4. **Tier 4 — the hierarchical persona model.** A persisted, population-sampled, correlated-trait
   persona + session drift + AR(1) action tempo. Fixes the "all bots are clones / each bot is
   memoryless" paradox.
5. **Tier 6 — close the loop with data.** Record real traces, calibrate the parameters, and gate
   releases on an adversarial discriminator that can't separate generated from human.

> **Bottom line:** humanpc is a well-engineered *macro-behavior* simulator. To become an actual
> *human-indistinguishable* layer it needs (in order) correct input **provenance**, correct
> motor/keystroke **micro-signals**, a stable **individual persona with memory**, and
> **data-driven validation**. The architecture is clean enough that these can be added at the
> seams it already exposes.

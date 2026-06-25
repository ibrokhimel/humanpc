# winval — Windows validation & realism harness

Standalone scripts that exercise the Windows-only input paths and score the
generated movement the way a mouse-dynamics detector would. They drive **real**
`SendInput` and capture the result with low-level `WH_KEYBOARD_LL` / `WH_MOUSE_LL`
hooks, so they require an **interactive Windows desktop** (a headless / locked /
RDP-without-console session won't deliver injected input — see `val_desktop_probe.py`).

Run with the project venv, e.g.:

```
.venv\Scripts\python winval\val_detector.py            # score relative-mode realism
.venv\Scripts\python winval\val_detector.py --absolute # score absolute-mode realism
.venv\Scripts\python winval\demo_moves.py              # watch the cursor feel
```

## Realism scoring
- **`val_detector.py`** — captures real trajectories, scores them against human
  reference ranges (velocity skew/peak, deceleration, straightness, direction
  changes, 8–12 Hz tremor, sample entropy) and against naive-bot baselines.
  Uses `humanpc.validation`. `--absolute` flips the mode.
- **`val_velocity_profile.py`** — measures where peak velocity occurs (~40–50% for
  the Sigma-Lognormal model) and the accel/decel split.
- **`val_relative_feel.py`** — per-move curve / overshoot / micro-pause / glitch
  metrics for relative mode.
- **`val_path_capture.py`** — absolute vs relative path, with timing cadence.
- **`val_end_glitch.py`** — dumps the tail of a move to inspect the landing.
- **`demo_moves.py`** — a watchable tour of both modes.

## Tier-0 / provenance validations (A–F from the original brief)
- **`winhook.py`** — shared low-level keyboard+mouse capture harness.
- **`val_a2_smoke.py`** — Notepad smoke test, reads typed text back from disk (A).
- **`val_bcf.py`** — keystroke dwell (B), Shift dynamics (C), injected-flag (F),
  via the LL hooks.
- **`val_bc_boundary.py` / `val_a_boundary.py`** — boundary-level B/C/A checks that
  run even when the session can't deliver injected input.
- **`val_d_timer.py`** — `timeBeginPeriod(1)` + `precise_sleep` accuracy (D).
- **`val_e_relmouse.py`** — relative-mouse landing accuracy (E).
- **`val_desktop_probe.py`** — diagnoses whether this session is interactive enough
  to inject input at all.

> These are validation runners, not part of the shipped package; the reusable
> scoring logic lives in `humanpc/validation.py` (with unit tests).

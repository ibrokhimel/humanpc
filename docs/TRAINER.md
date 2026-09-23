# Movement trainer

Records genuine human mouse input as training data for a learned movement model.
Code: [`humanpc/learn/`](../humanpc/learn/). Tests: [`tests/test_learn.py`](../tests/test_learn.py).

## Commands

| Command | What it does |
|---|---|
| `humanpc trainer [--person NAME] [--minutes 10] [--data-dir DIR]` | Fullscreen task app; records while tasks are on screen |
| `humanpc trainer-stats [--person NAME] [--json]` | Report: totals, coverage per category, humanness estimate, per-person table |
| `humanpc trainer-export OUT.zip [--person NAME]` | Bundle one person's sessions into a zip |
| `humanpc trainer-import ZIP... [--person NAME]` | Validate and unpack zips into `<data-dir>/<person>/` |
| `python scripts/build_trainer_exe.py` | Build `dist/HumanpcTrainer.exe` for machines without Python |

Data dir: `~/.humanpc/training` (override with `--data-dir` or `HUMANPC_TRAINING_DIR`).
Your own sessions live at the root; other people get subfolders.

Controls: **Space** start/resume · **Esc** pause · **S** skip · **Q** save & quit (on a pause screen).

## Tasks

| Kind | Prompt | Trains |
|---|---|---|
| `point` | Click the start dot, then the target (5–90 px radius, log-uniform distance) | Aiming, Fitts' law, overshoot |
| `double` / `right` | Same, with a double / right click | Click timing |
| `drag` | Drag a box into a zone | Movement with a button held |
| `scroll` | Scroll the red line into the band and stop | Scroll bursts, overshoot, settle |
| `scroll_click` | Scroll, then click the dot on the line | Scroll → aim transitions |
| `trace` | Hover along a curved path | Steady tracking |
| `read` | Read a paragraph; click Done when it appears | Idle drift / fidgeting |
| `chain` | Click 3–6 numbered dots in order | Movement-to-movement flow |

Kinds are sampled by weight (`tasks.DEFAULT_WEIGHTS`). Drop a `task_weights.json`
such as `{"scroll": 4}` into the data dir to ask for more of a kind.

## Recording

- `WH_MOUSE_LL` on a dedicated thread; events are `(t_ns, type, x, y, button, wheel)`.
- Events flagged `LLMHF_INJECTED` / `LLMHF_LOWER_IL_INJECTED` are dropped (counted in
  `meta.injected_dropped`), so humanpc's own output never pollutes the dataset.
- Recording runs only while tasks are on screen. Leaving the window (Alt+Tab, clicking
  elsewhere) pauses — so nothing outside the trainer is captured.
- Saves: every 15 tasks, on pause/break/focus loss, on quit, and on a crash.

## Data format

Each session is two files with the same stem, `session_YYYYMMDD_HHMMSS`:

**`.npz`** — compressed columns, delta-encoded in the narrowest integer type:

| Column | Meaning |
|---|---|
| `dt_us` | microseconds since previous event (first: since session start) |
| `type` | 0 move · 1 down · 2 up · 3 wheel · 4 hwheel |
| `x0`, `y0` | first event's absolute position |
| `dx`, `dy` | position delta from previous event (screen px) |
| `button` | 0 none · 1 left · 2 right · 3 middle |
| `wheel` | wheel delta (±120 per notch; smaller on touchpads) |

`dataset.load_session(stem)` returns absolute `t_us, type, x, y, button, wheel`.

**`.json`** — `{"meta": {...}, "tasks": [...]}`. Each task:

```json
{"kind": "point", "params": {"start": [412, 300], "start_r": 16, "target": [1210, 655], "r": 12.4},
 "t_shown_us": 1834022, "t_start_us": 2410331, "t_end_us": 3301877, "errors": 0, "result": "ok"}
```

Task coordinates are window pixels (`meta.window_origin` converts to screen; the window
is fullscreen at the origin). Scroll tasks move 100 px per notch (`meta.scroll_step_px`).
`meta` also records `person`, `screen`, `dpi_mode`, and `mouse` (Windows pointer speed and
whether "Enhance pointer precision" is on).

**Export zip** — `manifest.json` (`format: "humanpc-mousedata"`, person, session list) plus
the session files at the zip root. Import accepts only `session_YYYYMMDD_HHMMSS.{npz,json}`
members, requires both halves of each session, checks the npz columns and sidecar parse,
caps sizes, and skips sessions that already exist.

## Humanness estimate

`trainer-stats` estimates how indistinguishable a model trained on the data *would* be
(100% = a detector trained on the real person does no better than chance). It is a
heuristic (`learn/report.py`), not a measurement:

- Each category fills with diminishing returns, `1 − exp(−n / n0)`:
  aiming (n0 = 2500), scroll (700), idle seconds (2400), double/right clicks (600),
  drags (500), traces (300).
- Weighted 40 / 20 / 15 / 10 / 10 / 5 %, and capped at **80%** — data alone never reaches
  100%; model quality, landing correction and injection timing leave traces.
- Below 300 aiming movements it reports "not enough data to train".
- Calibrated so a balanced ~1 h dataset ≈ 17%, ~10 h ≈ 65–70%.

It will be replaced by a real detector score once the training pipeline exists.

## Multiple people

Pooling everyone into one model without identity learns an *average* person, which is
blurrier and easier to detect than any real one. The intended setup is one model with a
per-person style embedding: shared structure comes from everyone, quirks from each
person, and styles can be picked or blended at generation time. Record only people who
know what is collected and why.

## Standalone exe notes

- Built with PyInstaller (`--onefile --windowed`), ~24 MB; heavy optional deps are excluded.
- Data on that machine: `%LOCALAPPDATA%\humanpc-trainer\<name>\`; the zip is
  `Desktop\mousedata_<name>.zip` (follows OneDrive Desktop redirection).
- Unsigned: SmartScreen shows "More info → Run anyway". Some antivirus tools may flag a
  PyInstaller app with a global mouse hook; that is a false positive.
- Errors are logged to `%LOCALAPPDATA%\humanpc-trainer\trainer_error.log`.

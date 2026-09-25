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

`trainer-stats` shows the real detector score next to it once a model has been trained.

## Training the model

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128   # GPU build (CUDA 12.8)
humanpc train-model                  # trains on everything, then runs the detector
humanpc train-model --watch          # same, with a live window of the best model so far
humanpc eval-model                   # re-run just the detector on the saved model
```

Options: `--epochs` (upper limit, default 1000; it stops by itself after 15 epochs without
improvement, usually after a few hundred), `--watch`,
`--size auto|small|base|large` (auto picks by data volume; bigger overfits small datasets),
`--batch-tokens` (lower it if the GPU runs out of memory), `--cpu`, `--no-eval`.
Output: `<data-dir>/model/model.pt`, `train_log.json`, `metrics.json`.

`--watch` opens a window while it trains. Each time a new best model is saved, the window
gives it the same 8 fixed tasks (clicks, double-clicks, a right-click, a drag) and replays
its raw output (no landing fix), next to a loss chart and each best model's task score.
Closing the window stops training; the best model so far is kept.

Speed: the whole dataset is kept on the GPU (up to 4M steps), so an epoch of ~1 hour of
data takes under a second on an RTX 3060; a full run plus the detector is 2-3 minutes.

**Data prep** (`learn/ml/segments.py`, numpy only). Each task becomes goal-directed
*segments*: a point task gives two (reach the start dot, reach the target), a chain one per
dot, plus drag, scroll, scroll-click and read/idle segments. Events are binned into 10 ms
steps in a frame rotated so the target lies on +x. A terminal "stop" step follows the last event.

**Model** (`learn/ml/model.py`). Causal Transformer; condition (kind, distance, direction,
target size, scroll amount) and a per-person embedding are added to every step. Per step it
predicts *moved?*, a Gaussian mixture over (dx, dy), click class, wheel notches and stop.
Inputs are the previous step plus state: vector still to go, distance to go in target radii,
elapsed time, buttons held, scroll still to go, velocity over the last 50 ms, time-to-contact
with the target, time spent inside the target and time since the cursor last moved.
During training the previous-step and velocity inputs are jittered (`HISTORY_NOISE = 0.25`).
Without it the model learns to copy momentum from the person's real steps; generating, it
copies its own slightly-off steps, errors compound, and it arrives too fast, overshoots and
fidgets near the target (measured: worst-10% overshoot 54 px vs the person's 14). With the
jitter it steers by position and distance instead (16 px). Models trained before this
change must be retrained (loading one says so). Training uses bf16 autocast, AdamW with
warmup then halving the learning rate after 5 epochs without improvement, and top-bottom mirror augmentation. There is no step-index embedding: with
little data it made the model memorise by position instead of steering to the target.

**Generation** (`learn/ml/generate.py`). Batched sampling with a preallocated KV cache;
finished movements are dropped from the batch so one slow path doesn't hold up the rest.
**Guard:** a few % of free-running paths reach states no recording covers (e.g. far past the
target) and never recover. Training saves the person's *envelope* (99th percentile of
overshoot and sideways excursion per movement kind) in `model.pt`; `MovementGenerator.move`,
the demo, `--watch` and the detector generate 4 candidates and keep a random one inside 1.5x
that envelope. The detector reports how many candidates the guard replaced. Impossible clicks
(releasing an unheld button) are masked out. Click-ending segments stop exactly like the
task does, on the required release inside the target; only plain scrolls use the learned
stop. `MovementGenerator.load(path).move(start, target, radius=...)` returns screen-space
events; `land_on_target` nudges the final 40% of motion so the endpoint lands inside the target.

**Detector** (`learn/ml/detector.py`). For each real movement the model generates one
under the same condition. A bidirectional GRU is trained to tell them apart (3-fold), and
**measured humanness = 2 × (1 − accuracy)**. The report also shows the share of generated
movements that completed their task and real-vs-model medians (duration, straightness, peak
speed, clicks). Per-kind accuracy rewrites `task_weights.json` so the trainer asks for more
of what gets caught. `trainer-stats` shows the measured score next to the estimate.

Reference point: about 10 minutes of recordings (~470 movements) gave 7% measured humanness,
and 55% of generated movements completed their task. That matches the estimate for that much
data: the model is data-limited, not broken.

## Model demo

`humanpc model-demo [--model PATH]` opens a playground window. A fake cursor replays
generated movements at real speed; the bottom bar reports duration, whether the task
finished, and the outcome (last click on/off target, release inside/outside the zone,
line in/out of the band).

| Key | Action |
|---|---|
| 1 / 2 / 3 | click / double-click / right-click (click places the target, wheel sizes it) |
| 4 | drag the box into the zone |
| 5 / 6 | scroll the red line into the band / scroll then click the dot (wheel sets scroll distance) |
| 7 | read (idle drift), then click Done |
| Space / V | random setup / the same action 5 times at once to show variation |
| C / L / Esc | landing correction on-off / live mode (real cursor, clicks stay in the window) / stop-quit |

## Big datasets

- `--max-sessions N` on `train-model` / `eval-model` loads N sessions spread evenly across
  the data. Prepared data costs roughly 45 MB per recorded hour of RAM.
- Batch lengths are rounded up to multiples of 64 so the CUDA caching allocator sees few
  distinct shapes. Without this, fragmentation on a 12 GB card spilled into shared system
  memory (Windows WDDM) and epochs became ~30x slower. `expandable_segments` is not
  available on Windows.
- The detector scores only held-out movements when there are at least 100, so a model
  that memorises its training set gets no credit.
- Reference points: ~470 movements of real data gave 7% humanness and 55% completion. On a
  *synthetic* dataset (explicitly labelled as generator output, not human), ~3,800 movements
  gave 30% and 94%: the pipeline scales with data.

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

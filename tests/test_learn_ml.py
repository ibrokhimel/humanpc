"""Learned movement model: segment extraction, feature/rollout parity, model + generation."""

import math
import random

import pytest

np = pytest.importorskip("numpy")

from humanpc.learn.events import BTN_LEFT, DOWN, MOVE, UP, WHEEL  # noqa: E402
from humanpc.learn.ml.segments import (  # noqa: E402
    BIN_US, COND_DIM, FINISH, IN_DIM, WHEEL_MAX, Rollout, Segment, extract, pack,
)

MS = 1000  # events use microseconds


def _session(n_tasks=6, seed=0):
    """Synthetic session: point tasks performed by a scripted 'hand' + one scroll."""
    rng = random.Random(seed)
    ev, tasks = [], []
    t, x, y = 10_000, 500, 500

    def move_to(tx, ty, dur_ms):
        nonlocal t, x, y
        steps = max(1, dur_ms)
        sx, sy = x, y
        for i in range(1, steps + 1):
            f = 0.5 - 0.5 * math.cos(math.pi * i / steps)
            t += MS
            nx, ny = round(sx + (tx - sx) * f), round(sy + (ty - sy) * f)
            if (nx, ny) != (x, y):
                x, y = nx, ny
                ev.append((t, MOVE, x, y, 0, 0))

    def click():
        nonlocal t
        t += 80 * MS
        ev.append((t, DOWN, x, y, BTN_LEFT, 0))
        t += 90 * MS
        ev.append((t, UP, x, y, BTN_LEFT, 0))
        return t

    for _ in range(n_tasks):
        start = (rng.randint(100, 900), rng.randint(100, 700))
        target = (rng.randint(100, 900), rng.randint(100, 700))
        shown = t + 200 * MS
        t = shown
        move_to(*start, rng.randint(250, 500))
        t_start = click()
        move_to(*target, rng.randint(300, 700))
        t_end = click()
        tasks.append({"kind": "point", "params": {"start": list(start), "start_r": 16, "target": list(target),
                                                  "r": 12}, "t_shown_us": shown, "t_start_us": t_start,
                      "t_end_us": t_end, "errors": 0, "result": "ok"})
    shown = t + 100 * MS
    t = shown
    for _ in range(8):
        t += 40 * MS
        ev.append((t, WHEEL, x, y, 0, -120))
    t += 400 * MS
    tasks.append({"kind": "scroll", "params": {"offset": 0, "line": 1340, "band_y": 540, "band_h": 100,
                                               "content": 20000}, "t_shown_us": shown, "t_start_us": shown,
                  "t_end_us": t, "errors": 0, "result": "ok"})
    arr = np.asarray(ev, dtype=np.int64)
    events = {"t_us": arr[:, 0], "type": arr[:, 1], "x": arr[:, 2], "y": arr[:, 3],
              "button": arr[:, 4], "wheel": arr[:, 5]}
    return events, {"session": "s1", "person": "me", "window_origin": [0, 0]}, tasks


def test_extract_splits_point_tasks_into_two_aims_and_scroll():
    segs = extract(*_session())
    kinds = [s.kind for s in segs]
    assert kinds.count("aim") == 12 and kinds.count("scroll") == 1
    for s in segs:
        a = s.arrays
        assert a["inputs"].shape[1] == IN_DIM and a["cond"].shape == (COND_DIM,)
        assert a["end"][-1] == 1 and a["end"].sum() == 1
        assert len(a["inputs"]) == len(a["click"]) == len(a["moved"])
    aim = next(s for s in segs if s.kind == "aim")
    # the aim ends with a left release, followed by the terminal stop step
    assert aim.arrays["click"][-2] == 2 and aim.arrays["click"][-1] == 0
    # rotated frame: the path heads along +x and lands near the target
    total = aim.arrays["dxdy"][:, 0].sum() * 10
    dist = math.hypot(aim.target[0] - aim.start[0], aim.target[1] - aim.start[1])
    assert abs(total - dist) < 2
    scroll = next(s for s in segs if s.kind == "scroll")
    assert (scroll.arrays["wheel"] - WHEEL_MAX).sum() == -8


def test_rollout_reproduces_training_inputs_exactly():
    for seg in extract(*_session(seed=3)):
        a = seg.arrays
        r = Rollout(seg, seg.start)
        rows = []
        for i in range(len(a["end"])):
            rows.append(r.input())
            r.push(a["dxdy"][i, 0] * 10, a["dxdy"][i, 1] * 10, int(a["click"][i]), int(a["wheel"][i]) - WHEEL_MAX)
        assert np.allclose(np.stack(rows), a["inputs"], atol=1e-3), seg.kind  # float32 vs float64 cumsum


def test_rollout_finishes_only_on_release_inside_target():
    seg = Segment("aim", 0, 0, target=(200.0, 100.0), radius=10)
    r = Rollout(seg, (100.0, 100.0))
    r.push(50, 0, 1, 0)
    r.push(0, 0, 2, 0)  # release 50 px short: a misclick, not the end
    assert not r.finished
    r.push(48, 0, 1, 0)
    r.push(0, 0, 2, 0)
    assert r.finished
    dbl = Rollout(Segment("aim_double", 0, 0, target=(110.0, 100.0), radius=10), (100.0, 100.0))
    dbl.push(10, 0, 1, 0); dbl.push(0, 0, 2, 0)
    assert not dbl.finished
    dbl.push(0, 0, 1, 0); dbl.push(0, 0, 2, 0)
    assert dbl.finished
    assert "scroll" not in FINISH


def test_click_mask_blocks_impossible_clicks():
    r = Rollout(Segment("aim", 0, 0, target=(10.0, 0.0), radius=5), (0.0, 0.0))
    assert r.click_mask() == [True, True, False, True, False]
    r.push(0, 0, 1, 0)
    assert r.click_mask() == [True, False, True, True, False]
    drag = Rollout(Segment("drag", 0, 0, target=(10.0, 0.0), radius=5), (0.0, 0.0))
    assert drag.click_mask()[2]  # a drag starts with the button held


def test_pack_appends_terminal_step():
    seg = Segment("aim", 0, 5 * BIN_US, target=(50.0, 0.0), radius=5)
    a = pack(seg, (0.0, 0.0), np.array([10.0, 20, 20]), np.zeros(3), np.array([0, 1, 2]), np.zeros(3, int))
    assert len(a["end"]) == 4 and a["end"].tolist() == [0, 0, 0, 1]
    assert a["moved"].tolist() == [1, 1, 1, 0]


torch = pytest.importorskip("torch")


def _tiny_model():
    from humanpc.learn.ml.model import ModelConfig, MoveModel
    return MoveModel(ModelConfig(n_people=2, d_model=32, n_layers=2, n_heads=2, mixtures=3, dropout=0.0))


def test_kv_cache_matches_full_forward():
    torch.manual_seed(0)
    m = _tiny_model().eval()
    x, c, p = torch.randn(2, 17, IN_DIM), torch.randn(2, COND_DIM), torch.tensor([0, 1])
    with torch.no_grad():
        full = m(x, c, p)
        cache, ends = m.empty_cache(), []
        for t in range(17):
            o, cache = m(x[:, t:t + 1], c, p, cache=cache, start=t)
            ends.append(o["end"][:, -1])
    assert torch.allclose(full["end"], torch.stack(ends, 1), atol=1e-5)


def test_preallocated_cache_matches_full_forward_and_survives_row_drops():
    torch.manual_seed(0)
    m = _tiny_model().eval()
    x, c, p = torch.randn(3, 17, IN_DIM), torch.randn(3, COND_DIM), torch.tensor([0, 1, 0])
    with torch.no_grad():
        full = m(x, c, p)
        cache, ends = m.empty_cache(3, 32), []
        for t in range(9):
            o, cache = m(x[:, t:t + 1], c, p, cache=cache, start=t)
            ends.append(o["end"][:, -1])
        assert torch.allclose(full["end"][:, :9], torch.stack(ends, 1), atol=1e-5)
        rows = torch.tensor([0, 2])  # row 1 finished: drop it and keep going
        cache, c2, p2 = m.select_cache(cache, rows), c[rows], p[rows]
        for t in range(9, 17):
            o, cache = m(x[rows, t:t + 1], c2, p2, cache=cache, start=t)
            assert torch.allclose(full["end"][rows, t], o["end"][:, -1], atol=1e-5)


def test_training_step_reduces_loss_and_generation_runs(tmp_path):
    from humanpc.learn.ml.generate import MovementGenerator, generate, to_events
    from humanpc.learn.ml.model import load, losses, save
    from humanpc.learn.ml.train import batches

    torch.manual_seed(0)
    segs = extract(*_session(n_tasks=8))
    m = _tiny_model()
    opt = torch.optim.Adam(m.parameters(), 3e-3)
    first = last = None
    for _ in range(40):
        for b in batches(segs, ["me"], 4096, shuffle=True, device="cpu"):
            ls = losses(m(b["inputs"], b["cond"], b["person"]), b)
            opt.zero_grad(); ls["total"].backward(); opt.step()
            first = first if first is not None else float(ls["total"])
            last = float(ls["total"])
    assert last < first

    save(m, tmp_path / "m.pt", people=["me"])
    m2, ck = load(tmp_path / "m.pt")
    assert ck["people"] == ["me"]
    seg = Segment("aim", 0, 0, target=(400.0, 300.0), radius=12)
    g = generate(m2, [(seg, (100.0, 100.0))], [0], max_steps=60)[0]
    assert set(g) >= {"dx", "dy", "click", "wheel", "finished"} and len(g["dx"]) <= 60
    evs = to_events(g, seg, (100.0, 100.0))
    assert all(isinstance(e[2], int) and isinstance(e[3], int) for e in evs)
    gen = MovementGenerator(m2, ["me"])
    assert isinstance(gen.move((10, 10), (300, 200), radius=15), list)


def test_land_on_target_pulls_endpoint_inside_radius():
    from humanpc.learn.ml.generate import land_on_target
    seg = Segment("aim", 0, 0, target=(300.0, 0.0), radius=10)
    g = {"dx": np.full(20, 12.0), "dy": np.full(20, 1.0), "click": np.zeros(20, int), "wheel": np.zeros(20, int)}
    out = land_on_target(g, seg, (0.0, 0.0), random.Random(1))
    assert math.hypot(out["dx"].sum() - 300, out["dy"].sum()) <= 8.01
    assert np.allclose(out["dx"][:10], 12.0)  # early motion untouched


def test_train_reports_every_epoch_and_saves_before_best_callback(tmp_path, monkeypatch):
    from humanpc.learn.ml import train as train_mod

    segs = extract(*_session(n_tasks=12))
    monkeypatch.setattr(train_mod, "load_all", lambda *a, **k: segs)
    seen = []

    def on_epoch(rec, best):
        seen.append((rec["epoch"], best, (tmp_path / "model.pt").exists()))

    summary = train_mod.train(tmp_path, tmp_path, epochs=2, size="small", cpu=True, log=lambda *_: None,
                              on_epoch=on_epoch)
    assert [s[0] for s in seen] == [1, 2]
    assert seen[0][1] and seen[0][2]  # first epoch is always a best, and model.pt is already written
    assert summary["epochs_run"] == 2


def test_watch_exam_is_fixed_and_inside_the_window():
    from humanpc.learn.ml.watch import H, W, exam

    a, b = exam(), exam()
    assert [(s.kind, s.target, st) for s, st in a] == [(s.kind, s.target, st) for s, st in b]
    assert {s.kind for s, _ in a} == {"aim", "aim_double", "aim_right", "drag"}
    for seg, start in a:
        for x, y in (seg.target, start):
            assert 0 < x < W and 0 < y < H


def test_envelope_guard_rejects_runaways_and_unfinished_paths():
    from humanpc.learn.ml.generate import envelope, within_envelope

    segs = extract(*_session(n_tasks=12))
    env = envelope(segs)
    assert "aim" in env and env["aim"]["overshoot_px"] >= 0
    seg, start = Segment("aim", 0, 0, target=(300.0, 0.0), radius=10), (0.0, 0.0)
    clean = {"dx": np.full(30, 10.0), "dy": np.zeros(30), "finished": True}
    runaway = {"dx": np.full(30, 40.0), "dy": np.zeros(30), "finished": True}  # ends 900 px past
    assert within_envelope(clean, seg, start, env)
    assert not within_envelope(runaway, seg, start, env)
    assert not within_envelope({**clean, "finished": False}, seg, start, env)


def test_generate_guarded_returns_one_path_per_job(tmp_path):
    from humanpc.learn.ml.generate import generate_guarded

    m = _tiny_model().eval()
    jobs = [(Segment("aim", 0, 0, target=(200.0, 50.0), radius=12), (0.0, 0.0))] * 3
    paths, rejected = generate_guarded(m, jobs, [0, 0, 0], {}, candidates=2, max_steps=20,
                                       rng=random.Random(0))
    assert len(paths) == 3 and 0.0 <= rejected <= 1.0

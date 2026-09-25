"""Movement trainer: encoding round-trip, task sampling, task rules, storage."""

import random

import pytest

np = pytest.importorskip("numpy")

from humanpc.learn.dataset import SessionWriter, list_sessions, load_session, stats  # noqa: E402
from humanpc.learn.events import BTN_LEFT, BTN_RIGHT, DOWN, MOVE, UP, WHEEL, decode, encode  # noqa: E402
from humanpc.learn.task_runtime import DOUBLE_NS, NS, SCROLL_SETTLE_NS, make_runtime  # noqa: E402
from humanpc.learn.tasks import KINDS, Task, TaskSampler  # noqa: E402

W, H = 1920, 1080
MS = 1_000_000


def _raw(n=500, seed=1):
    rng = random.Random(seed)
    t, x, y, out = 0, 900, 500, []
    for _ in range(n):
        t += rng.randint(900_000, 8_000_000)
        x += rng.randint(-40, 40)
        y += rng.randint(-40, 40)
        typ = rng.choice([MOVE] * 8 + [DOWN, UP, WHEEL])
        out.append((t, typ, x, y, BTN_LEFT if typ in (DOWN, UP) else 0, 120 if typ == WHEEL else 0))
    return out


def test_encode_decode_roundtrip_and_compact_types():
    raw = _raw()
    cols = encode(raw)
    assert cols["dx"].dtype == np.int8 and cols["type"].dtype == np.uint8
    dec = decode(cols)
    arr = np.asarray(raw)
    assert (dec["t_us"] == arr[:, 0] // 1000).all()
    for i, k in enumerate(("type", "x", "y", "button", "wheel"), start=1):
        assert (dec[k] == arr[:, i]).all()


def test_encode_widens_on_large_jumps():
    raw = [(0, MOVE, 0, 0, 0, 0), (10**12, MOVE, 5000, -5000, 0, 0)]
    cols = encode(raw)
    assert cols["dx"].dtype == np.int16 and cols["dt_us"].dtype == np.uint32
    assert decode(cols)["x"][-1] == 5000


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_samples_on_screen(kind):
    s = TaskSampler(W, H, rng=random.Random(3))
    for _ in range(50):
        t = s.make(kind)
        pts = []
        p = t.params
        for key in ("start", "target", "box", "zone", "done"):
            if key in p:
                pts.append(p[key])
        pts += p.get("points", [])
        for x, y in pts:
            assert 0 <= x <= W and 0 <= y <= H, (kind, p)


def test_weights_bias_sampling():
    s = TaskSampler(W, H, rng=random.Random(0), weights={k: 0 for k in KINDS} | {"drag": 1})
    assert {s.sample().kind for _ in range(30)} == {"drag"}
    with pytest.raises(ValueError):
        TaskSampler(W, H, weights={k: 0 for k in KINDS})


def test_point_requires_start_then_target_and_counts_misses():
    t = Task("point", {"start": [100, 100], "start_r": 16, "target": [600, 400], "r": 10})
    rt = make_runtime(t, 0, (W, H))
    rt.press(600, 400, BTN_LEFT, 1)  # target before start: ignored
    rt.release(600, 400, BTN_LEFT, 2)
    assert not rt.done and rt.t_start is None
    rt.press(100, 100, BTN_LEFT, 10)
    rt.release(100, 100, BTN_LEFT, 20)
    assert rt.t_start == 20
    rt.press(700, 400, BTN_LEFT, 30)  # miss
    rt.release(700, 400, BTN_LEFT, 40)
    rt.press(605, 402, BTN_LEFT, 50)
    rt.release(605, 402, BTN_LEFT, 60)
    assert rt.done and rt.errors == 1 and rt.t_end == 60
    rec = rt.record(0)
    assert rec["result"] == "ok" and rec["kind"] == "point"


def test_double_and_right_click_rules():
    base = {"start": [100, 100], "start_r": 16, "target": [600, 400], "r": 20}
    rt = make_runtime(Task("double", dict(base)), 0, (W, H))
    rt.press(100, 100, BTN_LEFT, 0); rt.release(100, 100, BTN_LEFT, 1)
    rt.press(600, 400, BTN_LEFT, 10); rt.release(600, 400, BTN_LEFT, 11)
    assert not rt.done
    later = 11 + DOUBLE_NS + 1  # too slow: restart the pair
    rt.press(600, 400, BTN_LEFT, later); rt.release(600, 400, BTN_LEFT, later + 1)
    assert not rt.done
    rt.press(600, 400, BTN_LEFT, later + 100 * MS); rt.release(600, 400, BTN_LEFT, later + 110 * MS)
    assert rt.done

    rr = make_runtime(Task("right", dict(base)), 0, (W, H))
    rr.press(100, 100, BTN_LEFT, 0); rr.release(100, 100, BTN_LEFT, 1)
    rr.press(600, 400, BTN_LEFT, 2); rr.release(600, 400, BTN_LEFT, 3)
    assert not rr.done and rr.errors == 1
    rr.press(600, 400, BTN_RIGHT, 4); rr.release(600, 400, BTN_RIGHT, 5)
    assert rr.done


def test_drag_into_zone():
    t = Task("drag", {"box": [200, 200], "size": 40, "zone": [800, 500], "zone_size": 100})
    rt = make_runtime(t, 0, (W, H))
    rt.press(205, 205, BTN_LEFT, 1)
    rt.motion(500, 300, 2)
    rt.release(500, 300, BTN_LEFT, 3)
    assert not rt.done and rt.errors == 1
    rt.press(500, 300, BTN_LEFT, 4)
    rt.motion(810, 490, 5)
    rt.release(810, 490, BTN_LEFT, 6)
    assert rt.done and rt.t_start == 1


def test_scroll_settles_in_band_and_scroll_click():
    p = {"offset": 0, "line": 540 + 1000, "band_y": 540, "band_h": 100, "content": 20000}
    rt = make_runtime(Task("scroll", dict(p)), 0, (W, H))
    for i in range(10):  # 10 notches down = 1000 px
        rt.wheel(-120, i * 10 * MS)
    assert rt.in_band()
    rt.tick(90 * MS + SCROLL_SETTLE_NS - 1)
    assert not rt.done
    rt.tick(90 * MS + SCROLL_SETTLE_NS)
    assert rt.done

    rc = make_runtime(Task("scroll_click", dict(p, click_x=300, r=20)), 0, (W, H))
    rc.press(300, 540, BTN_LEFT, 1)  # line not in band yet
    assert rc.errors == 1
    for i in range(10):
        rc.wheel(-120, 2 + i)
    rc.press(300, rc.line_y, BTN_LEFT, 20); rc.release(300, rc.line_y, BTN_LEFT, 21)
    assert rc.done


def test_trace_needs_most_of_path():
    pts = [[100 + 10 * i, 300] for i in range(61)]
    rt = make_runtime(Task("trace", {"points": pts, "width": 30}), 0, (W, H))
    rt.motion(100, 300, 1)
    rt.motion(700, 300, 2)  # jump straight to the end
    assert not rt.done
    for i, (x, y) in enumerate(pts):
        rt.motion(x, y, 3 + i)
    assert rt.done


def test_read_and_chain():
    rt = make_runtime(Task("read", {"text": "hi", "min_seconds": 2, "done": [500, 500]}), 0, (W, H))
    rt.press(500, 500, BTN_LEFT, 1); rt.release(500, 500, BTN_LEFT, 2)
    assert not rt.done
    rt.tick(2 * NS)
    rt.press(500, 500, BTN_LEFT, 2 * NS + 1); rt.release(500, 500, BTN_LEFT, 2 * NS + 2)
    assert rt.done

    ch = make_runtime(Task("chain", {"points": [[100, 100], [400, 100], [400, 400]], "r": 15}), 0, (W, H))
    for i, (x, y) in enumerate([[100, 100], [400, 400], [400, 100], [400, 400]]):
        ch.press(x, y, BTN_LEFT, 10 * i); ch.release(x, y, BTN_LEFT, 10 * i + 1)
    assert ch.done and ch.errors == 1


def test_shapes_render_for_every_kind():
    s = TaskSampler(W, H, rng=random.Random(5))
    for kind in KINDS:
        rt = make_runtime(s.make(kind), 0, (W, H))
        rt.tick(100 * NS)
        assert rt.shapes(), kind


def test_session_save_load_and_stats(tmp_path):
    raw = _raw(200)
    tasks = [{"kind": "point", "params": {}, "result": "ok"}, {"kind": "drag", "params": {}, "result": "skipped"}]
    w = SessionWriter(tmp_path, "session_20260101_000000")
    w.save(raw, tasks, {"events": len(raw), "active_seconds": 12.5})
    w.save(raw, tasks, {"events": len(raw), "active_seconds": 12.5})  # overwrite is atomic + idempotent
    assert list_sessions(tmp_path) == [tmp_path / "session_20260101_000000"]
    ev, meta, tk = load_session(list_sessions(tmp_path)[0])
    assert len(ev["x"]) == 200 and meta["active_seconds"] == 12.5 and len(tk) == 2
    st = stats(tmp_path)
    assert st["sessions"] == 1 and st["tasks"] == 2 and st["tasks_ok"] == 1
    assert st["by_kind"] == {"point": 1, "drag": 1} and st["bytes"] > 0
    assert not list(tmp_path.glob("*.tmp*"))


def test_humanness_estimate_is_monotonic_capped_and_realistic():
    from humanpc.learn.report import CEILING, DEFAULT_RATES, estimate, format_report, summary

    at = lambda h: estimate({c: r * h for c, r in DEFAULT_RATES.items()})  # noqa: E731
    assert estimate({}) == 0
    assert at(0.1) < at(1) < at(5) < at(10) < at(50) <= CEILING * 100
    assert 10 <= at(1) <= 25 and 55 <= at(10) <= 75  # the calibration promised in the docs
    st = {"data_dir": "x", "sessions": 1, "tasks": 3, "tasks_ok": 3, "events": 100,
          "active_seconds": 120.0, "bytes": 2048, "by_kind": {}, "units": {"aim": 30}}
    s = summary(st)
    assert s["verdict"].startswith("Not enough") and s["minutes_to_next"] > 0
    assert "Estimated humanness" in format_report(st, polling_hz=1000)


def test_task_units_counts_by_category():
    from humanpc.learn.dataset import task_units
    assert task_units({"kind": "chain", "params": {"points": [[0, 0]] * 4}, "result": "ok"}) == {"aim": 4}
    assert task_units({"kind": "double", "params": {}, "result": "ok"}) == {"aim": 1, "click": 1}
    assert task_units({"kind": "point", "params": {}, "result": "skipped"}) == {}
    assert task_units({"kind": "read", "params": {}, "result": "ok", "t_shown_us": 0, "t_end_us": 8_000_000}) == {"idle": 8.0}


def _session(folder, name="session_20260101_000000", n=100):
    SessionWriter(folder, name).save(_raw(n), [{"kind": "point", "params": {}, "result": "ok"}],
                                     {"events": n, "active_seconds": 60.0})


def test_export_import_roundtrip_skips_duplicates(tmp_path):
    import zipfile

    from humanpc.learn.transfer import export_zip, import_zip
    src = tmp_path / "other_pc"
    _session(src)
    _session(src, "session_20260101_010000")
    info = export_zip(src, "Alice Smith", tmp_path / "out.zip")
    assert info["sessions"] == 2 and info["person"] == "Alice_Smith"
    with zipfile.ZipFile(tmp_path / "out.zip") as z:
        assert z.getinfo("session_20260101_000000.npz").compress_type == zipfile.ZIP_STORED

    root = tmp_path / "training"
    r1 = import_zip(tmp_path / "out.zip", root)
    assert r1["added"] == 2 and r1["person"] == "Alice_Smith"
    assert import_zip(tmp_path / "out.zip", root)["skipped"] == 2
    ev, _, _ = load_session(root / "Alice_Smith" / "session_20260101_000000")
    assert len(ev["x"]) == 100
    assert stats(root, recursive=True)["sessions"] == 2 and stats(root)["sessions"] == 0


@pytest.mark.parametrize("member", ["../evil.npz", "session_20260101_000000.exe", "sub/session_20260101_000000.json"])
def test_import_rejects_unexpected_members(tmp_path, member):
    import json
    import zipfile

    from humanpc.learn.transfer import FORMAT, import_zip
    zp = tmp_path / "bad.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": FORMAT, "person": "x"}))
        z.writestr(member, b"x")
    with pytest.raises(ValueError):
        import_zip(zp, tmp_path / "root")
    assert not (tmp_path / "root").exists() and not (tmp_path / "evil.npz").exists()


def test_import_rejects_corrupt_and_foreign_zips(tmp_path):
    import json
    import zipfile

    from humanpc.learn.transfer import FORMAT, import_zip
    zp = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": FORMAT, "person": "x"}))
        z.writestr("session_20260101_000000.npz", b"not numpy")
        z.writestr("session_20260101_000000.json", b"{}")
    with pytest.raises(ValueError, match="corrupt"):
        import_zip(zp, tmp_path / "root")
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as z:
        z.writestr("readme.txt", "hi")
    with pytest.raises(ValueError, match="manifest"):
        import_zip(other, tmp_path / "root")


def test_background_exporter_tracks_latest_data(tmp_path):
    import zipfile

    from humanpc.learn.transfer import BackgroundExporter
    src, out = tmp_path / "data", tmp_path / "desk" / "mousedata_bob.zip"
    _session(src)
    ex = BackgroundExporter(src, "bob", out)
    for _ in range(5):  # bursts collapse; the final zip still has everything
        ex.request()
    _session(src, "session_20260101_020000")
    ex.request()
    assert ex.flush(10)["sessions"] == 2
    with zipfile.ZipFile(out) as z:
        assert "session_20260101_020000.json" in z.namelist()
    assert not list(out.parent.glob("*.tmp"))


def test_person_names_and_people(tmp_path):
    from humanpc.learn.dataset import clean_person, people, person_dir
    assert clean_person("  Jöhn Doe!! ") == "J_hn_Doe"
    with pytest.raises(ValueError):
        clean_person("..//")
    assert person_dir(tmp_path, None) == tmp_path
    _session(person_dir(tmp_path, "amy"))
    (tmp_path / "empty").mkdir()
    assert list(people(tmp_path)) == ["amy"]


def test_cli_export_import_and_stats(tmp_path, capsys):
    from humanpc.cli import main
    _session(tmp_path / "pc2" / "dan")
    assert main(["trainer-export", str(tmp_path / "a.zip"), "--data-dir", str(tmp_path / "pc2"),
                 "--person", "dan"]) == 0
    assert main(["trainer-import", str(tmp_path / "a.zip"), "--data-dir", str(tmp_path / "home")]) == 0
    capsys.readouterr()
    assert main(["trainer-stats", "--data-dir", str(tmp_path / "home")]) == 0
    out = capsys.readouterr().out
    assert "Estimated humanness" in out and "dan" in out
    assert main(["trainer-import", str(tmp_path / "missing.zip"), "--data-dir", str(tmp_path)]) == 1

"""Offline checks for the workflow testbench (winval/workflow): no browser, no input."""

import json
import math
import random
import sys
import urllib.request
from pathlib import Path

WF = Path(__file__).resolve().parents[1] / "winval" / "workflow"
sys.path.insert(0, str(WF))

import bench  # noqa: E402
import score_workflow as sw  # noqa: E402


def test_task_is_seeded_and_valid():
    a = bench.make_task(random.Random(3), "bot")
    b = bench.make_task(random.Random(3), "bot")
    assert a == b
    assert a["country"] in bench.COUNTRIES
    assert len(a["interests"]) == 3 and set(a["interests"]) <= set(bench.INTERESTS)
    assert 0 <= a["slider"] <= 100 and a["slider"] != 50


def test_page_and_script_agree_on_choices():
    html = bench.PAGE.read_text(encoding="utf-8")
    for c in bench.COUNTRIES + bench.INTERESTS:
        assert f'"{c}"' in html


def test_server_roundtrip(tmp_path):
    b = bench.Bench(bench.make_task(random.Random(1), "bot"), "unit", tmp_path)
    url = b.start()
    try:
        assert b"testbench" in urllib.request.urlopen(url).read()
        assert json.loads(urllib.request.urlopen(url + "api/task").read()) == b.task
        lay = {"view": "home", "dpr": 1.5, "offset": [0, 100], "inner": [1280, 700], "els": {"x": [10, 20, 30, 40]}}
        req = urllib.request.Request(url + "api/layout", json.dumps(lay).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req).read()
        assert b.wait(lambda l: l["view"] == "home", timeout=2)["dpr"] == 1.5
        req = urllib.request.Request(url + "api/log", json.dumps({"events": []}).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req).read()
        assert b.log_saved.is_set() and b.log_path.exists()
        assert json.loads(b.log_path.read_text())["meta"]["label"] == "unit"
    finally:
        b.stop()


def test_screen_rect_and_visibility():
    lay = {"dpr": 1.5, "offset": [0, 100], "inner": [1280, 700],
           "els": {"a": [10, 20, 30, 40], "low": [10, 900, 30, 40]}}
    assert bench.screen_rect(lay, "a") == (15, 180, 45, 60)
    assert bench.visible(lay, "a") and not bench.visible(lay, "low")
    assert bench.screen_rect(lay, "missing") is None


def _synthetic_log(label, rng):
    """A minimum-jerk reach + click, then a short typed word."""
    ev, t = [], 0.0
    for k in range(60):
        f = k / 59
        s = 10 * f ** 3 - 15 * f ** 4 + 6 * f ** 5
        ev.append([t, "m", 100 + 600 * s + rng.gauss(0, 0.4), 300 + 40 * math.sin(math.pi * f)])
        t += 8 + rng.random() * 0.2
    t += 150
    ev.append([t, "d", 700, 300, 0, "name", 300, 36])
    ev.append([t + 90, "u", 700, 300, 0, "name", 300, 36])
    t += 400
    for ch in "hello":
        ev.append([t, "kd", "Key" + ch.upper(), ch, 0, "name"])
        ev.append([t + 80 + rng.random() * 20, "ku", "Key" + ch.upper(), ch, 0, "name"])
        t += 150 + rng.random() * 80
    ev.append([t + 200, "x", "submit"])
    return {"meta": {"label": label}, "results": {"pass": True}, "events": ev}


def test_session_metrics_extracts_everything():
    m = sw.session_metrics(_synthetic_log("human", random.Random(0)))
    assert len(m["move_time_ms"]) == 1
    assert 100 <= m["preclick_ms"][0] <= 200
    assert m["click_hold_ms"] == [90]
    assert len(m["key_dwell_ms"]) == 5 and len(m["iki_ms"]) == 4
    assert m["mouse_to_key_ms"] and m["session_s"][0] > 0
    assert len(m["_aimed"]) == 1


def test_compare_reports_separability_against_human():
    logs = [_synthetic_log("human", random.Random(i)) for i in range(4)]
    logs += [_synthetic_log("bot-model", random.Random(10 + i)) for i in range(4)]
    groups = sw.aggregate(logs)
    assert groups["human"]["runs"] == 4 and groups["bot-model"]["passed"] == 4
    rep = sw.compare(groups)
    row = rep["bot-model"]["key_dwell_ms"]
    assert 0.5 <= row["separability"] <= 1.0 and "ref_median" in row
    assert "separability" not in rep["human"]["key_dwell_ms"]

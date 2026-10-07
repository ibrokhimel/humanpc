"""Score workflow logs: did it work, and can the input be told apart from yours?

    python winval/workflow/score_workflow.py                 # all logs in captures/workflow
    python winval/workflow/score_workflow.py --dir some/dir --json report.json

Every log is reduced to per-item samples (one per movement, click, keystroke,
transition ...). Labels are compared against the ``human`` label: for each metric
the report shows both medians and a *separability* score — the best balanced
accuracy of a single threshold (0.5 = indistinguishable, 1.0 = trivially
separable). Metrics at >= 0.75 are flagged as tells.

Record a few human runs first (``run_workflow.py --mode human``); without them
the report can only show absolute numbers and the literature bands.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from humanpc.validation import (  # noqa: E402
    stream_features, threshold_accuracy, trajectory_features, trajectory_realism_report,
)

PAUSE_MS = 120      # a gap this long ends a movement
MIN_SEG_PTS = 8
MIN_SEG_PX = 40.0
AIM_WINDOW_MS = 600  # a press this soon after a movement ends means it was aimed
BURST_GAP_MS = 1500  # keystrokes closer than this belong to one typing burst
TELL, WEAK = 0.75, 0.62

# metric -> (description, which way is "more robotic" is not assumed)
METRICS = {
    "move_time_ms": "movement duration",
    "move_peak_speed_frac": "where in the move peak speed happens",
    "move_speed_skew": "velocity profile skew",
    "move_straightness": "path straightness",
    "move_dir_changes": "direction changes per move",
    "move_decel_ratio": "end speed / mid speed (homing)",
    "move_human_score": "fraction of literature bands passed",
    "stream_rate_hz": "pointer event rate during motion",
    "stream_interval_cv": "event interval variability",
    "fitts_residual_ms": "move time minus the Fitts fit for this label",
    "preclick_ms": "pause between stopping and pressing",
    "click_hold_ms": "button hold time",
    "key_dwell_ms": "key hold time",
    "iki_ms": "time between keystrokes",
    "burst_cps": "typing speed per burst (chars/s)",
    "burst_iki_cv": "rhythm variability within a burst",
    "backspace_rate": "corrections per keystroke (per session)",
    "mouse_to_key_ms": "last click -> first keystroke",
    "key_to_mouse_ms": "last keystroke -> mouse moves again",
    "typing_drift_px": "cursor travel while typing",
    "wheel_interval_ms": "time between wheel ticks",
    "preclick_cv": "how uniform the pre-click pauses are (per session)",
    "session_s": "total time to finish",
}


def _q(xs, p):
    s = sorted(xs)
    if not s:
        return float("nan")
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _cv(xs):
    if len(xs) < 2:
        return float("nan")
    m = statistics.fmean(xs)
    return statistics.pstdev(xs) / m if m else float("nan")


def split_movements(moves, pause_ms=PAUSE_MS):
    """[(t, x, y)] -> list of movements (lists of samples), split at pauses."""
    segs, cur = [], []
    for p in moves:
        if cur and p[0] - cur[-1][0] > pause_ms:
            segs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        segs.append(cur)
    out = []
    for s in segs:
        # drop leading/trailing samples that don't move (they just pad the timing)
        while len(s) > 1 and (s[1][1], s[1][2]) == (s[0][1], s[0][2]):
            s = s[1:]
        while len(s) > 1 and (s[-2][1], s[-2][2]) == (s[-1][1], s[-1][2]):
            s = s[:-1]
        length = sum(math.dist(s[i - 1][1:], s[i][1:]) for i in range(1, len(s)))
        if len(s) >= MIN_SEG_PTS and length >= MIN_SEG_PX:
            out.append(s)
    return out


def session_metrics(log: dict) -> dict:
    """One log -> {metric: [samples]} plus a few scalars."""
    ev = sorted(log["events"], key=lambda e: e[0])
    m = defaultdict(list)
    moves = [(e[0], e[2], e[3]) for e in ev if e[1] == "m"]
    downs = [e for e in ev if e[1] == "d"]
    ups = [e for e in ev if e[1] == "u"]

    # -- movements --------------------------------------------------------
    aimed = []  # (D, W, MT)
    segs = split_movements(moves)
    for s in segs:
        ts = [p[0] / 1000.0 for p in s]
        xs = [p[1] for p in s]
        ys = [p[2] for p in s]
        f = trajectory_features(xs, ys, ts)
        if f.get("n", 0) < MIN_SEG_PTS or "straightness" not in f:
            continue
        mt = s[-1][0] - s[0][0]
        m["move_time_ms"].append(mt)
        m["move_peak_speed_frac"].append(f["peak_speed_frac"])
        m["move_speed_skew"].append(f["speed_skew"])
        m["move_straightness"].append(f["straightness"])
        m["move_dir_changes"].append(f["dir_changes"])
        m["move_decel_ratio"].append(f["decel_ratio"])
        m["move_human_score"].append(trajectory_realism_report(xs, ys, ts)["human_score"])
        sf = stream_features(xs, ys, ts)
        if sf:
            m["stream_rate_hz"].append(sf["event_rate_hz"])
            m["stream_interval_cv"].append(sf["interval_cv"])
        press = next((d for d in downs if 0 <= d[0] - s[-1][0] <= AIM_WINDOW_MS), None)
        if press is not None:
            m["preclick_ms"].append(press[0] - s[-1][0])
            w = min(press[6], press[7]) if len(press) > 7 and press[6] and press[7] else 0
            if w > 0:
                aimed.append((math.dist(s[0][1:], s[-1][1:]), w, mt))
    m["_aimed"] = aimed

    for d in downs:
        u = next((u for u in ups if u[0] >= d[0] and u[4] == d[4]), None)
        if u is not None and u[0] - d[0] < 2000:
            m["click_hold_ms"].append(u[0] - d[0])

    # -- keyboard ---------------------------------------------------------
    kds = [e for e in ev if e[1] == "kd" and not e[4]]
    kus = [e for e in ev if e[1] == "ku"]
    for d in kds:
        u = next((u for u in kus if u[0] >= d[0] and u[2] == d[2]), None)
        if u is not None and u[0] - d[0] < 1500:
            m["key_dwell_ms"].append(u[0] - d[0])
    printable = [d for d in kds if len(d[3]) == 1 or d[3] == "Backspace"]
    bursts, cur = [], []
    for d in printable:
        if cur and d[0] - cur[-1][0] > BURST_GAP_MS:
            bursts.append(cur)
            cur = []
        cur.append(d)
    if cur:
        bursts.append(cur)
    for b in bursts:
        ikis = [b[i][0] - b[i - 1][0] for i in range(1, len(b))]
        m["iki_ms"].extend(ikis)
        if len(b) >= 5:
            span = (b[-1][0] - b[0][0]) / 1000.0
            if span > 0:
                m["burst_cps"].append((len(b) - 1) / span)
            m["burst_iki_cv"].append(_cv(ikis))
        # cursor travel while this burst was being typed
        inside = [p for p in moves if b[0][0] <= p[0] <= b[-1][0]]
        m["typing_drift_px"].append(sum(math.dist(inside[i - 1][1:], inside[i][1:]) for i in range(1, len(inside))))
        # transitions in and out of the keyboard
        last_up = max((u[0] for u in ups if u[0] < b[0][0]), default=None)
        if last_up is not None and b[0][0] - last_up < 5000:
            m["mouse_to_key_ms"].append(b[0][0] - last_up)
        nxt = next((p[0] for p in moves if p[0] > b[-1][0]), None)
        if nxt is not None and nxt - b[-1][0] < 5000:
            m["key_to_mouse_ms"].append(nxt - b[-1][0])
    if printable:
        m["backspace_rate"].append(sum(1 for d in printable if d[3] == "Backspace") / len(printable))

    # -- wheel / session --------------------------------------------------
    wheels = [e[0] for e in ev if e[1] == "w"]
    m["wheel_interval_ms"].extend(b - a for a, b in zip(wheels, wheels[1:]) if b - a < 500)
    if len(m["preclick_ms"]) >= 3:
        m["preclick_cv"].append(_cv(m["preclick_ms"]))
    submit = next((e[0] for e in ev if e[1] == "x" and e[2] == "submit"), ev[-1][0] if ev else 0)
    start = next((e[0] for e in ev if e[1] in ("m", "kd", "d")), 0)
    m["session_s"].append((submit - start) / 1000.0)
    return m


def fit_fitts(aimed):
    """Least squares MT = a + b * log2(D/W + 1). Returns (a, b, r2)."""
    pts = [(math.log2(d / w + 1), mt) for d, w, mt in aimed if w > 0]
    if len(pts) < 3:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-9:
        return None
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys) or 1e-9
    r2 = 1 - sum((y - (a + b * x)) ** 2 for x, y in pts) / ss_tot
    return a, b, r2


def aggregate(logs: list[dict]) -> dict:
    """label -> {'runs', 'passed', 'metrics': {name: [samples]}, 'fitts'}"""
    out = {}
    for log in logs:
        label = log.get("meta", {}).get("label", "unknown")
        g = out.setdefault(label, {"runs": 0, "passed": 0, "metrics": defaultdict(list), "_aimed": []})
        g["runs"] += 1
        g["passed"] += bool(log.get("results", {}).get("pass"))
        for k, v in session_metrics(log).items():
            (g["_aimed"] if k == "_aimed" else g["metrics"][k]).extend(v)
    for g in out.values():
        fit = fit_fitts(g["_aimed"])
        g["fitts"] = fit
        if fit:
            a, b, _ = fit
            g["metrics"]["fitts_residual_ms"] = [mt - (a + b * math.log2(d / w + 1)) for d, w, mt in g["_aimed"]]
        del g["_aimed"]
    return out


def compare(groups: dict, ref: str = "human") -> dict:
    """{label: {metric: {'median', 'iqr', 'n', 'ref_median', 'separability'}}}"""
    rep = {}
    base = groups.get(ref, {}).get("metrics", {})
    for label, g in groups.items():
        rows = {}
        for key in METRICS:
            xs = [x for x in g["metrics"].get(key, []) if x == x]
            if not xs:
                continue
            row = {"n": len(xs), "median": _q(xs, 0.5), "iqr": [_q(xs, 0.25), _q(xs, 0.75)]}
            ys = [y for y in base.get(key, []) if y == y]
            if label != ref and ys:
                row["ref_median"] = _q(ys, 0.5)
                row["separability"] = threshold_accuracy(xs, ys)
            rows[key] = row
        rep[label] = rows
    return rep


def _fmt(v):
    if v != v:
        return "-"
    return f"{v:.3f}" if abs(v) < 10 else f"{v:.0f}"


def print_report(groups: dict, rep: dict, ref: str = "human") -> None:
    have_ref = ref in groups
    for label, g in sorted(groups.items(), key=lambda kv: kv[0] != ref):
        print(f"\n=== {label}: {g['passed']}/{g['runs']} runs passed the form check ===")
        if g["fitts"]:
            a, b, r2 = g["fitts"]
            print(f"Fitts fit: MT = {a:.0f} + {b:.0f}*ID ms  (r2 {r2:.2f})")
        head = f"{'metric':<22}{'n':>6}{'median':>10}{'IQR':>20}"
        if have_ref and label != ref:
            head += f"{'human med':>11}{'separab.':>10}"
        print(head)
        tells = []
        for key, row in rep[label].items():
            line = f"{key:<22}{row['n']:>6}{_fmt(row['median']):>10}{_fmt(row['iqr'][0]) + '..' + _fmt(row['iqr'][1]):>20}"
            if "separability" in row:
                s = row["separability"]
                flag = "  TELL" if s >= TELL else ("  weak" if s >= WEAK else "")
                line += f"{_fmt(row['ref_median']):>11}{s:>10.2f}{flag}"
                if s >= TELL:
                    tells.append((s, key))
            print(line)
        if tells:
            print("biggest tells: " + ", ".join(f"{k} ({METRICS[k]}, {s:.2f})" for s, k in sorted(tells, reverse=True)))
    if not have_ref:
        print("\nNo 'human' runs yet - record some with: python winval/workflow/run_workflow.py --mode human")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(ROOT / "captures" / "workflow"))
    ap.add_argument("--ref", default="human", help="label to compare everything against")
    ap.add_argument("--json", help="also write the report here")
    args = ap.parse_args(argv)
    files = sorted(Path(args.dir).glob("*.json"))
    logs = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "events" in data:
            logs.append(data)
    if not logs:
        print(f"no workflow logs in {args.dir}")
        return 1
    groups = aggregate(logs)
    rep = compare(groups, args.ref)
    print_report(groups, rep, args.ref)
    if args.json:
        Path(args.json).write_text(json.dumps({
            "groups": {k: {"runs": g["runs"], "passed": g["passed"], "fitts": g["fitts"]} for k, g in groups.items()},
            "metrics": rep,
        }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

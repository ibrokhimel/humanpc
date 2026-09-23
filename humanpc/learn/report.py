"""Human-readable dataset report + a rough "humanness" estimate.

The estimate is a heuristic, not a measurement. It answers: *if a sequence
model were trained on this much of your data, how close would it get to being
indistinguishable from you?* 100% = a detector trained on your real movement
does no better than a coin flip; 0% = trivially caught.

Model: each movement category fills up with diminishing returns,
``1 - exp(-n / n0)``, where ``n0`` is roughly the amount of data after which
most of that category's variety has been seen. Categories are weighted by how
much they matter to a detector, and the total is capped at ``CEILING`` because
data alone never gets you to 100% — model quality, the landing-correction step
and the driver's timing all leave traces. Constants are informed guesses from
published mouse-dynamics / trajectory-generation work, calibrated so that a
balanced ~10 h dataset lands around the mid-60s. Replace this with the real
detector score once the training + detector scripts exist.
"""

from __future__ import annotations

import math
import sys

CEILING = 0.80

# category -> (weight, n0, label, unit)
CATEGORIES = {
    "aim": (0.40, 2500, "Aiming movements", ""),
    "scroll": (0.20, 700, "Scroll episodes", ""),
    "idle": (0.15, 2400, "Idle / reading", "s"),
    "click": (0.10, 600, "Double / right clicks", ""),
    "drag": (0.10, 500, "Drags", ""),
    "trace": (0.05, 300, "Path traces", ""),
}

MIN_AIM_TO_TRAIN = 300  # below this a sequence model just memorises

# Fallback collection rates (units per active hour) — matches the default task mix.
DEFAULT_RATES = {"aim": 950, "scroll": 110, "idle": 160, "click": 140, "drag": 80, "trace": 30}

MILESTONES = (10, 25, 40, 50, 60, 70, 75)

VERDICTS = (
    (10, "Not enough data to train a model yet."),
    (25, "A model would pick up your basic speed and curve style, but any detector would catch it."),
    (40, "Would pass simple checks (straight lines, constant speed); a trained detector still catches most of it."),
    (55, "Convincing to a person watching; a detector trained on your data catches it often."),
    (70, "Hard to tell apart with typical detectors; a strong detector trained on you still has an edge."),
    (101, "Close to the practical ceiling - more data now helps less than a better model."),
)


def fill(cat: str, n: float) -> float:
    return 1.0 - math.exp(-max(0.0, n) / CATEGORIES[cat][1])


def estimate(units: dict) -> float:
    """Estimated humanness in percent (0..CEILING*100)."""
    total = sum(w * fill(cat, units.get(cat, 0)) for cat, (w, *_rest) in CATEGORIES.items())
    return 100.0 * CEILING * total


def rates(st: dict) -> dict:
    """Units per active hour, from your own sessions once there is enough to go on."""
    hours = st.get("active_seconds", 0) / 3600
    if hours < 1 / 60:
        return dict(DEFAULT_RATES)
    return {c: st.get("units", {}).get(c, 0) / hours for c in CATEGORIES}


def minutes_to_reach(st: dict, target_pct: float, max_hours: float = 200) -> float | None:
    r = rates(st)
    units = dict(st.get("units", {}))
    step = 5 / 60
    h = 0.0
    while h <= max_hours:
        if estimate({c: units.get(c, 0) + r.get(c, 0) * h for c in CATEGORIES}) >= target_pct:
            return h * 60
        h += step
    return None


def weakest(units: dict) -> str:
    """Category where one more hour of focused recording gains the most."""
    return max(CATEGORIES, key=lambda c: CATEGORIES[c][0] * (1 - fill(c, units.get(c, 0))))


def verdict(pct: float, units: dict) -> str:
    if units.get("aim", 0) < MIN_AIM_TO_TRAIN:
        return VERDICTS[0][1]
    return next(text for limit, text in VERDICTS if pct < limit)


# -- formatting -------------------------------------------------------------------
def _glyphs():
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "█░─·".encode(enc)
        return "█", "░", "─", "·"
    except (UnicodeEncodeError, LookupError):
        return "#", ".", "-", "-"


def _bar(frac: float, width: int) -> str:
    full, empty, _, _ = _glyphs()
    n = round(max(0.0, min(1.0, frac)) * width)
    return full * n + empty * (width - n)


def _duration(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    return f"{m} min {s:02d} s" if m else f"{s} s"


def _size(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024 or unit == "GB":
            return f"{b:.0f} {unit}" if unit in ("B", "KB") else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} GB"


def summary(st: dict) -> dict:
    """Machine-readable estimate block (used by --json and the trainer UI)."""
    units = st.get("units", {})
    pct = estimate(units)
    nxt = next((m for m in MILESTONES if m > pct + 0.5), None)
    return {
        "humanness_pct": round(pct, 1),
        "ceiling_pct": CEILING * 100,
        "verdict": verdict(pct, units),
        "weakest": weakest(units),
        "next_milestone_pct": nxt,
        "minutes_to_next": None if nxt is None else minutes_to_reach(st, nxt),
    }


def format_report(st: dict, *, polling_hz: float | None = None) -> str:
    _, _, rule_ch, dot = _glyphs()
    units = st.get("units", {})
    s = summary(st)
    hours = st["active_seconds"] / 3600
    rule = rule_ch * 62
    lines = ["", "  humanpc trainer - your dataset", "  " + rule]

    sess = f"{st['sessions']} session{'s' if st['sessions'] != 1 else ''}"
    lines.append(f"  Recorded     {_duration(st['active_seconds'])}   ({sess}, {st['tasks_ok']} tasks done)")
    ev = f"  Events       {st['events']:,}"
    if polling_hz:
        ev += f"   (~{polling_hz:,.0f} Hz mouse)"
    lines.append(ev)
    disk = f"  On disk      {_size(st['bytes'])}"
    if hours > 0.01:
        disk += f"   (~{_size(st['bytes'] / hours)} per hour)"
    lines.append(disk)
    lines.append(f"  Location     {st['data_dir']}")

    lines += ["", "  What you've recorded                      coverage"]
    for cat, (_w, n0, label, unit) in CATEGORIES.items():
        n = units.get(cat, 0)
        amount = f"{n:,.0f}{unit}"
        lines.append(f"    {label:<22}{amount:>8}   {_bar(fill(cat, n), 16)} {fill(cat, n) * 100:3.0f}%")

    pct = s["humanness_pct"]
    lines += ["", f"  Estimated humanness   {pct:4.1f}%   {_bar(pct / 100, 30)}",
              f"  {'':22}(practical ceiling ~{s['ceiling_pct']:.0f}%)",
              f"  {s['verdict']}"]

    if s["next_milestone_pct"] is not None and s["minutes_to_next"] is not None:
        mins = max(5, round(s["minutes_to_next"] / 5) * 5)
        lines.append(f"  Next: {s['next_milestone_pct']}% after about "
                     f"{_duration(mins * 60).replace(' 00 s', '')} more recording.")
    lines.append(f"  Weakest area: {CATEGORIES[s['weakest']][2].lower()} - more of these helps most right now.")

    lines += ["", f"  Rough guide at your current task mix:"]
    for h in (1, 3, 5, 10, 20):
        if h > hours:
            r = rates(st)
            proj = estimate({c: units.get(c, 0) + r[c] * (h - hours) for c in CATEGORIES})
            lines.append(f"    {h:>2} h total  {dot}  ~{proj:.0f}%")
    lines += ["", "  This is an informed estimate, not a measurement. The real number will come",
              "  from the detector once the model is trained.", ""]
    return "\n".join(lines)


def polling_hz_of_latest(data_dir) -> float | None:
    """Median mouse-move rate of the most recent session (cheap: one file)."""
    try:
        import numpy as np

        from .dataset import list_sessions, load_session
        sessions = list_sessions(data_dir)
        if not sessions:
            return None
        ev, _, _ = load_session(sessions[-1])
        t = ev["t_us"][ev["type"] == 0]
        dt = np.diff(t)
        dt = dt[(dt > 0) & (dt < 20_000)]
        return float(1e6 / np.median(dt)) if dt.size > 50 else None
    except Exception:  # noqa: BLE001 - the report must never fail on this
        return None


def format_people(root) -> str:
    """One line per person (subfolder) plus your own root-level sessions."""
    from .dataset import people, stats

    _, _, rule_ch, _ = _glyphs()
    rows = []
    own = stats(root)
    if own["sessions"]:
        rows.append(("(you)", own))
    rows += [(name, stats(folder)) for name, folder in people(root).items()]
    lines = ["  People", "  " + rule_ch * 62,
             f"    {'name':<18}{'recorded':>14}{'tasks':>8}   estimate (alone)"]
    for name, st in rows:
        pct = estimate(st.get("units", {}))
        lines.append(f"    {name[:18]:<18}{_duration(st['active_seconds']):>14}{st['tasks_ok']:>8}"
                     f"   {_bar(pct / 100, 12)} {pct:3.0f}%")
    lines += ["", "  The combined estimate above assumes one model trained on everyone with a",
              "  per-person style code; each person's own line is what their data gives alone.", ""]
    return "\n".join(lines)

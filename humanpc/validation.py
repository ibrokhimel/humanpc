"""Realism validation harness.

The gap this addresses: realism was previously *asserted* ("it looks smooth"),
never *measured*. The right test is statistical — generate traces, extract the
features a detector would key on, and check they match human reference ranges (and
that a discriminator separates the realistic engine from a naive one).

This module is the measurement scaffold:

  * ``mouse_features`` / ``typing_features`` — extract the detector-relevant stats
    from a generated plan (velocity skew, peak-velocity fraction, timing
    variability; key-hold dwell, inter-key-interval skew).
  * ``mouse_realism_checks`` / ``typing_realism_checks`` — boolean checks against
    ranges from the motor-control / keystroke-dynamics literature.
  * ``threshold_accuracy`` — a 1-D discriminator: how separable two batches are on
    a feature. Use it to prove the realism layer produces a *measurably* different
    signature than a naive baseline (a regression guard), and as the seed of a
    full "train a classifier on real-vs-generated" evaluation.

Honest caveat: true validation needs a corpus of *real human* recordings to
calibrate the targets and train the discriminator. No such dataset ships here;
these checks encode literature ranges and guard against silent regressions.
"""

from __future__ import annotations

import math

from .geometry import distance


def _mean(xs) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def _cv(xs) -> float:
    m = _mean(xs)
    return _std(xs) / m if m > 1e-12 else 0.0


def skewness(xs) -> float:
    """Fisher-Pearson skewness. Positive == right-skewed (a long right tail)."""
    n = len(xs)
    if n < 3:
        return 0.0
    m = _mean(xs)
    s = _std(xs)
    if s <= 1e-12:
        return 0.0
    return sum(((x - m) / s) ** 3 for x in xs) / n


# --- mouse ------------------------------------------------------------------

def mouse_features(plan) -> dict:
    pts = [s.point for s in plan]
    dts = [s.dt for s in plan[1:]]
    segs = [distance(pts[i - 1], pts[i]) for i in range(1, len(pts))]
    speeds = [segs[i] / dts[i] if dts[i] > 1e-9 else 0.0 for i in range(len(dts))]
    peak_frac = (speeds.index(max(speeds)) / len(speeds)) if speeds else 0.0
    q = max(1, len(speeds) // 5)
    mid = _mean(speeds[2 * q:3 * q])
    last = _mean(speeds[-q:])
    decel_ratio = (last / mid) if mid > 1e-12 else 1.0
    # Max perpendicular deviation from the straight start->end line (curvature).
    a, b = pts[0], pts[-1]
    abx, aby = b.x - a.x, b.y - a.y
    L = math.hypot(abx, aby) or 1.0
    max_lat = max((abs((p.x - a.x) * aby - (p.y - a.y) * abx) / L for p in pts), default=0.0)
    return {
        "n": len(plan),
        "peak_speed_frac": peak_frac,
        "speed_skew": skewness(speeds),
        "dt_cv": _cv(dts),
        "decel_ratio": decel_ratio,
        "max_lateral_dev": max_lat,
        "path_len": sum(segs),
    }


def mouse_realism_checks(plan) -> dict:
    f = mouse_features(plan)
    return {
        # Homing: the cursor is much slower approaching the target than mid-flight.
        "decelerates_into_target": f["decel_ratio"] < 0.8,
        # The path is a curve, not a straight line.
        "curved": f["max_lateral_dev"] > 1.0,
        "moved": f["path_len"] > 0.0,
    }


def lag1_autocorr(xs) -> float:
    """Lag-1 autocorrelation. ~0 for white noise, high for 1/f (pink) noise."""
    n = len(xs)
    if n < 3:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / n
    if var <= 1e-12:
        return 0.0
    return sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, n)) / n / var


# --- typing -----------------------------------------------------------------

def typing_features(events) -> dict:
    dwells = [e.dwell for e in events]
    ikis = [e.delay for e in events]
    return {
        "n": len(events),
        "dwell_mean": _mean(dwells),
        "dwell_min": min(dwells) if dwells else 0.0,
        "iki_skew": skewness(ikis),
        "iki_cv": _cv(ikis),
    }


def typing_realism_checks(events) -> dict:
    f = typing_features(events)
    return {
        "dwell_in_human_range": 0.03 <= f["dwell_mean"] <= 0.18,
        "nonzero_dwell": f["dwell_min"] > 0.0,
        "iki_right_skewed": f["iki_skew"] > 0.0,  # lognormal, not Gaussian
    }


# --- trajectory features (work on real captured (x, y, t) samples) ----------
# These extract the discriminative features a mouse-dynamics detector keys on
# (see Human_Mouse_Movement_Research.md) from an actual sampled cursor path, so
# generated movement can be scored the same way a detector would score it.

def _resample_uniform(xs, ys, ts, n):
    """Resample an (x, y) path to ``n`` points at uniform time."""
    if len(ts) < 2:
        return list(xs), list(ys)
    t0, t1 = ts[0], ts[-1]
    span = (t1 - t0) or 1.0
    rx, ry, j = [], [], 0
    for k in range(n):
        t = t0 + span * k / (n - 1)
        while j < len(ts) - 2 and ts[j + 1] < t:
            j += 1
        seg = (ts[j + 1] - ts[j]) or 1e-9
        f = max(0.0, min(1.0, (t - ts[j]) / seg))
        rx.append(xs[j] * (1 - f) + xs[j + 1] * f)
        ry.append(ys[j] * (1 - f) + ys[j + 1] * f)
    return rx, ry


def sample_entropy(series, m: int = 2, r: float = 0.0) -> float:
    """Sample entropy: low == predictable/regular, high == irregular/noisy.

    Humans sit in the middle (structured unpredictability); a constant-velocity
    bot is ~0, pure noise is high.
    """
    n = len(series)
    if n < m + 2:
        return 0.0
    if r <= 0:
        r = 0.2 * _std(series)
    if r <= 0:
        return 0.0

    def count(mm):
        tpl = [series[i:i + mm] for i in range(n - mm + 1)]
        c = 0
        for i in range(len(tpl)):
            for j in range(i + 1, len(tpl)):
                if max(abs(a - b) for a, b in zip(tpl[i], tpl[j])) <= r:
                    c += 1
        return c

    b, a = count(m), count(m + 1)
    if b == 0 or a == 0:
        return 0.0
    return -math.log(a / b)


def dft_band_ratio(series, fs: float, lo: float = 8.0, hi: float = 12.0) -> float:
    """Fraction of spectral power in [lo, hi] Hz — the physiological-tremor band.

    Real motor output carries an 8-12 Hz tremor; analytic/bot paths have ~0 there.
    """
    n = len(series)
    if n < 8 or fs <= 0:
        return 0.0
    m = _mean(series)
    sig = [x - m for x in series]
    band, total = 0.0, 0.0
    for k in range(1, n // 2):
        f = k * fs / n
        re = sum(sig[t] * math.cos(2 * math.pi * k * t / n) for t in range(n))
        im = sum(sig[t] * math.sin(2 * math.pi * k * t / n) for t in range(n))
        p = re * re + im * im
        total += p
        if lo <= f <= hi:
            band += p
    return band / total if total > 1e-12 else 0.0


def trajectory_features(xs, ys, ts) -> dict:
    """Detector-relevant features from a sampled cursor trajectory."""
    n = len(xs)
    if n < 4:
        return {"n": n}
    disp = math.hypot(xs[-1] - xs[0], ys[-1] - ys[0])
    segs = [math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1]) for i in range(1, n)]
    path_len = sum(segs) or 1e-9
    dts = [ts[i] - ts[i - 1] for i in range(1, n)]
    speeds = [segs[i] / dts[i] if dts[i] > 1e-9 else 0.0 for i in range(len(segs))]

    # velocity peak position + decel-into-target
    peak_frac = (speeds.index(max(speeds)) / len(speeds)) if speeds else 0.0
    q = max(1, len(speeds) // 5)
    mid = _mean(speeds[2 * q:3 * q]) or 1e-9
    decel_ratio = _mean(speeds[-q:]) / mid

    # direction changes (sign flips of dx, dy)
    def flips(vals):
        s = [1 if v > 0.5 else (-1 if v < -0.5 else 0) for v in vals]
        s = [v for v in s if v != 0]
        return sum(1 for i in range(1, len(s)) if s[i] != s[i - 1])
    dirchg = flips([xs[i] - xs[i - 1] for i in range(1, n)]) + \
        flips([ys[i] - ys[i - 1] for i in range(1, n)])

    # max perpendicular deviation (curvature / MAD)
    abx, aby = xs[-1] - xs[0], ys[-1] - ys[0]
    L = math.hypot(abx, aby) or 1.0
    max_lat = max((abs((xs[i] - xs[0]) * aby - (ys[i] - ys[0]) * abx) / L for i in range(n)), default=0.0)

    # spectral tremor + entropy on a uniform-time resample of lateral deviation
    rx, ry = _resample_uniform(xs, ys, ts, min(160, max(32, n)))
    lat = [((rx[i] - xs[0]) * aby - (ry[i] - ys[0]) * abx) / L for i in range(len(rx))]
    fs = (len(rx) - 1) / ((ts[-1] - ts[0]) or 1.0)
    # High-pass (subtract a moving average) so the low-frequency path curve does
    # not swamp the spectrum — otherwise the small 8-12 Hz tremor is invisible.
    win = max(2, int(fs / 6))
    detr = [lat[i] - _mean(lat[max(0, i - win):i + win + 1]) for i in range(len(lat))]
    tremor = dft_band_ratio(detr, fs)
    rspeeds = [math.hypot(rx[i] - rx[i - 1], ry[i] - ry[i - 1]) for i in range(1, len(rx))]
    entropy = sample_entropy(rspeeds)

    return {
        "n": n,
        "straightness": disp / path_len,          # 1.0 == perfectly direct
        "peak_speed_frac": peak_frac,             # ~0.4-0.5 for humans
        "speed_skew": skewness(speeds),           # > 0 == right-skewed
        "decel_ratio": decel_ratio,               # < 1 == slows into target
        "dir_changes": dirchg,                    # corrections/jitter
        "max_lateral_dev": max_lat,               # curvature
        "dt_cv": _cv(dts),                        # timing irregularity
        "tremor_band_ratio": tremor,              # 8-12 Hz power fraction
        "sample_entropy": entropy,                # structured unpredictability
        "path_len": path_len,
    }


# Human reference bands (single point-to-point reach) from the motor-control /
# mouse-dynamics literature. (value -> in human range?)
_HUMAN_BANDS = {
    "peak_speed_frac": (0.30, 0.55),   # early peak, not start/midpoint/end
    "speed_skew": (0.05, 6.0),         # right-skewed (lognormal), not symmetric
    "decel_ratio": (0.0, 0.85),        # clear homing deceleration
    "straightness": (0.80, 0.998),     # slight curve, never perfectly straight
    "dir_changes": (1, 60),            # some corrections, not a rigid line
    "tremor_band_ratio": (0.01, 0.6),  # a present-but-small tremor band
    "sample_entropy": (0.2, 2.2),      # structured, not 0 and not pure noise
}


def trajectory_realism_report(xs, ys, ts) -> dict:
    """Per-feature human-range verdicts + an overall human-likeness score."""
    f = trajectory_features(xs, ys, ts)
    checks = {}
    for key, (lo, hi) in _HUMAN_BANDS.items():
        v = f.get(key)
        checks[key] = (v is not None and lo <= v <= hi)
    score = sum(checks.values()) / len(checks) if checks else 0.0
    return {"features": f, "checks": checks, "human_score": score}


# --- discriminator ----------------------------------------------------------

def threshold_accuracy(pos_vals, neg_vals) -> float:
    """Best balanced accuracy of a single threshold separating two batches.

    Returns 0.5 when indistinguishable, → 1.0 when cleanly separable (direction
    agnostic). The seed of an adversarial 'can a classifier tell?' evaluation.
    """
    if not pos_vals or not neg_vals:
        return 0.0
    total = len(pos_vals) + len(neg_vals)
    best = 0.0
    for t in sorted(set(list(pos_vals) + list(neg_vals))):
        hi = (sum(1 for v in pos_vals if v >= t) + sum(1 for v in neg_vals if v < t)) / total
        best = max(best, hi, 1.0 - hi)
    return best

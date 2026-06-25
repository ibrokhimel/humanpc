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

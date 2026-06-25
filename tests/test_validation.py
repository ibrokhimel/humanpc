"""Tier 6 — validation methodology: feature extraction, literature-range checks,
and a discriminator separating the realistic engine from a naive baseline."""

import random

from humanpc.hil.mouse import MouseTrajectoryEngine
from humanpc.hil.mouse.jitter import JitterInjector
from humanpc.hil.typing import HumanTypingEngine
from humanpc.validation import (
    lag1_autocorr,
    mouse_realism_checks,
    skewness,
    threshold_accuracy,
    trajectory_features,
    trajectory_realism_report,
    typing_features,
    typing_realism_checks,
)


def _realistic_mouse():
    return MouseTrajectoryEngine(settle_probability=0.0)


def _plan_to_xyt(plan):
    xs = [s.point.x for s in plan]
    ys = [s.point.y for s in plan]
    ts, t = [0.0], 0.0
    for s in plan[1:]:
        t += s.dt
        ts.append(t)
    return xs, ys, ts


def _naive_bot_xyt(start, end, n=60, total=0.4):
    """A classic bot trace: straight line at constant velocity, uniform time."""
    xs = [start[0] + (end[0] - start[0]) * k / (n - 1) for k in range(n)]
    ys = [start[1] + (end[1] - start[1]) * k / (n - 1) for k in range(n)]
    ts = [total * k / (n - 1) for k in range(n)]
    return xs, ys, ts


# --- feature helpers --------------------------------------------------------

def test_skewness_sign():
    assert skewness([1, 1, 1, 1, 10]) > 0     # right tail
    assert abs(skewness([-2, -1, 0, 1, 2])) < 0.1


# --- mouse realism checks ---------------------------------------------------

def test_realistic_mouse_passes_checks():
    eng = _realistic_mouse()
    passed = 0
    for s in range(30):
        checks = mouse_realism_checks(eng.plan((0, 0), (600, 100), rng=random.Random(s)))
        passed += all(checks.values())
    assert passed >= 27  # the large majority of traces look human


def test_discriminator_separates_colored_from_white_jitter():
    # The detector signal: colored (1/f + tremor) jitter is autocorrelated; white
    # noise is not. Measure lag-1 autocorr of each engine's jitter offsets.
    from humanpc.geometry import Point

    base = [Point(i * 6.0, 0.0) for i in range(60)]
    colored, white = JitterInjector(base_amplitude=2.0, colored=True), JitterInjector(
        base_amplitude=2.0, colored=False
    )
    col_ac, wht_ac = [], []
    for s in range(40):
        cpts = colored.inject(list(base), dt=0.01, rng=random.Random(s))
        wpts = white.inject(list(base), dt=0.01, rng=random.Random(s))
        col_ac.append(lag1_autocorr([p.y for p in cpts[1:-1]]))
        wht_ac.append(lag1_autocorr([p.y for p in wpts[1:-1]]))
    assert threshold_accuracy(col_ac, wht_ac) > 0.85


# --- trajectory-level detector features -------------------------------------

def test_realistic_trajectory_scores_higher_than_naive_bot():
    eng = _realistic_mouse()
    human, bot = [], []
    for s in range(20):
        plan = eng.plan((0, 0), (700, 120), rng=random.Random(s))
        human.append(trajectory_realism_report(*_plan_to_xyt(plan))["human_score"])
        bot.append(trajectory_realism_report(*_naive_bot_xyt((0, 0), (700, 120)))["human_score"])
    assert sum(human) / len(human) > sum(bot) / len(bot) + 0.3


def test_discriminator_separates_realistic_from_straight_bot():
    eng = _realistic_mouse()
    human, bot = [], []
    for s in range(25):
        plan = eng.plan((0, 0), (600, 220), rng=random.Random(s))
        human.append(trajectory_features(*_plan_to_xyt(plan))["speed_skew"])
        bot.append(trajectory_features(*_naive_bot_xyt((0, 0), (600, 220)))["speed_skew"])
    assert threshold_accuracy(human, bot) > 0.8


def test_straight_constant_velocity_bot_fails_checks():
    rep = trajectory_realism_report(*_naive_bot_xyt((0, 0), (800, 0)))
    # A perfectly direct, constant-speed line is flagged on every spatial/kinematic axis.
    assert not rep["checks"]["straightness"]      # too direct
    assert not rep["checks"]["decel_ratio"]       # no homing deceleration
    assert rep["human_score"] < 0.4


# --- typing realism checks --------------------------------------------------

def test_realistic_typing_passes_checks():
    eng = HumanTypingEngine()
    events = eng.plan("the quick brown fox jumps over the lazy dog", random.Random(0))
    checks = typing_realism_checks(events)
    assert checks["nonzero_dwell"] and checks["dwell_in_human_range"]
    assert checks["iki_right_skewed"]


def test_discriminator_separates_dwell_from_zero_dwell():
    eng = HumanTypingEngine()
    real_dwell, naive_dwell = [], []
    for s in range(30):
        ev = eng.plan("hello world example text", random.Random(s))
        real_dwell.append(typing_features(ev)["dwell_mean"])
        naive_dwell.append(0.0)  # the old atomic zero-dwell injection
    assert threshold_accuracy(real_dwell, naive_dwell) > 0.95

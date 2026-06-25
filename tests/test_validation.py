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
    typing_features,
    typing_realism_checks,
)


def _realistic_mouse():
    return MouseTrajectoryEngine(settle_probability=0.0)


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

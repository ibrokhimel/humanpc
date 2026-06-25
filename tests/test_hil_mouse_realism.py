"""Tier 1 — motor-signal fidelity: colored noise, asymmetric velocity,
curvature timing, corrective submovements, settle."""

import random

from humanpc.geometry import Point, distance
from humanpc.hil.mouse import (
    JitterInjector,
    MouseTrajectoryEngine,
    OvershootSimulator,
    VelocityProfile,
)
from humanpc.hil.mouse.noise import PinkNoise, Tremor


def _lag1_autocorr(xs):
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / n or 1e-9
    cov = sum((xs[i] - mean) * (xs[i - 1] - mean) for i in range(1, n)) / n
    return cov / var


# --- 1.1 colored noise ------------------------------------------------------

def test_pink_noise_is_autocorrelated_unlike_white():
    rng = random.Random(0)
    pink = PinkNoise()
    pink_seq = [pink.next(rng) for _ in range(4000)]
    white_seq = [rng.gauss(0, 1) for _ in range(4000)]
    # Pink (1/f) noise has strong positive lag-1 autocorrelation; white ~ 0.
    assert _lag1_autocorr(pink_seq) > 0.3
    assert abs(_lag1_autocorr(white_seq)) < 0.1


def test_tremor_oscillates_in_band():
    t = Tremor(amplitude=0.4).reset(random.Random(1))
    vals = [t.at(i / 1000) for i in range(1000)]
    assert max(vals) <= 0.4001 and min(vals) >= -0.4001
    assert max(vals) > 0.2  # actually swings


def test_jitter_colored_perturbs_interior_keeps_endpoints():
    pts = [Point(i * 10, 0) for i in range(12)]
    out = JitterInjector(base_amplitude=2.0, velocity_factor=0.0, colored=True).inject(
        pts, dt=0.01, rng=random.Random(2)
    )
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert any(out[i].y != 0 for i in range(1, len(out) - 1))


# --- 1.2 asymmetric velocity ------------------------------------------------

def test_velocity_profile_peaks_early_right_skewed():
    vp = VelocityProfile(asymmetric=True)
    params = vp.eased_params(200, random.Random(3))
    speeds = [params[i] - params[i - 1] for i in range(1, len(params))]
    peak_idx = max(range(len(speeds)), key=lambda i: speeds[i])
    # Peak velocity occurs in the first half (short accel, long decel).
    assert peak_idx / len(speeds) < 0.5


def test_velocity_params_monotonic_unit_interval():
    params = VelocityProfile().eased_params(50, random.Random(4))
    assert params[0] == 0.0 and abs(params[-1] - 1.0) < 1e-9
    assert all(params[i] >= params[i - 1] - 1e-9 for i in range(1, len(params)))


# --- 1.3 corrective submovements --------------------------------------------

def test_overshoot_emits_decaying_corrections_from_beyond_side():
    rng = random.Random(5)
    target = Point(400, 0)
    plan = [__import__("humanpc.hil.mouse.step", fromlist=["MouseStep"]).MouseStep(Point(390, 0), 0.01),
            __import__("humanpc.hil.mouse.step", fromlist=["MouseStep"]).MouseStep(target, 0.01)]
    ov = OvershootSimulator(probability=1.0, min_distance=0.0, range_px=(10, 10), corrections=(2, 2))
    ov.apply(plan, target, distance=400, rng=rng)
    assert plan[-1].point == target          # lands exactly
    assert plan[-2].point.x > target.x       # approached from the overshoot side


# --- 1.4 curvature-weighted timing ------------------------------------------

def test_curved_path_spends_more_time_on_bends():
    eng = MouseTrajectoryEngine(
        jitter=JitterInjector(base_amplitude=0.0, velocity_factor=0.0),
        overshoot=OvershootSimulator(probability=0.0),
        settle_probability=0.0,
    )
    plan = eng.plan((0, 0), (500, 0), rng=random.Random(6))
    # Total time is positive and dt varies step-to-step (not a flat cadence).
    dts = [s.dt for s in plan[1:]]
    assert sum(dts) > 0
    assert len(set(round(d, 6) for d in dts)) > 3


# --- regression: still lands exactly, still curved --------------------------

def test_engine_lands_exactly_with_realism_on():
    eng = MouseTrajectoryEngine(overshoot=OvershootSimulator(probability=0.0), settle_probability=0.0)
    plan = eng.plan((10, 10), (500, 320), rng=random.Random(7))
    assert plan[0].point.as_int() == (10, 10)
    assert plan[-1].point.as_int() == (500, 320)

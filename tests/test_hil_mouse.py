import random

from humanpc.geometry import Point, distance
from humanpc.hil.mouse import (
    JitterInjector,
    MouseTrajectoryEngine,
    OvershootSimulator,
    VelocityProfile,
)
from humanpc.hil.mouse.bezier import BezierPathGenerator
from humanpc.hil.mouse.step import MouseStep


def _engine(**kw):
    return MouseTrajectoryEngine(**kw)


def test_path_is_curved_not_straight():
    # Target straight along the x-axis: any curvature shows up as non-zero |y|.
    rng = random.Random(1)
    plan = _engine().plan((0, 0), (400, 0), rng=rng)
    max_dev = max(abs(s.point.y) for s in plan)
    assert max_dev > 2.0  # not a straight line


def test_endpoints_are_exact():
    rng = random.Random(2)
    # No overshoot so the last point is the target itself.
    eng = _engine(overshoot=OvershootSimulator(probability=0.0))
    plan = eng.plan((10, 10), (500, 320), rng=rng)
    assert plan[0].point.as_int() == (10, 10)
    assert plan[-1].point.as_int() == (500, 320)


def test_velocity_profile_accelerates_then_decelerates():
    # Disable jitter + overshoot so the speed profile is clean.
    rng = random.Random(3)
    eng = _engine(
        jitter=JitterInjector(base_amplitude=0.0, velocity_factor=0.0),
        overshoot=OvershootSimulator(probability=0.0),
    )
    plan = eng.plan((0, 0), (600, 0), rng=rng)
    seg = [distance(plan[i - 1].point, plan[i].point) for i in range(1, len(plan))]
    third = len(seg) // 3
    edge = (sum(seg[:third]) + sum(seg[-third:])) / (2 * third)
    middle = sum(seg[third:-third]) / max(1, len(seg) - 2 * third)
    assert middle > edge  # fast in the middle, slow at the ends


def test_fitts_movement_time_increases_with_distance():
    vp = VelocityProfile(speed_variance=0.0)  # deterministic
    rng = random.Random(0)
    near = vp.movement_time(100, 20, rng)
    far = vp.movement_time(800, 20, rng)
    assert far > near


def test_overshoot_passes_target_then_corrects_back():
    rng = random.Random(5)
    target = Point(400, 0)
    plan = [MouseStep(Point(390, 0), 0.01), MouseStep(target, 0.01)]
    ov = OvershootSimulator(probability=1.0, min_distance=0.0, range_px=(8, 8))
    ov.apply(plan, target, distance=400, rng=rng)
    assert plan[-1].point == target          # still lands on target
    assert plan[-2].point.x > target.x       # but went past it first


def test_jitter_preserves_endpoints_perturbs_interior():
    rng = random.Random(6)
    pts = [Point(i * 10, 0) for i in range(10)]
    out = JitterInjector(base_amplitude=2.0, velocity_factor=0.0).inject(pts, dt=0.01, rng=rng)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert any(out[i].y != 0 for i in range(1, len(out) - 1))


def test_bezier_endpoints_anchor_curve():
    rng = random.Random(7)
    curve = BezierPathGenerator().make(Point(0, 0), Point(100, 100), rng)
    assert curve.at(0.0) == Point(0, 0)
    assert curve.at(1.0) == Point(100, 100)

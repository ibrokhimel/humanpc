"""MouseTrajectoryEngine — composes Bézier + velocity + jitter + overshoot into a
plan: a list of ``MouseStep(point, dt)`` the Bot executes against the driver.

Pure and deterministic given an rng, so it can be tested and visualised without
touching the OS.
"""

from __future__ import annotations

import math

from ...geometry import Point, distance, to_point
from .bezier import BezierPathGenerator
from .jitter import JitterInjector
from .overshoot import OvershootSimulator
from .step import MouseStep
from .velocity import VelocityProfile


class MouseTrajectoryEngine:
    def __init__(
        self,
        bezier: BezierPathGenerator | None = None,
        velocity: VelocityProfile | None = None,
        jitter: JitterInjector | None = None,
        overshoot: OvershootSimulator | None = None,
        min_steps: int = 20,
        max_steps: int = 120,
        px_per_step: float = 7.0,
        curve_slow_gain: float = 0.7,
        settle_probability: float = 0.3,
        settle_min_distance: float = 60.0,
    ):
        self.bezier = bezier or BezierPathGenerator()
        self.velocity = velocity or VelocityProfile()
        self.jitter = jitter or JitterInjector()
        self.overshoot = overshoot or OvershootSimulator()
        self.min_steps = min_steps
        self.max_steps = max_steps
        self.px_per_step = px_per_step
        self.curve_slow_gain = curve_slow_gain
        self.settle_probability = settle_probability
        self.settle_min_distance = settle_min_distance

    def _step_count(self, dist: float) -> int:
        return int(max(self.min_steps, min(self.max_steps, dist / self.px_per_step + self.min_steps)))

    def _dt_weights(self, points: list[Point]) -> list[float]:
        """Per-segment time weights: spend longer where the path curves (2/3 power
        law — angular velocity drops on tight bends, so dwell rises there)."""
        n = len(points)
        w = [1.0] * (n - 1)
        for i in range(1, n - 1):
            ax, ay = points[i].x - points[i - 1].x, points[i].y - points[i - 1].y
            bx, by = points[i + 1].x - points[i].x, points[i + 1].y - points[i].y
            la = math.hypot(ax, ay) or 1.0
            lb = math.hypot(bx, by) or 1.0
            cosang = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
            turn = math.acos(cosang) / math.pi  # 0 straight .. 1 reversal
            factor = 1.0 + self.curve_slow_gain * turn
            w[i - 1] *= factor
            w[i] *= factor
        return w

    def _settle(self, plan: list[MouseStep], target: Point, dist: float, rng) -> None:
        """Tiny residual micro-movements after landing, before the click."""
        if dist < self.settle_min_distance or rng.random() > self.settle_probability:
            return
        for _ in range(rng.randint(1, 2)):
            off = Point(target.x + rng.gauss(0, 0.6), target.y + rng.gauss(0, 0.6))
            plan.append(MouseStep(off, rng.uniform(0.01, 0.03)))
        plan.append(MouseStep(target, rng.uniform(0.01, 0.02)))

    def plan(
        self,
        start,
        target,
        rng,
        target_size: tuple[int, int] = (20, 20),
        speed_multiplier: float = 1.0,
    ) -> list[MouseStep]:
        start = to_point(start)
        target = to_point(target)
        dist = distance(start, target)
        if dist < 1.0:
            return [MouseStep(target, 0.0)]

        steps = self._step_count(dist)
        curve = self.bezier.make(start, target, rng)

        # Sample at eased (asymmetric) parameters -> accel/cruise/long-decel.
        params = self.velocity.eased_params(steps, rng)
        points = [curve.at(u) for u in params]
        points[0] = start
        points[-1] = target  # land exactly on the target

        width = min(target_size) if target_size else 20
        total = self.velocity.movement_time(dist, width, rng) * max(0.1, speed_multiplier)

        # Distribute the total time across segments, weighted by local curvature.
        weights = self._dt_weights(points)
        wsum = sum(weights) or 1.0
        dts = [total * w / wsum for w in weights]

        points = self.jitter.inject(points, total / (steps - 1), rng)

        plan = [MouseStep(points[0], 0.0)]
        plan.extend(MouseStep(points[i], dts[i - 1]) for i in range(1, len(points)))

        self.overshoot.apply(plan, target, dist, rng)
        self._settle(plan, target, dist, rng)
        return plan

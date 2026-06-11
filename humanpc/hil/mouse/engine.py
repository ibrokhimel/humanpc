"""MouseTrajectoryEngine — composes Bézier + velocity + jitter + overshoot into a
plan: a list of ``MouseStep(point, dt)`` the Bot executes against the driver.

Pure and deterministic given an rng, so it can be tested and visualised without
touching the OS.
"""

from __future__ import annotations

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
    ):
        self.bezier = bezier or BezierPathGenerator()
        self.velocity = velocity or VelocityProfile()
        self.jitter = jitter or JitterInjector()
        self.overshoot = overshoot or OvershootSimulator()
        self.min_steps = min_steps
        self.max_steps = max_steps
        self.px_per_step = px_per_step

    def _step_count(self, dist: float) -> int:
        return int(max(self.min_steps, min(self.max_steps, dist / self.px_per_step + self.min_steps)))

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

        # Sample at eased parameters -> non-uniform spacing -> accel/cruise/decel.
        params = [self.velocity.easing(k / (steps - 1)) for k in range(steps)]
        points = [curve.at(u) for u in params]
        points[0] = start
        points[-1] = target  # land exactly on the target

        width = min(target_size) if target_size else 20
        total = self.velocity.movement_time(dist, width, rng) * max(0.1, speed_multiplier)
        dt = total / (steps - 1)

        points = self.jitter.inject(points, dt, rng)

        plan = [MouseStep(points[0], 0.0)]
        plan.extend(MouseStep(p, dt) for p in points[1:])

        self.overshoot.apply(plan, target, dist, rng)
        return plan

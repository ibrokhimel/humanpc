"""Target overshoot + correction.

For longer moves, humans frequently sail slightly past a target and snap back. We
replace the final landing point with a point just beyond the target, then append a
quick correction back onto the target so the cursor still ends exactly on it.
"""

from __future__ import annotations

import math

from ...geometry import Point
from .step import MouseStep


class OvershootSimulator:
    def __init__(
        self,
        probability: float = 0.35,
        min_distance: float = 180.0,
        range_px: tuple[float, float] = (6.0, 16.0),
    ):
        self.probability = probability
        self.min_distance = min_distance
        self.range_px = range_px

    def apply(self, plan: list[MouseStep], target: Point, distance: float, rng) -> list[MouseStep]:
        if distance < self.min_distance or len(plan) < 2:
            return plan
        if rng.random() > self.probability:
            return plan

        prev = plan[-2].point
        dx = target.x - prev.x
        dy = target.y - prev.y
        d = math.hypot(dx, dy) or 1.0
        overshoot_px = rng.uniform(*self.range_px)
        beyond = Point(target.x + dx / d * overshoot_px, target.y + dy / d * overshoot_px)

        last_dt = plan[-1].dt
        plan[-1] = MouseStep(beyond, last_dt)
        plan.append(MouseStep(target, rng.uniform(0.04, 0.09)))  # correction back
        return plan

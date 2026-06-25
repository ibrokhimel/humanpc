"""Target overshoot + corrective submovements.

The optimized-submovement model of human aiming: a fast ballistic phase often
sails slightly past the target, then **one or more decaying corrective
submovements** home in. We replace the final landing point with a point just
beyond the target, then approach back with a small number of corrections each
covering most (but not all) of the remaining error, so the cursor converges from
the overshoot side and lands exactly on the target.
"""

from __future__ import annotations

import math

from ...geometry import Point
from .step import MouseStep


class OvershootSimulator:
    def __init__(
        self,
        probability: float = 0.5,
        min_distance: float = 110.0,
        range_px: tuple[float, float] = (8.0, 18.0),
        corrections: tuple[int, int] = (1, 2),
        gain_range: tuple[float, float] = (0.6, 0.8),
    ):
        self.probability = probability
        self.min_distance = min_distance
        self.range_px = range_px
        self.corrections = corrections
        self.gain_range = gain_range

    def apply(self, plan: list[MouseStep], target: Point, distance: float, rng) -> list[MouseStep]:
        if distance < self.min_distance or len(plan) < 2:
            return plan
        if rng.random() > self.probability:
            return plan

        # Approach direction from a point clearly BEFORE the target. Using the
        # immediate predecessor is unstable: after jitter it sits ~1 px from the
        # target, so target-prev is a tiny noise vector that normalises to a random
        # direction — the cursor then 'overshoots' sideways/backward (a glitch).
        prev = plan[0].point
        for st in reversed(plan[:-1]):
            if math.hypot(target.x - st.point.x, target.y - st.point.y) >= 14.0:
                prev = st.point
                break
        dx = target.x - prev.x
        dy = target.y - prev.y
        d = math.hypot(dx, dy) or 1.0
        overshoot_px = rng.uniform(*self.range_px)
        beyond = Point(target.x + dx / d * overshoot_px, target.y + dy / d * overshoot_px)

        last_dt = plan[-1].dt
        plan[-1] = MouseStep(beyond, last_dt)

        # Decaying corrective submovements: each closes most of the remaining gap.
        n = rng.randint(*self.corrections)
        cur = beyond
        for _ in range(max(1, n) - 1):
            gain = rng.uniform(*self.gain_range)
            cur = Point(cur.x + (target.x - cur.x) * gain, cur.y + (target.y - cur.y) * gain)
            plan.append(MouseStep(cur, rng.uniform(0.03, 0.07)))
        plan.append(MouseStep(target, rng.uniform(0.04, 0.09)))  # final exact landing
        return plan

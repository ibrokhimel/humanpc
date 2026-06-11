"""Velocity model: Fitts-law movement time + easing functions.

The engine samples the Bézier curve at *eased parameters* with a uniform time
step, which yields accelerate -> cruise -> decelerate for free: where the easing
is flat (near the ends) sample points cluster, so each uniform-time step covers
little distance (slow); where the easing is steep (middle) points spread out (fast).
"""

from __future__ import annotations

import math


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    return 1 - math.pow(-2 * t + 2, 3) / 2


def ease_in_out_quad(t: float) -> float:
    if t < 0.5:
        return 2 * t * t
    return 1 - math.pow(-2 * t + 2, 2) / 2


EASINGS = {
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_in_out_quad": ease_in_out_quad,
}


class VelocityProfile:
    def __init__(
        self,
        fitts_a: float = 0.1,
        fitts_b: float = 0.2,
        easing: str = "ease_in_out_cubic",
        speed_variance: float = 0.15,
    ):
        self.fitts_a = fitts_a
        self.fitts_b = fitts_b
        self.easing = EASINGS.get(easing, ease_in_out_cubic)
        self.speed_variance = speed_variance

    def movement_time(self, distance: float, target_width: float, rng) -> float:
        """Fitts' law: MT = a + b * log2(2D/W + 1), with human variance."""
        width = max(1.0, target_width)
        index_of_difficulty = math.log2(2 * distance / width + 1)
        mt = self.fitts_a + self.fitts_b * index_of_difficulty
        if self.speed_variance:
            mt *= max(0.4, rng.gauss(1.0, self.speed_variance))
        return max(0.05, mt)

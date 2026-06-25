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


def _beta_velocity(s: float, peak: float, sharpness: float) -> float:
    """Bell-shaped velocity with its mode at ``peak`` (a Beta-like density).

    p, q are chosen so the mode (p-1)/(p+q-2) == ``peak``; a ``peak`` below 0.5
    yields a right-skewed profile (short acceleration, long deceleration), which
    is what real aimed movements show — unlike a symmetric easing.
    """
    if s <= 0.0 or s >= 1.0:
        return 0.0
    p = 1.0 + sharpness * peak
    q = 1.0 + sharpness * (1.0 - peak)
    return (s ** (p - 1.0)) * ((1.0 - s) ** (q - 1.0))


class VelocityProfile:
    def __init__(
        self,
        fitts_a: float = 0.1,
        fitts_b: float = 0.2,
        easing: str = "ease_in_out_cubic",
        speed_variance: float = 0.15,
        asymmetric: bool = True,
        peak_velocity_frac: float = 0.42,
        asymmetry: float = 4.0,
    ):
        self.fitts_a = fitts_a
        self.fitts_b = fitts_b
        self.easing = EASINGS.get(easing, ease_in_out_cubic)
        self.speed_variance = speed_variance
        self.asymmetric = asymmetric
        self.peak_velocity_frac = peak_velocity_frac
        self.asymmetry = asymmetry

    def movement_time(self, distance: float, target_width: float, rng) -> float:
        """Fitts' law: MT = a + b * log2(2D/W + 1), with human variance."""
        width = max(1.0, target_width)
        index_of_difficulty = math.log2(2 * distance / width + 1)
        mt = self.fitts_a + self.fitts_b * index_of_difficulty
        if self.speed_variance:
            mt *= max(0.4, rng.gauss(1.0, self.speed_variance))
        return max(0.05, mt)

    def eased_params(self, steps: int, rng) -> list[float]:
        """The eased curve parameters u in [0, 1] sampled at uniform time.

        With ``asymmetric`` (default) the velocity peaks early and decays slowly
        (right-skewed). Otherwise falls back to the symmetric easing function.
        """
        if steps <= 1:
            return [0.0]
        if not self.asymmetric:
            return [self.easing(k / (steps - 1)) for k in range(steps)]

        peak = min(0.8, max(0.2, self.peak_velocity_frac + rng.gauss(0.0, 0.03)))
        m = max(steps * 4, 64)
        cum = [0.0]
        for j in range(m):
            cum.append(cum[-1] + _beta_velocity((j + 0.5) / m, peak, self.asymmetry))
        total = cum[-1] or 1.0
        cum = [c / total for c in cum]

        params = []
        for k in range(steps):
            idx = (k / (steps - 1)) * (len(cum) - 1)
            lo = int(idx)
            hi = min(lo + 1, len(cum) - 1)
            frac = idx - lo
            params.append(cum[lo] * (1 - frac) + cum[hi] * frac)
        params[0], params[-1] = 0.0, 1.0
        return params

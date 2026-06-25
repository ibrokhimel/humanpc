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


def _lognormal_stroke(tau: float, mu: float, sigma: float) -> float:
    """A single neuromotor stroke's speed impulse (Plamondon, 1995).

    Each rapid human movement is a vectorial sum of lognormal velocity strokes;
    one stroke's speed is lognormal in elapsed time ``tau`` since its onset —
    a fast rise to an early peak then a long right-skewed tail.
    """
    if tau <= 1e-9:
        return 0.0
    return math.exp(-((math.log(tau) - mu) ** 2) / (2.0 * sigma * sigma)) / (
        sigma * math.sqrt(2.0 * math.pi) * tau
    )


class VelocityProfile:
    def __init__(
        self,
        fitts_a: float = 0.08,
        fitts_b: float = 0.14,
        easing: str = "ease_in_out_cubic",
        speed_variance: float = 0.15,
        asymmetric: bool = True,
        peak_velocity_frac: float = 0.42,
        asymmetry: float = 4.0,
        model: str = "sigma_lognormal",
        corrective_strokes: tuple[int, int] = (1, 2),
    ):
        self.fitts_a = fitts_a
        self.fitts_b = fitts_b
        self.easing = EASINGS.get(easing, ease_in_out_cubic)
        self.speed_variance = speed_variance
        self.asymmetric = asymmetric
        self.peak_velocity_frac = peak_velocity_frac
        self.asymmetry = asymmetry
        self.model = model
        self.corrective_strokes = corrective_strokes

    def movement_time(self, distance: float, target_width: float, rng) -> float:
        """Fitts' law: MT = a + b * log2(2D/W + 1), with human variance."""
        width = max(1.0, target_width)
        index_of_difficulty = math.log2(2 * distance / width + 1)
        mt = self.fitts_a + self.fitts_b * index_of_difficulty
        if self.speed_variance:
            mt *= max(0.4, rng.gauss(1.0, self.speed_variance))
        return max(0.05, mt)

    def _velocity_curve(self, m: int, rng) -> list[float]:
        """Speed sampled on a fine ``m``-point time grid over [0, 1].

        ``sigma_lognormal`` (default) sums a primary lognormal stroke with 1-2
        smaller, later corrective strokes — the Sigma-Lognormal model: a primary
        ballistic impulse plus overlapping homing/correction sub-movements (the
        AG1/AG2 agonist bursts). ``beta`` keeps the older single right-skewed bell.
        """
        if self.model != "sigma_lognormal":
            peak = min(0.8, max(0.2, self.peak_velocity_frac + rng.gauss(0.0, 0.06)))
            return [_beta_velocity((j + 0.5) / m, peak, self.asymmetry) for j in range(m)]

        # Primary stroke: peak (mode) lands at ~peak_velocity_frac of the move.
        peak = min(0.5, max(0.30, self.peak_velocity_frac + rng.gauss(0.0, 0.04)))
        sig_p = min(0.6, max(0.32, rng.gauss(0.42, 0.06)))
        strokes = [(0.0, math.log(peak) + sig_p * sig_p, sig_p, 1.0)]
        # Overlapping corrective strokes (homing): later onset, small amplitude.
        for _ in range(rng.randint(*self.corrective_strokes)):
            t0 = rng.uniform(0.42, 0.72)
            sig_c = min(0.6, max(0.30, rng.gauss(0.40, 0.05)))
            lag = rng.uniform(0.16, 0.30)  # corrective peaks this long after onset
            strokes.append((t0, math.log(lag) + sig_c * sig_c, sig_c, rng.uniform(0.05, 0.12)))

        out = []
        for j in range(m):
            t = (j + 0.5) / m
            out.append(sum(d * _lognormal_stroke(t - t0, mu, sig) for (t0, mu, sig, d) in strokes))
        return out

    def eased_params(self, steps: int, rng) -> list[float]:
        """The curve parameters u in [0, 1] sampled at uniform time.

        With ``asymmetric`` (default) the velocity follows the Sigma-Lognormal
        model — an early peak (~40-50%) with a long right-skewed tail and homing
        sub-movements. Otherwise falls back to the symmetric easing function.
        """
        if steps <= 1:
            return [0.0]
        if not self.asymmetric:
            return [self.easing(k / (steps - 1)) for k in range(steps)]

        m = max(steps * 4, 64)
        vel = self._velocity_curve(m, rng)
        cum = [0.0]
        for v in vel:
            cum.append(cum[-1] + max(0.0, v))
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

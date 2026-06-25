"""Per-step jitter so the path is never mathematically perfect.

Amplitude scales with local speed (the distance between consecutive points): fast
mid-flight segments wobble more, the slow approach near the target stays precise.
Endpoints are never perturbed so the cursor still starts and lands exactly where
intended.

By default the offsets are **colored** — 1/f pink wander plus an 8-12 Hz tremor
(``noise.py``) — instead of independent white Gaussian draws. White noise has a
flat power spectrum that synthetic-trace detectors key on; real motor noise is
autocorrelated and carries a tremor band. Set ``colored=False`` for the old
behaviour.
"""

from __future__ import annotations

from ...geometry import Point, distance
from .noise import PinkNoise, Tremor


class JitterInjector:
    def __init__(
        self,
        base_amplitude: float = 0.6,
        velocity_factor: float = 0.08,
        max_amplitude: float = 3.5,
        colored: bool = True,
        tremor_amplitude: float = 0.35,
    ):
        self.base_amplitude = base_amplitude
        self.velocity_factor = velocity_factor
        self.max_amplitude = max_amplitude
        self.colored = colored
        self.tremor_amplitude = tremor_amplitude

    def inject(self, points: list[Point], dt: float, rng) -> list[Point]:
        if len(points) <= 2 or self.base_amplitude <= 0 and self.velocity_factor <= 0:
            return points

        if self.colored:
            px, py = PinkNoise(), PinkNoise()
            tx = Tremor(amplitude=self.tremor_amplitude).reset(rng)
            ty = Tremor(amplitude=self.tremor_amplitude).reset(rng)

        out = [points[0]]
        t = 0.0
        for i in range(1, len(points) - 1):
            seg = distance(points[i - 1], points[i])
            amp = min(self.max_amplitude, self.base_amplitude + seg * self.velocity_factor)
            t += dt
            if self.colored:
                ox = amp * px.next(rng) + tx.at(t)
                oy = amp * py.next(rng) + ty.at(t)
            else:
                ox = rng.gauss(0, amp)
                oy = rng.gauss(0, amp)
            out.append(Point(points[i].x + ox, points[i].y + oy))
        out.append(points[-1])
        return out

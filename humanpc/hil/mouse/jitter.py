"""Per-step Gaussian jitter so the path is never mathematically perfect.

Amplitude scales with local speed (here, the distance between consecutive points,
since the time step is uniform): fast mid-flight segments wobble more, the slow
approach near the target stays precise. Endpoints are never perturbed so the
cursor still starts and lands exactly where intended.
"""

from __future__ import annotations

from ...geometry import Point, distance


class JitterInjector:
    def __init__(
        self,
        base_amplitude: float = 0.6,
        velocity_factor: float = 0.08,
        max_amplitude: float = 3.5,
    ):
        self.base_amplitude = base_amplitude
        self.velocity_factor = velocity_factor
        self.max_amplitude = max_amplitude

    def inject(self, points: list[Point], dt: float, rng) -> list[Point]:
        if len(points) <= 2 or self.base_amplitude <= 0 and self.velocity_factor <= 0:
            return points
        out = [points[0]]
        for i in range(1, len(points) - 1):
            seg = distance(points[i - 1], points[i])
            amp = min(self.max_amplitude, self.base_amplitude + seg * self.velocity_factor)
            out.append(Point(points[i].x + rng.gauss(0, amp), points[i].y + rng.gauss(0, amp)))
        out.append(points[-1])
        return out

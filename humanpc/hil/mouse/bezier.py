"""Cubic Bézier path generation.

Both control points are pushed to the *same* side of the straight line so the
curve is a gentle C, never an unnatural S. The curve can be evaluated at any
parameter ``u`` in [0, 1]; the engine samples it at eased parameters to shape the
velocity profile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ...geometry import Point


@dataclass
class CubicBezier:
    p0: Point
    p1: Point
    p2: Point
    p3: Point

    def at(self, u: float) -> Point:
        mu = 1.0 - u
        a = mu * mu * mu
        b = 3 * mu * mu * u
        c = 3 * mu * u * u
        d = u * u * u
        return Point(
            a * self.p0.x + b * self.p1.x + c * self.p2.x + d * self.p3.x,
            a * self.p0.y + b * self.p1.y + c * self.p2.y + d * self.p3.y,
        )


class BezierPathGenerator:
    def __init__(self, curve_strength: float = 0.3, control_variance: float = 0.2):
        self.curve_strength = curve_strength
        self.control_variance = control_variance

    def make(self, start: Point, end: Point, rng) -> CubicBezier:
        dx = end.x - start.x
        dy = end.y - start.y
        dist = math.hypot(dx, dy) or 1.0

        # Unit perpendicular to the direct path.
        perp_x = -dy / dist
        perp_y = dx / dist

        side = rng.choice((-1.0, 1.0))
        base_offset = dist * 0.12 * self.curve_strength * rng.uniform(0.6, 1.4)

        t1 = rng.uniform(0.2, 0.4)
        t2 = rng.uniform(0.6, 0.8)
        v = self.control_variance
        o1 = base_offset * side * rng.uniform(1 - v, 1 + v)
        o2 = base_offset * side * rng.uniform(1 - v, 1 + v)

        p1 = Point(start.x + dx * t1 + perp_x * o1, start.y + dy * t1 + perp_y * o1)
        p2 = Point(start.x + dx * t2 + perp_x * o2, start.y + dy * t2 + perp_y * o2)
        return CubicBezier(start, p1, p2, end)

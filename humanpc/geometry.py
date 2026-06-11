"""Lightweight, dependency-free geometry primitives.

Coordinates are screen pixels. ``Point`` carries floats so sub-pixel paths (used
by the Human Interaction Layer in Phase 1) stay smooth; round only at the driver
boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def as_int(self) -> tuple[int, int]:
        return (round(self.x), round(self.y))

    def __iter__(self):
        yield self.x
        yield self.y


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle: top-left (x, y) plus width/height."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2, self.y + self.height / 2)

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def contains(self, point) -> bool:
        px, py = _coords(point)
        return self.x <= px <= self.right and self.y <= py <= self.bottom

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


def to_point(obj) -> Point:
    """Coerce a Point / (x, y) tuple / Rect-center into a Point."""
    if isinstance(obj, Point):
        return obj
    if isinstance(obj, Rect):
        return obj.center
    if isinstance(obj, (tuple, list)) and len(obj) == 2:
        return Point(float(obj[0]), float(obj[1]))
    raise TypeError(f"cannot interpret {obj!r} as a Point")


def _coords(obj) -> tuple[float, float]:
    p = to_point(obj)
    return (p.x, p.y)


def distance(a, b) -> float:
    ax, ay = _coords(a)
    bx, by = _coords(b)
    return math.hypot(bx - ax, by - ay)

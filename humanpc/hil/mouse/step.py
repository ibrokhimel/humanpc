"""A single planned mouse step. Kept in its own module to avoid an import cycle
between the engine and the overshoot simulator."""

from __future__ import annotations

from dataclasses import dataclass

from ...geometry import Point


@dataclass
class MouseStep:
    point: Point
    dt: float  # seconds to wait AFTER moving the cursor to ``point``

"""Target and result types for the resolver.

A *target* (what you pass to ``bot.click(...)``) can be:
  - ``str``            -> text, found via UIA then OCR
  - ``(x, y)``         -> a point
  - ``(x, y, w, h)`` / ``Rect`` / ``Region`` -> a region (click its centre)
  - ``Image(...)``     -> an on-screen picture, found via template match
  - ``Locator(...)``   -> a structured UIA query
  - ``Match`` / ``Point`` -> passed straight through

A *Match* is the resolved result: a bounding box plus how it was found. Its
``size`` feeds the Fitts-law model so small controls get a slower, more careful
approach.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry import Point, Rect, to_point

# A Region is just a Rect with a friendlier name in targeting contexts.
Region = Rect


@dataclass
class Match:
    bbox: Rect
    confidence: float = 1.0
    method: str = "coords"            # coords | region | uia | ocr | template
    text: str | None = None
    handle: object | None = None      # native UIA element, when available

    @property
    def center(self) -> Point:
        return self.bbox.center

    @property
    def size(self) -> tuple[int, int]:
        return self.bbox.size

    @classmethod
    def from_point(cls, point, size: tuple[int, int] = (10, 10), method: str = "coords") -> "Match":
        p = to_point(point)
        w, h = size
        return cls(Rect(round(p.x) - w // 2, round(p.y) - h // 2, w, h), 1.0, method)

    @classmethod
    def from_rect(cls, rect: Rect, method: str = "region", confidence: float = 1.0) -> "Match":
        return cls(rect, confidence, method)


@dataclass
class Image:
    """A picture to locate on screen (template matching)."""

    source: object                    # file path (str), numpy array, or PIL.Image
    confidence: float = 0.8
    grayscale: bool = True
    scales: tuple[float, ...] = (1.0,)
    region: Rect | None = None


@dataclass
class Locator:
    """A structured query, primarily for UI Automation."""

    text: str | None = None           # falls back to text (UIA name / OCR) search
    name: str | None = None           # UIA Name
    control_type: str | None = None   # e.g. "Button", "Edit"
    automation_id: str | None = None
    window: str | None = None         # title regex to scope the search
    index: int = 0
    region: Rect | None = None

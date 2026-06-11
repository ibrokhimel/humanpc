"""Targeting: turn a target (text / image / coords / locator) into a screen Match.

UIA finds, OCR/template back it up, coordinates pass through — the resolved Match's
size then feeds the Fitts-law model so the Bot approaches small controls carefully.
"""

from __future__ import annotations

from .resolver import Resolver
from .types import Image, Locator, Match, Region

__all__ = ["Resolver", "Match", "Image", "Locator", "Region"]

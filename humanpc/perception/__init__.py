"""Perception: how the bot sees the screen (capture + coordinate correctness).

Phase 0 ships DPI awareness and screen capture. OCR / template matching arrive in
Phase 2 (the targeting resolver).
"""

from __future__ import annotations

from .dpi import set_dpi_awareness
from .screen import Screen

__all__ = ["set_dpi_awareness", "Screen"]

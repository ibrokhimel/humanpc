"""Parse a string into a target (for the CLI, flows, and servers).

  "300,200"        -> point (x, y)
  "10,20,60,24"    -> region (x, y, w, h)
  "button.png"     -> Image (template match)
  "Login"          -> text (UIA / OCR)
"""

from __future__ import annotations

import os
import re

from .types import Image

_COORD2 = re.compile(r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*$")
_COORD4 = re.compile(r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$")
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def parse_target(value):
    if not isinstance(value, str):
        return value  # already a target object / coords
    m = _COORD4.match(value)
    if m:
        return tuple(int(g) for g in m.groups())
    m = _COORD2.match(value)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    if os.path.splitext(value)[1].lower() in _IMAGE_EXTS:
        return Image(value)
    return value

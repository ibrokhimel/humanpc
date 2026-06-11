"""Screen capture via mss (lazy-loaded).

``mss`` and ``Pillow`` are optional (``pip install humanpc[capture]``). They are
imported only when a capture method is called, so ``import humanpc`` works on a
bare interpreter.
"""

from __future__ import annotations

from ..exceptions import DriverError
from ..geometry import Rect


class Screen:
    def __init__(self):
        self._sct = None

    def _backend(self):
        if self._sct is None:
            try:
                import mss
            except ImportError as exc:
                raise DriverError(
                    "screen capture needs mss: pip install humanpc[capture]"
                ) from exc
            self._sct = mss.mss()
        return self._sct

    def size(self) -> tuple[int, int]:
        """Virtual desktop size (all monitors combined)."""
        bbox = self._backend().monitors[0]
        return (bbox["width"], bbox["height"])

    def monitors(self) -> list[Rect]:
        """Per-monitor rectangles (excludes the combined virtual desktop)."""
        return [
            Rect(m["left"], m["top"], m["width"], m["height"])
            for m in self._backend().monitors[1:]
        ]

    def capture(self, region: Rect | None = None):
        """Grab a screenshot as a PIL.Image. Whole virtual desktop if no region."""
        try:
            from PIL import Image
        except ImportError as exc:
            raise DriverError(
                "capture needs Pillow: pip install humanpc[capture]"
            ) from exc
        sct = self._backend()
        if region is None:
            box = sct.monitors[0]
        else:
            box = {
                "left": region.x,
                "top": region.y,
                "width": region.width,
                "height": region.height,
            }
        shot = sct.grab(box)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def save(self, path: str, region: Rect | None = None) -> str:
        self.capture(region).save(path)
        return path

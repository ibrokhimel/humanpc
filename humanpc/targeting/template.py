"""Template matching via OpenCV (lazy-loaded).

Finds a sub-image on screen. ``find`` accepts an explicit ``haystack`` array (used
by tests) or captures the screen when none is given. Multi-scale: tries each scale
in ``Image.scales`` and keeps the best.
"""

from __future__ import annotations

from ..exceptions import DriverError
from ..geometry import Rect
from .types import Image, Match


class TemplateFinder:
    def __init__(self, screen=None):
        self.screen = screen

    def _cv(self):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise DriverError(
                "template matching needs opencv-python + numpy: pip install humanpc[vision]"
            ) from exc
        return cv2, np

    def _to_bgr(self, src, cv2, np):
        if isinstance(src, str):
            img = cv2.imread(src, cv2.IMREAD_COLOR)
            if img is None:
                raise DriverError(f"could not read image file: {src}")
            return img
        if isinstance(src, np.ndarray):
            return src
        arr = np.array(src.convert("RGB"))  # assume PIL.Image
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    def _capture_bgr(self, cv2, np, region):
        if self.screen is None:
            from ..perception.screen import Screen
            self.screen = Screen()
        pil = self.screen.capture(region)
        arr = np.array(pil.convert("RGB"))
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    def find(self, image, *, haystack=None, region=None, confidence=None, scales=None) -> Match | None:
        cv2, np = self._cv()
        spec = image if isinstance(image, Image) else Image(image)
        conf = confidence if confidence is not None else spec.confidence
        region = region if region is not None else spec.region

        needle = self._to_bgr(spec.source, cv2, np)
        if haystack is None:
            hay = self._capture_bgr(cv2, np, region)
            ox, oy = (region.x, region.y) if region is not None else (0, 0)
        else:
            hay = haystack if isinstance(haystack, np.ndarray) else self._to_bgr(haystack, cv2, np)
            ox, oy = 0, 0

        if spec.grayscale:
            hay_m = cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY)
            needle_m = cv2.cvtColor(needle, cv2.COLOR_BGR2GRAY)
        else:
            hay_m, needle_m = hay, needle

        best = None  # (score, x, y, w, h)
        for s in (scales or spec.scales or (1.0,)):
            n = needle_m if s == 1.0 else cv2.resize(needle_m, None, fx=s, fy=s)
            if n.shape[0] > hay_m.shape[0] or n.shape[1] > hay_m.shape[1]:
                continue
            result = cv2.matchTemplate(hay_m, n, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if best is None or max_val > best[0]:
                best = (max_val, max_loc[0], max_loc[1], n.shape[1], n.shape[0])

        if best is None or best[0] < conf:
            return None
        score, x, y, w, h = best
        return Match(Rect(int(x) + ox, int(y) + oy, int(w), int(h)), float(score), "template")

    def find_all(
        self,
        image,
        *,
        haystack=None,
        region=None,
        confidence=None,
        max_results: int = 50,
        min_distance: int | None = None,
    ) -> list[Match]:
        cv2, np = self._cv()
        spec = image if isinstance(image, Image) else Image(image)
        conf = confidence if confidence is not None else spec.confidence

        needle = self._to_bgr(spec.source, cv2, np)
        if haystack is None:
            hay = self._capture_bgr(cv2, np, region)
            ox, oy = (region.x, region.y) if region is not None else (0, 0)
        else:
            hay = haystack if isinstance(haystack, np.ndarray) else self._to_bgr(haystack, cv2, np)
            ox, oy = 0, 0

        if spec.grayscale:
            hay_m = cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY)
            needle_m = cv2.cvtColor(needle, cv2.COLOR_BGR2GRAY)
        else:
            hay_m, needle_m = hay, needle

        h, w = needle_m.shape[:2]
        if h > hay_m.shape[0] or w > hay_m.shape[1]:
            return []
        result = cv2.matchTemplate(hay_m, needle_m, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(result >= conf)
        candidates = sorted(
            ((float(result[y, x]), int(x), int(y)) for x, y in zip(xs, ys)),
            reverse=True,
        )
        md = min_distance if min_distance is not None else max(1, max(w, h) // 2)

        kept: list[tuple[float, int, int]] = []
        for score, x, y in candidates:
            if all(max(abs(x - kx), abs(y - ky)) >= md for _, kx, ky in kept):
                kept.append((score, x, y))
                if len(kept) >= max_results:
                    break
        return [
            Match(Rect(x + ox, y + oy, w, h), score, "template")
            for score, x, y in kept
        ]

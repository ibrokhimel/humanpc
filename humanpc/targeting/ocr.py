"""OCR text finding.

The matching logic (locate a word or phrase among recognised word-boxes) is pure
and unit-tested via an injected ``backend``. Two real backends are attempted when
none is injected — Windows OCR (``winocr``) then ``pytesseract`` — each best-effort
and wrapped so a missing/failing backend simply yields no result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..exceptions import DriverError
from ..geometry import Rect
from .types import Match

_NORM = re.compile(r"[^a-z0-9 ]+")


def _norm(s: str) -> str:
    return _NORM.sub("", s.lower()).strip()


def _union(a: Rect, b: Rect) -> Rect:
    x0 = min(a.x, b.x)
    y0 = min(a.y, b.y)
    x1 = max(a.right, b.right)
    y1 = max(a.bottom, b.bottom)
    return Rect(x0, y0, x1 - x0, y1 - y0)


@dataclass
class Word:
    text: str
    bbox: Rect
    confidence: float = 1.0


class OCRFinder:
    def __init__(self, screen=None, backend=None):
        self.screen = screen
        self._backend = backend  # callable(image) -> list[Word]

    def _capture(self, region):
        if self.screen is None:
            from ..perception.screen import Screen
            self.screen = Screen()
        return self.screen.capture(region)

    def _ocr(self, image) -> list[Word]:
        if self._backend is not None:
            return self._backend(image)
        for adapter in (_winocr_words, _tesseract_words):
            words = adapter(image)
            if words is not None:
                return words
        raise DriverError(
            "no OCR backend available: pip install winocr (Windows) or pytesseract"
        )

    def find(self, text, *, image=None, region=None) -> Match | None:
        target = _norm(text)
        if not target:
            return None
        words = self._ocr(image if image is not None else self._capture(region))
        ox, oy = (region.x, region.y) if (image is None and region is not None) else (0, 0)

        norm_words = [(_norm(w.text), w) for w in words]
        tokens = target.split()
        best = None  # (confidence, bbox)

        # Match the target as a run of consecutive recognised words.
        for i in range(len(norm_words)):
            bbox = None
            conf = 1.0
            ok = True
            for k, tok in enumerate(tokens):
                if i + k >= len(norm_words) or norm_words[i + k][0] != tok:
                    ok = False
                    break
                w = norm_words[i + k][1]
                bbox = w.bbox if bbox is None else _union(bbox, w.bbox)
                conf = min(conf, w.confidence)
            if ok and bbox is not None and (best is None or conf > best[0]):
                best = (conf, bbox)

        # Fallback: target contained within a single recognised token.
        if best is None:
            for wnorm, w in norm_words:
                if target in wnorm:
                    best = (w.confidence, w.bbox)
                    break

        if best is None:
            return None
        conf, bbox = best
        return Match(Rect(bbox.x + ox, bbox.y + oy, bbox.width, bbox.height), float(conf), "ocr", text=text)


def _winocr_words(image):
    try:
        import winocr
    except Exception:
        return None
    try:
        result = winocr.recognize_pil_sync(image, "en")
        words = []
        for line in result.lines:
            for w in line.words:
                r = w.bounding_rect
                words.append(Word(w.text, Rect(int(r.x), int(r.y), int(r.width), int(r.height))))
        return words
    except Exception:
        return None


def _tesseract_words(image):
    try:
        import pytesseract
    except Exception:
        return None
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        words = []
        for i, txt in enumerate(data["text"]):
            if not txt.strip():
                continue
            conf = data["conf"][i]
            conf = float(conf) / 100 if str(conf) not in ("-1", "") else 0.0
            words.append(
                Word(txt, Rect(data["left"][i], data["top"][i], data["width"][i], data["height"][i]), conf)
            )
        return words
    except Exception:
        return None

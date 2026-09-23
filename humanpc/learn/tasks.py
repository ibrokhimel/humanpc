"""Task catalogue + randomized sampler for the movement trainer.

Each ``Task`` is plain data (kind + JSON-able params in screen pixels) so it can
be stored next to the recording and later used as the conditioning "prompt" for
a learned model. Sampling is weighted per kind; weights can be overridden (e.g.
by a future detector that asks for more of the movements it catches most).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

KINDS = ("point", "double", "right", "drag", "scroll", "scroll_click", "trace", "read", "chain")

DEFAULT_WEIGHTS = {
    "point": 3.0,
    "double": 1.0,
    "right": 1.0,
    "drag": 1.5,
    "scroll": 1.5,
    "scroll_click": 1.0,
    "trace": 1.0,
    "read": 0.5,
    "chain": 1.5,
}

SCROLL_CONTENT = 20000  # virtual page height (px) for scroll tasks
START_RADIUS = 16

READ_TEXTS = (
    "Take a moment and read this line normally. Rest your hand on the mouse the way "
    "you usually do. When the Done button appears, click it whenever you are ready.",
    "Humans rarely hold the mouse perfectly still. Small drifts, tiny corrections and "
    "idle nudges happen while reading. Just read naturally, then press Done.",
    "The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor "
    "jugs. Read at your usual pace and click Done when it shows up.",
    "Think about what you might have for dinner tonight. There is no right answer. "
    "When you have decided, click the Done button.",
    "Glance around this paragraph as you would a web page you are skimming. Do not "
    "rush. The Done button will appear after a few seconds.",
)


@dataclass
class Task:
    kind: str
    params: dict

    def to_dict(self) -> dict:
        return {"kind": self.kind, "params": self.params}


def _log_uniform(rng: random.Random, lo: float, hi: float) -> float:
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


class TaskSampler:
    """Draws random tasks that fit inside a ``width`` x ``height`` screen."""

    def __init__(self, width: int, height: int, *, rng: random.Random | None = None,
                 weights: dict | None = None, margin: int = 60):
        self.w, self.h = int(width), int(height)
        self.rng = rng or random.Random()
        self.margin = margin
        merged = dict(DEFAULT_WEIGHTS)
        if weights:
            merged.update({k: float(v) for k, v in weights.items() if k in DEFAULT_WEIGHTS})
        self.weights = {k: max(0.0, v) for k, v in merged.items()}
        if not any(self.weights.values()):
            raise ValueError("at least one task weight must be positive")

    # -- helpers ---------------------------------------------------------------
    @property
    def max_dist(self) -> float:
        return math.hypot(self.w - 2 * self.margin, self.h - 2 * self.margin)

    def _point_in(self, pad: float = 0.0) -> tuple[int, int]:
        m = self.margin + pad
        return (round(self.rng.uniform(m, self.w - m)), round(self.rng.uniform(m + 30, self.h - m)))

    def _inside(self, x: float, y: float, pad: float = 0.0) -> bool:
        m = self.margin + pad
        return m <= x <= self.w - m and m + 30 <= y <= self.h - m

    def _pair(self, min_d: float, max_d: float, pad: float = 0.0):
        """Two points ``dist`` apart (log-uniform), both on screen."""
        max_d = max(min_d + 1, min(max_d, self.max_dist * 0.95))
        for _ in range(200):
            d = _log_uniform(self.rng, min_d, max_d)
            a = self._point_in(pad)
            ang = self.rng.uniform(0, 2 * math.pi)
            b = (round(a[0] + d * math.cos(ang)), round(a[1] + d * math.sin(ang)))
            if self._inside(*b, pad):
                return a, b
        return self._point_in(pad), self._point_in(pad)

    # -- kinds -----------------------------------------------------------------
    def _point(self, kind: str) -> Task:
        r = _log_uniform(self.rng, 5, 90)
        a, b = self._pair(40, self.max_dist, pad=max(r, START_RADIUS))
        return Task(kind, {"start": list(a), "start_r": START_RADIUS, "target": list(b), "r": round(r, 1)})

    def _drag(self) -> Task:
        size = round(self.rng.uniform(30, 90))
        zone = round(size * self.rng.uniform(1.5, 3.0))
        a, b = self._pair(100, self.max_dist, pad=zone / 2 + 5)
        return Task("drag", {"box": list(a), "size": size, "zone": list(b), "zone_size": zone})

    def _scroll(self, kind: str) -> Task:
        band_h = round(_log_uniform(self.rng, 60, 220))
        band_y = round(self.rng.uniform(self.h * 0.3, self.h * 0.7))
        dist = _log_uniform(self.rng, 200, 8000)
        down = self.rng.random() < 0.75
        offset = round(self.rng.uniform(0, SCROLL_CONTENT - self.h)) if not down else \
            round(self.rng.uniform(0, max(0.0, SCROLL_CONTENT - self.h - dist)))
        line = offset + band_y + (dist if down else -dist)
        line = round(min(max(line, band_y), SCROLL_CONTENT - (self.h - band_y)))
        p = {"offset": offset, "line": line, "band_y": band_y, "band_h": band_h,
             "content": SCROLL_CONTENT}
        if kind == "scroll_click":
            p["click_x"] = round(self.rng.uniform(self.margin + 40, self.w - self.margin - 40))
            p["r"] = round(_log_uniform(self.rng, 14, 40), 1)
        return Task(kind, p)

    def _trace(self) -> Task:
        width = round(self.rng.uniform(24, 70))
        (x0, y0), (x3, y3) = self._pair(300, self.max_dist, pad=width)
        c1, c2 = self._point_in(width), self._point_in(width)
        pts = []
        n = 60
        for i in range(n + 1):
            t = i / n
            u = 1 - t
            x = u**3 * x0 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * x3
            y = u**3 * y0 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * y3
            pts.append([round(x), round(y)])
        return Task("trace", {"points": pts, "width": width})

    def _read(self) -> Task:
        return Task("read", {
            "text": self.rng.choice(READ_TEXTS),
            "min_seconds": round(self.rng.uniform(5, 12), 1),
            "done": list(self._point_in(60)),
        })

    def _chain(self) -> Task:
        n = self.rng.randint(3, 6)
        r = round(_log_uniform(self.rng, 8, 40), 1)
        pts = [self._point_in(r)]
        while len(pts) < n:
            for _ in range(100):
                d = _log_uniform(self.rng, 60, self.max_dist * 0.6)
                ang = self.rng.uniform(0, 2 * math.pi)
                b = (round(pts[-1][0] + d * math.cos(ang)), round(pts[-1][1] + d * math.sin(ang)))
                if self._inside(*b, r):
                    break
            else:
                b = self._point_in(r)
            pts.append(b)
        return Task("chain", {"points": [list(p) for p in pts], "r": r})

    def make(self, kind: str) -> Task:
        if kind in ("point", "double", "right"):
            return self._point(kind)
        if kind == "drag":
            return self._drag()
        if kind in ("scroll", "scroll_click"):
            return self._scroll(kind)
        if kind == "trace":
            return self._trace()
        if kind == "read":
            return self._read()
        if kind == "chain":
            return self._chain()
        raise ValueError(f"unknown task kind: {kind}")

    def sample(self) -> Task:
        kinds = [k for k in KINDS if self.weights.get(k, 0) > 0]
        kind = self.rng.choices(kinds, weights=[self.weights[k] for k in kinds])[0]
        return self.make(kind)

"""Cursor drift while reading/thinking, replayed from the recorded "read" tasks.

The trainer's "read, then click Done" task records what the hand does while the
eyes are busy: in these recordings the cursor is in motion ~40% of the time, in
many short bouts. The model's own ``idle`` kind was trained on only ~27 such
segments and ignores the duration hint, so instead of sampling it we replay
windows of the *recorded* pre-click phase directly: a random window of the
needed length, from a random segment, rotated by a random angle (drift has no
preferred direction), clamped to a box so it can't wander off the page.
"""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

import numpy as np

from humanpc.hil.precise import precise_sleep
from humanpc.learn.ml.segments import BIN_MS, POS_SCALE, load_all

MIN_PHASE_S = 2.0


class IdleBank:
    def __init__(self, phases: list[np.ndarray]):
        self.phases = phases  # each: (n, 2) px deltas at BIN_MS

    @classmethod
    def load(cls, data_dir: Path) -> "IdleBank":
        phases = []
        for seg in load_all(data_dir):
            if seg.kind != "idle":
                continue
            a = seg.arrays
            clicks = np.flatnonzero(a["click"])
            n = int(clicks[0]) if len(clicks) else len(a["click"])
            if n * BIN_MS / 1000 >= MIN_PHASE_S:
                phases.append(np.asarray(a["dxdy"][:n], dtype=np.float64) * POS_SCALE)
        return cls(phases)

    def window(self, seconds: float, rng: random.Random) -> np.ndarray:
        """``seconds`` of drift deltas, stitched from recorded phases if needed."""
        need = max(1, int(seconds * 1000 / BIN_MS))
        out = []
        got = 0
        while got < need and self.phases:
            src = rng.choice(self.phases)
            take = min(need - got, len(src), max(1, int(rng.uniform(1.5, 4.0) * 1000 / BIN_MS)))
            i = rng.randrange(0, len(src) - take + 1)
            th = rng.uniform(0, 2 * math.pi)
            c, s = math.cos(th), math.sin(th)
            w = src[i:i + take]
            out.append(np.column_stack([w[:, 0] * c - w[:, 1] * s, w[:, 0] * s + w[:, 1] * c]))
            got += take
        return np.concatenate(out) if out else np.zeros((need, 2))

    def play(self, driver, seconds: float, rng: random.Random, *, box=None, killswitch=None) -> int:
        """Drift for ``seconds`` from the current cursor position. Returns px travelled.

        ``box`` = (x, y, w, h) screen px the cursor must stay inside.
        """
        if seconds <= 0:
            return 0
        fx, fy = driver.position()
        path = [(0.0, fx, fy)]
        for i, (dx, dy) in enumerate(self.window(seconds, rng)):
            fx, fy = fx + dx, fy + dy
            if box is not None:
                bx, by, bw, bh = box
                fx, fy = min(max(fx, bx), bx + bw - 1), min(max(fy, by), by + bh - 1)
            path.append(((i + 1) * BIN_MS, fx, fy))
        x, y = round(path[0][1]), round(path[0][2])
        travelled = 0.0
        t0 = time.perf_counter()
        for t_ms, nx, ny in regrid(path):
            wait = t0 + t_ms / 1000 - time.perf_counter()
            if wait > 0:
                precise_sleep(wait)
            if killswitch is not None:
                killswitch.check()
            travelled += math.hypot(nx - x, ny - y)
            x, y = nx, ny
            driver.move(x, y)
        return round(travelled)


# Real HID mice report on a fixed clock: 125 Hz (8 ms) is the common desktop rate.
# The model and the recordings' bins are 10 ms, a rate no mouse polls at, so every
# replayed path is re-sampled onto the device grid before it is emitted.
POLL_MS = 8.0


def regrid(path, period_ms: float = POLL_MS) -> list[tuple[float, int, int]]:
    """(t_ms, x, y) samples -> integer positions on a fixed ``period_ms`` grid.

    Linear interpolation between samples; consecutive duplicates are dropped
    (a still mouse sends nothing). The final sample is always kept exact.
    """
    if len(path) < 2:
        return [(t, round(x), round(y)) for t, x, y in path]
    out: list[tuple[float, int, int]] = []
    last = None
    j = 0
    t = period_ms * math.ceil(path[0][0] / period_ms)
    while t <= path[-1][0]:
        while j + 1 < len(path) and path[j + 1][0] < t:
            j += 1
        a, b = path[j], path[min(j + 1, len(path) - 1)]
        f = 0.0 if b[0] == a[0] else min(1.0, max(0.0, (t - a[0]) / (b[0] - a[0])))
        p = (round(a[1] + (b[1] - a[1]) * f), round(a[2] + (b[2] - a[2]) * f))
        if p != last:
            out.append((t, *p))
            last = p
        t += period_ms
    end = (round(path[-1][1]), round(path[-1][2]))
    if last != end:
        out.append((t, *end))
    return out

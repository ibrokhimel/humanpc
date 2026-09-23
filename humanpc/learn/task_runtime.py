"""Interactive task logic, UI-agnostic.

A runtime receives input callbacks (screen pixels, ``perf_counter_ns`` times),
tracks completion + misclicks, and describes what to draw via ``shapes()`` —
simple tuples a front-end renders. Keeping this free of tkinter makes every
task's rules unit-testable.

Shapes:
    ("circle", x, y, r, fill, label)
    ("rect", x0, y0, x1, y1, fill, outline)
    ("line", [x0, y0, x1, y1, ...], width, color)
    ("text", x, y, text, size, color, wrap)
"""

from __future__ import annotations

import math

from .events import BTN_LEFT, BTN_RIGHT
from .tasks import Task

NS = 1_000_000_000
HIT_SLOP = 2  # px of forgiveness on tiny targets
DOUBLE_NS = int(0.5 * NS)
SCROLL_STEP = 100  # px per 120-unit wheel notch
SCROLL_SETTLE_NS = int(0.35 * NS)
ROW_H = 120

C_START = "#4c8bf5"
C_TARGET = "#f5a623"
C_DONE = "#3ecf8e"
C_LINE = "#ff4d4f"
C_ZONE = "#2d3748"
C_MUTED = "#718096"
C_TEXT = "#e2e8f0"


def _hit(x, y, cx, cy, r) -> bool:
    return math.hypot(x - cx, y - cy) <= r + HIT_SLOP


class Runtime:
    def __init__(self, task: Task, now: int, screen: tuple[int, int] = (1920, 1080)):
        self.task = task
        self.p = task.params
        self.screen = screen
        self.t_shown = now
        self.t_start: int | None = None
        self.t_end: int | None = None
        self.errors = 0
        self.done = False
        self.dirty = True

    # input hooks (override as needed)
    def press(self, x, y, btn, now): ...
    def release(self, x, y, btn, now): ...
    def motion(self, x, y, now): ...
    def wheel(self, delta, now): ...
    def tick(self, now): ...
    def shapes(self) -> list:
        return []

    def _begin(self, now):
        if self.t_start is None:
            self.t_start = now

    def _finish(self, now):
        self._begin(now)
        self.done, self.t_end, self.dirty = True, now, True

    def record(self, t0: int) -> dict:
        us = lambda t: None if t is None else (t - t0) // 1000  # noqa: E731
        return {**self.task.to_dict(), "t_shown_us": us(self.t_shown),
                "t_start_us": us(self.t_start), "t_end_us": us(self.t_end),
                "errors": self.errors, "result": "ok" if self.done else "skipped"}


class PointRuntime(Runtime):
    """Click the start dot, then the target (left / double / right click)."""

    def __init__(self, task, now, screen=(1920, 1080)):
        super().__init__(task, now, screen)
        self.phase = 0  # 0 = start dot, 1 = target
        self._armed = False
        self._clicks: list[int] = []

    def press(self, x, y, btn, now):
        p = self.p
        if self.phase == 0:
            self._armed = btn == BTN_LEFT and _hit(x, y, *p["start"], p["start_r"])
            return
        want = BTN_RIGHT if self.task.kind == "right" else BTN_LEFT
        if btn == want and _hit(x, y, *p["target"], p["r"]):
            self._armed = True
        else:
            self._armed = False
            self._clicks.clear()
            self.errors += 1

    def release(self, x, y, btn, now):
        if not self._armed:
            return
        self._armed = False
        if self.phase == 0:
            self.phase, self.dirty = 1, True
            self._begin(now)
            return
        if self.task.kind != "double":
            self._finish(now)
            return
        self._clicks = [t for t in self._clicks if now - t <= DOUBLE_NS] + [now]
        if len(self._clicks) >= 2:
            self._finish(now)

    def shapes(self):
        p = self.p
        if self.phase == 0:
            return [("circle", *p["start"], p["start_r"], C_START, ""),
                    ("text", p["start"][0], p["start"][1] - p["start_r"] - 16, "start", 10, C_MUTED, 0)]
        label = {"double": "2x", "right": "R"}.get(self.task.kind, "")
        return [("circle", *p["target"], p["r"], C_TARGET, label)]


class DragRuntime(Runtime):
    """Drag the box into the zone."""

    def __init__(self, task, now, screen=(1920, 1080)):
        super().__init__(task, now, screen)
        self.box = list(task.params["box"])
        self._grab: tuple[float, float] | None = None

    def _in_box(self, x, y):
        h = self.p["size"] / 2 + HIT_SLOP
        return abs(x - self.box[0]) <= h and abs(y - self.box[1]) <= h

    def press(self, x, y, btn, now):
        if btn == BTN_LEFT and self._in_box(x, y):
            self._grab = (x - self.box[0], y - self.box[1])
            self._begin(now)
        else:
            self.errors += 1

    def motion(self, x, y, now):
        if self._grab:
            self.box = [x - self._grab[0], y - self._grab[1]]
            self.dirty = True

    def release(self, x, y, btn, now):
        if not self._grab:
            return
        self._grab = None
        zx, zy = self.p["zone"]
        half = (self.p["zone_size"] - self.p["size"]) / 2
        if abs(self.box[0] - zx) <= half and abs(self.box[1] - zy) <= half:
            self._finish(now)
        else:
            self.errors += 1

    def shapes(self):
        zx, zy = self.p["zone"]
        zh, bh = self.p["zone_size"] / 2, self.p["size"] / 2
        bx, by = self.box
        return [("rect", zx - zh, zy - zh, zx + zh, zy + zh, C_ZONE, C_MUTED),
                ("rect", bx - bh, by - bh, bx + bh, by + bh, C_TARGET, "")]


class ScrollRuntime(Runtime):
    """Scroll until the red line sits in the band (then click it for scroll_click)."""

    def __init__(self, task, now, screen=(1920, 1080)):
        super().__init__(task, now, screen)
        self.offset = float(task.params["offset"])
        self._last_wheel = now
        self._armed = False

    @property
    def line_y(self) -> float:
        return self.p["line"] - self.offset

    def in_band(self) -> bool:
        return abs(self.line_y - self.p["band_y"]) <= self.p["band_h"] / 2

    def wheel(self, delta, now):
        self._begin(now)
        self.offset -= delta / 120 * SCROLL_STEP
        self.offset = min(max(self.offset, 0.0), self.p["content"] - self.screen[1])
        self._last_wheel, self.dirty = now, True

    def tick(self, now):
        if self.task.kind == "scroll" and self.t_start is not None and self.in_band() \
                and now - self._last_wheel >= SCROLL_SETTLE_NS:
            self._finish(now)

    def press(self, x, y, btn, now):
        if self.task.kind != "scroll_click":
            return
        if btn == BTN_LEFT and self.in_band() and _hit(x, y, self.p["click_x"], self.line_y, self.p["r"]):
            self._armed = True
        else:
            self.errors += 1

    def release(self, x, y, btn, now):
        if self._armed:
            self._armed = False
            self._finish(now)

    def shapes(self):
        w, h = self.screen
        out = []
        first = int(self.offset // ROW_H)
        for i in range(first, first + h // ROW_H + 2):
            y = i * ROW_H - self.offset
            out.append(("rect", w * 0.2, y + 30, w * (0.35 + 0.4 * ((i * 37) % 10) / 10), y + 60, C_ZONE, ""))
        by, bh = self.p["band_y"], self.p["band_h"] / 2
        out.append(("rect", 0, by - bh, w, by + bh, "", C_START))
        ly = self.line_y
        out.append(("line", [0, ly, w, ly], 4, C_LINE))
        if self.task.kind == "scroll_click":
            out.append(("circle", self.p["click_x"], ly, self.p["r"], C_TARGET, ""))
        hint = "scroll the red line into the blue band" + (", then click the dot" if self.task.kind == "scroll_click" else "")
        out.append(("text", w / 2, 50, hint, 12, C_MUTED, 0))
        return out


class TraceRuntime(Runtime):
    """Hover the start, follow the path (no button), reach the end."""

    def __init__(self, task, now, screen=(1920, 1080)):
        super().__init__(task, now, screen)
        self.visited: set[int] = set()

    def motion(self, x, y, now):
        pts, half = self.p["points"], self.p["width"] / 2
        if self.t_start is None:
            if _hit(x, y, *pts[0], half):
                self._begin(now)
                self.dirty = True
            return
        for i, (px, py) in enumerate(pts):
            if i not in self.visited and _hit(x, y, px, py, half):
                self.visited.add(i)
        if _hit(x, y, *pts[-1], half) and len(self.visited) >= 0.8 * len(pts):
            self._finish(now)

    def shapes(self):
        pts, wdt = self.p["points"], self.p["width"]
        flat = [c for pt in pts for c in pt]
        start_col = C_DONE if self.t_start is not None else C_START
        return [("line", flat, wdt, C_ZONE),
                ("circle", *pts[0], wdt / 2, start_col, ""),
                ("circle", *pts[-1], wdt / 2, C_TARGET, ""),
                ("text", pts[0][0], pts[0][1] - wdt / 2 - 16, "hover to start", 10, C_MUTED, 0)]


class ReadRuntime(Runtime):
    """Read a paragraph; a Done button appears after ``min_seconds``."""

    BTN_W, BTN_H = 110, 44

    def __init__(self, task, now, screen=(1920, 1080)):
        super().__init__(task, now, screen)
        self._begin(now)
        self.ready = False
        self._armed = False

    def tick(self, now):
        if not self.ready and now - self.t_shown >= self.p["min_seconds"] * NS:
            self.ready, self.dirty = True, True

    def _in_btn(self, x, y):
        dx, dy = self.p["done"]
        return abs(x - dx) <= self.BTN_W / 2 and abs(y - dy) <= self.BTN_H / 2

    def press(self, x, y, btn, now):
        self._armed = self.ready and btn == BTN_LEFT and self._in_btn(x, y)

    def release(self, x, y, btn, now):
        if self._armed:
            self._finish(now)

    def shapes(self):
        w, h = self.screen
        out = [("text", w / 2, h * 0.35, self.p["text"], 20, C_TEXT, int(w * 0.5))]
        if self.ready:
            dx, dy = self.p["done"]
            out += [("rect", dx - self.BTN_W / 2, dy - self.BTN_H / 2, dx + self.BTN_W / 2,
                     dy + self.BTN_H / 2, C_START, ""),
                    ("text", dx, dy, "Done", 14, C_TEXT, 0)]
        return out


class ChainRuntime(Runtime):
    """Click numbered dots in order."""

    def __init__(self, task, now, screen=(1920, 1080)):
        super().__init__(task, now, screen)
        self.index = 0
        self._armed = False
        self._begin(now)

    def press(self, x, y, btn, now):
        pts, r = self.p["points"], self.p["r"]
        self._armed = btn == BTN_LEFT and _hit(x, y, *pts[self.index], r)
        if not self._armed:
            self.errors += 1

    def release(self, x, y, btn, now):
        if not self._armed:
            return
        self._armed = False
        self.index += 1
        self.dirty = True
        if self.index >= len(self.p["points"]):
            self._finish(now)

    def shapes(self):
        pts, r = self.p["points"], self.p["r"]
        out = []
        for i, (x, y) in enumerate(pts):
            if i < self.index:
                continue
            col = C_TARGET if i == self.index else C_MUTED
            out.append(("circle", x, y, r, col, str(i + 1)))
        return out[::-1]  # current dot drawn last (on top)


RUNTIMES = {
    "point": PointRuntime, "double": PointRuntime, "right": PointRuntime,
    "drag": DragRuntime, "scroll": ScrollRuntime, "scroll_click": ScrollRuntime,
    "trace": TraceRuntime, "read": ReadRuntime, "chain": ChainRuntime,
}


def make_runtime(task: Task, now: int, screen: tuple[int, int]) -> Runtime:
    return RUNTIMES[task.kind](task, now, screen)

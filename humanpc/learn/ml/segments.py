"""Recorded sessions -> fixed-timestep training segments.

A *segment* is one goal-directed chunk of a task (reach the start dot, reach the
target, scroll the line into the band, drag the box, ...). Its raw events are
binned into ``BIN_MS`` steps. Movement is expressed in a frame rotated so the
target lies on +x, so the model learns shape independent of direction (the true
direction is still given as a condition).

Per step the model predicts: moved? (dx, dy) · click event · wheel notches · end.
Per step it sees: the previous step + the state *before* this step (vector still
to go, elapsed time, buttons held, scroll still to go). ``Rollout`` recomputes the
same state incrementally during generation; tests pin the two together.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..events import BTN_LEFT, BTN_RIGHT, DOWN, UP, WHEEL
from ..task_runtime import SCROLL_STEP

BIN_MS = 10
BIN_US = BIN_MS * 1000
MAX_STEPS = 1280  # 12.8 s at 10 ms
MIN_STEPS = 3
POS_SCALE = 10.0  # px per model unit for dx/dy

GEN_KINDS = ("aim", "aim_double", "aim_right", "drag", "scroll", "scroll_click", "idle")
CLICK_CLASSES = 5  # none, L down, L up, R down, R up
WHEEL_MAX = 3
WHEEL_CLASSES = 2 * WHEEL_MAX + 1
STEP_DIM = 2 + 1 + CLICK_CLASSES + WHEEL_CLASSES  # 15
STATE_DIM = 9
IN_DIM = STEP_DIM + STATE_DIM
COND_DIM = len(GEN_KINDS) + 7

_CLICK_OF = {(DOWN, BTN_LEFT): 1, (UP, BTN_LEFT): 2, (DOWN, BTN_RIGHT): 3, (UP, BTN_RIGHT): 4}
# Kinds that end on a click: (release class, releases needed). Mirrors task_runtime's rules;
# "scroll" is the only kind whose end is learned (settling in the band).
FINISH = {"aim": (2, 1), "aim_double": (2, 2), "aim_right": (4, 1), "drag": (2, 1),
          "scroll_click": (2, 1), "idle": (2, 1)}
DOUBLE_STEPS = 500 // BIN_MS
HIT_SLOP_PX = 3
_SNAP_BEFORE_US, _SNAP_AFTER_US = 250_000, 60_000


@dataclass
class Segment:
    kind: str
    t0: int  # us, session clock
    t1: int
    start: tuple[float, float] | None = None  # cursor at t0 (filled by ``binned``)
    target: tuple[float, float] | None = None  # screen px
    radius: float = 0.0
    scroll_px: float = 0.0  # content px still to scroll down (+) / up (-)
    duration_hint: float = 0.0
    person: str = ""
    session: str = ""
    arrays: dict = field(default_factory=dict)


# -- extraction from one session --------------------------------------------------
class _Session:
    def __init__(self, ev: dict, meta: dict):
        self.ev = ev
        self.t = ev["t_us"]
        ox, oy = (meta.get("window_origin") or [0, 0])[:2]
        self.origin = (ox, oy)

    def screen(self, p):
        return (p[0] + self.origin[0], p[1] + self.origin[1])

    def pos_at(self, t: int) -> tuple[float, float]:
        i = max(0, int(np.searchsorted(self.t, t, side="right")) - 1)
        return float(self.ev["x"][i]), float(self.ev["y"][i])

    def snap(self, t: int, typ: int, button: int) -> int:
        """Hook time of the ``typ``/``button`` event closest to UI time ``t``."""
        lo, hi = np.searchsorted(self.t, [t - _SNAP_BEFORE_US, t + _SNAP_AFTER_US])
        idx = [i for i in range(lo, hi) if self.ev["type"][i] == typ and self.ev["button"][i] == button]
        return int(self.t[min(idx, key=lambda i: abs(self.t[i] - t))]) if idx else int(t)

    def ups(self, t0: int, t1: int, button: int) -> list[int]:
        lo, hi = np.searchsorted(self.t, [t0, t1], side="right")
        return [i for i in range(lo, hi) if self.ev["type"][i] == UP and self.ev["button"][i] == button]


def extract(ev: dict, meta: dict, tasks: list[dict]) -> list[Segment]:
    s = _Session(ev, meta)
    person, session = meta.get("person") or "", meta.get("session", "")
    out: list[Segment] = []

    def add(kind, t0, t1, **kw):
        if t1 > t0:
            out.append(Segment(kind, int(t0), int(t1), person=person, session=session, **kw))

    for task in tasks:
        if task.get("result") != "ok" or task.get("t_end_us") is None:
            continue
        kind, p = task["kind"], task["params"]
        shown, start, end = task["t_shown_us"], task["t_start_us"], task["t_end_us"]
        if kind in ("point", "double", "right"):
            a_end = s.snap(start, UP, BTN_LEFT)
            add("aim", shown, a_end, target=s.screen(p["start"]), radius=p["start_r"])
            btn = BTN_RIGHT if kind == "right" else BTN_LEFT
            gk = {"point": "aim", "double": "aim_double", "right": "aim_right"}[kind]
            add(gk, a_end, s.snap(end, UP, btn), target=s.screen(p["target"]), radius=p["r"])
        elif kind == "chain":
            pts, r, t_prev, k = [s.screen(q) for q in p["points"]], p["r"], shown, 0
            for i in s.ups(shown, end + _SNAP_AFTER_US, BTN_LEFT):
                if k >= len(pts):
                    break
                x, y = float(ev["x"][i]), float(ev["y"][i])
                if math.hypot(x - pts[k][0], y - pts[k][1]) <= r + 3:
                    add("aim", t_prev, int(s.t[i]), target=pts[k], radius=r)
                    t_prev, k = int(s.t[i]), k + 1
        elif kind == "drag" and task.get("errors", 0) == 0:
            t_down = s.snap(start, DOWN, BTN_LEFT)
            px, py = s.pos_at(t_down)
            bx, by = s.screen(p["box"])
            zx, zy = s.screen(p["zone"])
            add("drag", t_down, s.snap(end, UP, BTN_LEFT), target=(zx + px - bx, zy + py - by),
                radius=(p["zone_size"] - p["size"]) / 2)
        elif kind in ("scroll", "scroll_click"):
            need = p["line"] - p["band_y"] - p["offset"]
            if kind == "scroll":
                add("scroll", shown, end, scroll_px=need)
            else:
                add("scroll_click", shown, s.snap(end, UP, BTN_LEFT), scroll_px=need,
                    target=s.screen((p["click_x"], p["band_y"])), radius=p["r"])
        elif kind == "read":
            add("idle", shown, s.snap(end, UP, BTN_LEFT), target=s.screen(p["done"]), radius=22,
                duration_hint=p["min_seconds"])
    for seg in out:
        seg.arrays = binned(s, seg)
    return [seg for seg in out if seg.arrays]


# -- binning + features -----------------------------------------------------------
def _angle(seg_start, target) -> float:
    if target is None:
        return 0.0
    return math.atan2(target[1] - seg_start[1], target[0] - seg_start[0])


def _rot(dx, dy, ang):
    c, s = math.cos(-ang), math.sin(-ang)
    return dx * c - dy * s, dx * s + dy * c


def _slog(v):
    return np.sign(v) * np.log1p(np.abs(v) / 10.0)


def _to_go(remaining, seg: Segment):
    """Distance still to go in target radii, log-scaled (< log 2 means inside the target)."""
    if seg.target is None:
        return np.zeros_like(remaining) if isinstance(remaining, np.ndarray) else 0.0
    return np.log1p(remaining / max(seg.radius, 1.0))


def condition(seg: Segment, start: tuple[float, float]) -> np.ndarray:
    ang = _angle(start, seg.target)
    dist = 0.0 if seg.target is None else math.hypot(seg.target[0] - start[0], seg.target[1] - start[1])
    c = np.zeros(COND_DIM, np.float32)
    c[GEN_KINDS.index(seg.kind)] = 1
    c[len(GEN_KINDS):] = [math.log1p(dist) / 7, math.log1p(seg.radius) / 5, math.sin(ang), math.cos(ang),
                          seg.scroll_px / 2000, seg.duration_hint / 10, float(seg.target is not None)]
    return c


def binned(s: _Session, seg: Segment) -> dict:
    n = -(-(seg.t1 - seg.t0) // BIN_US)
    if not MIN_STEPS <= n < MAX_STEPS:  # +1 terminal step must fit
        return {}
    start = s.pos_at(seg.t0)
    seg.start = start
    ang = _angle(start, seg.target)
    lo, hi = np.searchsorted(s.t, [seg.t0, seg.t1], side="right")
    xs, ys = np.full(n, np.nan), np.full(n, np.nan)
    click = np.zeros(n, np.int64)
    wheel_raw = np.zeros(n)
    for i in range(lo, hi):
        b = min(n - 1, int((s.t[i] - seg.t0 - 1) // BIN_US))
        xs[b], ys[b] = s.ev["x"][i], s.ev["y"][i]
        typ = int(s.ev["type"][i])
        c = _CLICK_OF.get((typ, int(s.ev["button"][i])), 0)
        if c and click[b] == 0:
            click[b] = c
        if typ == WHEEL:
            wheel_raw[b] += s.ev["wheel"][i] / 120.0
    # carry positions forward; wheel keeps fractional (touchpad) remainders
    px, py = start
    dx, dy = np.zeros(n), np.zeros(n)
    wheel = np.zeros(n, np.int64)
    carry = 0.0
    for b in range(n):
        if not np.isnan(xs[b]):
            rx, ry = _rot(xs[b] - px, ys[b] - py, ang)
            dx[b], dy[b] = rx, ry
            px, py = xs[b], ys[b]
        carry += wheel_raw[b]
        w = int(max(-WHEEL_MAX, min(WHEEL_MAX, round(carry))))
        wheel[b], carry = w, carry - w
    return pack(seg, start, dx, dy, click, wheel)


def pack(seg: Segment, start, dx, dy, click, wheel) -> dict:
    """Steps (rotated px) -> model arrays: inputs, targets, condition.

    A terminal "stop" step (no motion, no click) is appended with ``end=1``, so the
    model decides to stop *after* it has seen the final click, not blindly alongside it.
    """
    dx, dy = np.append(np.asarray(dx, float), 0.0), np.append(np.asarray(dy, float), 0.0)
    click = np.append(np.asarray(click, np.int64), 0)
    wheel = np.append(np.asarray(wheel, np.int64), 0)
    n = len(dx)
    moved = ((dx != 0) | (dy != 0)).astype(np.float32)
    step = np.zeros((n, STEP_DIM), np.float32)
    step[:, 0] = np.clip(dx / POS_SCALE, -50, 50)
    step[:, 1] = np.clip(dy / POS_SCALE, -50, 50)
    step[:, 2] = moved
    step[np.arange(n), 3 + click] = 1
    step[np.arange(n), 3 + CLICK_CLASSES + wheel + WHEEL_MAX] = 1

    state = states(seg, start, dx, dy, click, wheel)
    inputs = np.concatenate([np.vstack([np.zeros((1, STEP_DIM), np.float32), step[:-1]]), state], axis=1)
    end = np.zeros(n, np.float32)
    end[-1] = 1
    return {"inputs": inputs, "dxdy": step[:, :2].copy(), "moved": moved, "click": click,
            "wheel": wheel + WHEEL_MAX, "end": end, "cond": condition(seg, start)}


def states(seg: Segment, start, dx, dy, click, wheel) -> np.ndarray:
    """State *before* each step (vectorised twin of ``Rollout.state``)."""
    n = len(dx)
    ang = _angle(start, seg.target)
    dist = 0.0 if seg.target is None else math.hypot(seg.target[0] - start[0], seg.target[1] - start[1])
    cx = np.concatenate([[0.0], np.cumsum(dx)[:-1]])
    cy = np.concatenate([[0.0], np.cumsum(dy)[:-1]])
    rx, ry = (dist - cx, -cy) if seg.target is not None else (np.zeros(n), np.zeros(n))
    held_l = np.concatenate([[0], np.cumsum((click == 1).astype(int) - (click == 2).astype(int))[:-1]])
    held_r = np.concatenate([[0], np.cumsum((click == 3).astype(int) - (click == 4).astype(int))[:-1]])
    if seg.kind == "drag":
        held_l = held_l + 1  # the segment starts with the button already down
    wsum = np.concatenate([[0], np.cumsum(wheel)[:-1]])
    d = max(dist, 1.0)
    st = np.stack([rx / d, ry / d, _slog(rx), _slog(ry), np.arange(n) * BIN_MS / 1000.0,
                   np.clip(held_l, 0, 1), np.clip(held_r, 0, 1),
                   (seg.scroll_px + wsum * SCROLL_STEP) / 1000.0,
                   _to_go(np.hypot(rx, ry), seg)], axis=1)
    return st.astype(np.float32)


class Rollout:
    """Incremental state tracker for generation (mirrors ``states``)."""

    def __init__(self, seg: Segment, start: tuple[float, float]):
        self.seg, self.start = seg, start
        self.ang = _angle(start, seg.target)
        self.dist = 0.0 if seg.target is None else math.hypot(seg.target[0] - start[0], seg.target[1] - start[1])
        self.cx = self.cy = 0.0
        self.held_l = 1 if seg.kind == "drag" else 0
        self.held_r = 0
        self.wsum = 0
        self.n = 0
        self.prev = np.zeros(STEP_DIM, np.float32)  # first input step is all zeros, like training
        self._releases: list[int] = []
        self.finished = False

    def state(self) -> np.ndarray:
        rx, ry = (self.dist - self.cx, -self.cy) if self.seg.target is not None else (0.0, 0.0)
        d = max(self.dist, 1.0)
        return np.array([rx / d, ry / d, _slog(rx), _slog(ry), self.n * BIN_MS / 1000.0,
                         min(max(self.held_l, 0), 1), min(max(self.held_r, 0), 1),
                         (self.seg.scroll_px + self.wsum * SCROLL_STEP) / 1000.0,
                         _to_go(math.hypot(rx, ry), self.seg)], np.float32)

    def input(self) -> np.ndarray:
        return np.concatenate([self.prev, self.state()])

    def push(self, dx: float, dy: float, click: int, wheel: int) -> None:
        """Advance by one step (rotated px, class ids with wheel in -3..3)."""
        self.cx += dx
        self.cy += dy
        self.held_l += (click == 1) - (click == 2)
        self.held_r += (click == 3) - (click == 4)
        self.wsum += wheel
        self.n += 1
        rule = FINISH.get(self.seg.kind)
        if rule and click == rule[0] and self.on_target():
            self._releases = [t for t in self._releases if self.n - t <= DOUBLE_STEPS] + [self.n]
            self.finished = len(self._releases) >= rule[1]
        p = np.zeros(STEP_DIM, np.float32)
        p[0], p[1] = np.clip(dx / POS_SCALE, -50, 50), np.clip(dy / POS_SCALE, -50, 50)
        p[2] = float(dx != 0 or dy != 0)
        p[3 + click] = 1
        p[3 + CLICK_CLASSES + wheel + WHEEL_MAX] = 1
        self.prev = p

    def click_mask(self) -> list[bool]:
        """Possible click classes: none, L down, L up, R down, R up."""
        held_l, held_r = self.held_l > 0, self.held_r > 0
        return [True, not held_l, held_l, not held_r, held_r]

    def on_target(self) -> bool:
        if self.seg.target is None:
            return False
        return math.hypot(self.cx - self.dist, self.cy) <= self.seg.radius + HIT_SLOP_PX

    def to_screen(self, dx: float, dy: float) -> tuple[float, float]:
        return _rot(dx, dy, -self.ang)


def load_all(root, *, recursive: bool = True, max_sessions: int | None = None) -> list[Segment]:
    """Every segment from every session under ``root``.

    ``max_sessions`` keeps memory bounded on big datasets by taking that many
    sessions spread evenly across the (time-sorted) list.
    """
    from pathlib import Path

    from ..dataset import list_sessions, load_session

    root = Path(root)
    bases = list_sessions(root, recursive=recursive)
    if max_sessions and len(bases) > max_sessions:
        step = len(bases) / max_sessions
        bases = [bases[int(i * step)] for i in range(max_sessions)]
    segs: list[Segment] = []
    for base in bases:
        ev, meta, tasks = load_session(base)
        if not meta.get("person"):
            meta = {**meta, "person": base.parent.name if base.parent != root else "me"}
        segs += extract(ev, meta, tasks)
    return segs

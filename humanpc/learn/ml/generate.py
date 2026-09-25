"""Generate movements with a trained model.

``generate`` samples many segments in lockstep (batched, KV-cached).
``to_events`` turns a generated segment into screen-space events.
``MovementGenerator`` is the small runtime API humanpc's mouse engine can use.
"""

from __future__ import annotations

import math
import random

import numpy as np
import torch

from ..events import BTN_LEFT, BTN_RIGHT, DOWN, MOVE, UP, WHEEL
from .model import load, sample
from .segments import BIN_MS, FINISH, MAX_STEPS, POS_SCALE, WHEEL_MAX, Rollout, Segment, condition

_CLICK_EVENT = {1: (DOWN, BTN_LEFT), 2: (UP, BTN_LEFT), 3: (DOWN, BTN_RIGHT), 4: (UP, BTN_RIGHT)}


@torch.no_grad()
def generate(model, jobs: list[tuple[Segment, tuple[float, float]]], persons: list[int], *,
             device="cpu", temperature: float = 1.0, max_steps: int = MAX_STEPS) -> list[dict]:
    """jobs: (segment spec, start position). Returns rotated-frame step arrays per job.

    Batched with a preallocated KV cache; finished rows are dropped from the batch, so
    one slow movement doesn't keep the whole batch busy.
    """
    model.eval()
    n = len(jobs)
    rolls = [Rollout(seg, start) for seg, start in jobs]
    cond = torch.tensor(np.stack([condition(seg, start) for seg, start in jobs]), device=device)
    person = torch.tensor(persons, device=device, dtype=torch.long)
    cache = model.empty_cache(n, max_steps, device)
    active = list(range(n))  # job index of each batch row
    done = np.zeros(n, bool)
    steps: list[list[tuple]] = [[] for _ in range(n)]
    for t in range(max_steps):
        inp = torch.tensor(np.stack([rolls[b].input() for b in active]), device=device)[:, None]
        out, cache = model(inp, cond, person, cache=cache, start=t)
        mask = torch.tensor([rolls[b].click_mask() for b in active], device=device)
        s = {k: v.cpu().numpy() for k, v in sample(out, temperature, mask).items()}
        for row, b in enumerate(active):
            if jobs[b][0].kind not in FINISH and s["end"][row]:  # learned end: the terminal step has no motion
                done[b] = True
                continue
            dx, dy = (s["dxdy"][row] * POS_SCALE).tolist()
            click, wheel = int(s["click"][row]), int(s["wheel"][row]) - WHEEL_MAX
            rolls[b].push(dx, dy, click, wheel)
            steps[b].append((dx, dy, click, wheel))
            done[b] = rolls[b].finished  # click-ending kinds stop exactly like the task does
        keep = [row for row, b in enumerate(active) if not done[b]]
        if not keep:
            break
        if len(keep) < len(active):
            rows = torch.tensor(keep, device=device)
            cache, cond, person = model.select_cache(cache, rows), cond[rows], person[rows]
            active = [active[row] for row in keep]
    return [{**{k: np.array([st[i] for st in seg_steps], dtype=np.float64 if i < 2 else np.int64)
                for i, k in enumerate(("dx", "dy", "click", "wheel"))}, "finished": bool(done[b])}
            for b, seg_steps in enumerate(steps)]


def land_on_target(gen: dict, seg: Segment, start, rng: random.Random | None = None) -> dict:
    """Nudge the path so it ends inside the target (spread over the last 40% of motion)."""
    if seg.target is None or not len(gen["dx"]):
        return gen
    rng = rng or random.Random()
    dist = math.hypot(seg.target[0] - start[0], seg.target[1] - start[1])
    ex, ey = gen["dx"].sum(), gen["dy"].sum()
    r = max(1.0, seg.radius)
    if math.hypot(ex - dist, ey) <= 0.8 * r:
        return gen
    # aim for a human-like landing point: Gaussian around the centre, inside the radius
    tx, ty = dist + rng.gauss(0, r / 3), rng.gauss(0, r / 3)
    scale = min(1.0, 0.8 * r / max(1e-9, math.hypot(tx - dist, ty)))
    tx, ty = dist + (tx - dist) * scale, ty * scale
    step_len = np.hypot(gen["dx"], gen["dy"])
    cum = np.cumsum(step_len)
    if cum[-1] <= 0:
        return gen
    w = np.clip((cum / cum[-1] - 0.6) / 0.4, 0, 1)
    wd = np.diff(np.concatenate([[0.0], w]))
    out = dict(gen)
    out["dx"] = gen["dx"] + wd * (tx - ex)
    out["dy"] = gen["dy"] + wd * (ty - ey)
    return out


def to_events(gen: dict, seg: Segment, start, *, t0_ms: float = 0.0) -> list[tuple]:
    """Rotated steps -> [(t_ms, type, x, y, button, wheel)] in screen px (integer, drift-free)."""
    roll = Rollout(seg, start)
    fx, fy = float(start[0]), float(start[1])
    x, y = round(fx), round(fy)
    events = []
    for i in range(len(gen["dx"])):
        t = t0_ms + (i + 1) * BIN_MS
        sx, sy = roll.to_screen(gen["dx"][i], gen["dy"][i])
        fx, fy = fx + sx, fy + sy
        nx, ny = round(fx), round(fy)
        if (nx, ny) != (x, y):
            x, y = nx, ny
            events.append((t, MOVE, x, y, 0, 0))
        c = int(gen["click"][i])
        if c in _CLICK_EVENT:
            typ, btn = _CLICK_EVENT[c]
            events.append((t, typ, x, y, btn, 0))
        w = int(gen["wheel"][i])
        if w:
            events.append((t, WHEEL, x, y, 0, 120 * w))
    return events


class MovementGenerator:
    """Load once, then ask for human-like movements.

    >>> gen = MovementGenerator.load("~/.humanpc/training/model/model.pt")
    >>> events = gen.move((100, 100), (900, 500), radius=12)
    """

    def __init__(self, model, people: list[str], device="cpu"):
        self.model, self.people, self.device = model, people, device

    @classmethod
    def load(cls, path, device: str | None = None) -> "MovementGenerator":
        from pathlib import Path
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        model, ck = load(Path(path).expanduser(), device)
        return cls(model, ck.get("people", ["me"]), device)

    def person_id(self, person: str | None) -> int:
        return self.people.index(person) if person in self.people else 0

    def move(self, start, target, *, radius: float = 10.0, kind: str = "aim", person: str | None = None,
             temperature: float = 1.0, land: bool = True, scroll_px: float = 0.0) -> list[tuple]:
        seg = Segment(kind, 0, 0, target=None if kind == "scroll" else tuple(target), radius=radius,
                      scroll_px=scroll_px)
        gen = generate(self.model, [(seg, tuple(start))], [self.person_id(person)],
                       device=self.device, temperature=temperature)[0]
        if land:
            gen = land_on_target(gen, seg, start)
        return to_events(gen, seg, start)

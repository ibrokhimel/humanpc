"""Mouse back-ends for the workflow test: same four verbs, different movement source."""

from __future__ import annotations

import random
import time
from pathlib import Path

from idle_bank import regrid

from humanpc import Bot
from humanpc.hil.precise import precise_sleep

# Generation step caps (10 ms each). One candidate that never "arrives" would
# otherwise keep the whole batch busy for MAX_STEPS = 12.8 s - the cursor sits
# frozen the whole time. No aim in the recordings needs 3.5 s; scrolls can.
_MAX_STEPS = {"aim": 350, "drag": 350, "scroll": 700}


def _center(rect) -> tuple[float, float]:
    x, y, w, h = rect
    return (x + w / 2, y + h / 2)


# ---------------------------------------------------------------------------
# Mouse back-ends: same four verbs, different movement source
# ---------------------------------------------------------------------------

class HilMouse:
    """humanpc's built-in Human Interaction Layer (Bot.move_to / click / drag)."""

    name = "hil"

    def __init__(self, bot: Bot):
        self.bot = bot

    def move(self, rect) -> None:
        self.bot.move_to(rect)

    def click(self, rect) -> None:
        self.bot.click(rect)

    def drag(self, frm_rect, to_pt) -> None:
        self.bot.drag(to=(round(to_pt[0]), round(to_pt[1])), frm=frm_rect)

    def scroll(self, notches: int, px: float) -> None:
        self.bot.scroll(notches)


class ModelMouse:
    """The trained movement model (humanpc.learn.ml) played through SendInput."""

    name = "model"

    def __init__(self, bot: Bot, model_path: Path, person: str | None, temperature: float):
        from humanpc.learn import events as E
        from humanpc.learn.ml.generate import MovementGenerator

        self.E = E
        self.bot = bot
        self.person, self.temperature = person, temperature
        self.early = 0  # presses the model made before reaching the target
        self.gen_s = 0.0  # seconds spent generating (the cursor is frozen meanwhile)
        print(f"loading movement model {model_path} ...")
        self.gen = MovementGenerator.load(model_path)
        print(f"  people: {self.gen.people}  device: {self.gen.device}")

    def _events(self, target, *, kind: str, radius: float = 10.0, scroll_px: float = 0.0):
        from humanpc.learn.ml.generate import generate_guarded, land_on_target, to_events
        from humanpc.learn.ml.segments import Segment

        start = self.bot.position()
        seg = Segment(kind, 0, 0, target=None if kind == "scroll" else tuple(target), radius=radius,
                      scroll_px=scroll_px)
        g = self.gen
        t0 = time.perf_counter()
        gen = generate_guarded(g.model, [(seg, start)], [g.person_id(self.person)], g.envelope,
                               device=g.device, temperature=self.temperature,
                               max_steps=_MAX_STEPS.get(kind, 350))[0][0]
        self.gen_s += time.perf_counter() - t0
        if kind != "scroll":
            gen = land_on_target(gen, seg, start)
        return self._regrid(to_events(gen, seg, start))

    def _regrid(self, events):
        """Put the 10 ms model samples on the 8 ms device grid; keep clicks/wheel in order."""
        E = self.E
        moves = [(t, x, y) for t, typ, x, y, _b, _w in events if typ == E.MOVE]
        others = [e for e in events if e[1] != E.MOVE]
        if len(moves) < 2:
            return events
        sx, sy = self.bot.position()
        grid = [(t, E.MOVE, x, y, 0, 0) for t, x, y in regrid([(0.0, sx, sy)] + moves)]
        return sorted(grid + others, key=lambda e: (e[0], e[1] != E.MOVE))

    def _play(self, events, *, clicks: bool, bound: float | None = None, rect=None) -> tuple[int, int]:
        """Replay [(t_ms, type, x, y, button, wheel)] in real time. Returns (#down, wheel notches).

        ``bound`` keeps the cursor within that many px of where it started (scrolling:
        the wheel only reaches the page while the pointer is over it).
        ``rect``: a press the model makes outside the target is held back until the
        cursor is inside it (counted in ``self.early``) - the model sometimes clicks
        before it has arrived on small targets.
        """
        E, drv, ks = self.E, self.bot.driver, self.bot.killswitch
        sx, sy = cx, cy = self.bot.position()
        downs = notches = 0
        held = pending = up_pending = False

        def inside():
            return rect is None or (rect[0] <= cx < rect[0] + rect[2] and rect[1] <= cy < rect[1] + rect[3])

        def press():
            nonlocal downs, held, pending, up_pending
            drv.mouse_down("left")
            downs, held, pending = 1, True, False
            if up_pending:  # the model already released while we waited: finish the click
                precise_sleep(random.uniform(0.06, 0.11))
                drv.mouse_up("left")
                held = up_pending = False

        t0 = time.perf_counter()
        for t_ms, typ, x, y, btn, wheel in events:
            wait = t0 + t_ms / 1000.0 - time.perf_counter()
            if wait > 0:
                precise_sleep(wait)
            ks.check()
            if typ == E.MOVE:
                if bound is not None:
                    x = sx + max(-bound, min(bound, x - sx))
                    y = sy + max(-bound, min(bound, y - sy))
                drv.move(x, y)
                cx, cy = x, y
                if pending and inside():
                    press()
            elif typ == E.WHEEL:
                n = round(wheel / 120)
                if n:
                    drv.scroll(0, n)
                    notches += n
            elif clicks and typ == E.DOWN and btn == 1 and downs == 0 and not pending:
                if inside():
                    press()
                else:
                    pending = True
                    self.early += 1
            elif clicks and typ == E.UP and btn == 1:
                if held:
                    drv.mouse_up("left")
                    held = False
                elif pending:
                    up_pending = True
        if pending:  # never entered the target during playback: press where it landed
            press()
        if held:  # the model pressed but never released: finish the click
            precise_sleep(random.uniform(0.05, 0.1))
            drv.mouse_up("left")
        return downs, notches

    def _radius(self, rect) -> float:
        return max(3.0, 0.4 * min(rect[2], rect[3]))

    def move(self, rect) -> None:
        self._play(self._events(_center(rect), kind="aim", radius=self._radius(rect)), clicks=False)

    def click(self, rect) -> None:
        downs, _ = self._play(self._events(_center(rect), kind="aim", radius=self._radius(rect)),
                              clicks=True, rect=rect)
        if not downs:  # the model moved but never clicked: click where it landed
            self.bot.click()

    def drag(self, frm_rect, to_pt) -> None:
        self.move(frm_rect)
        drv = self.bot.driver
        drv.mouse_down("left")
        precise_sleep(random.uniform(0.06, 0.14))
        try:
            self._play(self._events(to_pt, kind="drag", radius=4.0), clicks=False)
            precise_sleep(random.uniform(0.05, 0.12))
        finally:
            drv.mouse_up("left")

    def scroll(self, notches: int, px: float) -> None:
        _, done = self._play(self._events(None, kind="scroll", scroll_px=px), clicks=False, bound=80)
        print(f"      model wheel: {done:+d} notches (asked {notches:+d})")
        if done == 0:  # the model produced no wheel: fall back so the task can progress
            self.bot.scroll(notches)

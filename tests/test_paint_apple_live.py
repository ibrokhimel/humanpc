"""Live end-to-end demo/test: open Paint from the Start menu and draw an apple.

WARNING: this drives the REAL mouse and keyboard. It presses the Windows key,
searches for "paint", opens Microsoft Paint, draws a red apple (body + green leaf
+ brown stem) on the canvas with continuous, human-paced pen strokes, fills it in
with the bucket tool, and saves a screenshot to captures/paint_apple.png.

Abort at any time with the humanpc kill-switch: Ctrl+Alt+Q.

Because it takes over the desktop, it is SKIPPED in the normal test run. Opt in:

    HUMANPC_LIVE=1 pytest tests/test_paint_apple_live.py -s

or just run it directly (no env var needed):

    python tests/test_paint_apple_live.py

Drawing notes (why it works the way it does):
  * Movement uses the SendInput driver and dense (<=2px) steps. Windows 11 Paint
    is a WinUI app that samples real injected mouse events into a continuous pen
    line; a burst of instantaneous SetCursorPos/moveTo calls only registers its
    endpoints, so closed loops collapse to a dot. SendInput + small steps draws a
    clean, connected stroke.
  * Colour comes from Paint's palette + Fill (bucket) tool. The ribbon swatch /
    tool positions are fixed offsets from the (maximised) window's top-left.
"""

from __future__ import annotations

import math
import os
import sys
import time

import pytest

from humanpc import Bot
from humanpc.exceptions import TargetNotFound
from humanpc.geometry import Point

# Ribbon hit-points, as (x, y) offsets from the maximised window's top-left.
# Measured from a screenshot whose origin is the window corner (see module doc).
_TOOL_PENCIL = (270, 95)
_TOOL_BUCKET = (310, 96)        # "Fill with color"
_SWATCH_RED = (871, 92)
_SWATCH_GREEN = (943, 92)
_SWATCH_BROWN = (847, 116)

# ---------------------------------------------------------------------------
# Apple geometry (pure; no OS dependency)
# ---------------------------------------------------------------------------


def apple_body(cx: float, cy: float, rx: float, ry: float, n: int = 140) -> list[Point]:
    """A closed apple silhouette: round body, dimpled top, slightly tucked base."""
    pts: list[Point] = []
    for i in range(n + 1):                       # +1 -> closes the loop
        t = 2 * math.pi * i / n
        x = cx + rx * math.sin(t)
        y = cy - ry * math.cos(t)
        top_d = min(t, 2 * math.pi - t)          # angular distance from the top
        y += 0.24 * ry * math.exp(-((top_d / 0.5) ** 2))   # stem dimple
        y -= 0.07 * ry * math.exp(-(((t - math.pi) / 0.55) ** 2))  # tuck the base
        pts.append(Point(x, y))
    return pts


def apple_stem(cx: float, top_y: float, ry: float, n: int = 16) -> list[Point]:
    """A short stem curving up-right out of the top dimple."""
    return [Point(cx + 0.10 * ry * (i / n) ** 1.4, top_y - 0.34 * ry * (i / n))
            for i in range(n + 1)]


def apple_leaf(cx: float, cy: float, length: float, width: float, angle: float, n: int = 48) -> list[Point]:
    """A pointed-oval leaf, rotated by ``angle`` radians, beside the stem."""
    ca, sa = math.cos(angle), math.sin(angle)
    pts: list[Point] = []
    for i in range(n + 1):
        s = 2 * math.pi * i / n
        lx = length * math.cos(s)
        ly = width * math.sin(s) * abs(math.sin(s / 2))   # sharpen the tips
        pts.append(Point(cx + lx * ca - ly * sa, cy + lx * sa + ly * ca))
    return pts


# ---------------------------------------------------------------------------
# Drawing + colouring primitives
# ---------------------------------------------------------------------------


def _stroke(bot: Bot, pts: list[Point], *, settle: float = 0.10, step: float = 2.0,
            dwell: float = 0.004) -> None:
    """Draw one continuous pen stroke through ``pts`` with the button held.

    The polyline is densified to <=``step`` px between samples so Paint renders a
    connected line, with a hair of perpendicular jitter for a hand-drawn feel.
    """
    drv = bot.driver
    rng = bot._rng
    sx, sy = round(pts[0].x), round(pts[0].y)
    bot.move_to((sx, sy))                 # humanized pen-up approach
    drv.move(sx, sy)
    drv.mouse_down("left")
    time.sleep(settle)
    n_moves = 0
    try:
        ax, ay = pts[0].x, pts[0].y
        for p in pts[1:]:
            bx, by = p.x, p.y
            d = math.hypot(bx - ax, by - ay)
            n = max(1, int(d / step))
            nx, ny = (-(by - ay) / d, (bx - ax) / d) if d else (0.0, 0.0)
            for k in range(1, n + 1):
                f = k / n
                j = rng.uniform(-0.5, 0.5)
                drv.move(round(ax + (bx - ax) * f + nx * j),
                         round(ay + (by - ay) * f + ny * j))
                time.sleep(dwell)
                n_moves += 1
                if n_moves % 24 == 0:
                    bot.killswitch.check()
            ax, ay = bx, by
    finally:
        time.sleep(0.05)
        drv.mouse_up("left")


def _bucket_fill(bot: Bot, ribbon, swatch, at: tuple[int, int]) -> None:
    """Pick ``swatch``, select the Fill tool, and flood-fill the region at ``at``."""
    bot.click(ribbon(*swatch))
    bot.think("low")
    bot.click(ribbon(*_TOOL_BUCKET))
    bot.think("low")
    bot.click(at)


def draw_apple(bot: Bot, win) -> None:
    """Draw + colour a full apple centred in the canvas of window ``win``."""
    r = win.rect
    ribbon = lambda ix, iy: (r.x + ix, r.y + iy)   # ribbon point -> screen coords

    cx = r.x + r.width // 2
    rx = r.width * 0.40 * 0.42
    ry = r.height * 0.58 * 0.40
    body_cy = r.y + int(r.height * 0.56)
    top_y = body_cy - ry + 0.24 * ry               # the dimpled top

    body = apple_body(cx, body_cy, rx, ry)
    leaf_cx, leaf_cy = cx + 0.24 * rx, top_y - 0.22 * ry
    leaf = apple_leaf(leaf_cx, leaf_cy, 0.20 * rx, 0.10 * rx, angle=-0.5)

    # 1) Black outlines first (Paint opens on the black pencil).
    _stroke(bot, body)
    bot.think("low")
    _stroke(bot, leaf)
    bot.think("low")

    # 2) Flood-fill: red body, green leaf.
    _bucket_fill(bot, ribbon, _SWATCH_RED, (round(cx), round(body_cy)))
    bot.think("low")
    _bucket_fill(bot, ribbon, _SWATCH_GREEN, (round(leaf_cx), round(leaf_cy)))
    bot.think("low")

    # 3) Stem last, in brown, so it stays clean over the fills.
    bot.click(ribbon(*_SWATCH_BROWN))
    bot.think("low")
    bot.click(ribbon(*_TOOL_PENCIL))
    bot.think("low")
    _stroke(bot, apple_stem(cx, top_y, ry))


# ---------------------------------------------------------------------------
# Open Paint via the Start menu, then draw
# ---------------------------------------------------------------------------


def open_paint(bot: Bot, timeout: float = 20.0):
    """Press the Windows key, search "paint", launch it; fall back to mspaint.exe."""
    bot.press("win")                    # open Start
    time.sleep(1.0)
    bot.type("paint")                   # type into Start search (human rhythm)
    time.sleep(1.3)                     # let search results resolve
    bot.press("enter")                  # launch the top hit
    try:
        return bot.wait_for_window("Paint", timeout=timeout)
    except TargetNotFound:
        bot.press("esc")                # Start search was flaky -> launch directly
        bot.open_app("mspaint.exe")
        return bot.wait_for_window("Paint", timeout=timeout)


def run_demo() -> str:
    from humanpc.input.sendinput_driver import SendInputDriver

    # SendInput injects real mouse events that Paint samples into continuous lines.
    bot = Bot(persona="default", driver=SendInputDriver())
    try:
        print("Opening Paint in 2s (Ctrl+Alt+Q to abort)...")
        time.sleep(2)

        open_paint(bot)
        time.sleep(1.0)
        win = bot.focus("Paint")
        win.maximize()
        time.sleep(1.0)
        win = bot.find_window("Paint") or win   # refresh rect after maximize
        print(f"Paint up: {win.title!r} at {win.rect.as_tuple()}")

        draw_apple(bot, win)

        os.makedirs("captures", exist_ok=True)
        out = os.path.join("captures", "paint_apple.png")
        bot.screenshot(out, region=win.rect)
        print(f"Done. {len(bot.audit)} actions. Screenshot -> {out}")
        return out
    finally:
        bot.close()


# ---------------------------------------------------------------------------
# pytest entry point (gated)
# ---------------------------------------------------------------------------

_LIVE = os.environ.get("HUMANPC_LIVE") == "1"


@pytest.mark.skipif(sys.platform != "win32", reason="Paint is Windows-only")
@pytest.mark.skipif(not _LIVE, reason="set HUMANPC_LIVE=1 to run the live Paint demo")
def test_paint_apple_live():
    out = run_demo()
    assert os.path.exists(out)


if __name__ == "__main__":
    run_demo()

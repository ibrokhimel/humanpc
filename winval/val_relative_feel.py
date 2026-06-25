"""Aggregate feel check for RELATIVE mode (the user's default).

Runs several moves and reports the human-imperfection signals using the RIGHT
metrics: max perpendicular deviation (curve), overshoot, micro-pauses, plus the
glitch guards (max per-step jump, landing miss).
"""
import ctypes
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from winhook import Capture, WM_MOUSEMOVE  # noqa: E402

from humanpc import Bot  # noqa: E402
from humanpc.config import Config  # noqa: E402
from humanpc.input.sendinput_driver import SendInputDriver  # noqa: E402

u = ctypes.windll.user32
SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def perp_dev(pts, a, b):
    ax, ay = a; bx, by = b
    L = math.dist(a, b) or 1.0
    return max((abs((bx - ax) * (ay - y) - (ax - x) * (by - ay)) / L) for (x, y) in pts)


def one_move(bot, start, target):
    cap = Capture()
    u.SetCursorPos(*start)
    time.sleep(0.25)
    cap.run(lambda: bot.move_to(target), timeout=15.0)
    pts = [(e["x"], e["y"]) for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    ts = [e["t"] for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    if len(pts) < 3:
        return None
    d2t = [math.dist(p, target) for p in pts]
    imin = min(range(len(d2t)), key=lambda i: d2t[i])
    return {
        "miss": math.dist(pts[-1], target),
        "dev": perp_dev(pts, start, target),
        "maxjump": max(math.dist(pts[i - 1], pts[i]) for i in range(1, len(pts))),
        "overshoot": max((d2t[i] for i in range(imin, len(d2t))), default=0.0),
        "pauses": sum(1 for i in range(1, len(ts)) if (ts[i] - ts[i - 1]) > 0.045),
        "dur": ts[-1] - ts[0],
    }


pairs = [
    ((0.2, 0.75), (0.8, 0.25)), ((0.8, 0.25), (0.3, 0.6)),
    ((0.3, 0.6), (0.7, 0.8)), ((0.7, 0.8), (0.2, 0.3)),
    ((0.2, 0.3), (0.85, 0.7)), ((0.85, 0.7), (0.5, 0.45)),
]
bot = Bot(driver=SendInputDriver(), config=Config(relative_mouse=True), arm=False)
print("RELATIVE mode — per move:")
rows = []
for (sa, ta) in pairs:
    s = (int(SW * sa[0]), int(SH * sa[1]))
    t = (int(SW * ta[0]), int(SH * ta[1]))
    r = one_move(bot, s, t)
    if r:
        rows.append(r)
        print(f"  {s}->{t}: miss {r['miss']:.0f}px  curve(maxdev) {r['dev']:.0f}px  "
              f"overshoot {r['overshoot']:.0f}px  maxjump {r['maxjump']:.0f}px  "
              f"pauses {r['pauses']}  {r['dur']*1000:.0f}ms")
bot.close()

n = len(rows)
print(f"\nSUMMARY over {n} relative-mode moves:")
print(f"  all land exact (<=1px)     : {all(r['miss'] <= 1 for r in rows)}  "
      f"(max miss {max(r['miss'] for r in rows):.1f}px)")
print(f"  no glitch teleport (<40px) : {all(r['maxjump'] < 40 for r in rows)}  "
      f"(max jump {max(r['maxjump'] for r in rows):.1f}px)")
print(f"  curve present (maxdev)     : mean {sum(r['dev'] for r in rows)/n:.0f}px  "
      f"max {max(r['dev'] for r in rows):.0f}px")
print(f"  moves with overshoot >5px  : {sum(1 for r in rows if r['overshoot'] > 5)}/{n}")
print(f"  moves with a micro-pause   : {sum(1 for r in rows if r['pauses'] > 0)}/{n}")

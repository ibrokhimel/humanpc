"""Characterise the real on-screen cursor path (absolute vs relative mode).

Uses the WH_MOUSE_LL hook to record the actual cursor trajectory the driver
produces, then reports speed, path 'wanderiness', per-step jumps (glitch detector),
backtracking, and overshoot.
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


def analyse(label, pts_t, start, target):
    pts = [(x, y) for (x, y, t) in pts_t]
    ts = [t for (x, y, t) in pts_t]
    if len(pts) < 2:
        print(f"[{label}] too few points: {len(pts)}"); return
    dur = ts[-1] - ts[0]
    straight = math.dist(start, target)
    plen = sum(math.dist(pts[i - 1], pts[i]) for i in range(1, len(pts)))
    jumps = [math.dist(pts[i - 1], pts[i]) for i in range(1, len(pts))]
    # backtracking: steps whose distance-to-target increases
    d2t = [math.dist(p, target) for p in pts]
    backsteps = sum(1 for i in range(1, len(d2t)) if d2t[i] > d2t[i - 1] + 0.5)
    # overshoot: closest approach to target, then how far it went beyond afterward
    imin = min(range(len(d2t)), key=lambda i: d2t[i])
    beyond = max((d2t[i] for i in range(imin, len(d2t))), default=0.0)
    print(f"\n[{label}]  start={start} target={target}")
    print(f"   landed              : {pts[-1]}  (miss {math.dist(pts[-1], target):.1f}px)")
    print(f"   duration            : {dur*1000:.0f} ms   ({len(pts)} move events)")
    print(f"   straight dist        : {straight:.0f}px;  path length {plen:.0f}px;  "
          f"wanderiness {plen/max(1,straight):.2f}x")
    print(f"   per-step jump (px)   : median {sorted(jumps)[len(jumps)//2]:.1f}  "
          f"max {max(jumps):.1f}  (large max => glitchy teleport)")
    print(f"   backtracking steps   : {backsteps}/{len(pts)-1}  "
          f"(steps moving AWAY from target)")
    print(f"   overshoot past target: {beyond:.1f}px after closest approach")
    gaps = [(ts[i] - ts[i - 1]) * 1000 for i in range(1, len(ts))]
    pauses = [g for g in gaps if g > 45]
    sg = sorted(gaps)
    print(f"   inter-sample dt (ms) : median {sg[len(sg)//2]:.1f}  p90 {sg[int(len(sg)*0.9)]:.1f}  "
          f"max {max(gaps):.1f}   micro-pauses(>45ms): {len(pauses)}")


def capture_move(mode_relative, start, target):
    cap = Capture()
    bot = Bot(driver=SendInputDriver(),
              config=Config(seed=None, relative_mouse=mode_relative), arm=False)
    u.SetCursorPos(*start)
    time.sleep(0.3)

    def action():
        bot.move_to(target)
    cap.run(action, timeout=20.0)
    bot.close()
    pts = [(e["x"], e["y"], e["t"]) for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    return pts


SW = u.GetSystemMetrics(0); SH = u.GetSystemMetrics(1)
start = (int(SW * 0.2), int(SH * 0.75))
target = (int(SW * 0.8), int(SH * 0.25))

print("=== ABSOLUTE mode (default) ===")
analyse("absolute", capture_move(False, start, target), start, target)
time.sleep(0.5)
print("\n=== RELATIVE mode (relative_mouse=True) ===")
analyse("relative", capture_move(True, start, target), start, target)

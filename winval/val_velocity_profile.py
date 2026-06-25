"""Verify the Sigma-Lognormal velocity profile on real captured moves.

Research target: peak velocity at ~40-50% of movement duration, right-skewed
(short accel, long decel) — NOT symmetric/triangular/uniform (bot tells).
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


def speed_series(pts, ts):
    sp, tm = [], []
    for i in range(1, len(pts)):
        dt = ts[i] - ts[i - 1]
        if dt > 0:
            sp.append(math.dist(pts[i], pts[i - 1]) / dt)
            tm.append((ts[i] + ts[i - 1]) / 2)
    return sp, tm


def smooth(xs, w=5):
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - w), min(len(xs), i + w + 1)
        out.append(sum(xs[lo:hi]) / (hi - lo))
    return out


peak_fracs = []
for run in range(6):
    start = (int(SW * 0.2), int(SH * 0.75))
    target = (int(SW * 0.8), int(SH * 0.3))
    bot = Bot(driver=SendInputDriver(), config=Config(relative_mouse=True), arm=False)
    cap = Capture()
    u.SetCursorPos(*start)
    time.sleep(0.3)
    cap.run(lambda: bot.move_to(target), timeout=15.0)
    bot.close()
    pts = [(e["x"], e["y"]) for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    ts = [e["t"] for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    if len(pts) < 8:
        continue
    sp, tm = speed_series(pts, ts)
    sp = smooth(sp)
    pk = max(range(len(sp)), key=lambda i: sp[i])
    t0, t1 = tm[0], tm[-1]
    frac = (tm[pk] - t0) / (t1 - t0) if t1 > t0 else 0
    peak_fracs.append(frac)
    # rough skew: time in accel (before peak) vs decel (after)
    accel = (tm[pk] - t0) / (t1 - t0)
    print(f"  run {run+1}: peak velocity at {frac*100:4.0f}% of duration  "
          f"(accel {accel*100:.0f}% / decel {100-accel*100:.0f}%)  peakspeed {sp[pk]:.0f}px/s")

if peak_fracs:
    mean = sum(peak_fracs) / len(peak_fracs)
    print(f"\nmean peak-velocity position: {mean*100:.0f}% of duration "
          f"(research target ~40-50%; <50% = right-skewed/human)")
    print(f"right-skewed (peak in first half) on {sum(1 for f in peak_fracs if f < 0.5)}/{len(peak_fracs)} moves")

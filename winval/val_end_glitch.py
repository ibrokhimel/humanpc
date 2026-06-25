"""Diagnose the 'glitches when it stops' bug: dump the TAIL of a relative move."""
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

for run in range(3):
    start = (int(SW * 0.25), int(SH * 0.7))
    target = (int(SW * 0.75), int(SH * 0.35))
    bot = Bot(driver=SendInputDriver(), config=Config(relative_mouse=True), arm=False)
    cap = Capture()
    u.SetCursorPos(*start)
    time.sleep(0.3)
    cap.run(lambda: bot.move_to(target), timeout=15.0)
    bot.close()
    evs = [(e["x"], e["y"], e["t"]) for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    print(f"\n=== run {run+1}: target={target}  final cursor={evs[-1][:2]} ===")
    tail = evs[-16:]
    for i, (x, y, t) in enumerate(tail):
        d2t = math.dist((x, y), target)
        jump = "" if i == 0 else f"jump {math.dist((x, y), tail[i-1][:2]):5.1f}px"
        gap = "" if i == 0 else f"dt {(t - tail[i-1][2])*1000:5.1f}ms"
        print(f"   ({x:5d},{y:5d})  d2target {d2t:5.1f}px   {jump:14s} {gap}")

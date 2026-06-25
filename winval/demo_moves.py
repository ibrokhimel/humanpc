"""Watchable demo of the new mouse feel. WATCH YOUR CURSOR.

Part 1: absolute mode (the default) — faster ballistic + visible overshoot/correct.
Part 2: relative mode (relative_mouse=True) — now smooth (was glitchy/teleporting).
"""
import ctypes
import time

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.sendinput_driver import SendInputDriver

u = ctypes.windll.user32
SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)

# A varied tour of targets (near + far, different directions).
pts = [
    (0.20, 0.30), (0.80, 0.30), (0.50, 0.80), (0.15, 0.70),
    (0.85, 0.75), (0.50, 0.20), (0.30, 0.55), (0.70, 0.45),
]
targets = [(int(SW * fx), int(SH * fy)) for fx, fy in pts]

print("WATCH YOUR CURSOR — starting in 3s...")
time.sleep(3)

print("\n--- Part 1: ABSOLUTE mode (default) ---")
bot = Bot(driver=SendInputDriver(), config=Config(), arm=False)
for i, t in enumerate(targets, 1):
    s = time.perf_counter()
    bot.move_to(t)
    print(f"  move {i}: -> {t}  in {(time.perf_counter()-s)*1000:.0f} ms")
    time.sleep(0.45)
bot.close()

print("\n--- Part 2: RELATIVE mode (relative_mouse=True), now smooth ---")
bot = Bot(driver=SendInputDriver(), config=Config(relative_mouse=True), arm=False)
for i, t in enumerate(targets[:5], 1):
    s = time.perf_counter()
    bot.move_to(t)
    print(f"  move {i}: -> {t}  in {(time.perf_counter()-s)*1000:.0f} ms  landed {bot.position()}")
    time.sleep(0.45)
bot.close()
print("\nDone.")

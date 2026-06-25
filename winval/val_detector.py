"""Adversarial validation harness: score REAL generated movement like a detector.

Captures humanpc relative-mode trajectories on Windows, builds matched naive-bot
baselines (straight + constant velocity; and straight + white-noise jitter), and
reports, per research feature, where each falls vs human reference ranges plus the
single-feature discriminator accuracy (humanpc vs bot).
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
from humanpc.validation import (  # noqa: E402
    _HUMAN_BANDS, threshold_accuracy, trajectory_features, trajectory_realism_report,
)

u = ctypes.windll.user32
SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
random_state = 12345


def rnd():
    global random_state
    random_state = (1103515245 * random_state + 12345) & 0x7FFFFFFF
    return random_state / 0x7FFFFFFF


def straight_bot(s, t, n=70, total=0.45, noise=0.0):
    xs, ys, ts = [], [], []
    for k in range(n):
        f = k / (n - 1)
        nx = (rnd() - 0.5) * 2 * noise
        ny = (rnd() - 0.5) * 2 * noise
        xs.append(s[0] + (t[0] - s[0]) * f + nx)
        ys.append(s[1] + (t[1] - s[1]) * f + ny)
        ts.append(total * f)
    return xs, ys, ts


PAIRS = [((0.2, 0.75), (0.8, 0.3)), ((0.8, 0.3), (0.3, 0.65)), ((0.3, 0.65), (0.75, 0.8)),
         ((0.75, 0.8), (0.2, 0.35)), ((0.2, 0.35), (0.85, 0.7)), ((0.85, 0.7), (0.45, 0.4)),
         ((0.45, 0.4), (0.7, 0.75)), ((0.7, 0.75), (0.25, 0.55))]

RELATIVE = "--absolute" not in sys.argv
MODE = "relative" if RELATIVE else "absolute"
hp, b_straight, b_noisy = [], [], []
bot = Bot(driver=SendInputDriver(), config=Config(relative_mouse=RELATIVE), arm=False)
print(f"capturing humanpc {MODE}-mode trajectories...")
for (sa, ta) in PAIRS:
    s = (int(SW * sa[0]), int(SH * sa[1]))
    t = (int(SW * ta[0]), int(SH * ta[1]))
    cap = Capture()
    u.SetCursorPos(*s)
    time.sleep(0.25)
    cap.run(lambda: bot.move_to(t), timeout=15.0)
    xs = [e["x"] for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    ys = [e["y"] for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    ts = [e["t"] for e in cap.mouse if e["msg"] == WM_MOUSEMOVE]
    if len(xs) < 8:
        continue
    hp.append(trajectory_features(xs, ys, ts))
    b_straight.append(trajectory_features(*straight_bot(s, t)))
    b_noisy.append(trajectory_features(*straight_bot(s, t, noise=2.5)))
bot.close()


def mean(key, batch):
    vs = [f[key] for f in batch if key in f]
    return sum(vs) / len(vs) if vs else 0.0


def in_range(key, batch):
    lo, hi = _HUMAN_BANDS[key]
    vs = [f[key] for f in batch if key in f]
    return sum(1 for v in vs if lo <= v <= hi) / len(vs) if vs else 0.0


print(f"\ncaptured {len(hp)} humanpc moves\n")
print(f"{'feature':>18} | {'human band':>14} | {'humanpc':>9} | {'straight':>9} | "
      f"{'noisy':>8} | {'hp in-rng':>9} | {'disc(hp/bot)':>11}")
print("-" * 100)
for key, (lo, hi) in _HUMAN_BANDS.items():
    disc = threshold_accuracy([f[key] for f in hp if key in f],
                              [f[key] for f in b_straight if key in f])
    print(f"{key:>18} | {f'{lo:.2f}-{hi:.2f}':>14} | {mean(key, hp):9.3f} | "
          f"{mean(key, b_straight):9.3f} | {mean(key, b_noisy):8.3f} | "
          f"{in_range(key, hp)*100:7.0f}% | {disc:11.2f}")

def _score(feats):
    return sum(1 for k, (lo, hi) in _HUMAN_BANDS.items()
               if k in feats and lo <= feats[k] <= hi) / len(_HUMAN_BANDS)


print("-" * 100)
print(f"overall human-likeness score:  humanpc {sum(_score(f) for f in hp)/len(hp):.2f}   "
      f"straight-bot {sum(_score(f) for f in b_straight)/len(b_straight):.2f}   "
      f"noisy-bot {sum(_score(f) for f in b_noisy)/len(b_noisy):.2f}   (1.0 = all features human)")

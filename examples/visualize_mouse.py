"""Visualise the Phase 1 mouse engine.

Plans several human-like paths from a common start to different targets and plots
them. With matplotlib installed it writes a PNG; otherwise it prints a summary so
the script still runs on a bare interpreter.

    pip install matplotlib
    python examples/visualize_mouse.py
"""

from __future__ import annotations

import os
import random

from humanpc.geometry import distance
from humanpc.hil.mouse import MouseTrajectoryEngine


def main() -> None:
    engine = MouseTrajectoryEngine()
    rng = random.Random(42)
    start = (100, 100)
    targets = [(820, 540), (760, 130), (200, 500), (900, 300), (140, 160)]

    paths = [
        [(s.point.x, s.point.y) for s in engine.plan(start, t, rng=rng)]
        for t in targets
    ]

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed (pip install matplotlib); summary only:\n")
        for t, p in zip(targets, paths):
            straight = distance(start, t)
            travelled = sum(
                distance(p[i - 1], p[i]) for i in range(1, len(p))
            )
            print(
                f"  -> {t}: {len(p)} pts, path {travelled:.0f}px vs straight "
                f"{straight:.0f}px (+{(travelled / straight - 1) * 100:.0f}%)"
            )
        return

    plt.figure(figsize=(9, 6))
    for t, p in zip(targets, paths):
        xs = [q[0] for q in p]
        ys = [q[1] for q in p]
        plt.plot(xs, ys, marker="o", markersize=2, linewidth=1)
        plt.scatter([t[0]], [t[1]], marker="x", s=60, c="red")
    plt.scatter([start[0]], [start[1]], c="black", s=60, label="start")
    plt.gca().invert_yaxis()  # screen coords: y grows downward
    plt.title("humanpc — human-like mouse paths")
    plt.legend()

    os.makedirs("captures", exist_ok=True)
    out = os.path.join("captures", "mouse_paths.png")
    plt.savefig(out, dpi=120, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

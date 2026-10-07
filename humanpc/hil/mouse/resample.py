"""Resample a planned trajectory onto a fixed device polling grid.

Why this exists (the largest single realism gap in the old pipeline):

A physical mouse is a **fixed-clock sampler**. Its sensor integrates motion
continuously, but the HID interrupt endpoint is polled on a rigid schedule —
125 / 250 / 500 / 1000 Hz — and each report carries an *integer* displacement in
device counts. So a real event stream has:

  * near-constant inter-event intervals (CV ~0.01-0.05, always a multiple of the
    polling period), and
  * all of the human variability expressed in the **deltas**.

``MouseTrajectoryEngine`` produces the opposite: a per-step ``dt`` that is itself
jittered and occasionally interrupted by a long micro-pause, with smoothed
multi-pixel displacements. Measured on the old pipeline that gave an interval CV
of ~0.72 at 56-79 Hz with ~200 ms holes in the stream — a signature no mouse can
produce, and one that is trivially separable however good the path *shape* is.

This module converts a plan (a *path through time*) into a device report stream:

  1. Treat the plan's knots as samples of continuous position-vs-time.
  2. Walk a fixed ``1/hz`` grid, interpolating position at each tick.
  3. Add a sub-pixel tremor so a hand that is "paused" mid-move still registers
     the occasional count — a human hesitation is a *low-displacement* stretch,
     not a gap in the stream.
  4. Emit a report only when the integer position changes, exactly as a sensor
     that registers no counts sends no packet. Emitted timestamps therefore stay
     on the grid, and the deltas carry the variability.
"""

from __future__ import annotations

import math

from ...geometry import Point
from .step import MouseStep

# Polling rates real mice actually run at, with rough population weights: 125 Hz
# is the USB default (most office mice); 500/1000 Hz are gaming mice.
POLLING_RATES: tuple[int, ...] = (125, 250, 500, 1000)
POLLING_WEIGHTS: tuple[float, ...] = (0.55, 0.10, 0.15, 0.20)

DEFAULT_POLLING_HZ = 125


def sample_polling_hz(rng) -> int:
    """Draw a device polling rate for one ``Individual`` (a hardware trait)."""
    r = rng.random()
    acc = 0.0
    for hz, w in zip(POLLING_RATES, POLLING_WEIGHTS):
        acc += w
        if r <= acc:
            return hz
    return POLLING_RATES[-1]


def _knots(plan: list[MouseStep]) -> tuple[list[float], list[Point]]:
    """(time, position) knots. ``dt`` is the dwell *after* arriving at a point."""
    times: list[float] = []
    points: list[Point] = []
    t = 0.0
    for step in plan:
        times.append(t)
        points.append(step.point)
        t += max(0.0, step.dt)
    return times, points


def _interp(times: list[float], points: list[Point], t: float, cursor: int) -> tuple[Point, int]:
    """Position at time ``t``; ``cursor`` is a monotonic search hint."""
    n = len(times)
    while cursor + 1 < n and times[cursor + 1] <= t:
        cursor += 1
    if cursor + 1 >= n:
        return points[-1], cursor
    t0, t1 = times[cursor], times[cursor + 1]
    span = t1 - t0
    if span <= 0:
        return points[cursor + 1], cursor
    f = (t - t0) / span
    a, b = points[cursor], points[cursor + 1]
    return Point(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f), cursor


def resample_to_grid(
    plan: list[MouseStep],
    hz: int = DEFAULT_POLLING_HZ,
    rng=None,
    *,
    tremor_px: float = 0.34,
    tremor_hz: tuple[float, float] = (8.0, 12.0),
) -> list[MouseStep]:
    """Convert ``plan`` into a fixed-rate device report stream.

    Returns steps whose dwells are integer multiples of ``1/hz`` and whose points
    move in small integer increments. The last step lands exactly on the plan's
    final point, so callers keep pixel-accurate targeting.
    """
    if hz <= 0 or len(plan) < 2:
        return plan

    times, points = _knots(plan)
    total = times[-1]
    if total <= 0:
        return plan

    period = 1.0 / hz
    target = points[-1]

    # Physiological tremor keeps a "still" hand registering the odd count.
    tremor = rng is not None and tremor_px > 0
    if tremor:
        fx, fy = rng.uniform(*tremor_hz), rng.uniform(*tremor_hz)
        phx, phy = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)

    out: list[MouseStep] = [MouseStep(Point(*plan[0].point.as_int()), 0.0)]
    last = plan[0].point.as_int()
    pending = 0.0          # grid time accrued since the last emitted report
    cursor = 0

    for k in range(1, int(total / period) + 1):
        t = k * period
        pos, cursor = _interp(times, points, t, cursor)
        if tremor:
            pos = Point(pos.x + tremor_px * math.sin(2 * math.pi * fx * t + phx),
                        pos.y + tremor_px * math.sin(2 * math.pi * fy * t + phy))
        pending += period
        ip = (round(pos.x), round(pos.y))
        if ip != last:                       # counts registered -> a HID report
            # The accrued wait belongs to the PREVIOUS report: a step's dt is the
            # dwell after arriving at its own point.
            out[-1] = MouseStep(out[-1].point, pending)
            out.append(MouseStep(Point(*ip), 0.0))
            last = ip
            pending = 0.0

    tx, ty = target.as_int()
    if last != (tx, ty):
        out[-1] = MouseStep(out[-1].point, max(pending, period))
        out.append(MouseStep(Point(tx, ty), 0.0))
    else:
        out[-1] = MouseStep(out[-1].point, pending)
    return out

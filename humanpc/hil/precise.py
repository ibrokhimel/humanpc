"""High-resolution sleep + Windows timer-resolution control.

``time.sleep`` on Windows is bounded by the system timer tick (~15.6 ms by
default), so the sub-tick delays the HIL computes (e.g. an 8 ms inter-step wait)
quantise into a non-human "comb" in the timing histogram — a detection signal
independent of trajectory quality.

``precise_sleep`` sleeps coarsely, then busy-waits the small remainder against
``perf_counter`` for sub-tick accuracy. ``high_resolution_timer`` additionally
lowers the system tick to 1 ms on Windows for its duration (no-op elsewhere).
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager


def precise_sleep(seconds: float, *, spin: float = 0.0015) -> None:
    """Sleep ``seconds`` accurately. Coarse-sleep most of it, busy-wait the rest."""
    if seconds <= 0:
        return
    end = time.perf_counter() + seconds
    coarse = seconds - spin
    if coarse > 0:
        time.sleep(coarse)
    while time.perf_counter() < end:  # busy-wait the sub-tick remainder
        pass


def begin_high_resolution() -> bool:
    """Lower the Windows timer tick to 1 ms. Returns False (no-op) elsewhere."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.winmm.timeBeginPeriod(1)
            return True
        except Exception:
            return False
    return False


def end_high_resolution() -> None:
    """Restore the Windows timer tick. No-op elsewhere / if never begun."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass


@contextmanager
def high_resolution_timer():
    active = begin_high_resolution()
    try:
        yield active
    finally:
        if active:
            end_high_resolution()

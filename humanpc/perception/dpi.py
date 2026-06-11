"""Per-monitor DPI awareness.

On Windows 11, per-monitor display scaling is the single biggest cause of "the
click landed in the wrong place": without declaring DPI awareness, the OS lies to
the process about coordinates and virtualises the desktop. This must run before
any capture or input. It is a no-op off Windows.
"""

from __future__ import annotations

import ctypes
import logging
import sys

_log = logging.getLogger("humanpc.dpi")

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def set_dpi_awareness() -> str:
    """Make the process per-monitor DPI aware. Returns the mode that took effect."""
    if sys.platform != "win32":
        return "noop"

    # Best: per-monitor v2 (Win10 1703+). Returns BOOL; does not raise.
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(_PER_MONITOR_AWARE_V2):
            return "per_monitor_v2"
    except Exception:
        pass

    # Good: per-monitor (Win8.1+). PROCESS_PER_MONITOR_DPI_AWARE == 2.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per_monitor"
    except Exception:
        pass

    # Fallback: system DPI aware (Vista+).
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except Exception as exc:
        _log.warning("could not set DPI awareness: %s", exc)
        return "unknown"

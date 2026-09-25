"""Event schema + compact delta encoding for recorded input streams.

A raw event is a tuple ``(t_ns, type, x, y, button, wheel)`` where ``t_ns`` is a
``time.perf_counter_ns()`` offset from the session start and ``x, y`` are
absolute physical screen pixels. On disk every column is delta-encoded and
stored in the narrowest integer type that fits, so zlib squeezes it to a few
bytes per event.
"""

from __future__ import annotations

MOVE, DOWN, UP, WHEEL, HWHEEL = range(5)
TYPE_NAMES = ("move", "down", "up", "wheel", "hwheel")

BTN_NONE, BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = range(4)

COLUMNS = ("t_us", "type", "x", "y", "button", "wheel")


def _np():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ImportError("recording storage needs numpy: pip install -e .[learn]") from exc
    return np


def _fit_signed(a):
    np = _np()
    lo, hi = (int(a.min()), int(a.max())) if a.size else (0, 0)
    for dt in (np.int8, np.int16, np.int32):
        info = np.iinfo(dt)
        if info.min <= lo and hi <= info.max:
            return a.astype(dt)
    return a.astype(np.int64)


def _fit_unsigned(a):
    np = _np()
    hi = int(a.max()) if a.size else 0
    for dt in (np.uint8, np.uint16, np.uint32):
        if hi <= np.iinfo(dt).max:
            return a.astype(dt)
    return a.astype(np.uint64)


def encode(raw) -> dict:
    """Raw event tuples -> dict of compact numpy columns (delta-encoded)."""
    np = _np()
    arr = np.asarray(raw, dtype=np.int64).reshape(-1, 6)
    t_us = arr[:, 0] // 1000
    x0, y0 = (arr[:1, 2], arr[:1, 3]) if len(arr) else (np.zeros(1, np.int64),) * 2
    return {
        "dt_us": _fit_unsigned(np.diff(t_us, prepend=0)),
        "type": arr[:, 1].astype(np.uint8),
        "x0": x0.astype(np.int32),
        "y0": y0.astype(np.int32),
        "dx": _fit_signed(np.diff(arr[:, 2], prepend=x0)),
        "dy": _fit_signed(np.diff(arr[:, 3], prepend=y0)),
        "button": arr[:, 4].astype(np.uint8),
        "wheel": _fit_signed(arr[:, 5]),
    }


def decode(cols) -> dict:
    """Compact columns -> absolute int64 columns named by ``COLUMNS``."""
    np = _np()
    return {
        "t_us": np.cumsum(cols["dt_us"].astype(np.int64)),
        "type": cols["type"].astype(np.int64),
        "x": int(np.ravel(cols["x0"])[0]) + np.cumsum(cols["dx"].astype(np.int64)),
        "y": int(np.ravel(cols["y0"])[0]) + np.cumsum(cols["dy"].astype(np.int64)),
        "button": cols["button"].astype(np.int64),
        "wheel": cols["wheel"].astype(np.int64),
    }

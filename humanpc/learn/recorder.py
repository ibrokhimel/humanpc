"""Background WH_MOUSE_LL recorder for real (hardware) mouse input.

Runs the hook on its own thread with a message pump, appending
``(t_ns, type, x, y, button, wheel)`` tuples (see ``events``). Events carrying
the LLMHF_INJECTED flag — i.e. produced by software such as humanpc itself —
are dropped by default so the dataset only contains genuine human movement.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes

from .events import (BTN_LEFT, BTN_MIDDLE, BTN_NONE, BTN_RIGHT, DOWN, HWHEEL, MOVE, UP,
                     WHEEL)

WH_MOUSE_LL = 14
WM_QUIT = 0x0012
LLMHF_INJECTED = 0x01
LLMHF_LOWER_IL_INJECTED = 0x02

# wParam -> (event type, button)
_MSG_MAP = {
    0x0200: (MOVE, BTN_NONE),
    0x0201: (DOWN, BTN_LEFT), 0x0202: (UP, BTN_LEFT),
    0x0204: (DOWN, BTN_RIGHT), 0x0205: (UP, BTN_RIGHT),
    0x0207: (DOWN, BTN_MIDDLE), 0x0208: (UP, BTN_MIDDLE),
    0x020A: (WHEEL, BTN_NONE), 0x020E: (HWHEEL, BTN_NONE),
}


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


def mouse_settings() -> dict:
    """Windows pointer speed (1-20, default 10) + acceleration ("Enhance pointer precision")."""
    if sys.platform != "win32":
        return {}
    spi = ctypes.windll.user32.SystemParametersInfoW
    speed = ctypes.c_int(0)
    accel = (ctypes.c_int * 3)()
    ok_speed = spi(0x0070, 0, ctypes.byref(speed), 0)  # SPI_GETMOUSESPEED
    ok_accel = spi(0x0003, 0, accel, 0)  # SPI_GETMOUSE
    return {"pointer_speed": speed.value if ok_speed else None,
            "enhance_precision": bool(accel[2]) if ok_accel else None}


class Recorder:
    """Records global mouse events between ``start()`` and ``stop()``."""

    def __init__(self, *, keep_injected: bool = False):
        self.keep_injected = keep_injected
        self.events: list[tuple] = []
        self.injected_dropped = 0
        self.paused = False
        self.t0 = 0
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._proc = None

    def start(self) -> None:
        if sys.platform != "win32":
            raise OSError("the recorder needs Windows (WH_MOUSE_LL)")
        self.t0 = time.perf_counter_ns()
        self._thread = threading.Thread(target=self._run, name="humanpc-recorder", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._error:
            raise self._error

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(2)

    def snapshot(self) -> list[tuple]:
        return list(self.events)

    # -- hook thread -------------------------------------------------------------
    def _on_mouse(self, n_code, w_param, l_param):
        if n_code == 0 and not self.paused:
            kind = _MSG_MAP.get(w_param)
            if kind is not None:
                ms = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if ms.flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED) and not self.keep_injected:
                    self.injected_dropped += 1
                else:
                    wheel = ctypes.c_short(ms.mouseData >> 16).value if kind[0] in (WHEEL, HWHEEL) else 0
                    self.events.append((time.perf_counter_ns() - self.t0, kind[0],
                                        ms.pt.x, ms.pt.y, kind[1], wheel))
        return self._user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        lresult = ctypes.c_ssize_t
        hookproc = ctypes.CFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hookproc, wintypes.HINSTANCE, wintypes.DWORD]
        user32.CallNextHookEx.restype = lresult
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self._user32 = user32

        self._tid = kernel32.GetCurrentThreadId()
        self._proc = hookproc(self._on_mouse)
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self._error = OSError(f"SetWindowsHookEx failed: {ctypes.get_last_error()}")
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWindowsHookEx(hook)

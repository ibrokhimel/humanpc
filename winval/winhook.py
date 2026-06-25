"""Shared WH_KEYBOARD_LL / WH_MOUSE_LL capture harness for humanpc validation.

Installs global low-level hooks on the calling thread, runs an `action` callable
on a worker thread while pumping messages, and returns the captured event stream
with high-resolution timestamps and the raw hook flags (so we can read the
LLKHF_INJECTED / LLMHF_INJECTED bits and measure key-hold dwell).
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A

LLKHF_EXTENDED = 0x01
LLKHF_LOWER_IL_INJECTED = 0x02
LLKHF_INJECTED = 0x10

LLMHF_INJECTED = 0x01
LLMHF_LOWER_IL_INJECTED = 0x02

VK_PACKET = 0xE7
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1

PM_REMOVE = 0x0001


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.CFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.PeekMessageW.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class Capture:
    """Records keyboard + mouse low-level events while `action` runs."""

    def __init__(self):
        self.keys: list[dict] = []
        self.mouse: list[dict] = []
        self.t0 = 0.0
        self._kb_proc = None
        self._ms_proc = None

    def _on_key(self, nCode, wParam, lParam):
        if nCode == 0:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            self.keys.append({
                "t": time.perf_counter() - self.t0,
                "msg": int(wParam),
                "down": wParam in (WM_KEYDOWN, WM_SYSKEYDOWN),
                "vk": kb.vkCode,
                "scan": kb.scanCode,
                "flags": kb.flags,
                "injected": bool(kb.flags & LLKHF_INJECTED),
                "lower_il": bool(kb.flags & LLKHF_LOWER_IL_INJECTED),
                "evtime": kb.time,
                "extra": int(kb.dwExtraInfo),
            })
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _on_mouse(self, nCode, wParam, lParam):
        if nCode == 0:
            ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            self.mouse.append({
                "t": time.perf_counter() - self.t0,
                "msg": int(wParam),
                "x": ms.pt.x,
                "y": ms.pt.y,
                "flags": ms.flags,
                "injected": bool(ms.flags & LLMHF_INJECTED),
                "lower_il": bool(ms.flags & LLMHF_LOWER_IL_INJECTED),
                "extra": int(ms.dwExtraInfo),
            })
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def run(self, action, *, timeout: float = 20.0, grace: float = 0.4):
        self._kb_proc = HOOKPROC(self._on_key)
        self._ms_proc = HOOKPROC(self._on_mouse)
        hmod = kernel32.GetModuleHandleW(None)
        kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, hmod, 0)
        ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, hmod, 0)
        if not kb_hook or not ms_hook:
            raise OSError(f"SetWindowsHookEx failed: {ctypes.get_last_error()}")

        self.t0 = time.perf_counter()
        result_box = {}

        def worker():
            try:
                result_box["value"] = action()
            except Exception as e:  # noqa: BLE001
                result_box["error"] = e

        th = threading.Thread(target=worker, daemon=True)
        th.start()

        msg = wintypes.MSG()
        deadline = time.perf_counter() + timeout
        done_at = None
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            now = time.perf_counter()
            if not th.is_alive() and done_at is None:
                done_at = now
            if done_at is not None and now - done_at >= grace:
                break
            if now >= deadline:
                break
            time.sleep(0.001)

        user32.UnhookWindowsHookEx(kb_hook)
        user32.UnhookWindowsHookEx(ms_hook)
        if "error" in result_box:
            raise result_box["error"]
        return result_box.get("value")


def vk_name(vk: int) -> str:
    names = {
        VK_SHIFT: "SHIFT", VK_LSHIFT: "LSHIFT", VK_RSHIFT: "RSHIFT",
        0x11: "CTRL", 0xA2: "LCTRL", 0xA3: "RCTRL",
        0x12: "ALT", 0x08: "BACKSPACE", 0x0D: "ENTER", 0x20: "SPACE",
        VK_PACKET: "PACKET",
    }
    if vk in names:
        return names[vk]
    if 0x30 <= vk <= 0x5A:
        return chr(vk)
    return f"0x{vk:02X}"

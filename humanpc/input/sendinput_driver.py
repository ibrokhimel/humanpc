"""Native Win32 SendInput driver.

DirectX / anti-cheat games often ignore pyautogui's SetCursorPos-based movement;
SendInput injects at a lower level and is generally honoured. Text is injected as
Unicode (reliable for fields); named keys go through virtual-key codes.

Windows-only. Constructed explicitly and passed to ``Bot(driver=SendInputDriver())``.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from ..exceptions import DriverError
from .driver import Button, InputDriver

_VK = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12,
    "win": 0x5B, "capslock": 0x14,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def _vk_code(key: str) -> int:
    k = key.lower()
    if k in _VK:
        return _VK[k]
    if len(key) == 1:
        c = key.upper()
        if "A" <= c <= "Z" or "0" <= c <= "9":
            return ord(c)
    raise KeyError(f"no virtual-key code for {key!r}")


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p),
    ]


class _UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


_INPUT_MOUSE, _INPUT_KEYBOARD = 0, 1
_MOVE, _ABSOLUTE, _VIRTUALDESK = 0x0001, 0x8000, 0x4000
_LEFTDOWN, _LEFTUP = 0x0002, 0x0004
_RIGHTDOWN, _RIGHTUP = 0x0008, 0x0010
_MIDDLEDOWN, _MIDDLEUP = 0x0020, 0x0040
_WHEEL = 0x0800
_KEYUP, _UNICODE = 0x0002, 0x0004
_SM_XV, _SM_YV, _SM_CXV, _SM_CYV = 76, 77, 78, 79


class SendInputDriver(InputDriver):
    def __init__(self):
        if not hasattr(ctypes, "windll"):
            raise DriverError("SendInputDriver is Windows-only")
        self._u32 = ctypes.windll.user32

    def _send(self, inp: _INPUT) -> None:
        self._u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _mouse(self, flags: int, data: int = 0, dx: int = 0, dy: int = 0) -> None:
        mi = _MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, None)
        self._send(_INPUT(_INPUT_MOUSE, _UNION(mi=mi)))

    def move(self, x, y) -> None:
        vx = self._u32.GetSystemMetrics(_SM_XV)
        vy = self._u32.GetSystemMetrics(_SM_YV)
        vw = self._u32.GetSystemMetrics(_SM_CXV) or 1
        vh = self._u32.GetSystemMetrics(_SM_CYV) or 1
        nx = int((int(x) - vx) * 65535 / max(1, vw - 1))
        ny = int((int(y) - vy) * 65535 / max(1, vh - 1))
        self._mouse(_MOVE | _ABSOLUTE | _VIRTUALDESK, dx=nx, dy=ny)

    def mouse_down(self, button: Button = "left") -> None:
        self._mouse({"left": _LEFTDOWN, "right": _RIGHTDOWN, "middle": _MIDDLEDOWN}[button])

    def mouse_up(self, button: Button = "left") -> None:
        self._mouse({"left": _LEFTUP, "right": _RIGHTUP, "middle": _MIDDLEUP}[button])

    def scroll(self, dx, dy) -> None:
        if dy:
            self._mouse(_WHEEL, data=int(dy) * 120)

    def _key(self, vk: int, flags: int = 0) -> None:
        ki = _KEYBDINPUT(vk, 0, flags, 0, None)
        self._send(_INPUT(_INPUT_KEYBOARD, _UNION(ki=ki)))

    def key_down(self, key: str) -> None:
        self._key(_vk_code(key))

    def key_up(self, key: str) -> None:
        self._key(_vk_code(key), _KEYUP)

    def write_char(self, char: str) -> None:
        code = ord(char)
        down = _KEYBDINPUT(0, code, _UNICODE, 0, None)
        self._send(_INPUT(_INPUT_KEYBOARD, _UNION(ki=down)))
        up = _KEYBDINPUT(0, code, _UNICODE | _KEYUP, 0, None)
        self._send(_INPUT(_INPUT_KEYBOARD, _UNION(ki=up)))

    def position(self) -> tuple[int, int]:
        pt = wintypes.POINT()
        self._u32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

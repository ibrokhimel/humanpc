"""Native Win32 SendInput driver.

DirectX / anti-cheat games often ignore pyautogui's SetCursorPos-based movement;
SendInput injects at a lower level and is generally honoured. Text is injected as
Unicode (reliable for fields); named keys go through virtual-key codes.

Windows-only. Constructed explicitly and passed to ``Bot(driver=SendInputDriver())``.

Provenance limitation (important):
    Any user-mode ``SendInput`` event carries the kernel ``LLMHF_INJECTED`` /
    ``LLKHF_INJECTED`` flag, which a low-level hook (``WH_MOUSE_LL`` /
    ``WH_KEYBOARD_LL``) or ``GetMessageExtraInfo`` can read as "synthetic". This
    driver CANNOT remove that flag — no user-mode API can. Truly removing it
    requires a kernel-mode driver, an interception driver, or a hardware HID
    emulator. Such a backend plugs in via the same ``InputDriver`` seam (pass it
    as ``Bot(driver=...)``). The ``extra_info`` tag below only stamps a signature
    into ``dwExtraInfo`` so the bot can recognise its own events; it does not
    hide them. This driver improves *behavioural* realism (separable key-hold via
    char_down/char_up, relative motion through pointer ballistics), not provenance.
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
_EXTENDEDKEY, _KEYUP, _UNICODE = 0x0001, 0x0002, 0x0004
_MAPVK_VK_TO_VSC = 0
_SM_XV, _SM_YV, _SM_CXV, _SM_CYV = 76, 77, 78, 79

# Keys on the extended (grey) block of a 101-key keyboard. Real hardware sets
# KEYEVENTF_EXTENDEDKEY for these; omitting it is itself a mismatch.
_EXTENDED_VKS = frozenset({
    0x21, 0x22, 0x23, 0x24,           # pageup, pagedown, end, home
    0x25, 0x26, 0x27, 0x28,           # arrows
    0x2D, 0x2E,                       # insert, delete
    0x5B, 0x5C,                       # win keys
    0x6F,                             # numpad divide
})


class SendInputDriver(InputDriver):
    supports_dwell = True
    supports_relative = True
    supports_scancodes = True

    def __init__(self, *, extra_info: int = 0, unicode_fallback: bool = True):
        if not hasattr(ctypes, "windll"):
            raise DriverError("SendInputDriver is Windows-only")
        self._u32 = ctypes.windll.user32
        # Pin the signatures: both return 16/32-bit values that ctypes would
        # otherwise read as a plain int, so VkKeyScanW's -1 ("no mapping") would
        # not survive the round trip.
        self._u32.VkKeyScanW.argtypes = [wintypes.WCHAR]
        self._u32.VkKeyScanW.restype = wintypes.SHORT
        self._u32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        self._u32.MapVirtualKeyW.restype = wintypes.UINT
        # Stamped into every event's dwExtraInfo. Lets the bot identify its own
        # input; does NOT mask the injected flag (see module docstring).
        self._extra = ctypes.c_void_p(extra_info) if extra_info else None
        self._unicode_fallback = unicode_fallback
        self._vk_cache: dict[str, tuple[int, int] | None] = {}

    def _send(self, inp: _INPUT) -> None:
        self._u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _mouse(self, flags: int, data: int = 0, dx: int = 0, dy: int = 0) -> None:
        mi = _MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, self._extra)
        self._send(_INPUT(_INPUT_MOUSE, _UNION(mi=mi)))

    def move(self, x, y) -> None:
        vx = self._u32.GetSystemMetrics(_SM_XV)
        vy = self._u32.GetSystemMetrics(_SM_YV)
        vw = self._u32.GetSystemMetrics(_SM_CXV) or 1
        vh = self._u32.GetSystemMetrics(_SM_CYV) or 1
        nx = int((int(x) - vx) * 65535 / max(1, vw - 1))
        ny = int((int(y) - vy) * 65535 / max(1, vh - 1))
        self._mouse(_MOVE | _ABSOLUTE | _VIRTUALDESK, dx=nx, dy=ny)

    def move_relative(self, dx, dy) -> None:
        """Inject a relative move so it passes through pointer acceleration.

        Unlike the absolute ``move`` above, relative deltas are shaped by the OS
        ballistics curve and produce natural WM_INPUT raw-input streams. The Bot
        issues a final correction nudge to absorb any acceleration drift.
        """
        if int(dx) or int(dy):
            self._mouse(_MOVE, dx=int(dx), dy=int(dy))

    def mouse_down(self, button: Button = "left") -> None:
        self._mouse({"left": _LEFTDOWN, "right": _RIGHTDOWN, "middle": _MIDDLEDOWN}[button])

    def mouse_up(self, button: Button = "left") -> None:
        self._mouse({"left": _LEFTUP, "right": _RIGHTUP, "middle": _MIDDLEUP}[button])

    def scroll(self, dx, dy) -> None:
        if dy:
            self._mouse(_WHEEL, data=int(dy) * 120)

    def _key(self, vk: int, flags: int = 0) -> None:
        """Emit a keyboard event carrying the key's real hardware scan code.

        A hardware keypress always arrives with BOTH a virtual-key code and the
        scan code the keyboard controller produced; ``wScan=0`` (the old
        behaviour) is not a value any physical key can report, and anything
        reading scan codes rather than VKs — DirectInput, most games, some
        low-level hooks — sees nothing at all.
        """
        scan = self._u32.MapVirtualKeyW(vk, _MAPVK_VK_TO_VSC)
        if vk in _EXTENDED_VKS:
            flags |= _EXTENDEDKEY
        ki = _KEYBDINPUT(vk, scan, flags, 0, self._extra)
        self._send(_INPUT(_INPUT_KEYBOARD, _UNION(ki=ki)))

    def key_down(self, key: str) -> None:
        self._key(_vk_code(key))

    def key_up(self, key: str) -> None:
        self._key(_vk_code(key), _KEYUP)

    def _unicode(self, char: str, flags: int) -> None:
        ki = _KEYBDINPUT(0, ord(char), _UNICODE | flags, 0, self._extra)
        self._send(_INPUT(_INPUT_KEYBOARD, _UNION(ki=ki)))

    def _char_vk(self, char: str) -> tuple[int, int] | None:
        """(vk, shift_state) for ``char`` on the ACTIVE layout, or None.

        ``VkKeyScanW`` returns the virtual key in the low byte and the modifier
        state needed to produce the character in the high byte (1=Shift, 2=Ctrl,
        4=Alt). We only take keys reachable with at most Shift — AltGr and
        dead-key sequences are left to the Unicode path, which is always correct
        even though it is less realistic.
        """
        if char in self._vk_cache:
            return self._vk_cache[char]
        result = None
        try:
            scan = self._u32.VkKeyScanW(char)
        except Exception:
            scan = -1
        if scan != -1:
            vk, state = scan & 0xFF, (scan >> 8) & 0xFF
            if vk and not (state & ~0x01):   # no modifier, or Shift only
                result = (vk, state & 0x01)
        self._vk_cache[char] = result
        return result

    def char_down(self, char: str) -> None:
        """Press a character key.

        Prefers a real virtual key + scan code from the active layout. The old
        Unicode-only path made EVERY typed character arrive as ``VK_PACKET``
        (0xE7) with no scan code — a value no keyboard produces, so keystroke
        provenance was broken on every character regardless of dwell/rhythm
        modelling. Characters the layout can't reach with at most Shift still
        fall back to Unicode injection, which is less realistic but always
        produces the exact character.
        """
        mapped = self._char_vk(char)
        if mapped is None:
            if not self._unicode_fallback:
                raise DriverError(f"no layout mapping for {char!r}")
            self._unicode(char, 0)
        else:
            self._key(mapped[0])

    def char_up(self, char: str) -> None:
        mapped = self._char_vk(char)
        if mapped is None:
            self._unicode(char, _KEYUP)
        else:
            self._key(mapped[0], _KEYUP)

    def char_needs_shift(self, char: str) -> bool | None:
        """Whether the ACTIVE layout needs Shift for ``char``; None if unmapped.

        The Bot asks the driver rather than assuming US QWERTY, so the Shift it
        presses matches the key it is about to send.
        """
        mapped = self._char_vk(char)
        return None if mapped is None else bool(mapped[1])

    def write_char(self, char: str) -> None:
        # Atomic emit; the Bot uses char_down/char_up directly to insert a dwell.
        self.char_down(char)
        self.char_up(char)

    def position(self) -> tuple[int, int]:
        pt = wintypes.POINT()
        self._u32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

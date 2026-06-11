"""pyautogui-backed input driver (the Phase 0 default for real execution).

pyautogui is imported lazily so the core package has no hard dependency. We disable
pyautogui's own per-call PAUSE (the Bot/HIL owns all timing) and wire its
slam-to-corner FAILSAFE to the failsafe flag.
"""

from __future__ import annotations

from ..exceptions import DriverError
from .driver import Button, InputDriver


class PyAutoGUIDriver(InputDriver):
    def __init__(self, failsafe: bool = True):
        try:
            import pyautogui
        except Exception as exc:  # pragma: no cover - env dependent
            raise DriverError(
                "real input needs pyautogui: pip install humanpc[input]"
            ) from exc
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = 0  # we manage all delays ourselves
        self._pg = pyautogui

    def move(self, x: int, y: int) -> None:
        self._pg.moveTo(int(x), int(y), _pause=False)

    def mouse_down(self, button: Button = "left") -> None:
        self._pg.mouseDown(button=button, _pause=False)

    def mouse_up(self, button: Button = "left") -> None:
        self._pg.mouseUp(button=button, _pause=False)

    def scroll(self, dx: int, dy: int) -> None:
        if dy:
            self._pg.scroll(int(dy), _pause=False)
        if dx:
            self._pg.hscroll(int(dx), _pause=False)

    def key_down(self, key: str) -> None:
        self._pg.keyDown(key, _pause=False)

    def key_up(self, key: str) -> None:
        self._pg.keyUp(key, _pause=False)

    def write_char(self, char: str) -> None:
        if char == "\n":
            self._pg.press("enter", _pause=False)
        elif char == "\t":
            self._pg.press("tab", _pause=False)
        else:
            self._pg.write(char, _pause=False)

    def position(self) -> tuple[int, int]:
        p = self._pg.position()
        return (int(p[0]), int(p[1]))

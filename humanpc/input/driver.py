"""Input driver interface + a dependency-free NullDriver.

A driver exposes only *primitive* events (move one step, press one button, type one
char). Higher-level humanisation (curved paths, dwell, typing rhythm) lives above
it in the Bot / HIL, so every backend stays thin and interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

Button = str  # "left" | "right" | "middle"


class InputDriver(ABC):
    @abstractmethod
    def move(self, x: int, y: int) -> None:
        """Place the cursor at absolute (x, y)."""

    @abstractmethod
    def mouse_down(self, button: Button = "left") -> None: ...

    @abstractmethod
    def mouse_up(self, button: Button = "left") -> None: ...

    @abstractmethod
    def scroll(self, dx: int, dy: int) -> None:
        """Scroll by wheel deltas (positive dy == up)."""

    @abstractmethod
    def key_down(self, key: str) -> None: ...

    @abstractmethod
    def key_up(self, key: str) -> None: ...

    @abstractmethod
    def write_char(self, char: str) -> None:
        """Type a single character (handles shift/layout internally)."""

    @abstractmethod
    def position(self) -> tuple[int, int]:
        """Current cursor position."""

    # Convenience composites -------------------------------------------------
    def click(self, button: Button = "left") -> None:
        self.mouse_down(button)
        self.mouse_up(button)

    def tap(self, key: str) -> None:
        self.key_down(key)
        self.key_up(key)


class NullDriver(InputDriver):
    """Records events without touching the OS. Powers dry-run mode and tests."""

    def __init__(self):
        self.events: list[tuple] = []
        self._pos: tuple[int, int] = (0, 0)

    def move(self, x: int, y: int) -> None:
        self._pos = (int(x), int(y))
        self.events.append(("move", self._pos[0], self._pos[1]))

    def mouse_down(self, button: Button = "left") -> None:
        self.events.append(("mouse_down", button))

    def mouse_up(self, button: Button = "left") -> None:
        self.events.append(("mouse_up", button))

    def scroll(self, dx: int, dy: int) -> None:
        self.events.append(("scroll", dx, dy))

    def key_down(self, key: str) -> None:
        self.events.append(("key_down", key))

    def key_up(self, key: str) -> None:
        self.events.append(("key_up", key))

    def write_char(self, char: str) -> None:
        self.events.append(("write_char", char))

    def position(self) -> tuple[int, int]:
        return self._pos

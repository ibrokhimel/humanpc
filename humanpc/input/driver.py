"""Input driver interface + a dependency-free NullDriver.

A driver exposes only *primitive* events (move one step, press one button, type one
char). Higher-level humanisation (curved paths, dwell, typing rhythm) lives above
it in the Bot / HIL, so every backend stays thin and interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

Button = str  # "left" | "right" | "middle"


class InputDriver(ABC):
    # --- capability flags ---------------------------------------------------
    # Declared, not guessed. The Bot reads these to decide whether a HIL feature
    # can actually be realised on this backend; features that cannot be are
    # SKIPPED rather than silently degraded. (Sleeping a key-hold around an
    # atomic emit, for instance, produces no dwell at all *and* corrupts the
    # inter-key interval — worse than not modelling dwell in the first place.)
    supports_dwell: bool = False       # can separate char press from release
    supports_relative: bool = False    # can inject true relative motion
    supports_scancodes: bool = False   # emits hardware scan codes, not VK_PACKET

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

    # Optional primitives with safe fallbacks --------------------------------
    # Backends that can separate a character key-press into down/up events
    # (e.g. the native SendInput driver) override these AND set
    # ``supports_dwell = True``. The default keeps the atomic behaviour, so a
    # driver that only implements ``write_char`` still works — it just cannot
    # model dwell, and the Bot skips the hold rather than faking it.
    def char_down(self, char: str) -> None:
        """Press a character key. Default: atomic emit (no separable hold)."""
        self.write_char(char)

    def char_up(self, char: str) -> None:
        """Release a character key. Default: no-op (write_char already released)."""

    def char_needs_shift(self, char: str) -> bool | None:
        """Whether this backend's layout needs Shift for ``char``.

        ``None`` means "don't know" — the caller keeps its own (US QWERTY)
        assumption. Backends that resolve characters against the active keyboard
        layout override this so the modifier matches the key actually sent.
        """
        return None

    def move_relative(self, dx: int, dy: int) -> None:
        """Move by a relative delta. Default: compute the absolute target.

        Native backends override this to inject true relative motion, which
        passes through the OS pointer-acceleration curve (unlike absolute moves).
        """
        x, y = self.position()
        self.move(int(x + dx), int(y + dy))

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

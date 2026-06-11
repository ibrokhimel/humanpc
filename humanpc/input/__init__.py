"""Input backends.

The ``InputDriver`` interface is the seam that lets the same Bot drive different
low-level input methods (pyautogui today; native SendInput / DirectInput for games
in Phase 5). The Human Interaction Layer (Phase 1) generates *paths and timings*;
the driver just executes individual primitive events.
"""

from __future__ import annotations

from .driver import InputDriver, NullDriver

__all__ = ["InputDriver", "NullDriver", "default_driver", "sendinput_driver"]


def default_driver(failsafe: bool = True) -> InputDriver:
    """Construct the real OS input driver (lazy import of pyautogui)."""
    from .pyautogui_driver import PyAutoGUIDriver

    return PyAutoGUIDriver(failsafe=failsafe)


def sendinput_driver() -> InputDriver:
    """Construct the native Win32 SendInput driver (for games; Windows-only)."""
    from .sendinput_driver import SendInputDriver

    return SendInputDriver()

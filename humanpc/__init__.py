"""humanpc — human-like PC automation framework.

Quick start::

    from humanpc import Bot
    bot = Bot()                      # real input (lazy-loads pyautogui)
    bot.move_to((400, 300)).click().type("hello")

    dry = Bot(dry_run=True)          # plans + audits without touching the OS
    dry.click((10, 10))
    print(dry.audit.entries)

Or the module-level singleton for throwaway scripts::

    import humanpc as h
    h.click((100, 200)); h.type("hi")
"""

from __future__ import annotations

from .bot import Bot
from .config import PERSONAS, Config, Persona
from .exceptions import Aborted, DriverError, HumanpcError, TargetNotFound
from .geometry import Point, Rect
from .targeting import Image, Locator, Match, Region, Resolver

__version__ = "0.0.1"

__all__ = [
    "Bot",
    "Config",
    "Persona",
    "PERSONAS",
    "Point",
    "Rect",
    "Match",
    "Image",
    "Locator",
    "Region",
    "Resolver",
    "HumanpcError",
    "Aborted",
    "TargetNotFound",
    "DriverError",
    "__version__",
    # singleton conveniences
    "click",
    "double_click",
    "right_click",
    "move_to",
    "type",
    "press",
    "hotkey",
    "scroll",
    "find",
    "exists",
    "wait_for",
]

_default_bot: Bot | None = None


def bot() -> Bot:
    """Return (creating on first use) the shared module-level Bot."""
    global _default_bot
    if _default_bot is None:
        _default_bot = Bot()
    return _default_bot


def click(*args, **kwargs):
    return bot().click(*args, **kwargs)


def double_click(*args, **kwargs):
    return bot().double_click(*args, **kwargs)


def right_click(*args, **kwargs):
    return bot().right_click(*args, **kwargs)


def move_to(*args, **kwargs):
    return bot().move_to(*args, **kwargs)


def type(*args, **kwargs):  # noqa: A001 - deliberate ergonomic shadow of builtin
    return bot().type(*args, **kwargs)


def press(*args, **kwargs):
    return bot().press(*args, **kwargs)


def hotkey(*args, **kwargs):
    return bot().hotkey(*args, **kwargs)


def scroll(*args, **kwargs):
    return bot().scroll(*args, **kwargs)


def find(*args, **kwargs):
    return bot().find(*args, **kwargs)


def exists(*args, **kwargs):
    return bot().exists(*args, **kwargs)


def wait_for(*args, **kwargs):
    return bot().wait_for(*args, **kwargs)

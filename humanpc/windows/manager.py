"""Window enumeration and control.

``WindowManager`` and ``Window`` are backend-agnostic (unit-tested with a fake
backend). The real Win32 backend is lazy-loaded so importing this never requires
pywin32 or a live desktop.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..geometry import Rect

SHOW_STATES = ("minimize", "maximize", "restore", "normal", "hide", "show")


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    rect: Rect
    visible: bool = True


class WindowBackend(ABC):
    @abstractmethod
    def enumerate(self) -> list[WindowInfo]: ...

    @abstractmethod
    def foreground(self) -> int | None: ...

    @abstractmethod
    def rect(self, hwnd) -> Rect: ...

    @abstractmethod
    def activate(self, hwnd) -> None: ...

    @abstractmethod
    def set_bounds(self, hwnd, x, y, w, h) -> None: ...

    @abstractmethod
    def set_show(self, hwnd, state: str) -> None: ...

    @abstractmethod
    def close(self, hwnd) -> None: ...

    def is_minimized(self, hwnd) -> bool:
        return False


class Window:
    def __init__(self, info: WindowInfo, backend: WindowBackend):
        self._info = info
        self._backend = backend

    @property
    def hwnd(self):
        return self._info.hwnd

    @property
    def title(self) -> str:
        return self._info.title

    @property
    def pid(self) -> int:
        return self._info.pid

    @property
    def rect(self) -> Rect:
        try:
            return self._backend.rect(self.hwnd)
        except Exception:
            return self._info.rect

    def focus(self) -> "Window":
        self._backend.activate(self.hwnd)
        return self

    activate = focus

    def move(self, x, y) -> "Window":
        r = self.rect
        self._backend.set_bounds(self.hwnd, x, y, r.width, r.height)
        return self

    def resize(self, w, h) -> "Window":
        r = self.rect
        self._backend.set_bounds(self.hwnd, r.x, r.y, w, h)
        return self

    def set_bounds(self, x, y, w, h) -> "Window":
        self._backend.set_bounds(self.hwnd, x, y, w, h)
        return self

    def minimize(self) -> "Window":
        self._backend.set_show(self.hwnd, "minimize")
        return self

    def maximize(self) -> "Window":
        self._backend.set_show(self.hwnd, "maximize")
        return self

    def restore(self) -> "Window":
        self._backend.set_show(self.hwnd, "restore")
        return self

    def close(self) -> "Window":
        self._backend.close(self.hwnd)
        return self

    def __repr__(self) -> str:
        return f"<Window {self.title!r} hwnd={self.hwnd} pid={self.pid}>"


class WindowManager:
    def __init__(self, backend: WindowBackend | None = None):
        self._backend = backend

    @property
    def backend(self) -> WindowBackend:
        if self._backend is None:
            from .win32_backend import Win32Backend
            self._backend = Win32Backend()
        return self._backend

    def list(self, *, title=None, visible_only: bool = True) -> list[Window]:
        out = []
        for info in self.backend.enumerate():
            if visible_only and not info.visible:
                continue
            if title is not None and not _title_match(info.title, title):
                continue
            out.append(Window(info, self.backend))
        return out

    def find(self, title, *, visible_only: bool = True) -> Window | None:
        matches = self.list(title=title, visible_only=visible_only)
        return matches[0] if matches else None

    def active(self) -> Window | None:
        hwnd = self.backend.foreground()
        if not hwnd:
            return None
        for info in self.backend.enumerate():
            if info.hwnd == hwnd:
                return Window(info, self.backend)
        return None


def _title_match(title: str, query) -> bool:
    if isinstance(query, re.Pattern):
        return bool(query.search(title or ""))
    return query.lower() in (title or "").lower()

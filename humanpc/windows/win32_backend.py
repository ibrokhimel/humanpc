"""Win32 window backend (pywin32, lazy). Exercised by live-desktop integration."""

from __future__ import annotations

from ..exceptions import DriverError
from ..geometry import Rect
from .manager import WindowBackend, WindowInfo


class Win32Backend(WindowBackend):
    def _w(self):
        try:
            import win32con
            import win32gui
            import win32process
        except Exception as exc:
            raise DriverError(
                "window management needs pywin32: pip install humanpc[uia]"
            ) from exc
        return win32gui, win32con, win32process

    def enumerate(self) -> list[WindowInfo]:
        win32gui, _, win32process = self._w()
        results: list[WindowInfo] = []

        def callback(hwnd, _ctx):
            title = win32gui.GetWindowText(hwnd)
            visible = bool(win32gui.IsWindowVisible(hwnd)) and bool(title)
            try:
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            except Exception:
                left = top = right = bottom = 0
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                pid = 0
            results.append(
                WindowInfo(hwnd, title, pid, Rect(left, top, right - left, bottom - top), visible)
            )
            return True

        win32gui.EnumWindows(callback, None)
        return results

    def foreground(self) -> int | None:
        win32gui, _, _ = self._w()
        hwnd = win32gui.GetForegroundWindow()
        return hwnd or None

    def rect(self, hwnd) -> Rect:
        win32gui, _, _ = self._w()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return Rect(left, top, right - left, bottom - top)

    def activate(self, hwnd) -> None:
        win32gui, win32con, _ = self._w()
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            try:
                win32gui.BringWindowToTop(hwnd)
            except Exception:
                pass

    def set_bounds(self, hwnd, x, y, w, h) -> None:
        win32gui, _, _ = self._w()
        win32gui.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)

    def set_show(self, hwnd, state: str) -> None:
        win32gui, win32con, _ = self._w()
        mapping = {
            "minimize": win32con.SW_MINIMIZE,
            "maximize": win32con.SW_MAXIMIZE,
            "restore": win32con.SW_RESTORE,
            "normal": win32con.SW_SHOWNORMAL,
            "hide": win32con.SW_HIDE,
            "show": win32con.SW_SHOW,
        }
        win32gui.ShowWindow(hwnd, mapping.get(state, win32con.SW_SHOWNORMAL))

    def close(self, hwnd) -> None:
        win32gui, win32con, _ = self._w()
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    def is_minimized(self, hwnd) -> bool:
        win32gui, _, _ = self._w()
        try:
            return bool(win32gui.IsIconic(hwnd))
        except Exception:
            return False

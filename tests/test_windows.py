from humanpc.geometry import Rect
from humanpc.windows.manager import Window, WindowBackend, WindowInfo, WindowManager


class FakeBackend(WindowBackend):
    def __init__(self, infos, foreground=None):
        self._infos = infos
        self._fg = foreground
        self.ops = []

    def enumerate(self):
        return list(self._infos)

    def foreground(self):
        return self._fg

    def rect(self, hwnd):
        return next((i.rect for i in self._infos if i.hwnd == hwnd), Rect(0, 0, 0, 0))

    def activate(self, hwnd):
        self.ops.append(("activate", hwnd))

    def set_bounds(self, hwnd, x, y, w, h):
        self.ops.append(("bounds", hwnd, x, y, w, h))

    def set_show(self, hwnd, state):
        self.ops.append(("show", hwnd, state))

    def close(self, hwnd):
        self.ops.append(("close", hwnd))


def _infos():
    return [
        WindowInfo(1, "Untitled - Notepad", 111, Rect(0, 0, 400, 300), True),
        WindowInfo(2, "Calculator", 222, Rect(50, 50, 200, 400), True),
        WindowInfo(3, "", 333, Rect(0, 0, 10, 10), False),  # hidden / no title
    ]


def test_list_excludes_invisible():
    titles = [w.title for w in WindowManager(FakeBackend(_infos())).list()]
    assert "Untitled - Notepad" in titles
    assert "Calculator" in titles
    assert "" not in titles


def test_find_substring_case_insensitive():
    w = WindowManager(FakeBackend(_infos())).find("notepad")
    assert w is not None and w.hwnd == 1


def test_find_missing_returns_none():
    assert WindowManager(FakeBackend(_infos())).find("Photoshop") is None


def test_active_window():
    a = WindowManager(FakeBackend(_infos(), foreground=2)).active()
    assert a is not None and a.title == "Calculator"


def test_window_operations_dispatch_to_backend():
    be = FakeBackend(_infos())
    w = WindowManager(be).find("Calculator")
    w.focus()
    w.move(10, 20)       # keeps current size (200, 400)
    w.resize(640, 480)   # keeps current pos (50, 50)
    w.maximize()
    w.close()
    assert [op[0] for op in be.ops] == ["activate", "bounds", "bounds", "show", "close"]
    assert ("bounds", 2, 10, 20, 200, 400) in be.ops
    assert ("bounds", 2, 50, 50, 640, 480) in be.ops
    assert ("show", 2, "maximize") in be.ops

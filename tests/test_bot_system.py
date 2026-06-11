import sys

import pytest

from humanpc import Bot
from humanpc.config import Config
from humanpc.exceptions import TargetNotFound
from humanpc.geometry import Rect
from humanpc.system.clipboard import Clipboard
from humanpc.targeting import Match
from humanpc.windows.manager import WindowBackend, WindowInfo, WindowManager


def _bot(**kw):
    return Bot(dry_run=True, config=Config(seed=7), **kw)


class StubResolver:
    def __init__(self, matches):
        self.matches = matches

    def resolve(self, target, **kw):
        return self.matches[0] if self.matches else None

    def resolve_all(self, target, **kw):
        return self.matches


def test_find_all_delegates_to_resolver():
    ms = [Match(Rect(0, 0, 5, 5), 1.0, "template"), Match(Rect(9, 9, 5, 5), 1.0, "template")]
    assert _bot(resolver=StubResolver(ms)).find_all("x") == ms


def test_run_skipped_in_dry_run():
    bot = _bot()
    r = bot.run([sys.executable, "-c", "print('should not run')"])
    assert r.returncode == 0
    assert "dry-run" in r.stderr.lower()
    assert any(e["action"] == "run" and e.get("skipped") for e in bot.audit.entries)


def test_open_app_skipped_in_dry_run():
    bot = _bot()
    proc = bot.open_app("notepad.exe")
    assert proc.pid == -1
    assert any(e["action"] == "open_app" and e.get("skipped") for e in bot.audit.entries)


class FakeWinBackend(WindowBackend):
    def __init__(self, infos):
        self._infos = infos
        self.activated = []

    def enumerate(self):
        return list(self._infos)

    def foreground(self):
        return None

    def rect(self, hwnd):
        return next((i.rect for i in self._infos if i.hwnd == hwnd), Rect(0, 0, 0, 0))

    def activate(self, hwnd):
        self.activated.append(hwnd)

    def set_bounds(self, *a):
        pass

    def set_show(self, *a):
        pass

    def close(self, *a):
        pass


def test_focus_finds_and_activates():
    be = FakeWinBackend([WindowInfo(1, "Notepad", 1, Rect(0, 0, 100, 100), True)])
    # not dry-run so focus actually activates; arm=False to skip the kill-hotkey
    bot = Bot(config=Config(seed=1), windows=WindowManager(be), arm=False)
    win = bot.focus("Notepad")
    assert win.title == "Notepad"
    assert be.activated == [1]


def test_focus_missing_window_raises():
    bot = Bot(dry_run=True, config=Config(seed=1), windows=WindowManager(FakeWinBackend([])))
    with pytest.raises(TargetNotFound):
        bot.focus("Ghost")


def test_clipboard_via_bot():
    class FakeCB:
        def __init__(self):
            self.t = None

        def get_text(self):
            return self.t

        def set_text(self, v):
            self.t = v

        def get_image(self):
            return None

        def set_image(self, i):
            pass

    bot = _bot(clipboard=Clipboard(FakeCB()))
    bot.clipboard.set_text("copied")
    assert bot.clipboard.get_text() == "copied"

import pytest

from humanpc import Bot
from humanpc.config import Config
from humanpc.exceptions import TargetNotFound
from humanpc.geometry import Rect
from humanpc.targeting import Match


def _bot(resolver=None, **cfg):
    return Bot(dry_run=True, config=Config(seed=7, **cfg), resolver=resolver)


class StubResolver:
    def __init__(self, match):
        self.match = match
        self.calls = 0

    def resolve(self, target, **kw):
        self.calls += 1
        return self.match


class NoneResolver:
    def resolve(self, target, **kw):
        return None


class FlakyResolver:
    def __init__(self, match, succeed_on):
        self.match = match
        self.n = 0
        self.k = succeed_on

    def resolve(self, target, **kw):
        self.n += 1
        return self.match if self.n >= self.k else None


def _last_move(bot):
    return [e for e in bot.driver.events if e[0] == "move"][-1]


def test_move_to_region_lands_on_center():
    bot = _bot()  # default resolver handles Rect with no deps
    bot.move_to(Rect(100, 100, 40, 20))  # center (120, 110)
    assert _last_move(bot) == ("move", 120, 110)


def test_click_by_string_uses_resolver_and_records_method():
    m = Match(Rect(300, 200, 50, 30), 1.0, "uia")  # center (325, 215)
    bot = _bot(resolver=StubResolver(m))
    bot.click("Login")
    assert _last_move(bot) == ("move", 325, 215)
    assert any(e["action"] == "move_to" and e.get("via") == "uia" for e in bot.audit.entries)


def test_find_and_exists():
    m = Match(Rect(0, 0, 10, 10), 1.0, "ocr")
    bot = _bot(resolver=StubResolver(m))
    assert bot.find("x") is m
    assert bot.exists("x") is True


def test_exists_false_when_not_found():
    assert _bot(resolver=NoneResolver()).exists("ghost") is False


def test_move_to_missing_target_raises():
    bot = _bot(resolver=NoneResolver())
    with pytest.raises(TargetNotFound):
        bot.move_to("ghost")


def test_wait_for_polls_until_found():
    m = Match(Rect(0, 0, 10, 10), 1.0, "ocr")
    bot = _bot(resolver=FlakyResolver(m, succeed_on=3))
    assert bot.wait_for("x", timeout=2.0, interval=0.01) is m


def test_wait_for_times_out():
    bot = _bot(resolver=NoneResolver())
    with pytest.raises(TargetNotFound):
        bot.wait_for("x", timeout=0.05, interval=0.01)

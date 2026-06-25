"""Tier 7 — action verification: confirm an action took effect, retry if not."""

import pytest

from humanpc import Bot
from humanpc.config import Config
from humanpc.exceptions import VerificationError


def _bot():
    return Bot(dry_run=True, config=Config(seed=1))


def test_verify_true_when_check_passes_immediately():
    assert _bot().verify(lambda: True) is True


def test_verify_retries_with_retry_action_until_pass():
    bot = _bot()
    calls = {"check": 0, "retry": 0}

    def check():
        calls["check"] += 1
        return calls["check"] >= 3  # passes on the 3rd look

    def retry():
        calls["retry"] += 1

    assert bot.verify(check, attempts=3, interval=0, retry=retry) is True
    assert calls["retry"] == 2  # retried between the first two failed checks


def test_verify_false_when_never_passes():
    assert _bot().verify(lambda: False, attempts=3, interval=0) is False


def test_ensure_raises_on_failure():
    with pytest.raises(VerificationError):
        _bot().ensure(lambda: False, attempts=2, interval=0)


def test_ensure_returns_bot_on_success():
    bot = _bot()
    assert bot.ensure(lambda: True) is bot


def test_click_until_reclicks_until_satisfied():
    bot = _bot()
    state = {"n": 0}

    def until():
        state["n"] += 1
        return state["n"] >= 2  # the UI "changes" on the 2nd check

    bot.click_until((100, 100), until, attempts=3, interval=0)
    downs = [e for e in bot.driver.events if e[0] == "mouse_down"]
    assert len(downs) == 2  # initial click + one retry


def test_click_until_raises_if_never_satisfied():
    bot = _bot()
    with pytest.raises(VerificationError):
        bot.click_until((100, 100), lambda: False, attempts=2, interval=0)

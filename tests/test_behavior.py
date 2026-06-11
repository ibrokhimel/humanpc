import pytest

from humanpc import Bot
from humanpc.config import Config
from humanpc.hil.behavior import BehaviorState, BehaviorTracker, InvalidTransition


def test_observe_records_history():
    t = BehaviorTracker()
    t.observe(BehaviorState.READING).observe(BehaviorState.THINKING).observe(BehaviorState.MOVING)
    assert t.state == BehaviorState.MOVING
    assert t.history[-3:] == [BehaviorState.READING, BehaviorState.THINKING, BehaviorState.MOVING]


def test_can_reports_allowed_transition():
    assert BehaviorTracker().can(BehaviorState.MOVING)


def test_strict_rejects_invalid_transition():
    t = BehaviorTracker(strict=True)
    t.observe(BehaviorState.MOVING)
    with pytest.raises(InvalidTransition):
        t.observe(BehaviorState.READING)  # MOVING -> READING not allowed


def test_nonstrict_allows_anything():
    t = BehaviorTracker()
    t.observe(BehaviorState.MOVING).observe(BehaviorState.READING)  # no raise


def test_reset():
    t = BehaviorTracker()
    t.observe(BehaviorState.MOVING).reset()
    assert t.state == BehaviorState.IDLE and t.history == [BehaviorState.IDLE]


def test_bot_tracks_state_through_actions():
    bot = Bot(dry_run=True, config=Config(seed=1))
    bot.move_to((10, 10)).click().type("x")
    states = bot.behavior.history
    assert BehaviorState.MOVING in states
    assert BehaviorState.CLICKING in states
    assert bot.state == BehaviorState.TYPING  # last action

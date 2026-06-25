"""Tier 3 — cognition & temporal realism: fixation reading, Hick-Hyman,
session warm-up / fatigue / distraction."""

import random

from humanpc import Bot
from humanpc.config import Config
from humanpc.hil.session import SessionState
from humanpc.hil.timing import HumanTimingManager


# --- 3.1 reading -----------------------------------------------------------

def test_reading_scales_with_length():
    tm = HumanTimingManager()
    short = sum(tm.reading_delay(50, random.Random(s)) for s in range(50))
    long = sum(tm.reading_delay(500, random.Random(s)) for s in range(50))
    assert long > short


def test_scanning_is_faster_than_reading():
    tm = HumanTimingManager()
    read = sum(tm.reading_delay(300, random.Random(s), scan=False) for s in range(60))
    scan = sum(tm.reading_delay(300, random.Random(s), scan=True) for s in range(60))
    assert scan < read


# --- 3.2 Hick-Hyman --------------------------------------------------------

def test_decision_time_grows_with_choices():
    tm = HumanTimingManager()
    few = sum(tm.decision_delay(2, random.Random(s)) for s in range(80))
    many = sum(tm.decision_delay(16, random.Random(s)) for s in range(80))
    assert many > few


def test_bot_think_with_choices_records_decision_delay():
    bot = Bot(dry_run=True, config=Config(seed=1))
    bot.think(choices=8)
    entry = bot.audit.entries[-1]
    assert entry["action"] == "think"
    assert entry["choices"] == 8
    assert entry["delay"] > 0


# --- 3.3 session warm-up / fatigue -----------------------------------------

def test_warmup_starts_slow_then_settles():
    s = SessionState()
    assert s.warmup_factor(0.0) > s.warmup_factor(120.0)
    assert abs(s.warmup_factor(1e6) - 1.0) < 1e-3


def test_fatigue_grows_over_time_and_caps():
    s = SessionState(fatigue_per_minute=0.04, fatigue_cap=0.6)
    assert s.fatigue_factor(600.0) > s.fatigue_factor(0.0)
    assert s.fatigue_factor(1e7) <= 1.0 + 0.6 + 1e-9


def test_pace_multiplier_is_at_least_one_eventually():
    s = SessionState()
    assert s.pace_multiplier(0.0) > 1.0      # warm-up makes early actions slower
    assert s.pace_multiplier(1e6) >= 1.0     # fatigue keeps it >= 1


def test_distraction_fires_sometimes_with_high_prob():
    s = SessionState(distraction_prob=1.0, distraction_range=(1.0, 2.0))
    assert s.maybe_distraction(random.Random(0)) >= 1.0
    s2 = SessionState(distraction_prob=0.0)
    assert s2.maybe_distraction(random.Random(0)) == 0.0


def test_session_ticks_with_actions():
    bot = Bot(dry_run=True, config=Config(seed=2))
    start = bot._session.actions
    bot.think()
    bot.read("some text here")
    assert bot._session.actions > start

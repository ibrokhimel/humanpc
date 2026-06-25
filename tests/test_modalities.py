"""Tier 5 — scroll momentum / reading coupling / overshoot, and drag-and-drop."""

import random

from humanpc import Bot
from humanpc.config import Config
from humanpc.hil.scroll import plan_scroll


# --- 5.1 scroll -------------------------------------------------------------

def test_momentum_scroll_still_sums_to_amount():
    for seed in range(20):
        assert sum(d for d, _ in plan_scroll(37, random.Random(seed))) == 37
        assert sum(d for d, _ in plan_scroll(-23, random.Random(seed))) == -23


def test_momentum_produces_larger_initial_clicks():
    # A fling starts fast: at least one multi-click step should appear.
    deltas = [abs(d) for d, _ in plan_scroll(40, random.Random(1)) if d != 0]
    assert max(deltas) >= 2


def test_reading_pause_can_be_long():
    events = plan_scroll(60, random.Random(2), read_pause_prob=1.0)
    assert any(d == 0 and dt > 0.5 for d, dt in events)  # stopped to read


def test_overshoot_opt_in_reverses_then_nets_amount():
    events = plan_scroll(20, random.Random(3), overshoot_prob=1.0)
    assert sum(d for d, _ in events) == 20            # still nets the request
    assert any(d < 0 for d, _ in events)              # but reversed at some point


def test_default_scroll_stays_single_direction():
    deltas = [d for d, _ in plan_scroll(15, random.Random(4)) if d != 0]
    assert all(d > 0 for d in deltas)


# --- 5.2 drag-and-drop ------------------------------------------------------

def test_drag_presses_moves_then_releases():
    bot = Bot(dry_run=True, config=Config(seed=1))
    bot.drag((400, 300), frm=(50, 50))
    ev = bot.driver.events
    down_i = next(i for i, e in enumerate(ev) if e[0] == "mouse_down")
    up_i = next(i for i, e in enumerate(ev) if e[0] == "mouse_up")
    moves_held = [i for i, e in enumerate(ev) if e[0] == "move" and down_i < i < up_i]
    assert down_i < up_i
    assert moves_held                      # cursor moved while the button was held
    assert bot.position() == (400, 300)    # ended on the drop target


def test_drag_records_audit_entry():
    bot = Bot(dry_run=True, config=Config(seed=2))
    bot.drag((200, 200))
    assert any(e["action"] == "drag" for e in bot.audit.entries)

"""Tier 2 — typing fidelity: digraph timing, richer reversible typos, shift."""

import random

from humanpc import Bot
from humanpc.config import Config
from humanpc.hil.typing import HumanTypingEngine, SpeedModel


def _apply(events):
    buf = []
    for ev in events:
        if ev.kind == "char":
            buf.append(ev.value)
        elif ev.kind == "key" and ev.value == "backspace":
            if buf:
                buf.pop()
    return "".join(buf)


# --- 2.3 richer, reversible error model -------------------------------------

def test_all_error_kinds_self_correct_exactly():
    # error on every letter, always correct: transposition/doubling/sub/insert
    # must all net back to the exact input.
    eng = HumanTypingEngine(error_probability=1.0, always_correct=True)
    text = "the quick brown fox"
    for seed in range(40):
        assert _apply(eng.plan(text, random.Random(seed))) == text


def test_errors_add_keystrokes_and_backspaces():
    eng = HumanTypingEngine(error_probability=1.0, always_correct=True)
    events = eng.plan("hello world", random.Random(1))
    assert any(e.kind == "key" and e.value == "backspace" for e in events)
    assert len(events) > len("hello world")


# --- 2.4 digraph hand/finger structure --------------------------------------

def test_same_finger_digraph_slower_than_alternating_hand():
    sm = SpeedModel()
    same, alt = [], []
    for seed in range(300):
        r = random.Random(seed)
        # 'r'->'b' = same finger (L_index); 'f'->'j' = alternating hands.
        # Neither is a COMMON_BIGRAM, so only the finger/hand factor differs.
        same.append(sm.char_delay("b", "r", "rb", 5, 72.0, r))
        alt.append(sm.char_delay("j", "f", "fj", 5, 72.0, r))
    assert sum(same) / len(same) > sum(alt) / len(alt)


def test_inter_key_intervals_vary_lognormally():
    delays = [SpeedModel().char_delay("a", "n", "an", 5, 72.0, random.Random(s)) for s in range(200)]
    assert all(d > 0 for d in delays)
    assert len(set(round(d, 5) for d in delays)) > 50  # genuinely spread


# --- 2.2 shift / modifier dynamics ------------------------------------------

def test_capitals_and_symbols_carry_shift_modifier():
    events = HumanTypingEngine(errors_enabled=False).plan("Ab!", random.Random(0))
    by_val = {e.value: e for e in events}
    assert by_val["A"].modifiers == ("shift",)
    assert by_val["b"].modifiers == ()
    assert by_val["!"].modifiers == ("shift",)


def test_bot_presses_shift_around_capitals():
    bot = Bot(dry_run=True, config=Config(seed=0, typing_errors=False))
    bot.type("Ab")
    assert ("key_down", "shift") in bot.driver.events
    assert ("key_up", "shift") in bot.driver.events
    # lowercase 'b' should not be wrapped in extra shifts beyond the one for 'A'
    assert sum(1 for e in bot.driver.events if e == ("key_down", "shift")) == 1

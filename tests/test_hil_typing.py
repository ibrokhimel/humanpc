import random

from humanpc import Bot
from humanpc.config import Config
from humanpc.hil.typing import HumanTypingEngine


def _apply(events):
    """Reduce a KeyEvent stream to the resulting text (chars + backspaces)."""
    buf = []
    for ev in events:
        if ev.kind == "char":
            buf.append(ev.value)
        elif ev.kind == "key" and ev.value == "backspace":
            if buf:
                buf.pop()
    return "".join(buf)


def _apply_driver(events):
    """Same reduction, but over NullDriver events (write_char / key_down)."""
    buf = []
    for e in events:
        if e[0] == "write_char":
            buf.append(e[1])
        elif e[0] == "key_down" and e[1] == "backspace":
            if buf:
                buf.pop()
    return "".join(buf)


TEXT = "Hello, World! The quick brown fox jumps. 123"


def test_self_correction_is_exact_across_seeds():
    # High typo rate, always-correct: the net text must still equal the input.
    eng = HumanTypingEngine(error_probability=0.5, always_correct=True)
    for seed in range(50):
        events = eng.plan(TEXT, random.Random(seed))
        assert _apply(events) == TEXT


def test_typos_are_actually_injected():
    eng = HumanTypingEngine(error_probability=0.5, always_correct=True)
    events = eng.plan(TEXT, random.Random(0))
    backspaces = [e for e in events if e.kind == "key" and e.value == "backspace"]
    assert backspaces  # corrections happened
    assert len(events) > len(TEXT)  # extra keystrokes from typo+fix


def test_no_errors_when_disabled():
    eng = HumanTypingEngine(errors_enabled=False)
    events = eng.plan(TEXT, random.Random(1))
    assert [e.value for e in events if e.kind == "char"] == list(TEXT)
    assert not any(e.kind == "key" for e in events)


def test_delays_are_non_negative_and_varied():
    eng = HumanTypingEngine(errors_enabled=False)
    delays = [e.delay for e in eng.plan(TEXT, random.Random(2))]
    assert all(d >= 0 for d in delays)
    assert len(set(round(d, 5) for d in delays)) > 5  # not metronomic


def test_bot_type_reproduces_text_through_driver():
    # Even with default typo injection on, the Bot's driver stream nets to the text.
    for seed in range(20):
        bot = Bot(dry_run=True, config=Config(seed=seed, typing_errors=True))
        bot.type(TEXT)
        assert _apply_driver(bot.driver.events) == TEXT


def test_every_event_has_a_realistic_dwell():
    # Tier 0: keystrokes must carry a non-zero key-hold (dwell) time, within bounds.
    eng = HumanTypingEngine()
    events = eng.plan(TEXT, random.Random(3))
    assert events
    for ev in events:
        assert 0.02 <= ev.dwell <= 0.31  # clamped lognormal hold, never zero


def test_dwell_varies_between_keystrokes():
    eng = HumanTypingEngine(errors_enabled=False)
    dwells = [ev.dwell for ev in eng.plan(TEXT, random.Random(4))]
    assert len(set(round(d, 5) for d in dwells)) > 5  # not a constant hold

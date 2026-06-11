import pytest

from humanpc import Bot
from humanpc.config import Config
from humanpc.exceptions import Aborted
from humanpc.input import NullDriver


def make_bot(**cfg):
    return Bot(dry_run=True, config=Config(seed=1234, **cfg))


def test_dryrun_uses_nulldriver():
    bot = make_bot()
    assert isinstance(bot.driver, NullDriver)


def test_move_is_multistep_and_lands_on_target():
    bot = make_bot()
    bot.move_to((300, 150))
    moves = [e for e in bot.driver.events if e[0] == "move"]
    assert len(moves) >= 10                        # HIL emits a multi-step path
    assert moves[-1] == ("move", 300, 150)         # lands exactly on target
    assert bot.position() == (300, 150)


def test_click_emits_down_then_up_and_audits():
    bot = make_bot()
    bot.click((10, 10))
    kinds = [e[0] for e in bot.driver.events]
    assert "mouse_down" in kinds and "mouse_up" in kinds
    assert kinds.index("mouse_down") < kinds.index("mouse_up")
    assert any(e["action"] == "click" for e in bot.audit.entries)


def test_type_writes_each_char():
    bot = make_bot(typing_errors=False)  # no typo/correction noise -> exact stream
    bot.type("hi!")
    typed = [e[1] for e in bot.driver.events if e[0] == "write_char"]
    assert typed == ["h", "i", "!"]


def test_hotkey_presses_then_releases_in_reverse():
    bot = make_bot()
    bot.hotkey("ctrl", "c")
    seq = [e for e in bot.driver.events if e[0] in ("key_down", "key_up")]
    assert seq == [
        ("key_down", "ctrl"),
        ("key_down", "c"),
        ("key_up", "c"),
        ("key_up", "ctrl"),
    ]


def test_persona_context_restores():
    bot = make_bot()
    assert bot.current_persona.name == "default"
    with bot.persona("careful"):
        assert bot.current_persona.name == "careful"
    assert bot.current_persona.name == "default"


def test_killswitch_aborts_midrun():
    bot = make_bot()
    bot.killswitch.request_abort()
    with pytest.raises(Aborted):
        bot.move_to((500, 500))


def test_max_actions_limit():
    # The cap counts every guarded primitive. A click() with no target is one op
    # (a click((x, y)) would be two: an internal move_to plus the click).
    bot = make_bot(max_actions=2)
    bot.click()  # op 1
    bot.click()  # op 2
    with pytest.raises(Aborted):
        bot.click()  # op 3 -> blocked


def test_chaining_returns_bot():
    bot = make_bot()
    assert bot.move_to((1, 1)).click().type("x") is bot

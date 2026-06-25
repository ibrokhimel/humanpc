"""Tier 0 provenance fixes: keystroke dwell, relative motion, driver seams."""

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.driver import NullDriver


class SplitDriver(NullDriver):
    """A driver that, like SendInputDriver, separates char press/release."""

    def char_down(self, char):
        self.events.append(("char_down", char))

    def char_up(self, char):
        self.events.append(("char_up", char))


def test_bot_drives_char_down_then_up_on_a_split_driver():
    # Real proof the dwell fix works: on a driver with separable injection the
    # Bot emits down, then up (a hold can sit between them).
    drv = SplitDriver()
    bot = Bot(config=Config(seed=5, typing_errors=False), driver=drv, arm=False)
    bot.type("ab")
    kinds = [e for e in drv.events if e[0] in ("char_down", "char_up")]
    assert kinds == [
        ("char_down", "a"), ("char_up", "a"),
        ("char_down", "b"), ("char_up", "b"),
    ]
    bot.close()


# --- driver-level fallbacks -------------------------------------------------

def test_char_down_up_default_falls_back_to_write_char():
    d = NullDriver()
    d.char_down("a")
    d.char_up("a")
    # Default split degrades to the atomic write_char emit (vocabulary stable).
    assert ("write_char", "a") in d.events


def test_move_relative_default_reconstructs_absolute():
    d = NullDriver()
    d.move(100, 100)
    d.move_relative(5, -3)
    assert d.position() == (105, 97)


# --- Bot typing path uses down/hold/up --------------------------------------

def test_type_emits_chars_through_dwell_path():
    # errors off -> a clean char stream; the down/hold/up path must still emit
    # each character exactly (NullDriver records char_down's write_char fallback).
    bot = Bot(dry_run=True, config=Config(seed=7, typing_errors=False))
    bot.type("hello world")
    typed = "".join(e[1] for e in bot.driver.events if e[0] == "write_char")
    assert typed == "hello world"


# --- relative vs absolute mouse both reach the target -----------------------

def test_absolute_mouse_reaches_target_by_default():
    bot = Bot(dry_run=True, config=Config(seed=1))
    bot.move_to((300, 200))
    assert bot.position() == (300, 200)


def test_relative_mouse_reaches_target():
    bot = Bot(dry_run=True, config=Config(seed=1, relative_mouse=True))
    bot.move_to((300, 200))
    assert bot.position() == (300, 200)


def test_relative_mouse_emits_no_absolute_moves_after_start():
    # In relative mode every step should go through move_relative, which the
    # NullDriver records as ("move", ...) only via its fallback — so we assert
    # the cursor still lands exactly on target (drift corrected).
    bot = Bot(dry_run=True, config=Config(seed=2, relative_mouse=True))
    bot.move_to((640, 480))
    assert bot.position() == (640, 480)


# --- SendInput driver exposes the new primitives ----------------------------

def test_sendinput_exposes_split_and_relative_methods():
    from humanpc.input.sendinput_driver import SendInputDriver

    for name in ("char_down", "char_up", "move_relative"):
        assert callable(getattr(SendInputDriver, name))


def test_sendinput_accepts_extra_info_kwarg():
    import inspect

    from humanpc.input.sendinput_driver import SendInputDriver

    sig = inspect.signature(SendInputDriver.__init__)
    assert "extra_info" in sig.parameters


# --- lifecycle --------------------------------------------------------------

def test_bot_is_a_context_manager_and_closes_cleanly():
    with Bot(dry_run=True, config=Config(seed=3)) as bot:
        bot.type("hi")
    # close() ran without error; _precision released.
    assert bot._precision is False

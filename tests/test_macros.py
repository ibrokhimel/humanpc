from humanpc import Bot
from humanpc.config import Config
from humanpc.flows.record import Macro, Recorder


def _bot():
    return Bot(dry_run=True, config=Config(seed=2))


def test_record_builds_steps_without_executing():
    rec = Recorder()  # no bot -> execute disabled
    rec.click("100,100").type("hi").hotkey("ctrl", "a").scroll(-2)
    assert rec.steps == [
        {"click": "100,100"},
        {"type": "hi"},
        {"hotkey": ["ctrl", "a"]},
        {"scroll": -2},
    ]


def test_record_executes_on_attached_bot():
    bot = _bot()
    Recorder(bot=bot).click("50,50").type("x")
    kinds = [e[0] for e in bot.driver.events]
    assert "mouse_down" in kinds and "write_char" in kinds


def test_save_load_replay_roundtrip(tmp_path):
    rec = Recorder()
    rec.click("10,10").type("hi")
    path = tmp_path / "macro.json"
    rec.save(str(path))

    macro = Macro.load(str(path))
    assert len(macro) == 2

    bot = _bot()
    results = macro.replay(bot=bot)
    assert len(results) == 2 and results[0]["ok"]


def test_macro_replay_drives_driver():
    bot = _bot()
    Macro([{"move": "5,5"}, {"click": "5,5"}]).replay(bot=bot)
    assert any(e[0] == "mouse_down" for e in bot.driver.events)

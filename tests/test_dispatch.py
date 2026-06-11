import sys

import pytest

from humanpc import Bot, execute, list_actions
from humanpc.config import Config


def _bot():
    return Bot(dry_run=True, config=Config(seed=3))


def test_click_coords_moves_and_oks():
    bot = _bot()
    assert execute(bot, "click", {"target": "300,200"})["ok"]
    assert [e for e in bot.driver.events if e[0] == "move"][-1] == ("move", 300, 200)


def test_type_writes():
    bot = _bot()
    execute(bot, "type", {"text": "hi"})
    assert [e for e in bot.driver.events if e[0] == "write_char"]


def test_hotkey_list():
    bot = _bot()
    execute(bot, "hotkey", {"keys": ["ctrl", "c"]})
    assert [e for e in bot.driver.events if e[0] == "key_down"][0] == ("key_down", "ctrl")


def test_hotkey_plus_string_splits():
    bot = _bot()
    execute(bot, "hotkey", {"keys": "ctrl+a"})
    assert [e[1] for e in bot.driver.events if e[0] == "key_down"] == ["ctrl", "a"]


def test_find_coords():
    r = execute(_bot(), "find", {"target": "10,20"})
    assert r["found"] and r["match"]["x"] == 10 and r["match"]["y"] == 20


def test_exists_coords_true():
    assert execute(_bot(), "exists", {"target": "5,5"})["exists"] is True


def test_wait_for_coords_immediate():
    assert execute(_bot(), "wait_for", {"target": "5,5"})["found"]


def test_run_dry_run_sentinel():
    r = execute(_bot(), "run", {"command": [sys.executable, "-c", "print(1)"]})
    assert r["returncode"] == 0 and "dry-run" in r["stderr"].lower()


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        execute(_bot(), "frobnicate", {})


def test_list_actions_includes_core():
    actions = list_actions()
    assert {"click", "type", "run", "find_all", "focus"} <= set(actions)

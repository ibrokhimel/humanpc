import json

import pytest

from humanpc import Bot, FlowRunner
from humanpc.config import Config


def _bot():
    return Bot(dry_run=True, config=Config(seed=1))


def test_run_steps_from_dict():
    spec = {"steps": [{"click": "100,100"}, {"type": "hi"}, {"hotkey": ["ctrl", "a"]}, {"scroll": -2}]}
    bot = _bot()
    res = FlowRunner().run(spec, bot=bot)
    assert len(res) == 4 and res[0]["ok"]
    kinds = [e[0] for e in bot.driver.events]
    assert "mouse_down" in kinds and "write_char" in kinds


def test_bare_list_of_steps():
    bot = _bot()
    res = FlowRunner().run([{"move": "50,50"}, {"click": "50,50"}], bot=bot)
    assert len(res) == 2 and all(r["ok"] for r in res)


def test_verbose_action_form():
    bot = _bot()
    res = FlowRunner().run([{"action": "click", "target": "5,5", "clicks": 2}], bot=bot)
    assert res[0]["ok"]
    assert len([e for e in bot.driver.events if e[0] == "mouse_down"]) == 2


def test_run_file_json(tmp_path):
    path = tmp_path / "flow.json"
    path.write_text(json.dumps([{"click": "5,5"}, {"type": "x"}]))
    res = FlowRunner().run_file(str(path), bot=_bot())
    assert len(res) == 2


def test_step_with_two_verbs_raises():
    with pytest.raises(ValueError):
        FlowRunner().run([{"click": "1,1", "type": "x"}], bot=_bot())


def test_yaml_flow_if_pyyaml_available(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "flow.yaml"
    path.write_text("steps:\n  - click: '7,7'\n  - type: hello\n")
    res = FlowRunner().run_file(str(path), bot=_bot())
    assert len(res) == 2

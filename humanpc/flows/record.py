"""Record and replay macros.

A ``Recorder`` builds a flow as you call verbs on it; with a bot attached it also
executes them live. The result is a ``Macro`` (a list of flow steps) you can save
to JSON/YAML and replay later via the shared flow runner.

    rec = Recorder(bot=Bot())
    rec.click("Login").type("user").press("tab").type("pass").press("enter")
    rec.save("login.yaml")
    # later:
    Macro.load("login.yaml").replay(bot=Bot())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..dispatch import execute as _execute
from ..exceptions import DriverError
from .runner import ALIASES, FlowRunner, _load, _step_to_call


@dataclass
class Macro:
    steps: list = field(default_factory=list)

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_dump(path, self.steps))
        return path

    @classmethod
    def load(cls, path: str) -> "Macro":
        data = _load(path)
        steps = data.get("steps", []) if isinstance(data, dict) else data
        return cls(list(steps))

    def replay(self, bot=None, **kwargs) -> list[dict]:
        return FlowRunner().run(self.steps, bot=bot, **kwargs)

    def __len__(self) -> int:
        return len(self.steps)


def _dump(path: str, steps: list) -> str:
    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml
        except Exception as exc:
            raise DriverError("YAML macros need pyyaml: pip install humanpc[flows]") from exc
        return yaml.safe_dump({"steps": steps}, sort_keys=False)
    return json.dumps({"steps": steps}, indent=2)


class Recorder:
    def __init__(self, bot=None, execute: bool | None = None):
        self.bot = bot
        self.execute = (bot is not None) if execute is None else execute
        self.steps: list = []

    def _add(self, step: dict) -> "Recorder":
        # Execute through the same dispatcher as replay, so live recording and
        # replay have identical semantics (e.g. "50,50" -> coordinates).
        self.steps.append(step)
        if self.execute and self.bot is not None:
            action, params = _step_to_call(step)
            _execute(self.bot, ALIASES.get(action, action), params)
        return self

    def click(self, target):
        return self._add({"click": target})

    def double_click(self, target):
        return self._add({"double_click": target})

    def right_click(self, target):
        return self._add({"right_click": target})

    def move(self, target):
        return self._add({"move": target})

    def type(self, text):
        return self._add({"type": text})

    def press(self, *keys):
        return self._add({"press": list(keys)})

    def hotkey(self, *keys):
        return self._add({"hotkey": list(keys)})

    def scroll(self, amount):
        return self._add({"scroll": amount})

    def wait_for(self, target):
        return self._add({"wait_for": target})

    def run(self, command):
        return self._add({"run": command})

    def open_app(self, target):
        return self._add({"open_app": target})

    def focus(self, target):
        return self._add({"focus": target})

    def think(self, complexity="medium"):
        return self._add({"think": complexity})

    def sleep(self, seconds):
        return self._add({"sleep": seconds})

    def macro(self) -> Macro:
        return Macro(list(self.steps))

    def save(self, path: str) -> str:
        return self.macro().save(path)

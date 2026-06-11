"""Declarative flow runner.

A flow is JSON or YAML: an optional ``persona`` / ``dry_run`` plus a list of
``steps``. Each step is a one-key mapping ``{verb: value}`` (or a verbose
``{action: verb, ...params}``). Values are interpreted per-verb, then handed to
the shared dispatcher.

    persona: careful
    steps:
      - open_app: notepad.exe
      - wait_for: "Text editor"
      - click: "Text editor"
      - type: "Hello from humanpc"
      - hotkey: [ctrl, s]
"""

from __future__ import annotations

import json

from ..dispatch import execute
from ..exceptions import DriverError

ALIASES = {"move": "move_to"}

_TARGET_VERBS = {
    "click", "double_click", "right_click", "move", "move_to",
    "find", "find_all", "exists", "wait_for",
}


def _value_to_params(verb: str, value) -> dict:
    if isinstance(value, dict):
        return value
    if verb in _TARGET_VERBS:
        return {"target": value}
    if verb == "type":
        return {"text": value}
    if verb in ("press", "hotkey"):
        return {"keys": value if isinstance(value, list) else [value]}
    if verb == "scroll":
        return {"amount": value}
    if verb == "run":
        return {"command": value}
    if verb == "open_app":
        return {"target": value}
    if verb == "focus":
        return {"title": value}
    if verb == "think":
        return {"complexity": value}
    if verb == "sleep":
        return {"seconds": value}
    if verb == "screenshot":
        return {"path": value}
    if verb == "read_text":
        return {}
    return {"value": value}


def _step_to_call(step: dict) -> tuple[str, dict]:
    if "action" in step:
        action = step["action"]
        return action, {k: v for k, v in step.items() if k != "action"}
    verbs = [k for k in step if k != "name"]
    if len(verbs) != 1:
        raise ValueError(f"each step needs exactly one verb, got {list(step)}")
    verb = verbs[0]
    return verb, _value_to_params(verb, step[verb])


class FlowRunner:
    def __init__(self, bot=None):
        self.bot = bot

    def run(self, spec, *, bot=None, dry_run=None, persona=None) -> list[dict]:
        steps = spec.get("steps", []) if isinstance(spec, dict) else spec
        bot = bot or self.bot
        if bot is None:
            from .. import Bot
            p = persona or (spec.get("persona") if isinstance(spec, dict) else None) or "default"
            d = dry_run if dry_run is not None else (
                spec.get("dry_run", False) if isinstance(spec, dict) else False
            )
            bot = Bot(persona=p, dry_run=d)

        results = []
        for step in steps:
            action, params = _step_to_call(step)
            results.append(execute(bot, ALIASES.get(action, action), params))
        return results

    def run_file(self, path, **kwargs) -> list[dict]:
        return self.run(_load(path), **kwargs)


def _load(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml
        except Exception as exc:
            raise DriverError("YAML flows need pyyaml: pip install humanpc[flows]") from exc
        return yaml.safe_load(text)
    return json.loads(text)

"""Action dispatcher — the single source of truth shared by the CLI, flow runner,
HTTP server, and MCP server.

``execute(bot, action, params)`` interprets a params dict, calls the matching Bot
verb, and returns a JSON-serialisable result. Every interface is a thin adapter
over this.
"""

from __future__ import annotations

import time

from .geometry import Rect
from .targeting.parse import parse_target


def _target(params):
    if "target" in params:
        t = params["target"]
        return parse_target(t) if isinstance(t, str) else t
    if "x" in params and "y" in params:
        return (int(params["x"]), int(params["y"]))
    raise ValueError("missing 'target'")


def _keys(params):
    k = params.get("keys", params.get("key"))
    if k is None:
        raise ValueError("missing 'keys'")
    if isinstance(k, str):
        return k.split("+") if "+" in k else [k]
    return list(k)


def _region(params):
    r = params.get("region")
    if r is None:
        return None
    if isinstance(r, (list, tuple)) and len(r) == 4:
        return Rect(*[int(v) for v in r])
    return r


def _match_dict(m):
    if m is None:
        return None
    cx, cy = m.center.as_int()
    return {
        "x": cx,
        "y": cy,
        "bbox": list(m.bbox.as_tuple()),
        "confidence": round(m.confidence, 4),
        "method": m.method,
        "text": m.text,
    }


# --- handlers -------------------------------------------------------------
def _click(bot, p):
    bot.click(_target(p), button=p.get("button", "left"), clicks=int(p.get("clicks", 1)))
    return {"ok": True}


def _double_click(bot, p):
    bot.double_click(_target(p))
    return {"ok": True}


def _right_click(bot, p):
    bot.right_click(_target(p))
    return {"ok": True}


def _move(bot, p):
    bot.move_to(_target(p))
    return {"ok": True}


def _type(bot, p):
    bot.type(p["text"])
    return {"ok": True}


def _press(bot, p):
    bot.press(*_keys(p))
    return {"ok": True}


def _hotkey(bot, p):
    bot.hotkey(*_keys(p))
    return {"ok": True}


def _scroll(bot, p):
    bot.scroll(int(p["amount"]))
    return {"ok": True}


def _find(bot, p):
    m = bot.find(_target(p))
    return {"found": m is not None, "match": _match_dict(m)}


def _find_all(bot, p):
    matches = bot.find_all(_target(p))
    return {"count": len(matches), "matches": [_match_dict(m) for m in matches]}


def _exists(bot, p):
    return {"exists": bot.exists(_target(p))}


def _wait_for(bot, p):
    m = bot.wait_for(
        _target(p),
        timeout=float(p.get("timeout", 10.0)),
        interval=float(p.get("interval", 0.25)),
    )
    return {"found": True, "match": _match_dict(m)}


def _run(bot, p):
    extra = {k: p[k] for k in ("cwd", "timeout", "shell") if k in p}
    r = bot.run(p["command"], **extra)
    return {"ok": r.ok, "returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


def _open_app(bot, p):
    proc = bot.open_app(
        p["target"], p.get("args", ()), wait=p.get("wait"), timeout=float(p.get("timeout", 15.0))
    )
    return {"pid": proc.pid}


def _focus(bot, p):
    win = bot.focus(p.get("title", p.get("target")))
    return {"title": win.title, "hwnd": win.hwnd}


def _windows(bot, p):
    return {
        "windows": [
            {"title": w.title, "hwnd": w.hwnd, "pid": w.pid, "rect": list(w.rect.as_tuple())}
            for w in bot.list_windows()
        ]
    }


def _screenshot(bot, p):
    path = p.get("path")
    bot.screenshot(path, region=_region(p))
    return {"path": path, "saved": path is not None}


def _read_text(bot, p):
    return {"text": bot.read_text(region=_region(p))}


def _think(bot, p):
    bot.think(p.get("complexity", "medium"))
    return {"ok": True}


def _sleep(bot, p):
    time.sleep(float(p.get("seconds", p.get("amount", 0))))
    return {"ok": True}


ACTIONS = {
    "click": _click,
    "double_click": _double_click,
    "right_click": _right_click,
    "move": _move,
    "move_to": _move,
    "type": _type,
    "press": _press,
    "hotkey": _hotkey,
    "scroll": _scroll,
    "find": _find,
    "find_all": _find_all,
    "exists": _exists,
    "wait_for": _wait_for,
    "run": _run,
    "open_app": _open_app,
    "focus": _focus,
    "windows": _windows,
    "screenshot": _screenshot,
    "read_text": _read_text,
    "think": _think,
    "sleep": _sleep,
}


def execute(bot, action: str, params: dict | None = None) -> dict:
    handler = ACTIONS.get(action)
    if handler is None:
        raise ValueError(f"unknown action: {action!r} (known: {', '.join(sorted(ACTIONS))})")
    return handler(bot, params or {})


def list_actions() -> list[str]:
    return sorted(ACTIONS)

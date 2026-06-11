"""Command-line interface: ``humanpc <verb> ...``.

Built on argparse (stdlib) so the CLI works with no extra installs. Every command
is a thin call into the shared dispatcher.
"""

from __future__ import annotations

import argparse
import json
import sys

from .dispatch import execute

# argparse uses dashes; the dispatcher uses underscores.
_CLI_TO_ACTION = {
    "double-click": "double_click",
    "right-click": "right_click",
    "wait-for": "wait_for",
    "open-app": "open_app",
    "read-text": "read_text",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="humanpc", description="Human-like PC automation.")
    p.add_argument("--persona", default="default", help="default | fast | careful | tired")
    p.add_argument("--dry-run", action="store_true", help="plan + audit without touching the OS")
    p.add_argument("--seed", type=int, help="deterministic RNG seed")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name):
        return sub.add_parser(name)

    c = add("click")
    c.add_argument("target")
    c.add_argument("--button", default="left")
    c.add_argument("--clicks", type=int, default=1)
    for name in ("double-click", "right-click", "move", "find", "find_all", "exists"):
        add(name).add_argument("target")
    add("type").add_argument("text")
    add("press").add_argument("keys", nargs="+")
    add("hotkey").add_argument("keys", nargs="+")
    add("scroll").add_argument("amount", type=int)
    w = add("wait-for")
    w.add_argument("target")
    w.add_argument("--timeout", type=float, default=10.0)
    add("run").add_argument("command", nargs=argparse.REMAINDER)
    o = add("open-app")
    o.add_argument("target")
    o.add_argument("--wait")
    add("focus").add_argument("title")
    add("windows")
    s = add("screenshot")
    s.add_argument("path", nargs="?")
    rt = add("read-text")
    rt.add_argument("--region", help="x,y,w,h")
    add("flow").add_argument("file")
    srv = add("serve")
    srv.add_argument("--mcp", action="store_true", help="run the MCP tool server (stdio)")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    return p


def _params(args) -> dict:
    cmd = args.cmd
    if cmd == "click":
        return {"target": args.target, "button": args.button, "clicks": args.clicks}
    if cmd in ("double-click", "right-click", "move", "find", "find_all", "exists"):
        return {"target": args.target}
    if cmd == "type":
        return {"text": args.text}
    if cmd in ("press", "hotkey"):
        return {"keys": args.keys}
    if cmd == "scroll":
        return {"amount": args.amount}
    if cmd == "wait-for":
        return {"target": args.target, "timeout": args.timeout}
    if cmd == "run":
        return {"command": args.command}
    if cmd == "open-app":
        return {"target": args.target, "wait": args.wait}
    if cmd == "focus":
        return {"title": args.title}
    if cmd == "screenshot":
        return {"path": args.path}
    if cmd == "read-text":
        region = [int(v) for v in args.region.split(",")] if args.region else None
        return {"region": region}
    return {}


def _make_bot(args):
    from .bot import Bot
    from .config import Config
    return Bot(
        persona=args.persona,
        dry_run=args.dry_run,
        config=Config(seed=args.seed),
    )


def _emit(args, result) -> None:
    if args.json:
        print(json.dumps(result))
        return
    if isinstance(result, dict) and set(result) == {"ok"}:
        print("ok")
    else:
        print(json.dumps(result, indent=2))


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "flow":
        from .flows import FlowRunner
        bot = _make_bot(args)
        results = FlowRunner().run_file(args.file, bot=bot)
        _emit(args, {"steps": results})
        return 0

    if args.cmd == "serve":
        if args.mcp:
            from .server.mcp_server import main as mcp_main
            mcp_main()
        else:
            from .server.http import main as http_main
            http_main(host=args.host, port=args.port, persona=args.persona)
        return 0

    bot = _make_bot(args)
    action = _CLI_TO_ACTION.get(args.cmd, args.cmd)
    try:
        result = execute(bot, action, _params(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _emit(args, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

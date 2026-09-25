"""Command-line interface: ``humanpc <verb> ...``.

Built on argparse (stdlib) so the CLI works with no extra installs. Every command
is a thin call into the shared dispatcher.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
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
    p.add_argument("-V", "--version", action="version", version=f"humanpc {__version__}")
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
    tr = add("trainer")
    tr.add_argument("--data-dir", help="where sessions are stored (default ~/.humanpc/training)")
    tr.add_argument("--minutes", type=float, default=10.0, help="suggest a break after N minutes")
    tr.add_argument("--keep-injected", action="store_true", help="also record software-injected input")
    tr.add_argument("--person", help="record into a per-person subfolder")
    ts = add("trainer-stats")
    ts.add_argument("--data-dir")
    ts.add_argument("--person", help="only this person (default: everyone)")
    te = add("trainer-export")
    te.add_argument("output", help="zip file to write")
    te.add_argument("--data-dir")
    te.add_argument("--person")
    ti = add("trainer-import")
    ti.add_argument("zip", nargs="+", help="zip file(s) exported by the trainer")
    ti.add_argument("--data-dir")
    ti.add_argument("--person", help="override the name stored in the zip")
    tm = add("train-model")
    tm.add_argument("--data-dir")
    tm.add_argument("--out", help="model folder (default <data-dir>/model)")
    tm.add_argument("--epochs", type=int, default=60)
    tm.add_argument("--size", default="auto", choices=["auto", "small", "base", "large"])
    tm.add_argument("--batch-tokens", type=int, default=32768, help="steps per batch (lower = less GPU memory)")
    tm.add_argument("--cpu", action="store_true")
    tm.add_argument("--no-eval", action="store_true", help="skip the detector evaluation")
    tm.add_argument("--max-sessions", type=int, help="cap sessions loaded (big datasets / low RAM)")
    em = add("eval-model")
    em.add_argument("--data-dir")
    em.add_argument("--model", help="model.pt (default <data-dir>/model/model.pt)")
    em.add_argument("--temperature", type=float, default=1.0)
    em.add_argument("--cpu", action="store_true")
    em.add_argument("--max-sessions", type=int)
    em.add_argument("--no-weights", action="store_true", help="don't rewrite task_weights.json")
    md = add("model-demo")
    md.add_argument("--data-dir")
    md.add_argument("--model", help="model.pt (default <data-dir>/model/model.pt)")
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


def _trainer_cmd(args) -> int:
    from .learn.dataset import default_data_dir, person_dir
    root = args.data_dir or default_data_dir()
    try:
        if args.cmd == "trainer":
            from .learn.trainer_app import run_trainer
            _emit(args, run_trainer(person_dir(root, args.person), minutes=args.minutes, seed=args.seed,
                                    keep_injected=args.keep_injected, person=args.person))
        elif args.cmd == "trainer-stats":
            from .learn.report import (format_people, format_report, load_measured, polling_hz_of_latest,
                                       summary)
            from .learn.dataset import people, stats
            data_dir = person_dir(root, args.person)
            everyone = not args.person
            st = stats(data_dir, recursive=everyone)
            if args.json:
                _emit(args, {**st, "estimate": summary(st)})
            else:
                print(format_report(st, polling_hz=polling_hz_of_latest(data_dir),
                                    measured=None if args.person else load_measured(root)))
                if everyone and people(root):
                    print(format_people(root))
        elif args.cmd == "trainer-export":
            from .learn.transfer import export_zip
            _emit(args, export_zip(person_dir(root, args.person), args.person or "me", args.output))
        elif args.cmd == "trainer-import":
            from .learn.transfer import import_zip
            _emit(args, [import_zip(z, root, person=args.person) for z in args.zip])
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _model_cmd(args) -> int:
    try:
        import torch  # noqa: F401
    except ImportError:
        print("error: needs PyTorch - see docs/TRAINER.md (GPU: pip install torch "
              "--index-url https://download.pytorch.org/whl/cu128)", file=sys.stderr)
        return 1
    from .learn.dataset import default_data_dir
    from .learn.ml.detector import evaluate, format_metrics
    root = args.data_dir or default_data_dir()
    try:
        if args.cmd == "model-demo":
            from pathlib import Path

            from .learn.ml.demo import run_demo
            model = Path(args.model) if args.model else Path(root) / "model" / "model.pt"
            if not model.exists():
                raise FileNotFoundError(f"no model at {model} - run 'humanpc train-model' first")
            run_demo(model)
        elif args.cmd == "train-model":
            from .learn.ml.train import train
            summary = train(root, args.out, epochs=args.epochs, size=args.size,
                            token_budget=args.batch_tokens, cpu=args.cpu, max_sessions=args.max_sessions)
            print(f"\nbest model: epoch {summary['best_epoch']}, val loss {summary['best_val_loss']:.4f}"
                  f" -> {summary['model']}  ({summary['minutes']} min)")
            if not args.no_eval:
                print(format_metrics(evaluate(root, summary["model"], cpu=args.cpu,
                                              max_sessions=args.max_sessions)))
        else:
            print(format_metrics(evaluate(root, args.model, temperature=args.temperature, cpu=args.cpu,
                                          max_sessions=args.max_sessions, write_weights=not args.no_weights)))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "flow":
        from .flows import FlowRunner
        bot = _make_bot(args)
        results = FlowRunner().run_file(args.file, bot=bot)
        _emit(args, {"steps": results})
        return 0

    if args.cmd.startswith("trainer"):
        return _trainer_cmd(args)
    if args.cmd in ("train-model", "eval-model", "model-demo"):
        return _model_cmd(args)

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

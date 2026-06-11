"""Phase 3 system tools demo.

Dry-run shows the verbs without side effects. The window/clipboard/process calls
that touch the real OS are shown but guarded behind --real (and need the optional
pywin32 / psutil backends).

    python examples/system_demo.py
    python examples/system_demo.py --real
"""

from __future__ import annotations

import sys

from humanpc import Bot


def main() -> None:
    real = "--real" in sys.argv
    bot = Bot() if real else Bot(dry_run=True)

    if not real:
        print("DRY-RUN: shell + app launches are skipped, returning sentinels.\n")
        result = bot.run([sys.executable, "-c", "print('hi')"])
        print(f"  run -> returncode={result.returncode} stderr={result.stderr!r}")
        proc = bot.open_app("notepad.exe")
        print(f"  open_app -> pid={proc.pid} (sentinel)")
        print("\nRun with --real to enumerate windows, use the clipboard, and run commands.")
        return

    # Real: enumerate windows, drive the clipboard, run a command, launch an app.
    print("Open windows:")
    for w in bot.list_windows()[:10]:
        print(f"  {w.title!r}  {w.rect.as_tuple()}")
    active = bot.active_window()
    print(f"Active: {active.title if active else None}")

    bot.clipboard.set_text("hello from humanpc")
    print("Clipboard now holds:", repr(bot.clipboard.get_text()))

    print("Shell:", bot.run("echo from-shell").stdout.strip())

    notepad = bot.open_app("notepad.exe", wait="Notepad", timeout=10)
    print(f"Launched Notepad (pid={notepad.pid}); focusing it...")
    bot.focus("Notepad")


if __name__ == "__main__":
    main()

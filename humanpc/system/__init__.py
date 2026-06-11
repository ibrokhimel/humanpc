"""System tools: clipboard, shell, and process launch/kill."""

from __future__ import annotations

from .apps import AppProcess, is_running, kill, launch
from .clipboard import Clipboard
from .shell import ShellResult, run

__all__ = [
    "Clipboard",
    "ShellResult",
    "run",
    "AppProcess",
    "launch",
    "kill",
    "is_running",
]

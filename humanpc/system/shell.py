"""Run shell commands and capture their output."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class ShellResult:
    command: object
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok


def run(
    command,
    *,
    cwd=None,
    timeout=None,
    shell=None,
    env=None,
    check=False,
) -> ShellResult:
    """Run ``command`` (a list, or a string for shell syntax) and capture output.

    ``shell`` defaults to True for string commands, False for list commands. With
    ``check=True`` a non-zero exit raises ``ChildProcessError``.
    """
    use_shell = shell if shell is not None else isinstance(command, str)
    proc = subprocess.run(
        command,
        shell=use_shell,
        cwd=cwd,
        timeout=timeout,
        env=env,
        capture_output=True,
        text=True,
    )
    result = ShellResult(command, proc.returncode, proc.stdout or "", proc.stderr or "")
    if check and not result.ok:
        raise ChildProcessError(
            f"command failed ({result.returncode}): {command}\n{result.stderr}"
        )
    return result

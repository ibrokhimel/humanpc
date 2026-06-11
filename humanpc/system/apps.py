"""Launch and terminate applications/processes."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from ..exceptions import DriverError


@dataclass
class AppProcess:
    pid: int
    _popen: object = None

    def is_running(self) -> bool:
        if self._popen is not None:
            return self._popen.poll() is None
        return _pid_alive(self.pid)

    def kill(self) -> None:
        if self._popen is not None:
            self._popen.terminate()
            try:
                self._popen.wait(timeout=5)
            except Exception:
                self._popen.kill()
        else:
            _kill_pid(self.pid)

    def wait(self, timeout=None):
        if self._popen is not None:
            return self._popen.wait(timeout=timeout)
        return None


def launch(target, args=(), *, cwd=None, shell=False) -> AppProcess:
    """Start an application. ``target`` is an executable path/name (+ optional args)."""
    cmd = target if shell else [target, *args]
    popen = subprocess.Popen(cmd, cwd=cwd, shell=shell)
    return AppProcess(popen.pid, popen)


def kill(target) -> int:
    """Terminate by AppProcess, pid (int), or process name (str). Returns count."""
    if isinstance(target, AppProcess):
        target.kill()
        return 1
    if isinstance(target, int):
        return 1 if _kill_pid(target) else 0
    if isinstance(target, str):
        return _kill_by_name(target)
    raise TypeError(f"cannot kill {target!r}")


def is_running(name: str) -> bool:
    return _count_by_name(name) > 0


# --- helpers --------------------------------------------------------------
def _kill_pid(pid: int) -> bool:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True,
            )
        else:
            import signal

            os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _iter_psutil():
    try:
        import psutil
    except Exception as exc:
        raise DriverError("process-by-name needs psutil: pip install psutil") from exc
    return psutil


def _kill_by_name(name: str) -> int:
    psutil = _iter_psutil()
    low = name.lower()
    count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if low in (proc.info["name"] or "").lower():
                proc.terminate()
                count += 1
        except Exception:
            continue
    return count


def _count_by_name(name: str) -> int:
    try:
        import psutil
    except Exception:
        return 0
    low = name.lower()
    count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if low in (proc.info["name"] or "").lower():
                count += 1
        except Exception:
            continue
    return count

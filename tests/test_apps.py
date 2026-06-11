import sys
import time

from humanpc.system import kill, launch
from humanpc.system.apps import AppProcess

SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]


def _await_dead(proc, tries=60):
    for _ in range(tries):
        if not proc.is_running():
            return True
        time.sleep(0.05)
    return False


def test_launch_returns_running_process():
    proc = launch(SLEEP[0], SLEEP[1:])
    try:
        assert isinstance(proc, AppProcess)
        assert proc.pid > 0
        assert proc.is_running()
    finally:
        proc.kill()


def test_kill_by_handle():
    proc = launch(SLEEP[0], SLEEP[1:])
    proc.kill()
    assert _await_dead(proc)


def test_kill_via_module_returns_count():
    proc = launch(SLEEP[0], SLEEP[1:])
    assert kill(proc) == 1
    assert _await_dead(proc)

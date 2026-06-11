import sys

import pytest

from humanpc.system import run


def test_run_captures_stdout():
    r = run([sys.executable, "-c", "print('hi')"])
    assert r.ok
    assert r.returncode == 0
    assert r.stdout.strip() == "hi"


def test_run_nonzero_returncode_is_falsey():
    r = run([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert r.returncode == 3
    assert not r.ok
    assert not r  # __bool__ reflects success


def test_run_check_raises_on_failure():
    with pytest.raises(ChildProcessError):
        run([sys.executable, "-c", "import sys; sys.exit(1)"], check=True)


def test_run_string_uses_shell():
    r = run("echo hello-shell")
    assert "hello-shell" in r.stdout

import json

from humanpc.cli import main


def test_click_json_ok(capsys):
    assert main(["--dry-run", "--json", "click", "100,100"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


def test_type_prints_ok(capsys):
    assert main(["--dry-run", "type", "hello"]) == 0
    assert "ok" in capsys.readouterr().out


def test_find_coords_json(capsys):
    assert main(["--dry-run", "--json", "find", "10,20"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["found"] and d["match"]["x"] == 10


def test_hotkey(capsys):
    assert main(["--dry-run", "hotkey", "ctrl", "c"]) == 0


def test_scroll(capsys):
    assert main(["--dry-run", "scroll", "-3"]) == 0


def test_run_dry_run_json(capsys):
    assert main(["--dry-run", "--json", "run", "echo", "hi"]) == 0
    assert json.loads(capsys.readouterr().out)["returncode"] == 0


def test_unresolvable_string_target_errors(capsys):
    # No UIA/OCR backend available -> target not found -> non-zero exit.
    assert main(["--dry-run", "click", "NoSuchButtonAnywhere"]) == 1

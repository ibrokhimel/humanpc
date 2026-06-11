import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from humanpc import Bot  # noqa: E402
from humanpc.config import Config  # noqa: E402
from humanpc.server.http import build_app  # noqa: E402


def _client():
    return TestClient(build_app(Bot(dry_run=True, config=Config(seed=1))))


def test_actions_endpoint():
    r = _client().get("/actions")
    assert r.status_code == 200 and "click" in r.json()["actions"]


def test_click_endpoint():
    r = _client().post("/click", json={"target": "100,100"})
    assert r.status_code == 200 and r.json()["ok"]


def test_find_endpoint():
    r = _client().post("/find", json={"target": "10,20"})
    d = r.json()
    assert d["found"] and d["match"]["x"] == 10


def test_unknown_action_returns_400():
    r = _client().post("/bogus", json={})
    assert r.status_code == 400

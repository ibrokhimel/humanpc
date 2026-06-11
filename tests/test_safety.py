import pytest

from humanpc.exceptions import Aborted
from humanpc.safety import AuditLog, KillSwitch, SafetyGuard


def test_audit_records_entries(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path=str(path))
    log.record("click", x=1, y=2)
    log.record("type", length=5)
    assert len(log) == 2
    assert log.entries[0]["action"] == "click"
    assert path.read_text().count("\n") == 2  # one JSON line per record


def test_killswitch_check_raises_after_abort():
    ks = KillSwitch(hotkey=None)
    ks.check()  # no-op before
    ks.request_abort()
    assert ks.aborted
    with pytest.raises(Aborted):
        ks.check()
    ks.reset()
    ks.check()  # cleared


def test_guard_enforces_max_actions():
    ks = KillSwitch(hotkey=None)
    guard = SafetyGuard(ks, max_actions=2)
    guard.precheck("a")
    guard.precheck("b")
    with pytest.raises(Aborted):
        guard.precheck("c")


def test_guard_relays_killswitch():
    ks = KillSwitch(hotkey=None)
    guard = SafetyGuard(ks)
    ks.request_abort()
    with pytest.raises(Aborted):
        guard.precheck("anything")

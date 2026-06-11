import pytest

from humanpc.config import PERSONAS, Config, get_persona


def test_personas_present():
    assert set(PERSONAS) >= {"default", "fast", "careful", "tired"}


def test_get_persona_unknown_raises():
    with pytest.raises(KeyError):
        get_persona("nope")


def test_config_from_dict_roundtrip():
    cfg = Config.from_dict({"persona": "fast", "dry_run": True, "max_actions": 5})
    assert cfg.persona == "fast"
    assert cfg.dry_run is True
    assert cfg.max_actions == 5


def test_config_from_dict_rejects_unknown_keys():
    with pytest.raises(ValueError):
        Config.from_dict({"bogus": 1})


def test_config_copy_overrides():
    cfg = Config(persona="default")
    assert cfg.copy(persona="tired").persona == "tired"
    assert cfg.persona == "default"  # original unchanged

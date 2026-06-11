"""Configuration and behaviour personas.

Phase 0 keeps this dependency-free with dataclasses. The plan calls for moving to
pydantic + YAML loading once the surface stabilises; ``Config.from_dict`` is the
seam where that swap happens.

Persona fields here are deliberately simple placeholders (linear timing). Phase 1
replaces this timing model with the Human Interaction Layer (Fitts-law velocity,
typing rhythm, etc.); personas will then tune those richer parameters instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Persona:
    """A behavioural profile. Higher ``speed_multiplier`` == slower / more careful."""

    name: str
    speed_multiplier: float = 1.0
    move_duration: float = 0.45          # baseline seconds for a cursor move
    click_dwell: tuple[float, float] = (0.04, 0.12)  # mouse-down hold range (s)
    type_cps: float = 6.0                # characters per second baseline


PERSONAS: dict[str, Persona] = {
    "default": Persona("default"),
    "fast": Persona("fast", speed_multiplier=0.6, move_duration=0.25,
                    click_dwell=(0.03, 0.08), type_cps=9.0),
    "careful": Persona("careful", speed_multiplier=1.5, move_duration=0.65,
                       click_dwell=(0.06, 0.16), type_cps=4.5),
    "tired": Persona("tired", speed_multiplier=1.8, move_duration=0.75,
                     click_dwell=(0.07, 0.20), type_cps=3.5),
}


def get_persona(name: str) -> Persona:
    try:
        return PERSONAS[name]
    except KeyError:
        raise KeyError(
            f"unknown persona {name!r}; choose from {sorted(PERSONAS)}"
        ) from None


@dataclass
class Config:
    persona: str = "default"
    dry_run: bool = False

    # Safety
    failsafe: bool = True                 # pyautogui slam-to-corner abort
    kill_hotkey: str | None = "ctrl+alt+q"
    max_actions: int | None = None        # hard cap per Bot instance; None == unlimited

    # Audit
    audit_enabled: bool = True
    audit_path: str | None = None         # JSONL file path; None == in-memory + logger only

    # Movement (placeholder until HIL)
    move_steps: int = 60

    # Determinism for tests / reproducible sessions
    seed: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**data)

    def copy(self, **overrides) -> "Config":
        return replace(self, **overrides)

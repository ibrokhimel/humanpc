"""Human Interaction Layer — makes input look human.

Each engine is a pure *planner*: given an rng it returns a plan (mouse steps,
keystroke events, scroll bursts) that the Bot executes against the input driver.
Keeping them side-effect-free makes the whole layer testable and visualisable in
dry-run, with no GUI required.
"""

from __future__ import annotations

from .behavior import BehaviorState, BehaviorTracker
from .idle import IdleDriftLoop, IdleMovementGenerator
from .individual import ActionTempo, Individual, sample_individual
from .mouse import MouseStep, MouseTrajectoryEngine
from .scroll import plan_scroll
from .session import SessionState
from .timing import HumanTimingManager
from .typing import HumanTypingEngine, KeyEvent

__all__ = [
    "MouseTrajectoryEngine",
    "MouseStep",
    "HumanTypingEngine",
    "KeyEvent",
    "HumanTimingManager",
    "SessionState",
    "Individual",
    "ActionTempo",
    "sample_individual",
    "plan_scroll",
    "BehaviorState",
    "BehaviorTracker",
    "IdleMovementGenerator",
    "IdleDriftLoop",
]

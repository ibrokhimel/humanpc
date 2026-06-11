"""Human Interaction Layer — makes input look human.

Each engine is a pure *planner*: given an rng it returns a plan (mouse steps,
keystroke events, scroll bursts) that the Bot executes against the input driver.
Keeping them side-effect-free makes the whole layer testable and visualisable in
dry-run, with no GUI required.
"""

from __future__ import annotations

from .behavior import BehaviorState, BehaviorTracker
from .idle import IdleDriftLoop, IdleMovementGenerator
from .mouse import MouseStep, MouseTrajectoryEngine
from .scroll import plan_scroll
from .timing import HumanTimingManager
from .typing import HumanTypingEngine, KeyEvent

__all__ = [
    "MouseTrajectoryEngine",
    "MouseStep",
    "HumanTypingEngine",
    "KeyEvent",
    "HumanTimingManager",
    "plan_scroll",
    "BehaviorState",
    "BehaviorTracker",
    "IdleMovementGenerator",
    "IdleDriftLoop",
]

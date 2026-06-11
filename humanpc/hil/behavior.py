"""Behavioral state machine.

Tracks what the bot is "doing" (reading / thinking / moving / typing / ...) for
observability and optional strict-mode validation of transitions. The Bot records
transitions as it acts (non-strict), so ``bot.behavior.history`` is a readable
trace of a session.
"""

from __future__ import annotations

from enum import Enum


class BehaviorState(Enum):
    IDLE = "idle"
    READING = "reading"
    THINKING = "thinking"
    MOVING = "moving"
    HOVERING = "hovering"
    CLICKING = "clicking"
    TYPING = "typing"
    SCROLLING = "scrolling"
    CORRECTING = "correcting"
    WAITING = "waiting"


_S = BehaviorState
TRANSITIONS: dict[BehaviorState, set[BehaviorState]] = {
    _S.IDLE: {_S.READING, _S.THINKING, _S.MOVING, _S.TYPING, _S.SCROLLING, _S.WAITING},
    _S.READING: {_S.THINKING, _S.MOVING, _S.SCROLLING, _S.IDLE, _S.WAITING},
    _S.THINKING: {_S.MOVING, _S.TYPING, _S.SCROLLING, _S.IDLE, _S.WAITING},
    _S.MOVING: {_S.HOVERING, _S.CLICKING, _S.MOVING, _S.IDLE, _S.WAITING},
    _S.HOVERING: {_S.CLICKING, _S.MOVING, _S.IDLE},
    _S.CLICKING: {_S.IDLE, _S.READING, _S.THINKING, _S.MOVING, _S.TYPING},
    _S.TYPING: {_S.CORRECTING, _S.TYPING, _S.IDLE, _S.THINKING, _S.WAITING},
    _S.SCROLLING: {_S.READING, _S.THINKING, _S.IDLE, _S.SCROLLING},
    _S.CORRECTING: {_S.TYPING, _S.IDLE},
    _S.WAITING: {_S.IDLE, _S.READING, _S.THINKING, _S.MOVING, _S.TYPING, _S.SCROLLING},
}


class InvalidTransition(Exception):
    pass


class BehaviorTracker:
    def __init__(self, state: BehaviorState = BehaviorState.IDLE, strict: bool = False):
        self.state = state
        self.strict = strict
        self.history: list[BehaviorState] = [state]

    def can(self, to: BehaviorState) -> bool:
        return to in TRANSITIONS.get(self.state, set())

    def observe(self, to: BehaviorState) -> "BehaviorTracker":
        if self.strict and not self.can(to):
            raise InvalidTransition(f"{self.state.value} -> {to.value} not allowed")
        self.state = to
        self.history.append(to)
        return self

    def reset(self, state: BehaviorState = BehaviorState.IDLE) -> "BehaviorTracker":
        self.state = state
        self.history = [state]
        return self

"""Safety subsystem: kill-switch, audit trail, and a per-action guard.

A human-like agent that drives the *real* mouse and keyboard can trap the user,
so safety is foundational (Phase 0), not an afterthought. Every Bot action passes
through :class:`SafetyGuard` before it runs and is recorded by :class:`AuditLog`
after.
"""

from __future__ import annotations

from .audit import AuditLog
from .killswitch import KillSwitch
from .guard import SafetyGuard

__all__ = ["AuditLog", "KillSwitch", "SafetyGuard"]

"""Exception hierarchy for humanpc."""

from __future__ import annotations


class HumanpcError(Exception):
    """Base class for all humanpc errors."""


class Aborted(HumanpcError):
    """Raised when the kill-switch fires or a safety limit is hit mid-action."""


class TargetNotFound(HumanpcError):
    """Raised when the targeting resolver cannot locate a target (Phase 2+)."""


class DriverError(HumanpcError):
    """Raised when an input/screen backend fails or is unavailable."""

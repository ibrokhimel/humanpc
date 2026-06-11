"""Per-action gate run immediately before every Bot action executes."""

from __future__ import annotations

from ..exceptions import Aborted


class SafetyGuard:
    def __init__(self, killswitch, *, max_actions: int | None = None):
        self.killswitch = killswitch
        self.max_actions = max_actions
        self._count = 0

    def precheck(self, action: str) -> None:
        self.killswitch.check()
        if self.max_actions is not None and self._count >= self.max_actions:
            raise Aborted(
                f"max_actions limit ({self.max_actions}) reached before {action!r}"
            )
        self._count += 1

    @property
    def count(self) -> int:
        return self._count

    def reset(self) -> None:
        self._count = 0

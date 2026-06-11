"""Append-only audit trail of every action a Bot performs."""

from __future__ import annotations

import json
import logging
import time

_log = logging.getLogger("humanpc.audit")


class AuditLog:
    def __init__(self, path: str | None = None, enabled: bool = True):
        self.path = path
        self.enabled = enabled
        self.entries: list[dict] = []

    def record(self, action: str, **fields) -> dict:
        entry = {"ts": time.time(), "action": action, **fields}
        self.entries.append(entry)
        if self.enabled:
            _log.debug("action %s", entry)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
        return entry

    def clear(self) -> None:
        self.entries.clear()

    def __len__(self) -> int:
        return len(self.entries)

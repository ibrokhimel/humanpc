"""Session storage: one compressed ``.npz`` of events + one ``.json`` sidecar.

Layout under the data dir::

    session_20260924_153012.npz   # delta-encoded event columns (see events.py)
    session_20260924_153012.json  # {"meta": {...}, "tasks": [...]}
    task_weights.json             # optional: per-kind sampling weights override
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .events import decode, encode

WEIGHTS_FILE = "task_weights.json"


def default_data_dir() -> Path:
    env = os.environ.get("HUMANPC_TRAINING_DIR")
    return Path(env) if env else Path.home() / ".humanpc" / "training"


class SessionWriter:
    """Writes (and atomically re-writes) a single session's files."""

    def __init__(self, data_dir: Path, name: str):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name = name

    @property
    def npz_path(self) -> Path:
        return self.dir / f"{self.name}.npz"

    @property
    def json_path(self) -> Path:
        return self.dir / f"{self.name}.json"

    def save(self, raw_events, tasks: list[dict], meta: dict) -> None:
        import numpy as np

        tmp_npz = self.dir / f"{self.name}.tmp.npz"
        np.savez_compressed(tmp_npz, **encode(raw_events))
        os.replace(tmp_npz, self.npz_path)
        tmp_json = self.json_path.with_suffix(".json.tmp")
        tmp_json.write_text(json.dumps({"meta": meta, "tasks": tasks}, indent=1), encoding="utf-8")
        os.replace(tmp_json, self.json_path)


def list_sessions(data_dir: Path) -> list[Path]:
    d = Path(data_dir)
    if not d.is_dir():
        return []
    return sorted(p.with_suffix("") for p in d.glob("session_*.json")
                  if p.with_suffix(".npz").exists())


def load_session(base: Path) -> tuple[dict, dict, list[dict]]:
    """Return ``(events, meta, tasks)`` with events decoded to absolute columns."""
    import numpy as np

    base = Path(base)
    with np.load(base.with_suffix(".npz")) as z:
        events = decode({k: z[k] for k in z.files})
    side = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    return events, side.get("meta", {}), side.get("tasks", [])


def load_weights(data_dir: Path) -> dict | None:
    p = Path(data_dir) / WEIGHTS_FILE
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def task_units(task: dict) -> dict:
    """Trainable units a completed task contributes, by movement category."""
    if task.get("result") != "ok":
        return {}
    kind, p = task.get("kind"), task.get("params", {})
    if kind == "point":
        return {"aim": 1}
    if kind in ("double", "right"):
        return {"aim": 1, "click": 1}
    if kind == "chain":
        return {"aim": len(p.get("points", []))}
    if kind == "drag":
        return {"drag": 1}
    if kind == "scroll":
        return {"scroll": 1}
    if kind == "scroll_click":
        return {"scroll": 1, "aim": 1}
    if kind == "trace":
        return {"trace": 1}
    if kind == "read" and task.get("t_end_us") is not None:
        return {"idle": (task["t_end_us"] - task["t_shown_us"]) / 1e6}
    return {}


def stats(data_dir: Path) -> dict:
    """Totals across all sessions, read from sidecars only (cheap)."""
    out = {"data_dir": str(data_dir), "sessions": 0, "tasks": 0, "tasks_ok": 0, "events": 0,
           "active_seconds": 0.0, "bytes": 0, "by_kind": {}, "units": {}}
    for base in list_sessions(data_dir):
        try:
            side = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta, tasks = side.get("meta", {}), side.get("tasks", [])
        out["sessions"] += 1
        out["tasks"] += len(tasks)
        out["events"] += int(meta.get("events", 0))
        out["active_seconds"] += float(meta.get("active_seconds", 0.0))
        out["bytes"] += base.with_suffix(".npz").stat().st_size + base.with_suffix(".json").stat().st_size
        for t in tasks:
            kind = t.get("kind", "?")
            out["by_kind"][kind] = out["by_kind"].get(kind, 0) + 1
            out["tasks_ok"] += t.get("result") == "ok"
            for cat, n in task_units(t).items():
                out["units"][cat] = out["units"].get(cat, 0) + n
    return out

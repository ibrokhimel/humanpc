"""Move recordings between machines as a single ``.zip``.

Export bundles a person's sessions plus a manifest; import validates the zip
(it comes from another machine, so it is untrusted input) before writing
anything: only ``session_YYYYMMDD_HHMMSS.{npz,json}`` members are accepted, both
halves of each session must be present and parse, and sizes are capped.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from .. import __version__
from .dataset import clean_person, list_sessions, person_dir

FORMAT = "humanpc-mousedata"
_MEMBER = re.compile(r"^session_\d{8}_\d{6}\.(npz|json)$")
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024


def export_zip(data_dir: Path, person: str, out_path: Path) -> dict:
    """Write every session in ``data_dir`` to ``out_path``. Returns a summary."""
    sessions = list_sessions(data_dir)
    if not sessions:
        raise FileNotFoundError(f"no sessions to export in {data_dir}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"format": FORMAT, "version": 1, "person": clean_person(person),
                "created": datetime.now().isoformat(timespec="seconds"), "humanpc": __version__,
                "sessions": [b.name for b in sessions]}
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    # .npz is already compressed; store it as-is and only deflate the JSON.
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=1), compress_type=zipfile.ZIP_DEFLATED)
        for base in sessions:
            z.write(base.with_suffix(".npz"), base.name + ".npz", compress_type=zipfile.ZIP_STORED)
            z.write(base.with_suffix(".json"), base.name + ".json", compress_type=zipfile.ZIP_DEFLATED)
    tmp.replace(out_path)
    return {"zip": str(out_path), "person": manifest["person"], "sessions": len(sessions),
            "bytes": out_path.stat().st_size}


def _validate_npz(data: bytes) -> None:
    import numpy as np

    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        missing = {"dt_us", "type", "dx", "dy", "button", "wheel", "x0", "y0"} - set(z.files)
        if missing:
            raise ValueError(f"missing columns {sorted(missing)}")
        n = len(z["type"])
        if any(len(z[k]) != n for k in ("dt_us", "dx", "dy", "button", "wheel")):
            raise ValueError("column lengths differ")


def import_zip(zip_path: Path, root: Path, *, person: str | None = None) -> dict:
    """Unpack an exported zip into ``root/<person>/``. Existing sessions are skipped."""
    with zipfile.ZipFile(zip_path) as z:
        try:
            manifest = json.loads(z.read("manifest.json"))
        except KeyError:
            raise ValueError("not a humanpc mouse-data zip (no manifest.json)") from None
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise ValueError("not a humanpc mouse-data zip (wrong format)")
        who = clean_person(person or manifest.get("person", ""))

        infos = [i for i in z.infolist() if i.filename != "manifest.json"]
        bad = [i.filename for i in infos if not _MEMBER.match(i.filename)]
        if bad:
            raise ValueError(f"unexpected files in zip: {bad[:5]}")
        if any(i.file_size > MAX_MEMBER_BYTES for i in infos) or \
                sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ValueError("zip is too large")
        names = {i.filename.rsplit(".", 1)[0] for i in infos}
        members = {i.filename for i in infos}
        incomplete = sorted(n for n in names if {n + ".npz", n + ".json"} - members)
        if incomplete:
            raise ValueError(f"sessions missing a file: {incomplete[:5]}")

        dest = person_dir(root, who)
        added, skipped = [], []
        for name in sorted(names):
            if (dest / f"{name}.json").exists():
                skipped.append(name)
                continue
            npz, side = z.read(name + ".npz"), z.read(name + ".json")
            try:
                _validate_npz(npz)
                parsed = json.loads(side)
                if not isinstance(parsed, dict) or not isinstance(parsed.get("tasks", []), list):
                    raise ValueError("bad sidecar")
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"{name} is corrupt: {exc}") from exc
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{name}.npz").write_bytes(npz)
            (dest / f"{name}.json").write_bytes(side)
            added.append(name)
    return {"person": who, "folder": str(dest), "added": len(added), "skipped": len(skipped)}


class BackgroundExporter:
    """Keeps an export zip up to date without blocking the UI.

    ``request()`` is cheap and can be called after every save: requests that
    arrive while an export is running collapse into one follow-up export.
    ``flush()`` waits for the latest data to be written (call it on exit).
    """

    def __init__(self, data_dir: Path, person: str, out_path: Path, on_error=None):
        import threading

        self.data_dir, self.person, self.out_path = Path(data_dir), person, Path(out_path)
        self.on_error = on_error
        self.last: dict | None = None
        self._pending = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, name="humanpc-export", daemon=True)
        self._thread.start()

    def request(self) -> None:
        with self._lock:
            self._idle.clear()
            self._pending.set()

    def flush(self, timeout: float = 30.0) -> dict | None:
        self._idle.wait(timeout)
        return self.last

    def _loop(self) -> None:
        while True:
            self._pending.wait()
            with self._lock:
                self._pending.clear()
            try:
                self.last = export_zip(self.data_dir, self.person, self.out_path)
            except Exception as exc:  # noqa: BLE001 - report, keep the thread alive
                if self.on_error:
                    self.on_error(exc)
            with self._lock:
                if not self._pending.is_set():
                    self._idle.set()

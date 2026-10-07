"""Testbench plumbing: the task generator, the local HTTP server, the browser.

The page (``testbench.html``) reports two things back to this server:

  * ``POST /api/layout`` — every ~100 ms while anything changed: element rects
    (client CSS px), the client->screen offset, devicePixelRatio, scroll, focus,
    and the current form values. The driver turns rects into screen pixels.
  * ``POST /api/log`` — once, on submit: the full event log plus pass/fail.

Only binds 127.0.0.1. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "testbench.html"

COUNTRIES = ["Argentina", "Brazil", "Canada", "Denmark", "Egypt", "France", "Germany", "Japan"]
INTERESTS = ["music", "sports", "travel", "cooking", "gaming", "reading"]
_FIRST = ["Maya", "Jonas", "Priya", "Tomas", "Leila", "Owen", "Sofia", "Daniel", "Amara", "Felix"]
_LAST = ["Hartley", "Novak", "Okafor", "Lindqvist", "Moreau", "Tanaka", "Castillo", "Brennan"]
_DOMAINS = ["example.com", "mail.test", "inbox.example.org"]
_ABOUT = [
    "I work on a small team that builds internal tools, and I mostly need this account for reports.",
    "Signing up to try the monthly usage reports before we roll them out to the rest of the office.",
    "I manage billing for two departments and want one place to see invoices and payment history.",
    "Just testing the registration flow, nothing important. Please send the welcome email to this address.",
]

BROWSERS = {
    "edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
    "chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
               r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
}


def make_task(rng: random.Random, mode: str) -> dict:
    first, last = rng.choice(_FIRST), rng.choice(_LAST)
    return {
        "mode": mode,
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}{rng.randint(2, 99)}@{rng.choice(_DOMAINS)}",
        "about": rng.choice(_ABOUT),
        "country": rng.choice(COUNTRIES),
        "interests": sorted(rng.sample(INTERESTS, 3), key=INTERESTS.index),
        "slider": rng.choice([v for v in range(12, 95) if abs(v - 50) > 8]),
    }


class Bench:
    """Shared state between the HTTP thread and the driver."""

    def __init__(self, task: dict, label: str, out_dir: Path):
        self.task, self.label, self.out_dir = task, label, out_dir
        self.layout: dict | None = None
        self.layout_seq = 0
        self.log_path: Path | None = None
        self.log_saved = threading.Event()
        self.lock = threading.Lock()
        self.server: ThreadingHTTPServer | None = None

    # -- server --------------------------------------------------------------
    def start(self) -> str:
        bench = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep the console quiet
                pass

            def _send(self, code, body: bytes, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path in ("/", "/index.html") or self.path.startswith("/#"):
                    self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                elif self.path == "/api/task":
                    self._send(200, json.dumps(bench.task).encode())
                else:
                    self._send(404, b"{}")

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > 64 * 1024 * 1024:
                    self._send(400, b"{}")
                    return
                try:
                    data = json.loads(self.rfile.read(n))
                except ValueError:
                    self._send(400, b"{}")
                    return
                if self.path == "/api/layout" and isinstance(data, dict):
                    with bench.lock:
                        bench.layout = data
                        bench.layout_seq += 1
                    self._send(200, b"{}")
                elif self.path == "/api/log" and isinstance(data, dict):
                    bench._save_log(data)
                    self._send(200, b"{}")
                else:
                    self._send(404, b"{}")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}/"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    def _save_log(self, data: dict) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = self.out_dir / f"{self.label}_{stamp}.json"
        data.setdefault("meta", {})["label"] = self.label
        path.write_text(json.dumps(data), encoding="utf-8")
        self.log_path = path
        self.log_saved.set()

    # -- layout access for the driver -----------------------------------------
    def snapshot(self) -> dict | None:
        with self.lock:
            return self.layout

    def wait(self, pred, timeout: float = 10.0, what: str = "page state") -> dict:
        """Block until ``pred(layout)`` is true; returns that layout."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            lay = self.snapshot()
            if lay is not None and pred(lay):
                return lay
            time.sleep(0.03)
        raise TimeoutError(f"timed out waiting for {what}")

    def fresh(self, settle: float = 0.25) -> dict:
        """A layout posted after now (so it reflects the last action)."""
        seq = self.layout_seq
        time.sleep(settle)
        try:
            return self.wait(lambda _l: self.layout_seq > seq, timeout=1.0)
        except TimeoutError:
            return self.snapshot()  # nothing changed -> the old one is current


def screen_rect(lay: dict, el: str) -> tuple[int, int, int, int] | None:
    """Element rect in physical screen px: (x, y, w, h)."""
    r = lay["els"].get(el)
    if r is None:
        return None
    d, (ox, oy) = lay["dpr"], lay["offset"]
    return (round((ox + r[0]) * d), round((oy + r[1]) * d), max(1, round(r[2] * d)), max(1, round(r[3] * d)))


def visible(lay: dict, el: str, margin: float = 20.0) -> bool:
    r = lay["els"].get(el)
    if r is None:
        return False
    return r[1] >= margin and r[1] + r[3] <= lay["inner"][1] - margin


def find_browser(name: str) -> str:
    for p in BROWSERS.get(name, []):
        if os.path.exists(p):
            return p
    found = shutil.which("msedge" if name == "edge" else name)
    if found:
        return found
    raise FileNotFoundError(f"{name} not found; pass --browser chrome/edge or --browser-path")


class Browser:
    """A throwaway browser instance (fresh profile, maximized, no first-run UI)."""

    def __init__(self, exe: str):
        self.exe = exe
        self.profile = tempfile.mkdtemp(prefix="humanpc-bench-")
        self.proc: subprocess.Popen | None = None

    def open(self, url: str = "about:blank") -> None:
        self.proc = subprocess.Popen([
            self.exe, f"--user-data-dir={self.profile}", "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate,msEdgeSidebarV2,msUndersideButton", "--disable-sync",
            "--start-maximized", "--new-window", url,
        ])

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                           capture_output=True, check=False)
        time.sleep(0.5)
        shutil.rmtree(self.profile, ignore_errors=True)

"""Fullscreen trainer: prompts movement tasks while recording raw mouse input.

Controls: Space = start/resume, Esc = pause, S = skip task, Q (while paused) = save & quit.
The recorder only runs while a task session is active (not on pause screens).
"""

from __future__ import annotations

import random
import time
from datetime import datetime
from pathlib import Path

from .. import __version__
from .dataset import SessionWriter, load_weights, stats, task_units
from .report import estimate
from .events import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT
from .recorder import Recorder
from .task_runtime import C_MUTED, C_TEXT, NS, make_runtime
from .tasks import TaskSampler

BG = "#111827"
_TK_BTN = {1: BTN_LEFT, 2: BTN_MIDDLE, 3: BTN_RIGHT}
AUTOSAVE_EVERY = 15
TICK_MS = 5


class TrainerApp:
    def __init__(self, data_dir: Path, *, minutes: float = 10.0, seed: int | None = None,
                 keep_injected: bool = False):
        self.data_dir = Path(data_dir)
        self.break_after = minutes * 60
        self.rng = random.Random(seed)
        self.seed = seed
        self.recorder = Recorder(keep_injected=keep_injected)
        self.recorder.paused = True
        self.name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self.writer = SessionWriter(self.data_dir, self.name)
        self.prior = stats(self.data_dir)
        self.records: list[dict] = []
        self.rt = None
        self.state = "intro"  # intro | running | gap | paused
        self.active = 0.0
        self._last_tick = time.perf_counter()
        self._gap_until = 0
        self._since_break = 0.0
        self.dpi_mode = "unknown"

    # -- lifecycle ---------------------------------------------------------------
    def run(self) -> dict:
        import tkinter as tk

        from ..perception.dpi import set_dpi_awareness
        self.dpi_mode = set_dpi_awareness()
        self.recorder.start()
        self.root = tk.Tk()
        self.root.title("humanpc trainer")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.root.update()
        self.origin = (self.root.winfo_rootx(), self.root.winfo_rooty())
        self.size = (self.canvas.winfo_width(), self.canvas.winfo_height())
        self.sampler = TaskSampler(*self.size, rng=self.rng, weights=load_weights(self.data_dir))

        c = self.canvas
        for n in (1, 2, 3):
            c.bind(f"<ButtonPress-{n}>", lambda e, n=n: self._press(e, n))
            c.bind(f"<ButtonRelease-{n}>", lambda e, n=n: self._release(e, n))
        c.bind("<Motion>", self._motion)
        c.bind("<MouseWheel>", self._wheel)
        self.root.bind("<Key>", self._key)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.focus_force()
        self._render()
        self.root.after(TICK_MS, self._tick)
        try:
            self.root.mainloop()
        finally:
            self.recorder.stop()
        return {"session": str(self.writer.npz_path), "tasks": len(self.records),
                "events": len(self.recorder.events), "active_seconds": round(self.active, 1)}

    def _meta(self) -> dict:
        return {"version": 1, "humanpc": __version__, "session": self.name,
                "started": self.name[8:], "screen": list(self.size), "window_origin": list(self.origin),
                "dpi_mode": self.dpi_mode, "seed": self.seed, "hook": "WH_MOUSE_LL",
                "coords": "tasks in window px; events in screen px", "scroll_step_px": 100,
                "events": len(self.recorder.events), "injected_dropped": self.recorder.injected_dropped,
                "active_seconds": round(self.active, 2), "weights": self.sampler.weights}

    def _save(self) -> None:
        self.writer.save(self.recorder.snapshot(), self.records, self._meta())

    def _quit(self) -> None:
        if self.rt is not None and not self.rt.done:
            self.records.append(self.rt.record(self.recorder.t0))
            self.rt = None
        if self.recorder.events or self.records:
            self._save()
        self.root.destroy()

    # -- state -------------------------------------------------------------------
    def _now(self) -> int:
        return time.perf_counter_ns()

    def _local(self, e) -> tuple[int, int]:
        return e.x_root - self.origin[0], e.y_root - self.origin[1]

    def _next_task(self) -> None:
        self.rt = make_runtime(self.sampler.sample(), self._now(), self.size)
        self.state = "running"

    def _resume(self) -> None:
        self.recorder.paused = False
        self._last_tick = time.perf_counter()
        self._next_task()
        self._render()

    def _pause(self, reason: str = "") -> None:
        self.recorder.paused = True
        self.rt = None  # an interrupted task is discarded, not recorded
        self.state = "paused"
        self._pause_reason = reason
        self._save()
        self._render()

    def _complete(self) -> None:
        self.records.append(self.rt.record(self.recorder.t0))
        self.rt = None
        if len(self.records) % AUTOSAVE_EVERY == 0:
            self._save()
        if self._since_break >= self.break_after:
            self._since_break = 0.0
            self._pause("Break time - your data is saved. Rest your hand for a minute.")
            return
        self.state = "gap"
        self._gap_until = self._now() + int(self.rng.uniform(0.25, 0.6) * NS)
        self._render()

    def _tick(self) -> None:
        now_s = time.perf_counter()
        if self.state in ("running", "gap"):
            dt = now_s - self._last_tick
            self.active += dt
            self._since_break += dt
        self._last_tick = now_s
        now = self._now()
        if self.state == "gap" and now >= self._gap_until:
            self._next_task()
            self._render()
        elif self.state == "running" and self.rt is not None:
            self.rt.tick(now)
            if self.rt.done:
                self._complete()
            elif self.rt.dirty:
                self._render()
        self.root.after(TICK_MS, self._tick)

    # -- input -------------------------------------------------------------------
    def _press(self, e, n):
        if self.state == "running" and self.rt:
            self.rt.press(*self._local(e), _TK_BTN[n], self._now())

    def _release(self, e, n):
        if self.state == "running" and self.rt:
            self.rt.release(*self._local(e), _TK_BTN[n], self._now())

    def _motion(self, e):
        if self.state == "running" and self.rt:
            self.rt.motion(*self._local(e), self._now())

    def _wheel(self, e):
        if self.state == "running" and self.rt:
            self.rt.wheel(e.delta, self._now())

    def _key(self, e):
        key = e.keysym.lower()
        if self.state in ("intro", "paused"):
            if key == "space":
                self._resume()
            elif key in ("q", "escape"):
                self._quit()
        elif key == "escape":
            self._pause()
        elif key == "s" and self.state == "running" and self.rt:
            self.records.append(self.rt.record(self.recorder.t0))
            self.rt = None
            self.state = "gap"
            self._gap_until = self._now()

    # -- drawing -----------------------------------------------------------------
    def _render(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = self.size
        if self.state in ("intro", "paused"):
            self._draw_menu(w, h)
            return
        if self.rt is not None:
            for s in self.rt.shapes():
                self._draw(s)
            self.rt.dirty = False
        total_h = (self.prior["active_seconds"] + self.active) / 3600
        m, s = divmod(int(self.active), 60)
        c.create_text(16, 14, anchor="nw", fill=C_MUTED, font=("Segoe UI", 10),
                      text=f"task {len(self.records) + 1}  ·  session {m:02d}:{s:02d}  ·  "
                           f"total {total_h:.2f} h  ·  Esc pause  ·  S skip")

    def _draw_menu(self, w, h) -> None:
        c = self.canvas
        total_h = (self.prior["active_seconds"] + self.active) / 3600
        if self.state == "intro":
            title = "humanpc movement trainer"
            body = ("Do each task the way you normally use a mouse - don't try to be precise or fast, "
                    "just be yourself. Real hardware input only is recorded.\n\n"
                    "Space  start        Esc  pause        S  skip task        Q  save & quit")
        else:
            title = "Paused"
            body = (getattr(self, "_pause_reason", "") + "\n\n" if getattr(self, "_pause_reason", "") else "") + \
                   f"This session: {len(self.records)} tasks, {int(self.active // 60)} min.\n\n" \
                   "Space  resume        Q  save & quit"
        c.create_text(w / 2, h * 0.3, text=title, fill=C_TEXT, font=("Segoe UI", 28, "bold"))
        c.create_text(w / 2, h * 0.45, text=body, fill=C_TEXT, font=("Segoe UI", 14),
                      width=int(w * 0.55), justify="center")
        units = dict(self.prior.get("units", {}))
        for rec in self.records:
            for cat, n in task_units(rec).items():
                units[cat] = units.get(cat, 0) + n
        c.create_text(w / 2, h * 0.62, fill=C_TEXT, font=("Segoe UI", 13),
                      text=f"Estimated humanness if trained now: ~{estimate(units):.0f}%  (rough estimate)")
        c.create_text(w / 2, h * 0.7, fill=C_MUTED, font=("Segoe UI", 11),
                      text=f"total recorded: {total_h:.2f} h across {self.prior['sessions'] + 1} sessions"
                           f"  ·  data: {self.data_dir}")

    def _draw(self, s) -> None:
        c = self.canvas
        kind = s[0]
        if kind == "circle":
            _, x, y, r, fill, label = s
            c.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline="")
            if label:
                c.create_text(x, y, text=label, fill=BG, font=("Segoe UI", max(8, int(min(r, 30) * 0.7)), "bold"))
        elif kind == "rect":
            _, x0, y0, x1, y1, fill, outline = s
            c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=2 if outline else 0)
        elif kind == "line":
            _, pts, width, color = s
            c.create_line(*pts, width=width, fill=color, capstyle="round", joinstyle="round", smooth=False)
        elif kind == "text":
            _, x, y, text, size, color, wrap = s
            c.create_text(x, y, text=text, fill=color, font=("Segoe UI", size),
                          width=wrap or 0, justify="center")


def run_trainer(data_dir: Path, *, minutes: float = 10.0, seed: int | None = None,
                keep_injected: bool = False) -> dict:
    return TrainerApp(data_dir, minutes=minutes, seed=seed, keep_injected=keep_injected).run()

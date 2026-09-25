"""Live window for ``humanpc train-model --watch``.

Training runs on a background thread. Every time it saves a new best model the
window loads it (on the CPU) and keeps giving it the same 8-task exam: four
clicks, two double-clicks, a right-click and a drag, with fixed starts and
targets so rounds are comparable. Paths are the raw model output (no landing
fix), so you can watch them go from wandering to clean.

The side panel shows the loss per epoch, each best model's exam score and, at
the end, the detector's humanness result. Closing the window stops training;
``model.pt`` keeps the best model saved so far.
"""

from __future__ import annotations

import math
import queue
import random
import threading
import time
import traceback
from pathlib import Path

import torch

from ..events import DOWN, MOVE, UP
from .generate import generate, to_events
from .model import load
from .segments import Segment

W, H, PANEL = 1000, 760, 500
BG, FG, DIM, GRID = "#101216", "#d8dde6", "#6b7280", "#23272f"
BEST, TRAIN_LINE, VAL_LINE, BAR = "#f5c542", "#555b66", "#4ea1ff", "#5bd68a"
COLORS = ("#4ea1ff", "#ff7a59", "#5bd68a", "#f5c542", "#c77dff", "#ff5d8f", "#38d9d9", "#ffa94d")
KIND_LABEL = {"aim": "click", "aim_double": "double", "aim_right": "right", "drag": "drag"}
EXAM_STEPS = 400  # 4 s: anything slower counts as not finished


def exam(seed: int = 7) -> list[tuple[Segment, tuple[float, float]]]:
    """Fixed tasks: (segment, start) in window pixels."""
    r = random.Random(seed)
    out = []
    for kind in ("aim", "aim", "aim", "aim", "aim_double", "aim_double", "aim_right", "drag"):
        while True:
            s = (r.uniform(60, W - 60), r.uniform(90, H - 60))
            t = (r.uniform(60, W - 60), r.uniform(90, H - 60))
            if 200 < math.dist(s, t) < 750:
                break
        out.append((Segment(kind, 0, 0, target=t, radius=r.choice((10, 14, 18, 24))), s))
    return out


class TrainingWatch:
    def __init__(self, model_path: Path, train_fn, eval_fn=None):
        self.model_path = Path(model_path)
        self.train_fn, self.eval_fn = train_fn, eval_fn
        self.tasks = exam()
        self.events: queue.Queue = queue.Queue()  # from the training thread
        self.results: queue.Queue = queue.Queue()  # from the exam thread
        self.epochs: list[tuple[int, float, float, bool]] = []
        self.scores: dict[int, list[int]] = {}  # epoch -> [done, tries]
        self.notes: list[str] = []
        self.stage = "loading data..."
        self.model = self.model_epoch = None
        self.exam_busy = False
        self.summary = None

    # -- worker threads -------------------------------------------------------------
    def _train(self):
        def log(line):
            print(line, flush=True)
            self.events.put(("log", line))

        def on_epoch(rec, best):
            self.events.put(("epoch", rec, best))

        try:
            self.summary = self.train_fn(log=log, on_epoch=on_epoch)
            self.events.put(("log", f"best model: epoch {self.summary['best_epoch']}, "
                                    f"val loss {self.summary['best_val_loss']:.4f}"))
            if self.eval_fn:
                self.events.put(("stage", "measuring humanness with the detector (a few minutes)..."))
                text = self.eval_fn(self.summary["model"])
                print(text, flush=True)
                self.events.put(("result", text))
            self.events.put(("stage", "finished - close the window when you're done"))
        except Exception as exc:  # noqa: BLE001 - show it in the window, not a dead thread
            traceback.print_exc()
            self.events.put(("stage", f"error: {exc}"))

    def _run_exam(self, model, epoch):
        try:
            raws = generate(model, self.tasks, [0] * len(self.tasks), device="cpu", max_steps=EXAM_STEPS)
            self.results.put((epoch, raws))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self.results.put((epoch, None))

    # -- ui ---------------------------------------------------------------------------
    def run(self):
        import tkinter as tk

        from ...perception.dpi import set_dpi_awareness
        set_dpi_awareness()
        torch.set_num_threads(2)  # the exam runs on the CPU; leave the rest to training
        self.root = tk.Tk()
        self.root.title("humanpc - watching the model learn")
        self.root.configure(bg=BG)
        self.cv = tk.Canvas(self.root, width=W, height=H, bg=BG, highlightthickness=0)
        self.cv.grid(row=0, column=0)
        self.side = tk.Canvas(self.root, width=PANEL, height=H, bg=BG, highlightthickness=0)
        self.side.grid(row=0, column=1)
        self._draw_exam("waiting for the first saved model...")
        self._draw_side()
        threading.Thread(target=self._train, daemon=True).start()
        self.root.after(100, self._tick)
        self.root.mainloop()
        return self.summary

    def _tick(self):
        changed = False
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            self._handle(ev)
        if self.model is not None and not self.exam_busy:
            self.exam_busy = True
            threading.Thread(target=self._run_exam, args=(self.model, self.model_epoch), daemon=True).start()
        try:
            epoch, raws = self.results.get_nowait()
            if raws is None:
                self.exam_busy = False
            else:
                self._play(epoch, raws)
        except queue.Empty:
            pass
        if changed:
            self._draw_side()
        self.root.after(100, self._tick)

    def _handle(self, ev):
        kind = ev[0]
        if kind == "epoch":
            rec, best = ev[1], ev[2]
            self.epochs.append((rec["epoch"], rec["train"]["total"], rec["val"]["total"], best))
            self.stage = f"training - epoch {rec['epoch']} done ({rec['seconds']:.0f}s per epoch)"
            if best:
                try:
                    self.model, ck = load(self.model_path, "cpu")
                    self.model_epoch = ck.get("epoch", rec["epoch"])
                    self.scores.setdefault(self.model_epoch, [0, 0])
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
        elif kind == "log":
            line = ev[1]
            if line.startswith(("device", "model '", "best model")):
                self.notes.append(line)
                if line.startswith("model '"):
                    self.stage = "training - first epoch..."
            elif line.startswith("no improvement"):
                self.notes.append("stopped early: no improvement")
        elif kind == "stage":
            self.stage = ev[1]
        elif kind == "result":
            self.notes += [ln.strip() for ln in ev[1].splitlines()
                           if "humanness" in ln.lower() or "completed their task" in ln]

    # -- exam drawing ---------------------------------------------------------------------
    def _draw_exam(self, head):
        c = self.cv
        c.delete("all")
        for i, (seg, s) in enumerate(self.tasks):
            col = COLORS[i]
            (tx, ty), r = seg.target, seg.radius
            c.create_oval(tx - r, ty - r, tx + r, ty + r, outline=col, width=2)
            c.create_text(tx, ty - r - 10, text=KIND_LABEL[seg.kind], fill=col, font=("Segoe UI", 9))
            c.create_rectangle(s[0] - 4, s[1] - 4, s[0] + 4, s[1] + 4, outline=col)
        c.create_text(16, 14, anchor="nw", fill=FG, font=("Segoe UI", 13, "bold"), text=head)
        c.create_text(16, 40, anchor="nw", fill=DIM, font=("Segoe UI", 10),
                      text="raw model output, no landing fix.  square = start, circle = target, "
                           "ring = press, dot = release.")

    def _play(self, epoch, raws):
        paths = [to_events(raw, seg, s) for (seg, s), raw in zip(self.tasks, raws)]
        done = sum(raw["finished"] for raw in raws)
        sc = self.scores.setdefault(epoch, [0, 0])
        sc[0] += done
        sc[1] += len(raws)
        self._draw_exam(f"best model so far: epoch {epoch}   |   this round {done}/{len(raws)} done   |   "
                        f"{100 * sc[0] / sc[1]:.0f}% over {sc[1]} tries")
        self._draw_side()
        pos = [s for _, s in self.tasks]
        dots = [self.cv.create_oval(0, 0, 0, 0, fill=COLORS[i], outline="") for i in range(len(paths))]
        idx = [0] * len(paths)
        start = time.perf_counter()

        def step():
            now = (time.perf_counter() - start) * 1000
            live = False
            for p, ev in enumerate(paths):
                while idx[p] < len(ev) and ev[idx[p]][0] <= now:
                    _t, typ, x, y, _b, _w = ev[idx[p]]
                    if typ == MOVE:
                        self.cv.create_line(*pos[p], x, y, fill=COLORS[p], width=2)
                        pos[p] = (x, y)
                    elif typ == DOWN:
                        self.cv.create_oval(x - 7, y - 7, x + 7, y + 7, outline=COLORS[p], width=2)
                    elif typ == UP:
                        self.cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=FG, outline="")
                    idx[p] += 1
                x, y = pos[p]
                self.cv.coords(dots[p], x - 5, y - 5, x + 5, y + 5)
                self.cv.tag_raise(dots[p])
                live = live or idx[p] < len(ev)
            if live:
                self.root.after(8, step)
            else:
                self.root.after(1200, lambda: setattr(self, "exam_busy", False))
        step()

    # -- side panel -------------------------------------------------------------------------
    def _draw_side(self):
        c = self.side
        c.delete("all")
        c.create_text(16, 14, anchor="nw", fill=FG, font=("Segoe UI", 13, "bold"), text="Training")
        c.create_text(16, 40, anchor="nw", fill=DIM, font=("Segoe UI", 10), text=self.stage, width=PANEL - 30)
        x0, y0, cw, ch = 50, 80, PANEL - 70, 250
        c.create_rectangle(x0, y0, x0 + cw, y0 + ch, outline=GRID)
        c.create_text(x0, y0 + ch + 14, anchor="w", fill=DIM, font=("Segoe UI", 9),
                      text="loss per epoch (lower = better)   grey train   blue validation   gold = new best")
        if self.epochs:
            vals = [e[1] for e in self.epochs] + [e[2] for e in self.epochs]
            lo, hi = min(vals), max(vals)
            hi = hi if hi > lo else lo + 1
            n = max(len(self.epochs), 2)

            def pt(i, v):
                return x0 + cw * i / (n - 1), y0 + ch - ch * (v - lo) / (hi - lo)
            for k, col in ((1, TRAIN_LINE), (2, VAL_LINE)):
                pts = [pt(i, e[k]) for i, e in enumerate(self.epochs)]
                if len(pts) > 1:
                    c.create_line(*[v for p in pts for v in p], fill=col, width=2)
            for i, e in enumerate(self.epochs):
                if e[3]:
                    x, y = pt(i, e[2])
                    c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=BEST, outline="")
            c.create_text(x0 - 6, y0, anchor="e", fill=DIM, font=("Segoe UI", 8), text=f"{hi:.2f}")
            c.create_text(x0 - 6, y0 + ch, anchor="e", fill=DIM, font=("Segoe UI", 8), text=f"{lo:.2f}")
        y = y0 + ch + 44
        c.create_text(16, y, anchor="nw", fill=FG, font=("Segoe UI", 11, "bold"), text="Exam score of each best model")
        y += 24
        for ep, (done, tries) in sorted(self.scores.items())[-8:]:
            if not tries:
                continue
            frac = done / tries
            c.create_text(16, y, anchor="nw", fill=DIM, font=("Consolas", 10), text=f"epoch {ep:>3}")
            c.create_rectangle(100, y + 3, 100 + 250 * frac, y + 13, fill=BAR, outline="")
            c.create_rectangle(100, y + 3, 350, y + 13, outline=GRID)
            c.create_text(360, y, anchor="nw", fill=FG, font=("Consolas", 10), text=f"{100 * frac:3.0f}%  ({tries})")
            y += 20
        if self.notes:
            c.create_text(16, y + 10, anchor="nw", fill=DIM, font=("Consolas", 9), width=PANEL - 30,
                          text="\n".join(self.notes[-8:]))


def run_watch(model_path: Path, train_fn, eval_fn=None):
    """``train_fn(log=, on_epoch=) -> summary``; ``eval_fn(model_path) -> report text``."""
    return TrainingWatch(model_path, train_fn, eval_fn).run()

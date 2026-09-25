"""Interactive playground for a trained movement model.

    humanpc model-demo [--model PATH]

A fake cursor replays generated movements at real speed inside a window, so the
real mouse is untouched unless live mode is switched on.

Actions (number keys):
    1 click   2 double-click   3 right-click   4 drag   5 scroll   6 scroll + click   7 read, then click Done

Keys / mouse:
    click        put the target / drop zone / Done button there and run the action
    wheel        target size (pointer actions) or scroll distance (scroll actions)
    Space        random target / random scroll distance, then run
    V            same action 5 times at once: see how the paths differ
    C            landing correction on/off (off = the raw model output)
    L            live mode on/off: the REAL cursor performs it (clicks stay in this window; Esc stops)
    Esc          stop live playback / quit
"""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

from ..events import DOWN, MOVE, UP, WHEEL
from ..task_runtime import SCROLL_STEP
from .generate import MovementGenerator, generate, land_on_target, to_events
from .segments import Segment

BG, FG, MUTED, ZONE = "#111827", "#e2e8f0", "#718096", "#2d3748"
TARGET, CURSOR, LINE, BAND = "#f5a623", "#ffffff", "#ff4d4f", "#4c8bf5"
TRAILS = ("#4c8bf5", "#3ecf8e", "#ff4d4f", "#b47cff", "#ffd166")
W, H = 1280, 800
BAND_Y, BAND_H, ROW_H, BOX = H / 2, 100, 120, 40

ACTIONS = {
    "1": ("aim", "click"), "2": ("aim_double", "double-click"), "3": ("aim_right", "right-click"),
    "4": ("drag", "drag the box into the zone"), "5": ("scroll", "scroll the red line into the band"),
    "6": ("scroll_click", "scroll, then click the dot"), "7": ("idle", "read, then click Done"),
}
POINTER = ("aim", "aim_double", "aim_right", "drag", "idle")


class Demo:
    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.gen: MovementGenerator | None = None
        self.kind, self.label = ACTIONS["1"]
        self.cursor = (W * 0.25, H * 0.6)
        self.target = (W * 0.7, H * 0.4)
        self.radius = 16.0
        self.scroll_px = 1200.0
        self.land = True
        self.live = False
        self.playing = False
        self.stop_live = False
        self.rng = random.Random()

    # -- setup ---------------------------------------------------------------------
    def run(self) -> None:
        import tkinter as tk

        from ...perception.dpi import set_dpi_awareness
        set_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("humanpc model demo")
        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=BG, highlightthickness=0)
        self.canvas.pack()
        self.status = tk.StringVar(value="loading model...")
        tk.Label(self.root, textvariable=self.status, bg=BG, fg=FG, font=("Consolas", 10),
                 justify="left", anchor="w").pack(fill="x")
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.root.bind("<Key>", self._key)
        self.root.update()
        self.gen = MovementGenerator.load(self.model_path)
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        self._redraw()
        self._say("ready - 1-7 pick an action, click to place the target, Space = random, V = 5 paths")
        self.root.mainloop()

    # -- input -----------------------------------------------------------------------
    def _click(self, e):
        if self.playing:
            return
        if self.kind == "scroll":
            self._play(1)
            return
        self.target = (e.x, BAND_Y) if self.kind == "scroll_click" else (e.x, e.y)
        self._play(1)

    def _wheel(self, e):
        if self.playing:
            return
        up = e.delta > 0
        if self.kind in POINTER:
            self.radius = max(4.0, min(80.0, self.radius * (1.15 if up else 1 / 1.15)))
        else:
            self.scroll_px = max(-6000.0, min(6000.0, self.scroll_px + (200 if up else -200)))
        self._redraw()

    def _key(self, e):
        k = e.keysym.lower()
        if k == "escape":
            if self.playing:
                self.stop_live = True
            else:
                self.root.destroy()
            return
        if self.playing:
            return
        if k in ACTIONS:
            self.kind, self.label = ACTIONS[k]
            if self.kind == "scroll_click":
                self.target = (self.target[0], BAND_Y)
            self._redraw()
            self._say(f"action: {self.label}")
        elif k == "space":
            self._randomise()
            self._play(1)
        elif k == "v":
            self._play(5)
        elif k == "c":
            self.land = not self.land
            self._say(f"landing correction {'ON' if self.land else 'OFF (raw model output)'}")
        elif k == "l":
            self.live = not self.live
            self._say("LIVE mode ON - the real cursor will move, click and scroll (Esc stops)" if self.live
                      else "live mode off - fake cursor only")

    def _randomise(self) -> None:
        r = self.rng
        self.target = (r.uniform(80, W - 80), r.uniform(80, H - 80))
        self.radius = math.exp(r.uniform(math.log(6), math.log(50)))
        self.scroll_px = r.choice((-1, 1, 1, 1)) * math.exp(r.uniform(math.log(300), math.log(4000)))
        if self.kind == "scroll_click":
            self.target = (self.target[0], BAND_Y)

    # -- segments ----------------------------------------------------------------------
    def _segment(self) -> Segment:
        k = self.kind
        if k == "scroll":
            return Segment(k, 0, 0, scroll_px=self.scroll_px)
        if k == "scroll_click":
            return Segment(k, 0, 0, scroll_px=self.scroll_px, target=self.target, radius=self.radius)
        if k == "idle":
            return Segment(k, 0, 0, target=self.target, radius=22, duration_hint=self.rng.uniform(5, 10))
        if k == "drag":
            return Segment(k, 0, 0, target=self.target, radius=self.radius)
        return Segment(k, 0, 0, target=self.target, radius=self.radius)

    def _outcome(self, seg: Segment, ev: list[tuple], end) -> str:
        notches = sum(e[5] for e in ev if e[1] == WHEEL) / 120
        to_go = seg.scroll_px + notches * SCROLL_STEP
        in_band = abs(to_go) <= BAND_H / 2
        inside = seg.target is not None and math.hypot(end[0] - seg.target[0], end[1] - seg.target[1]) <= seg.radius + 1
        clicks = sum(1 for e in ev if e[1] == DOWN)
        if seg.kind == "scroll":
            return f"{notches:+.0f} notches, line {'IN the band' if in_band else f'{to_go:+.0f}px from the band'}"
        if seg.kind == "scroll_click":
            return (f"{notches:+.0f} notches, line {'in band' if in_band else 'NOT in band'}, "
                    f"{'clicked the dot' if inside else 'missed the dot'}, {clicks} click(s)")
        if seg.kind == "drag":
            return f"released {'INSIDE' if inside else 'OUTSIDE'} the zone"
        return f"last click {'ON the target' if inside else 'OFF the target'}, {clicks} click(s)"

    # -- generation + playback ----------------------------------------------------------
    def _play(self, n: int) -> None:
        self.playing = True
        self._redraw()
        self._say(f"generating {n} x {self.label}...")
        self.root.update()
        seg = self._segment()
        t0 = time.perf_counter()
        raws = generate(self.gen.model, [(seg, self.cursor)] * n, [0] * n, device=self.gen.device)
        gen_ms = (time.perf_counter() - t0) * 1000
        paths, lines = [], []
        for i, raw in enumerate(raws):
            g = land_on_target(raw, seg, self.cursor, self.rng) if self.land else raw
            ev = to_events(g, seg, self.cursor)
            ups = [e for e in ev if e[1] == UP]
            moves = [e for e in ev if e[1] == MOVE]
            end = (ups[-1][2], ups[-1][3]) if ups else (moves[-1][2], moves[-1][3]) if moves else self.cursor
            lines.append(f"  path {i + 1}: {len(g['dx']) * 10} ms, "
                         f"{'finished' if raw['finished'] else 'did NOT finish (time limit)'}, "
                         f"{self._outcome(seg, ev, end)}")
            paths.append(ev)
        head = (f"{self.label}  |  generated in {gen_ms:.0f} ms  |  landing fix {'on' if self.land else 'off'}"
                f"{'  |  LIVE' if self.live else ''}")
        if len(paths) > 1 and self.kind in ("scroll", "scroll_click"):
            head += "  |  page shows path 1"
        self._say("\n".join([head] + lines))
        if self.live and n == 1:
            self._play_live(paths[0])
        else:
            self._animate(paths)

    def _new_state(self, n):
        self.canvas.delete("startbox")
        self.pstate = [{"pos": self.cursor, "held": self.kind == "drag", "offset": 0.0,
                        "dot": self.canvas.create_oval(0, 0, 0, 0, fill=CURSOR, outline=""),
                        "box": self.canvas.create_rectangle(0, 0, 0, 0, fill=TARGET, outline="")
                        if self.kind == "drag" else None} for _ in range(n)]

    def _apply(self, p: int, e: tuple) -> None:
        """Draw one event of path ``p``."""
        st = self.pstate[p]
        _t, typ, x, y, btn, wheel = e
        c = self.canvas
        if typ == MOVE:
            c.create_line(*st["pos"], x, y, fill=TRAILS[p % len(TRAILS)], width=2, tags="trail")
            st["pos"] = (x, y)
        elif typ == DOWN:
            c.create_oval(x - 7, y - 7, x + 7, y + 7, outline=FG, width=2, tags="trail")
            if btn == 1:
                st["held"] = True
        elif typ == UP:
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=FG, outline="", tags="trail")
            if btn == 1:
                st["held"] = False
        elif typ == WHEEL:
            st["offset"] -= wheel / 120 * SCROLL_STEP
            if p == 0 and self.kind in ("scroll", "scroll_click"):
                self._draw_page(st["offset"])
        x, y = st["pos"]
        if st["box"] is not None and st["held"]:
            c.coords(st["box"], x - BOX / 2, y - BOX / 2, x + BOX / 2, y + BOX / 2)
        c.coords(st["dot"], x - 4, y - 4, x + 4, y + 4)
        c.tag_raise("trail")
        if st["box"] is not None:
            c.tag_raise(st["box"])
        c.tag_raise(st["dot"])

    def _animate(self, paths: list[list[tuple]]) -> None:
        self._new_state(len(paths))
        for p in range(len(paths)):
            self._apply(p, (0, -1, *self.cursor, 0, 0))
        start = time.perf_counter()
        idx = [0] * len(paths)

        def step():
            now_ms = (time.perf_counter() - start) * 1000
            busy = False
            for p, ev in enumerate(paths):
                while idx[p] < len(ev) and ev[idx[p]][0] <= now_ms:
                    self._apply(p, ev[idx[p]])
                    idx[p] += 1
                busy = busy or idx[p] < len(ev)
            if busy:
                self.root.after(5, step)
            else:
                self._finish(self.pstate[0]["pos"])
        step()

    def _play_live(self, ev: list[tuple]) -> None:
        from ...input.sendinput_driver import SendInputDriver
        drv = SendInputDriver()
        ox, oy = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
        self.stop_live = False
        self._new_state(1)
        drv.move(round(self.cursor[0] + ox), round(self.cursor[1] + oy))
        if self.kind == "drag":
            drv.mouse_down("left")  # a drag segment starts with the button already held
        start = time.perf_counter()
        for e in ev:
            while (time.perf_counter() - start) * 1000 < e[0]:
                self.root.update()  # keeps Esc responsive
                if self.stop_live:
                    break
                time.sleep(0.001)
            if self.stop_live:
                self._say("live playback stopped")
                break
            _t, typ, x, y, btn, wheel = e
            if typ == MOVE:
                drv.move(x + ox, y + oy)
            elif typ in (DOWN, UP):
                # clicks land on this demo window itself, never on another app
                (drv.mouse_down if typ == DOWN else drv.mouse_up)("right" if btn == 2 else "left")
            elif typ == WHEEL:
                drv.scroll(0, round(wheel / 120))
            self._apply(0, e)
        if self.kind == "drag" and self.pstate[0]["held"]:
            drv.mouse_up("left")
        self.root.after(50, lambda: self._finish(self.pstate[0]["pos"]))

    def _finish(self, end) -> None:
        if self.kind in POINTER and self.kind != "drag":
            self.cursor = end
        self.playing = False

    # -- drawing -----------------------------------------------------------------------
    def _draw_page(self, offset: float) -> None:
        c = self.canvas
        c.delete("page")
        first = int(offset // ROW_H)
        for i in range(first, first + H // ROW_H + 2):
            y = i * ROW_H - offset
            c.create_rectangle(W * 0.2, y + 30, W * (0.35 + 0.4 * ((i * 37) % 10) / 10), y + 60,
                               fill=ZONE, outline="", tags="page")
        c.create_rectangle(0, BAND_Y - BAND_H / 2, W, BAND_Y + BAND_H / 2, outline=BAND, width=2, tags="page")
        ly = BAND_Y + self.scroll_px - offset
        c.create_line(0, ly, W, ly, fill=LINE, width=4, tags="page")
        if self.kind == "scroll_click":
            r = self.radius
            c.create_oval(self.target[0] - r, ly - r, self.target[0] + r, ly + r, fill=TARGET, outline="", tags="page")
        c.tag_lower("page")

    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        k = self.kind
        tx, ty = self.target
        r = self.radius
        if k in ("scroll", "scroll_click"):
            self._draw_page(0.0)
        elif k == "drag":
            h = r + BOX / 2
            c.create_rectangle(tx - h, ty - h, tx + h, ty + h, fill=ZONE, outline=MUTED, width=2)
            x, y = self.cursor
            c.create_rectangle(x - BOX / 2, y - BOX / 2, x + BOX / 2, y + BOX / 2, fill=TARGET, outline="",
                               tags="startbox")
        elif k == "idle":
            c.create_text(W / 2, H * 0.2, fill=FG, font=("Segoe UI", 16), width=int(W * 0.6), justify="center",
                          text="(the model 'reads' for a few seconds, drifting like a resting hand, "
                               "then clicks Done)")
            c.create_rectangle(tx - 55, ty - 22, tx + 55, ty + 22, fill=BAND, outline="")
            c.create_text(tx, ty, text="Done", fill=FG, font=("Segoe UI", 12))
        else:
            c.create_oval(tx - r, ty - r, tx + r, ty + r, fill=TARGET, outline="")
            label = {"aim_double": "2x", "aim_right": "R"}.get(k, "")
            if label:
                c.create_text(tx, ty, text=label, fill=BG, font=("Segoe UI", max(8, int(min(r, 30) * 0.7)), "bold"))
        x, y = self.cursor
        c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=CURSOR, outline="")
        extra = f"scroll {self.scroll_px:+.0f}px (wheel changes it)" if k in ("scroll", "scroll_click") \
            else f"target radius {r:.0f}px (wheel changes it)"
        c.create_text(12, 12, anchor="nw", fill=MUTED, font=("Segoe UI", 10),
                      text=f"action {self.label}  ·  {extra}  ·  keys 1-7 change action\nmodel: {self.model_path}")

    def _say(self, text: str) -> None:
        self.status.set(text)


def run_demo(model_path: Path) -> None:
    Demo(model_path).run()

"""End-to-end workflow test: navigate, click, type, scroll, pick, drag, submit.

WARNING: ``--mode bot`` drives the REAL mouse and keyboard. Hands off the mouse
while it runs; abort any time with Ctrl+Alt+Q.

    python winval/workflow/run_workflow.py                    # bot, trained model mouse
    python winval/workflow/run_workflow.py --mouse hil        # bot, built-in HIL mouse
    python winval/workflow/run_workflow.py --runs 5
    python winval/workflow/run_workflow.py --mode human       # you do it (baseline)
    python winval/workflow/score_workflow.py                  # compare everything

The workflow (same for bot and human, values change every run):
  1. fresh browser -> Ctrl+L -> type the testbench URL -> Enter
  2. read the task, click "Account registration" (same-document navigation)
  3. click Full name, type it; Tab to Email, type it; click About, type a sentence
  4. scroll down past the terms; open the Country dropdown and pick an option
  5. tick three interest checkboxes; drag the slider, fine-tune with arrow keys
  6. click "Create account" -> the page scores the form and uploads its event log

Logs land in captures/workflow/<label>_<time>.json.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench import Bench, Browser, find_browser, make_task, screen_rect, visible  # noqa: E402
from idle_bank import IdleBank  # noqa: E402
from mice import HilMouse, ModelMouse  # noqa: E402

from humanpc import Bot  # noqa: E402
from humanpc.config import Config  # noqa: E402
from humanpc.exceptions import Aborted  # noqa: E402
from humanpc.hil.precise import precise_sleep  # noqa: E402

DEFAULT_MODEL = ROOT / "data" / "model" / "model.pt"
DEFAULT_OUT = ROOT / "captures" / "workflow"
DEFAULT_TRAINING = ROOT / "data" / "training"


# ---------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------

class Workflow:
    """The scripted task, with a model of *where the hands are*.

    ``hand`` is "mouse" or "keyboard". Switching costs a pause (the hand travels
    between devices). While the hand is on the mouse, every pause (thinking,
    reading) is spent drifting the cursor the way the recordings do; while it is
    on the keyboard the cursor is still, because nothing is touching the mouse.
    """

    def __init__(self, bot: Bot, mouse, bench: Bench, idle: IdleBank | None):
        self.bot, self.mouse, self.bench, self.idle = bot, mouse, bench, idle
        self.task = bench.task
        self.rng = random.Random()
        self.hand = "mouse"
        self.last_click = None
        self.retries: list[str] = []
        self.stats = {"drift_px": 0, "drift_s": 0.0, "hand_switches": 0, "still_s": 0.0}

    # -- hands, pauses, reading ----------------------------------------------------
    def _page_box(self):
        """Where drift may roam: the page's client area, else the screen minus a
        margin (the corner failsafe would otherwise read a wander as an abort)."""
        lay = self.bench.snapshot()
        if lay and lay.get("calibrated"):
            d, (ox, oy) = lay["dpr"], lay["offset"]
            iw, ih = lay["inner"]
            return ((ox + 30) * d, (oy + 30) * d, (iw - 60) * d, (ih - 60) * d)
        try:
            import ctypes
            u = ctypes.windll.user32
            sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        except Exception:
            sw, sh = 1920, 1080
        return (80, 80, sw - 160, sh - 160)

    def pause(self, seconds: float) -> None:
        """Wait ``seconds``: drifting if the hand is on the mouse, still otherwise."""
        if seconds <= 0:
            return
        if self.hand == "mouse" and self.idle is not None:
            self.stats["drift_px"] += self.idle.play(self.bot.driver, seconds, self.rng, box=self._page_box(),
                                                     killswitch=self.bot.killswitch)
            self.stats["drift_s"] += seconds
        else:
            self.stats["still_s"] += seconds
            precise_sleep(seconds)

    def think(self, complexity: str = "medium", *, choices: int | None = None) -> None:
        b = self.bot
        if choices is not None:
            delay = b._timing.decision_delay(choices, b._rng)
        else:
            delay = b._timing.thinking_delay(complexity, b._rng)
        self.pause(delay * b._pace())

    def read(self, text: str, complexity: float = 1.0, *, scan: bool = False) -> None:
        b = self.bot
        delay = b._timing.reading_delay(text, b._rng, complexity, scan=scan) * b._pace()
        self.pause(delay + b._session.maybe_distraction(b._rng))

    def to_keyboard(self) -> None:
        if self.hand == "keyboard":
            return
        self.hand = "keyboard"
        self.stats["hand_switches"] += 1
        self.pause(min(2.0, 0.45 * math.exp(self.rng.gauss(0.35, 0.35))))  # hand travels mouse -> keys

    def to_mouse(self) -> None:
        if self.hand == "mouse":
            return
        self.pause(min(2.0, 0.45 * math.exp(self.rng.gauss(0.25, 0.35))))  # hand travels keys -> mouse
        self.hand = "mouse"
        self.stats["hand_switches"] += 1
        self.pause(self.rng.uniform(0.15, 0.4))  # settling the hand on the mouse jogs it

    def type(self, text: str, *, proofread: bool = True) -> None:
        self.to_keyboard()
        self.bot.type(text)
        if proofread:  # look back over what was typed before moving on
            self.read(text, complexity=0.7, scan=True)

    def press(self, *keys: str) -> None:
        self.to_keyboard()
        self.bot.press(*keys)

    def hotkey(self, *keys: str) -> None:
        self.to_keyboard()
        self.bot.hotkey(*keys)

    # -- page interaction ----------------------------------------------------------
    def rect(self, el: str, lay: dict | None = None):
        lay = lay or self.bench.fresh(0.05)
        r = screen_rect(lay, el)
        if r is None:
            raise RuntimeError(f"element #{el} not on the page (view={lay.get('view')})")
        return r

    def ensure_visible(self, el: str, below: float = 0.0) -> dict:
        """Scroll (wheel) until ``el`` (plus ``below`` css px under it) is inside the viewport."""
        for attempt in range(8):
            lay = self.bench.fresh(0.08 if attempt == 0 else 0.45)  # after a scroll: let it settle
            r = lay["els"].get(el)
            if r is None:
                raise RuntimeError(f"element #{el} not on the page")
            if visible(lay, el) and r[1] + r[3] + below <= lay["inner"][1] - 20:
                return lay
            dy = r[1] + (r[3] + below) / 2 - lay["inner"][1] * 0.42  # css px, + == need to go down
            notches = max(1, min(10, round(abs(dy) / 100)))
            print(f"    scroll for #{el}: need {dy:+.0f}px at scrollY={lay['scrollY']} el_y={r[1]:.0f}")
            self.to_mouse()
            self.mouse.scroll(-notches if dy > 0 else notches, px=dy)
            self.think("low")
        raise RuntimeError(f"could not scroll #{el} into view")

    def click(self, el: str, below: float = 0.0) -> None:
        self.to_mouse()
        r = self.rect(el, self.ensure_visible(el, below))
        self.last_click = (el, r)
        self.mouse.click(r)
        self.last_click = (el, r, self.bot.position())

    def click_check(self, el: str, pred, what: str, tries: int = 3, below: float = 0.0) -> None:
        """Click, then confirm the page reacted; re-click like a person would if it didn't."""
        for n in range(tries):
            self.click(el, below)
            try:
                self.expect(pred, what, timeout=1.5)
                return
            except TimeoutError:
                self.retries.append(el)
                print(f"    ! click on #{el} missed (try {n + 1}); cursor ended at {self.bot.position()}, "
                      f"target {self.last_click[1]}")
                self.think("low")
        raise TimeoutError(f"timed out waiting for {what}")

    def expect(self, pred, what: str, timeout: float = 3.0) -> dict:
        return self.bench.wait(pred, timeout=timeout, what=what)

    def fill(self, el: str, value: str, *, via_tab: bool = False) -> None:
        """Focus a field, glance at the task for its value, type it, proofread it."""
        if via_tab:
            self.press("tab")
        else:
            self.click(el)
        self.expect(lambda l: l["focus"] == el, f"focus on {el}")
        self.read(value, complexity=0.5, scan=True)  # find the value on the task card
        self.type(value)

    def run(self, url: str) -> None:
        t = self.task
        step = lambda s: print(f"  - {s}")  # noqa: E731

        step("navigate: Ctrl+L, type URL, Enter")
        self.think("low")
        self.hotkey("ctrl", "l")
        self.think("low")
        self.type(url.rstrip("/"), proofread=False)
        self.press("enter")
        lay = self.expect(lambda l: l["view"] == "home", "the testbench to load", timeout=20)

        step("read the task, open Account registration")
        self.to_mouse()
        self.mouse.move(self.rect("task-home", lay))  # also calibrates client->screen offset
        self.expect(lambda l: l["calibrated"], "pointer calibration")
        self.read(" ".join(str(v) for v in t.values()), complexity=0.8)
        self.click_check("nav-register", lambda l: l["view"] == "register", "the registration view")

        step("name -> Tab -> email")
        self.think("low")
        self.fill("name", t["name"])
        self.fill("email", t["email"], via_tab=True)

        step("about (long text)")
        self.think("low")
        self.fill("about", t["about"])
        lay = self.expect(lambda l: l["values"]["about"] == t["about"], "the typed text", timeout=5)
        for k in ("name", "email"):
            if lay["values"][k] != t[k]:
                print(f"    ! {k} field reads {lay['values'][k]!r}, expected {t[k]!r}")

        step("scroll down, pick country")
        self.to_mouse()
        self.think("medium")
        opt = "opt-" + t["country"].lower()
        self.click_check("country-btn", lambda l: opt in l["els"], "the dropdown to open",
                         below=320)  # room for the list that opens under it
        self.think(choices=8)
        self.click_check(opt, lambda l: l["values"]["country"] == t["country"], "the country selection")

        step("tick interests")
        self.read(", ".join(t["interests"]), complexity=0.5, scan=True)
        for k in t["interests"]:
            self.think("low")
            self.click_check("int-" + k, lambda l, k=k: k in l["values"]["interests"], f"#{k} to be ticked")
        for k in self.bench.fresh(0.1)["values"]["interests"]:
            if k not in t["interests"]:  # a miss ticked a neighbour: untick it
                print(f"    ! #{k} got ticked by mistake, unticking")
                self.think("low")
                self.click_check("int-" + k, lambda l, k=k: k not in l["values"]["interests"], f"#{k} unticked")
        self.expect(lambda l: sorted(l["values"]["interests"]) == sorted(t["interests"]), "the checkboxes")

        step(f"slider -> {t['slider']}")
        self.think("low")
        self.set_slider(t["slider"])

        step("submit")
        self.to_mouse()
        self.think("medium")  # a last look over the form
        self.click("submit")
        if not self.bench.log_saved.wait(10):
            raise RuntimeError("the page never uploaded its log")

    def set_slider(self, target: int) -> None:
        for _attempt in range(2):
            lay = self.ensure_visible("slider")
            x, y, w, h = self.rect("slider", lay)
            thumb = lay["thumb"] * lay["dpr"]
            val = lay["values"]["slider"]
            span = w - thumb
            thumb_rect = (round(x + span * val / 100), round(y + h / 2 - thumb / 2), round(thumb), round(thumb))
            goal = (x + thumb / 2 + span * target / 100, y + h / 2)
            self.to_mouse()
            self.mouse.drag(thumb_rect, goal)
            lay = self.bench.fresh(0.2)
            diff = target - lay["values"]["slider"]
            if abs(diff) <= 12:
                break
        if diff:
            self.think("low")
            key = "right" if diff > 0 else "left"
            for _ in range(abs(diff)):
                self.press(key)
        self.expect(lambda l: l["values"]["slider"] == target, "the slider value")


# ---------------------------------------------------------------------------

def run_bot(args, rng: random.Random, i: int, idle: IdleBank | None) -> Path | None:
    label = args.label or f"bot-{args.mouse}"
    bench = Bench(make_task(rng, "bot"), label, Path(args.out))
    url = bench.start()
    exe = args.browser_path or find_browser(args.browser)
    from humanpc.input.sendinput_driver import SendInputDriver

    cfg = Config(relative_mouse=False if args.absolute else None, seed=args.seed)
    bot = Bot(persona=args.persona, driver=SendInputDriver(), config=cfg)
    mouse = (ModelMouse(bot, Path(args.model), args.person, args.temperature)
             if args.mouse == "model" else HilMouse(bot))
    browser = Browser(exe)
    print(f"\nrun {i + 1}/{args.runs}  [{label}]  task: {bench.task['name']} / {bench.task['country']} "
          f"/ slider {bench.task['slider']}")
    t0 = time.monotonic()
    try:
        browser.open("about:blank")
        time.sleep(3.0)  # window up and focused
        wf = Workflow(bot, mouse, bench, idle)
        wf.run(url)
        early = getattr(mouse, "early", None)
        st = wf.stats
        print(f"  done in {time.monotonic() - t0:.1f}s, re-clicks: {wf.retries or 'none'}"
              + (f", early presses held back: {early}, model generation {mouse.gen_s:.1f}s total"
                 if early is not None else "")
              + f"\n  idle drift {st['drift_px']}px over {st['drift_s']:.1f}s, still {st['still_s']:.1f}s, "
              f"hand switches {st['hand_switches']} -> {bench.log_path}")
        return bench.log_path
    except Aborted:
        print("  ABORTED by kill-switch")
        raise
    except Exception as e:  # keep going with the next run; the log is simply missing
        print(f"  FAILED after {time.monotonic() - t0:.1f}s: {type(e).__name__}: {e}")
        lay = bench.snapshot() or {}
        print(f"    page: view={lay.get('view')} dpr={lay.get('dpr')} offset={lay.get('offset')} "
              f"calibrated={lay.get('calibrated')} focus={lay.get('focus')!r}")
        print(f"    last click (element, screen rect, cursor after): {getattr(locals().get('wf'), 'last_click', None)}")
        return None
    finally:
        time.sleep(1.0)
        browser.close()
        bench.stop()
        bot.close()


def run_human(args, rng: random.Random) -> Path | None:
    bench = Bench(make_task(rng, "human"), args.label or "human", Path(args.out))
    url = bench.start()
    browser = Browser(args.browser_path or find_browser(args.browser))
    browser.open("about:blank")
    print("\nHUMAN BASELINE")
    print(f"  1. click the browser's address bar (or Ctrl+L) and type:  {url.rstrip('/')}")
    print("  2. follow the task shown on the page, at your normal pace, then click Create account")
    print("  (waiting for the page to upload its log; Ctrl+C to give up)")
    try:
        while not bench.log_saved.wait(0.5):
            if browser.proc and browser.proc.poll() is not None:
                print("  browser closed before submit - nothing saved")
                return None
        print(f"  saved -> {bench.log_path}")
        return bench.log_path
    finally:
        time.sleep(1.0)
        browser.close()
        bench.stop()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("bot", "human"), default="bot")
    ap.add_argument("--mouse", choices=("model", "hil"), default="model",
                    help="model = your trained movement model, hil = built-in engine")
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--person", help="which recorded person the model imitates (default: first)")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--persona", default="default", help="typing/timing persona: default|fast|careful|tired")
    ap.add_argument("--absolute", action="store_true", help="hil mouse: absolute instead of relative injection")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--seed", type=int, help="fixes both the task values and the bot's person")
    ap.add_argument("--browser", choices=("edge", "chrome"), default="edge")
    ap.add_argument("--browser-path")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--training", default=str(DEFAULT_TRAINING),
                    help="recordings dir; the 'read' tasks in it supply idle cursor drift")
    ap.add_argument("--no-idle", action="store_true", help="freeze the cursor during pauses (old behaviour)")
    ap.add_argument("--label", help="log label (default bot-<mouse> / human)")
    ap.add_argument("--countdown", type=int, default=5, help="seconds to take your hands off first")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    if args.mode == "human":
        for _ in range(max(1, args.runs)):
            run_human(args, rng)
        return 0

    if args.mouse == "model" and not Path(args.model).exists():
        print(f"model not found: {args.model}", file=sys.stderr)
        return 2
    print("This drives the REAL mouse and keyboard. Abort: Ctrl+Alt+Q.")
    for s in range(args.countdown, 0, -1):
        print(f"  starting in {s}...", end="\r")
        time.sleep(1)
    idle = None
    if not args.no_idle:
        idle = IdleBank.load(Path(args.training))
        print(f"idle drift bank: {len(idle.phases)} recorded reading phases")
        if not idle.phases:
            idle = None
    ok = 0
    try:
        for i in range(args.runs):
            ok += run_bot(args, rng, i, idle) is not None
    except Aborted:
        return 130
    print(f"\n{ok}/{args.runs} runs completed. Score them: python winval/workflow/score_workflow.py")
    return 0 if ok == args.runs else 1


if __name__ == "__main__":
    sys.exit(main())

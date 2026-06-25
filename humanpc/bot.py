"""The Bot facade: the synchronous, script-facing public API.

Phase 0 implements raw-coordinate actions with a simple smoothstep-eased, stepped
move. This is intentionally a placeholder: Phase 1 swaps the movement/timing here
for the Human Interaction Layer (Bezier paths, Fitts-law velocity, typing rhythm),
and Phase 2 adds string/image *targets* on top of the coordinate primitives below.

Every action funnels through ``_begin`` (safety precheck) and ``_end`` (audit), so
the kill-switch, action cap, and audit trail apply uniformly.
"""

from __future__ import annotations

import random
import time
from contextlib import contextmanager

from .config import Config, Persona, get_persona
from .exceptions import TargetNotFound, VerificationError
from .geometry import Point
from .hil import (
    BehaviorState,
    BehaviorTracker,
    HumanTimingManager,
    HumanTypingEngine,
    MouseTrajectoryEngine,
    SessionState,
    plan_scroll,
)
from .hil.idle import IdleDriftLoop
from .hil.individual import ActionTempo, sample_individual
from .hil.precise import begin_high_resolution, end_high_resolution, precise_sleep
from .input import NullDriver, default_driver
from .perception.dpi import set_dpi_awareness
from .safety import AuditLog, KillSwitch, SafetyGuard
from .system import Clipboard, ShellResult
from .system import run as shell_run
from .system.apps import AppProcess, launch
from .targeting import Match, Resolver
from .windows import Window, WindowManager

# Per-emit relative-mode delta bounds (px). _REL_STEP_PX caps each chunk just
# under the pointer-acceleration ("Enhance pointer precision") threshold so deltas
# pass through ~1:1 instead of being amplified. _REL_MIN_PX is the smallest delta
# the curve can still express — below it a relative move rounds to 0 px, so we
# defer rather than stutter in place.
_REL_STEP_PX = 6
_REL_MIN_PX = 2

# Which behavioural state each action implies (for bot.behavior observability).
_ACTION_STATES = {
    "move_to": BehaviorState.MOVING,
    "drag": BehaviorState.MOVING,
    "click": BehaviorState.CLICKING,
    "double_click": BehaviorState.CLICKING,
    "right_click": BehaviorState.CLICKING,
    "type": BehaviorState.TYPING,
    "press": BehaviorState.TYPING,
    "hotkey": BehaviorState.TYPING,
    "scroll": BehaviorState.SCROLLING,
    "think": BehaviorState.THINKING,
    "read": BehaviorState.READING,
    "read_text": BehaviorState.READING,
}


class Bot:
    def __init__(
        self,
        persona: str = "default",
        *,
        dry_run: bool = False,
        config: Config | None = None,
        driver=None,
        audit: AuditLog | None = None,
        killswitch: KillSwitch | None = None,
        resolver: Resolver | None = None,
        windows: WindowManager | None = None,
        clipboard: Clipboard | None = None,
        idle: bool = False,
        arm: bool = True,
        profile=None,
    ):
        self.config = config or Config()
        if persona:
            self.config.persona = persona
        self.dry_run = dry_run or self.config.dry_run

        self._persona: Persona = get_persona(self.config.persona)
        self._rng = random.Random(self.config.seed)
        self.dpi_mode = set_dpi_awareness()

        self.audit = audit if audit is not None else AuditLog(
            path=self.config.audit_path, enabled=self.config.audit_enabled
        )
        self.killswitch = killswitch if killswitch is not None else KillSwitch(
            hotkey=self.config.kill_hotkey
        )
        self.guard = SafetyGuard(self.killswitch, max_actions=self.config.max_actions)

        # Tier 4 — a stable per-instance behavioural fingerprint. Sampled from a
        # dedicated rng so it never perturbs the action rng stream. With a seed
        # the person is reproducible; with no seed each run is a different person.
        self._profile_rng = random.Random(
            None if self.config.seed is None else self.config.seed + 7919
        )
        self.individual = profile
        if self.individual is None and self.config.individuality:
            self.individual = sample_individual(self._profile_rng)
        self._tempo = ActionTempo()

        # Human Interaction Layer engines (parameterised by the individual).
        if self.individual is not None:
            self._mouse = self.individual.build_mouse_engine()
            self._typing = self.individual.build_typing_engine(
                errors_enabled=self.config.typing_errors,
                always_correct=self.config.always_correct_typing,
            )
            self._move_speed = self.individual.move_speed
        else:
            self._mouse = MouseTrajectoryEngine()
            self._typing = HumanTypingEngine(
                errors_enabled=self.config.typing_errors,
                always_correct=self.config.always_correct_typing,
            )
            self._move_speed = 1.0
        if self.config.relative_mouse:
            # The settle phase's sub-pixel micro-moves don't survive relative
            # emission (acceleration swallows them) and read as an end-of-move
            # twitch, so skip them in relative mode.
            self._mouse.settle_probability = 0.0
        self._timing = HumanTimingManager()
        self._session = SessionState()
        self._resolver = resolver  # default built lazily (cheap; finders load on use)
        self._windows = windows    # default built lazily (Win32 backend loads on use)
        self._clipboard = clipboard
        self._screen = None        # perception.Screen, lazy

        self.behavior = BehaviorTracker()
        self._last_action = time.monotonic()
        self._idle_loop: IdleDriftLoop | None = None

        # Dry-run never touches the OS. Real driver is created lazily on first use.
        self._driver = NullDriver() if self.dry_run else driver
        self._precision = False

        if arm and not self.dry_run:
            self.killswitch.start()
            if self.config.precision_timing:
                self._precision = begin_high_resolution()
        if idle:
            self.start_idle()

    # --- properties -------------------------------------------------------
    @property
    def driver(self):
        if self._driver is None:
            self._driver = default_driver(failsafe=self.config.failsafe)
        return self._driver

    @property
    def current_persona(self) -> Persona:
        return self._persona

    @property
    def state(self) -> BehaviorState:
        return self.behavior.state

    @property
    def resolver(self) -> Resolver:
        if self._resolver is None:
            self._resolver = Resolver()
        return self._resolver

    @property
    def windows(self) -> WindowManager:
        if self._windows is None:
            self._windows = WindowManager()
        return self._windows

    @property
    def clipboard(self) -> Clipboard:
        if self._clipboard is None:
            self._clipboard = Clipboard()
        return self._clipboard

    @property
    def screen(self):
        if self._screen is None:
            from .perception import Screen
            self._screen = Screen()
        return self._screen

    def position(self) -> tuple[int, int]:
        return self.driver.position()

    def _resolve(self, target) -> Match:
        match = self.resolver.resolve(target)
        if match is None:
            raise TargetNotFound(f"could not locate target: {target!r}")
        return match

    # --- internals --------------------------------------------------------
    def _begin(self, action: str) -> None:
        self.guard.precheck(action)
        self._tempo.advance(self._rng)  # AR(1): stay in fast/slow streaks
        state = _ACTION_STATES.get(action)
        if state is not None:
            self.behavior.observe(state)

    def _pace(self) -> float:
        """Combined timing multiplier: session warm-up/fatigue * AR(1) tempo."""
        return self._session.pace_multiplier() * self._tempo.value

    def _end(self, action: str, **fields) -> None:
        self.audit.record(
            action, persona=self._persona.name, dry_run=self.dry_run, **fields
        )
        self._last_action = time.monotonic()
        self._session.tick()

    def _sleep(self, seconds: float) -> None:
        if self.dry_run or seconds <= 0:
            return
        if self.config.precision_timing:
            precise_sleep(seconds)
        else:
            time.sleep(seconds)

    # --- personas ---------------------------------------------------------
    @contextmanager
    def persona(self, name: str):
        """Temporarily switch persona: ``with bot.persona("careful"): ...``"""
        previous = self._persona
        self._persona = get_persona(name)
        try:
            yield self
        finally:
            self._persona = previous

    # --- mouse ------------------------------------------------------------
    def move_to(self, target, *, target_size: tuple[int, int] | None = None) -> "Bot":
        match = self._resolve(target)
        point = match.center
        size = target_size or match.size
        self._begin("move_to")
        start = Point(*self.position())
        plan = self._mouse.plan(
            start,
            point,
            rng=self._rng,
            target_size=size,
            speed_multiplier=self._persona.speed_multiplier * self._move_speed * self._tempo.value,
        )
        self._run_plan(plan, point)
        self._end("move_to", x=round(point.x), y=round(point.y), via=match.method)
        return self

    def _run_plan(self, plan, target) -> None:
        """Execute a planned trajectory step-by-step against the driver.

        Absolute mode: one positioned move per step, then the step's dwell.
        Relative mode: glide each step (see ``_glide_relative``), then snap the
        final residual the OS acceleration curve can't express relatively.
        """
        relative = self.config.relative_mouse
        next_micro = self._rng.randint(8, 15) if relative else None
        n = len(plan)
        for idx, step in enumerate(plan):
            self.killswitch.check()
            if relative:
                self._glide_relative(step.point, step.dt)
                # Sparse visually-guided micro-corrections: closed-loop gliding is
                # otherwise too smooth (EPP swallows the sub-2px jitter that gives
                # absolute mode its direction-changes), so inject a few discrete
                # lateral wobbles big enough to survive acceleration.
                if idx >= next_micro and idx < n - 4:
                    self._relative_microcorrect(step.dt)
                    next_micro = idx + self._rng.randint(8, 15)
            else:
                px, py = step.point.as_int()
                self.driver.move(px, py)
                self._sleep(step.dt)
        if relative:
            self._correct_cursor(target)

    def _relative_microcorrect(self, dt: float) -> None:
        """A tiny lateral excursion-and-return — a corrective sub-movement.

        Net displacement ~0 (closed-loop gliding + the final snap absorb any
        acceleration residue), but it adds the direction changes / path crossings a
        mouse-dynamics detector expects, sized above the EPP floor so it survives.
        """
        w = self._rng.choice((-1, 1)) * self._rng.randint(_REL_MIN_PX + 1, 5)
        if self._rng.random() < 0.5:
            dx, dy = w, 0
        else:
            dx, dy = 0, w
        self.driver.move_relative(dx, dy)
        self._sleep(min(0.02, max(0.004, dt * 0.5)))
        self.driver.move_relative(-dx, -dy)

    def _glide_relative(self, point, dt: float) -> None:
        """Glide toward ``point`` with relative deltas, smoothly, over ``dt``.

        Three things keep relative motion from looking robotic OR glitchy:
          * **closed-loop** — aim from the cursor's ACTUAL position so
            pointer-acceleration error can't accumulate and fling the cursor off;
          * **small chunks** (<=``_REL_STEP_PX``) — each delta stays in the OS
            ballistics curve's ~1:1 region instead of being amplified;
          * **time-spread** — the chunks' sleeps add up to ``dt`` so the cursor
            moves continuously in time, instead of bursting all the motion then
            freezing for the step (which reads as a stutter while gliding).
        Deltas the curve can't express relatively (<``_REL_MIN_PX`` — it rounds
        them to 0 px) are deferred to the next step / the final snap, so the cursor
        never creeps in sub-pixel stutters near the target.
        """
        tx, ty = point.as_int()
        cx, cy = self.driver.position()
        dx, dy = tx - cx, ty - cy
        if max(abs(dx), abs(dy)) < _REL_MIN_PX:
            self._sleep(dt)
            return
        n = (max(abs(dx), abs(dy)) + _REL_STEP_PX - 1) // _REL_STEP_PX  # ceil
        slice_dt = dt / n
        ex = ey = 0
        for i in range(1, n + 1):
            tx_i, ty_i = round(dx * i / n), round(dy * i / n)
            sx, sy = tx_i - ex, ty_i - ey
            if sx or sy:
                self.driver.move_relative(sx, sy)
                ex, ey = tx_i, ty_i
            self._sleep(slice_dt)

    def _correct_cursor(self, target) -> None:
        """Land exactly on target after a relative glide.

        Closed-loop gliding already leaves the cursor within a few px, and pointer
        acceleration can't express the final 1-2 px as a relative delta (it scales
        them toward 0 px), so finish with one clean absolute snap rather than
        creeping in with sub-pixel relative nudges — that creep is what read as an
        end-of-move 'glitch' when the cursor stopped.
        """
        tx, ty = target.as_int()
        if self.driver.position() != (tx, ty):
            self.driver.move(tx, ty)

    def click(self, target=None, *, button: str = "left", clicks: int = 1) -> "Bot":
        if target is not None:
            self.move_to(target)
        self._begin("click")
        # Natural hesitation: humans don't fire the instant the cursor lands —
        # a brief pause precedes committing the press.
        self._sleep(self._rng.uniform(0.03, 0.19) * self._pace())
        for n in range(clicks):
            self.killswitch.check()
            self.driver.mouse_down(button)
            self._sleep(self._rng.uniform(*self._persona.click_dwell))
            self.driver.mouse_up(button)
            if n < clicks - 1:
                self._sleep(self._rng.uniform(0.08, 0.18))
        self._end("click", button=button, clicks=clicks)
        return self

    def double_click(self, target=None, *, button: str = "left") -> "Bot":
        return self.click(target, button=button, clicks=2)

    def right_click(self, target=None) -> "Bot":
        return self.click(target, button="right", clicks=1)

    def drag(self, to, *, frm=None, button: str = "left") -> "Bot":
        """Press at the source, move to ``to`` with the button held, release.

        ``frm`` (optional) is moved to first; otherwise the drag starts wherever
        the cursor currently is. Both accept text / image / coordinate targets.
        """
        if frm is not None:
            self.move_to(frm)
        match = self._resolve(to)
        point = match.center
        self._begin("drag")
        start = Point(*self.position())
        self.driver.mouse_down(button)
        self._sleep(self._rng.uniform(0.05, 0.12))  # grab before moving
        plan = self._mouse.plan(
            start,
            point,
            rng=self._rng,
            target_size=match.size,
            speed_multiplier=self._persona.speed_multiplier * self._move_speed * self._tempo.value,
        )
        self._run_plan(plan, point)
        self._sleep(self._rng.uniform(0.05, 0.12))  # settle before releasing
        self.driver.mouse_up(button)
        self._end("drag", x=round(point.x), y=round(point.y), button=button, via=match.method)
        return self

    def scroll(self, amount: int, *, at=None) -> "Bot":
        if at is not None:
            self.move_to(at)
        self._begin("scroll")
        for delta, dt in plan_scroll(amount, self._rng):
            self.killswitch.check()
            if delta:
                self.driver.scroll(0, delta)
            self._sleep(dt)
        self._end("scroll", amount=int(amount))
        return self

    # --- keyboard ---------------------------------------------------------
    def type(self, text: str) -> "Bot":
        self._begin("type")
        if self.individual is not None:
            base_wpm = max(20.0, self.individual.base_wpm * (self._persona.type_cps / 6.0))
        else:
            base_wpm = max(20.0, self._persona.type_cps * 12)  # cps -> wpm (~5 chars/word)
        for event in self._typing.plan(text, self._rng, base_wpm=base_wpm, session_fatigue=self._pace()):
            self.killswitch.check()
            self._sleep(event.delay)
            # Held modifiers (e.g. Shift for a capital) press first and overlap
            # the keystroke, then release after it — real modifier dynamics.
            mods = getattr(event, "modifiers", ())
            for m in mods:
                self.driver.key_down(m)
                self._sleep(self._rng.uniform(0.01, 0.03))
            # Down -> hold(dwell) -> up so the keystroke has a realistic key-hold
            # time (a primary keystroke-dynamics signal), instead of an atomic
            # zero-dwell emit. Drivers without separable injection fall back
            # gracefully (see InputDriver.char_down/char_up).
            if event.kind == "char":
                self.driver.char_down(event.value)
                self._sleep(event.dwell)
                self.driver.char_up(event.value)
            else:
                self.driver.key_down(event.value)
                self._sleep(event.dwell)
                self.driver.key_up(event.value)
            for m in reversed(mods):
                self._sleep(self._rng.uniform(0.005, 0.02))
                self.driver.key_up(m)
        self._end("type", length=len(text))
        return self

    def press(self, *keys: str) -> "Bot":
        for key in keys:
            self._begin("press")
            self.killswitch.check()
            self.driver.key_down(key)
            self._sleep(self._rng.uniform(0.03, 0.09))
            self.driver.key_up(key)
            self._end("press", key=key)
            self._sleep(self._rng.uniform(0.05, 0.12))
        return self

    def hotkey(self, *keys: str) -> "Bot":
        """Chord: press keys in order, release in reverse (e.g. ctrl+c)."""
        self._begin("hotkey")
        for key in keys:
            self.driver.key_down(key)
            self._sleep(self._rng.uniform(0.02, 0.06))
        self._sleep(self._rng.uniform(0.03, 0.08))
        for key in reversed(keys):
            self.driver.key_up(key)
        self._end("hotkey", keys=list(keys))
        return self

    # --- deliberation -----------------------------------------------------
    def think(self, complexity: str = "medium", *, choices: int | None = None) -> "Bot":
        """Pause as if deciding. complexity: low | medium | high | very_high.

        Pass ``choices`` (number of on-screen options) to use Hick-Hyman decision
        timing instead of the coarse complexity bucket.
        """
        self._begin("think")
        if choices is not None:
            delay = self._timing.decision_delay(choices, self._rng)
        else:
            delay = self._timing.thinking_delay(complexity, self._rng)
        delay = delay * self._pace() + self._session.maybe_distraction(self._rng)
        self._sleep(delay)
        self._end("think", complexity=complexity, choices=choices, delay=round(delay, 4))
        return self

    def read(self, content, *, complexity: float = 1.0, scan: bool = False) -> "Bot":
        """Pause as if reading (``scan=True`` for skimming a familiar UI).

        ``content`` may be text or a character count.
        """
        self._begin("read")
        delay = self._timing.reading_delay(content, self._rng, complexity, scan=scan)
        delay = delay * self._pace() + self._session.maybe_distraction(self._rng)
        self._sleep(delay)
        chars = content if isinstance(content, int) else len(str(content))
        self._end("read", chars=chars, delay=round(delay, 4))
        return self

    # --- verification -----------------------------------------------------
    def verify(self, check, *, attempts: int = 3, interval: float = 0.25, retry=None) -> bool:
        """Confirm an action took effect: poll ``check()`` until it is truthy.

        Optionally run ``retry()`` (e.g. re-click) between attempts. Returns the
        boolean outcome — humans don't blindly assume a click landed; they look.
        """
        attempts = max(1, attempts)
        for i in range(attempts):
            try:
                if check():
                    return True
            except (TargetNotFound, TypeError):
                pass
            if i < attempts - 1:
                if retry is not None:
                    retry()
                if not self.dry_run and interval > 0:
                    time.sleep(interval)
        return False

    def ensure(self, check, *, attempts: int = 3, interval: float = 0.25, retry=None, message=None) -> "Bot":
        """Like :meth:`verify`, but raise ``VerificationError`` if never satisfied."""
        if not self.verify(check, attempts=attempts, interval=interval, retry=retry):
            raise VerificationError(message or "action could not be verified")
        return self

    def click_until(self, target, until, *, attempts: int = 3, interval: float = 0.3, button: str = "left") -> "Bot":
        """Click ``target`` and re-click until ``until()`` holds (or attempts run out).

        Action verification for the common case: a click that must produce a UI
        change (a dialog opens, a state toggles). Raises if it never takes effect.
        """
        self.click(target, button=button)
        if not self.verify(until, attempts=attempts, interval=interval,
                           retry=lambda: self.click(target, button=button)):
            raise VerificationError(f"click on {target!r} did not produce the expected result")
        return self

    # --- finding ----------------------------------------------------------
    def find(self, target) -> Match | None:
        """Locate a target without acting on it. Returns None if not found."""
        return self.resolver.resolve(target)

    def find_all(self, target) -> list[Match]:
        """Locate every instance of a target. Returns [] if none found."""
        return self.resolver.resolve_all(target)

    def screenshot(self, path=None, *, region=None):
        """Capture the screen. Saves to ``path`` if given, else returns a PIL.Image."""
        self._begin("screenshot")
        if path:
            self.screen.save(path, region)
            result = path
        else:
            result = self.screen.capture(region)
        self._end("screenshot", path=path)
        return result

    def read_text(self, *, region=None) -> str:
        """OCR the screen (or a region) and return the recognised text."""
        self._begin("read_text")
        text = self.resolver.ocr().text(region=region)
        self._end("read_text", chars=len(text))
        return text

    def exists(self, target) -> bool:
        try:
            return self.find(target) is not None
        except (TargetNotFound, TypeError):
            return False

    def wait_for(self, target, *, timeout: float = 10.0, interval: float = 0.25) -> Match:
        """Poll until ``target`` appears, returning its Match (or raising)."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                match = self.find(target)
            except TargetNotFound:
                match = None
            if match is not None:
                self.audit.record("wait_for", found=True, via=match.method)
                return match
            if time.monotonic() >= deadline:
                self.audit.record("wait_for", found=False)
                raise TargetNotFound(f"{target!r} did not appear within {timeout}s")
            time.sleep(interval)

    # --- system & windows -------------------------------------------------
    def run(self, command, **kwargs) -> ShellResult:
        """Run a shell command. Skipped (returns a sentinel) in dry-run."""
        self._begin("run")
        if self.dry_run:
            self._end("run", command=str(command), skipped=True)
            return ShellResult(command, 0, "", "[dry-run] not executed")
        result = shell_run(command, **kwargs)
        self._end("run", returncode=result.returncode)
        return result

    def open_app(self, target, args=(), *, wait=None, timeout: float = 15.0, **kwargs) -> AppProcess:
        """Launch an application. With ``wait`` (a window title), block until it appears."""
        self._begin("open_app")
        if self.dry_run:
            self._end("open_app", target=str(target), skipped=True)
            return AppProcess(pid=-1)
        proc = launch(target, args, **kwargs)
        self._end("open_app", target=str(target), pid=proc.pid)
        if wait:
            self.wait_for_window(wait, timeout=timeout)
        return proc

    def list_windows(self, **kwargs) -> list[Window]:
        return self.windows.list(**kwargs)

    def find_window(self, title, **kwargs) -> Window | None:
        return self.windows.find(title, **kwargs)

    def active_window(self) -> Window | None:
        return self.windows.active()

    def focus(self, target) -> Window:
        """Bring a window to the foreground (by title or Window)."""
        win = target if isinstance(target, Window) else self.find_window(target)
        if win is None:
            raise TargetNotFound(f"no window matching {target!r}")
        self._begin("focus")
        if not self.dry_run:
            win.focus()
        self._end("focus", title=win.title)
        return win

    def wait_for_window(self, title, *, timeout: float = 15.0, interval: float = 0.3) -> Window:
        deadline = time.monotonic() + timeout
        while True:
            win = self.find_window(title)
            if win is not None:
                return win
            if time.monotonic() >= deadline:
                raise TargetNotFound(f"no window titled {title!r} within {timeout}s")
            time.sleep(interval)

    # --- idle drift -------------------------------------------------------
    def _idle_seconds(self) -> float:
        return time.monotonic() - self._last_action

    def start_idle(self, **kwargs) -> "Bot":
        """Start background idle mouse drift (no-op in dry-run)."""
        if self.dry_run or self._idle_loop is not None:
            return self
        self._idle_loop = IdleDriftLoop(
            self.driver, self._idle_seconds, random.Random(), **kwargs
        )
        self._idle_loop.start()
        return self

    def stop_idle(self) -> "Bot":
        if self._idle_loop is not None:
            self._idle_loop.stop()
            self._idle_loop = None
        return self

    # --- lifecycle --------------------------------------------------------
    def close(self) -> "Bot":
        """Release OS resources: stop idle drift, kill-switch, and timer tick."""
        self.stop_idle()
        if getattr(self, "_precision", False):
            end_high_resolution()
            self._precision = False
        try:
            self.killswitch.stop()
        except Exception:
            pass
        return self

    def __enter__(self) -> "Bot":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

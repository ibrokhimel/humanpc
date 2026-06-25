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
from .exceptions import TargetNotFound
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
from .hil.precise import begin_high_resolution, end_high_resolution, precise_sleep
from .input import NullDriver, default_driver
from .perception.dpi import set_dpi_awareness
from .safety import AuditLog, KillSwitch, SafetyGuard
from .system import Clipboard, ShellResult
from .system import run as shell_run
from .system.apps import AppProcess, launch
from .targeting import Match, Resolver
from .windows import Window, WindowManager

# Which behavioural state each action implies (for bot.behavior observability).
_ACTION_STATES = {
    "move_to": BehaviorState.MOVING,
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

        # Human Interaction Layer engines (pure planners; cheap to construct).
        self._mouse = MouseTrajectoryEngine()
        self._typing = HumanTypingEngine(
            errors_enabled=self.config.typing_errors,
            always_correct=self.config.always_correct_typing,
        )
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
        state = _ACTION_STATES.get(action)
        if state is not None:
            self.behavior.observe(state)

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
            speed_multiplier=self._persona.speed_multiplier,
        )
        cur = start.as_int()
        for step in plan:
            self.killswitch.check()
            cur = self._emit_move(cur, step.point)
            self._sleep(step.dt)
        if self.config.relative_mouse:
            self._correct_cursor(point)
        self._end("move_to", x=round(point.x), y=round(point.y), via=match.method)
        return self

    def _emit_move(self, cur: tuple[int, int], point) -> tuple[int, int]:
        """Emit one move step (absolute by default, relative if configured)."""
        px, py = point.as_int()
        if self.config.relative_mouse:
            dx, dy = px - cur[0], py - cur[1]
            if dx or dy:
                self.driver.move_relative(dx, dy)
        else:
            self.driver.move(px, py)
        return (px, py)

    def _correct_cursor(self, target) -> None:
        """After relative moves, nudge out any pointer-acceleration drift."""
        tx, ty = target.as_int()
        cx, cy = self.driver.position()
        if (cx, cy) != (tx, ty):
            self.driver.move_relative(tx - cx, ty - cy)

    def click(self, target=None, *, button: str = "left", clicks: int = 1) -> "Bot":
        if target is not None:
            self.move_to(target)
        self._begin("click")
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
        base_wpm = max(20.0, self._persona.type_cps * 12)  # cps -> wpm (~5 chars/word)
        fatigue = self._session.pace_multiplier()
        for event in self._typing.plan(text, self._rng, base_wpm=base_wpm, session_fatigue=fatigue):
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
        delay = delay * self._session.pace_multiplier() + self._session.maybe_distraction(self._rng)
        self._sleep(delay)
        self._end("think", complexity=complexity, choices=choices, delay=round(delay, 4))
        return self

    def read(self, content, *, complexity: float = 1.0, scan: bool = False) -> "Bot":
        """Pause as if reading (``scan=True`` for skimming a familiar UI).

        ``content`` may be text or a character count.
        """
        self._begin("read")
        delay = self._timing.reading_delay(content, self._rng, complexity, scan=scan)
        delay = delay * self._session.pace_multiplier() + self._session.maybe_distraction(self._rng)
        self._sleep(delay)
        chars = content if isinstance(content, int) else len(str(content))
        self._end("read", chars=chars, delay=round(delay, 4))
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

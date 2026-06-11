"""Emergency stop.

Two independent abort paths:
  1. A global panic hotkey (default Ctrl+Alt+Q) registered via the optional
     ``keyboard`` package. Works even while another window has focus.
  2. pyautogui's built-in slam-to-corner failsafe (configured by the input
     driver), which raises mid-movement if the cursor is thrown to a screen
     corner.

``check()`` is called before and during every action; when an abort is latched it
raises :class:`humanpc.exceptions.Aborted`. If ``keyboard`` is not installed the
hotkey is simply unavailable and we fall back to the corner failsafe.
"""

from __future__ import annotations

import logging
import threading

from ..exceptions import Aborted

_log = logging.getLogger("humanpc.killswitch")


class KillSwitch:
    def __init__(self, hotkey: str | None = "ctrl+alt+q"):
        self.hotkey = hotkey
        self._abort = threading.Event()
        self._handle = None
        self._backend = None

    # --- arming -----------------------------------------------------------
    def start(self) -> bool:
        """Register the global hotkey. Returns True if it was installed."""
        if self.hotkey is None or self._handle is not None:
            return False
        try:
            import keyboard
        except Exception:
            _log.warning(
                "global kill-hotkey unavailable (pip install keyboard); "
                "relying on the corner failsafe only"
            )
            return False
        try:
            self._handle = keyboard.add_hotkey(self.hotkey, self.request_abort)
            self._backend = keyboard
            _log.info("kill-switch armed on %s", self.hotkey)
            return True
        except Exception as exc:  # registration can fail without admin rights
            _log.warning("could not register kill-hotkey %s: %s", self.hotkey, exc)
            return False

    def stop(self) -> None:
        if self._handle is not None and self._backend is not None:
            try:
                self._backend.remove_hotkey(self._handle)
            except Exception:
                pass
        self._handle = None

    # --- signalling -------------------------------------------------------
    def request_abort(self) -> None:
        self._abort.set()
        _log.warning("kill-switch triggered")

    @property
    def aborted(self) -> bool:
        return self._abort.is_set()

    def check(self) -> None:
        if self._abort.is_set():
            raise Aborted("kill-switch triggered")

    def reset(self) -> None:
        self._abort.clear()

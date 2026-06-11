"""UI Automation finding via pywinauto (lazy-loaded).

This is the *primary* text finder: it locates native controls by Name / type /
AutomationId and returns their screen rectangle. We deliberately return only the
rectangle (and keep the element as ``handle`` for reference) — the Bot still moves
and clicks like a human rather than calling ``Invoke()``, so the human-likeness is
preserved.

Requires a live Windows desktop, so this is exercised by integration tests rather
than headless unit tests.
"""

from __future__ import annotations

from ..exceptions import DriverError
from ..geometry import Rect
from .types import Match


class UIAFinder:
    def __init__(self):
        self._desktop = None

    def _backend(self):
        try:
            from pywinauto import Desktop
        except Exception as exc:
            raise DriverError("UIA needs pywinauto: pip install humanpc[uia]") from exc
        if self._desktop is None:
            self._desktop = Desktop(backend="uia")
        return self._desktop

    def _roots(self, desktop, window):
        if window:
            try:
                return [desktop.window(title_re=window)]
            except Exception:
                return []
        try:
            return list(desktop.windows())
        except Exception:
            return []

    def find(
        self,
        *,
        name=None,
        control_type=None,
        automation_id=None,
        window=None,
        index=0,
        region=None,
    ) -> Match | None:
        filt = {}
        if name:
            filt["title"] = name
        if control_type:
            filt["control_type"] = control_type
        if automation_id:
            filt["auto_id"] = automation_id
        if not filt:
            return None

        desktop = self._backend()
        matches = []
        for root in self._roots(desktop, window):
            try:
                matches.extend(root.descendants(**filt))
            except Exception:
                continue
        if not matches:
            return None

        element = matches[min(index, len(matches) - 1)]
        try:
            r = element.rectangle()
            bbox = Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)
        except Exception:
            return None

        if region is not None and not _intersects(bbox, region):
            return None
        return Match(bbox, 1.0, "uia", text=name, handle=element)


def _intersects(a: Rect, b: Rect) -> bool:
    return not (a.right < b.x or a.x > b.right or a.bottom < b.y or a.y > b.bottom)

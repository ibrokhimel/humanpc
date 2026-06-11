"""Resolver — dispatches a target to the right finder and returns a ``Match``.

Order for text targets: UIA first (robust, pixel-free), OCR as fallback. Coordinate
and region targets resolve locally with no dependencies. Finders are built lazily
and a missing backend (``DriverError``) is skipped rather than fatal, so text still
falls back from UIA to OCR when pywinauto isn't installed.
"""

from __future__ import annotations

from ..exceptions import DriverError
from ..geometry import Point, Rect
from .types import Image, Locator, Match


class Resolver:
    def __init__(
        self,
        *,
        screen=None,
        uia=None,
        ocr=None,
        template=None,
        prefer: tuple[str, ...] = ("uia", "ocr"),
        uia_enabled: bool = True,
        ocr_enabled: bool = True,
    ):
        self.screen = screen
        self._uia = uia
        self._ocr = ocr
        self._template = template
        self.prefer = prefer
        self.uia_enabled = uia_enabled
        self.ocr_enabled = ocr_enabled

    # --- lazy finders -----------------------------------------------------
    def uia(self):
        if self._uia is None:
            from .accessibility import UIAFinder
            self._uia = UIAFinder()
        return self._uia

    def ocr(self):
        if self._ocr is None:
            from .ocr import OCRFinder
            self._ocr = OCRFinder(screen=self.screen)
        return self._ocr

    def template(self):
        if self._template is None:
            from .template import TemplateFinder
            self._template = TemplateFinder(screen=self.screen)
        return self._template

    # --- dispatch ---------------------------------------------------------
    def resolve(self, target, *, region: Rect | None = None) -> Match | None:
        if isinstance(target, Match):
            return target
        if isinstance(target, Image):
            try:
                return self.template().find(target, region=region)
            except DriverError:
                return None
        if isinstance(target, Locator):
            return self._resolve_locator(target, region)
        if isinstance(target, Rect):  # Region is an alias of Rect
            return Match.from_rect(target)
        if isinstance(target, Point):
            return Match.from_point(target)
        if isinstance(target, (tuple, list)):
            if len(target) == 2:
                return Match.from_point(target)
            if len(target) == 4:
                return Match.from_rect(Rect(*target))
            raise TypeError(f"coordinate target must be (x, y) or (x, y, w, h); got {target!r}")
        if isinstance(target, str):
            return self._resolve_text(target, region)
        raise TypeError(f"unsupported target type: {type(target).__name__}")

    def resolve_all(self, target, *, region: Rect | None = None) -> list[Match]:
        """Like ``resolve`` but returns every match (used by ``find_all``)."""
        if isinstance(target, Match):
            return [target]
        if isinstance(target, Image):
            try:
                return self.template().find_all(target, region=region)
            except DriverError:
                return []
        if isinstance(target, Locator):
            return self._resolve_all_text(target.text, region) if target.text else self._uia_all(target, region)
        if isinstance(target, Rect):
            return [Match.from_rect(target)]
        if isinstance(target, Point):
            return [Match.from_point(target)]
        if isinstance(target, (tuple, list)):
            if len(target) == 2:
                return [Match.from_point(target)]
            if len(target) == 4:
                return [Match.from_rect(Rect(*target))]
            raise TypeError(f"coordinate target must be (x, y) or (x, y, w, h); got {target!r}")
        if isinstance(target, str):
            return self._resolve_all_text(target, region)
        raise TypeError(f"unsupported target type: {type(target).__name__}")

    def _resolve_all_text(self, text: str, region) -> list[Match]:
        results: list[Match] = []
        if self.uia_enabled:
            try:
                results = self.uia().find_all(name=text, region=region)
            except DriverError:
                results = []
        if not results and self.ocr_enabled:
            try:
                results = self.ocr().find_all(text, region=region)
            except DriverError:
                results = []
        return results

    def _uia_all(self, loc: Locator, region) -> list[Match]:
        try:
            return self.uia().find_all(
                name=loc.name, control_type=loc.control_type, window=loc.window, region=region
            )
        except DriverError:
            return []

    def _resolve_text(self, text: str, region) -> Match | None:
        for method in self.prefer:
            try:
                if method == "uia" and self.uia_enabled:
                    m = self.uia().find(name=text, region=region)
                    if m:
                        return m
                elif method == "ocr" and self.ocr_enabled:
                    m = self.ocr().find(text, region=region)
                    if m:
                        return m
            except DriverError:
                continue  # backend missing -> try the next method
        return None

    def _resolve_locator(self, loc: Locator, region) -> Match | None:
        region = region if region is not None else loc.region
        if (loc.name or loc.control_type or loc.automation_id or loc.window) and self.uia_enabled:
            try:
                m = self.uia().find(
                    name=loc.name,
                    control_type=loc.control_type,
                    automation_id=loc.automation_id,
                    window=loc.window,
                    index=loc.index,
                    region=region,
                )
                if m:
                    return m
            except DriverError:
                pass
        if loc.text:
            return self._resolve_text(loc.text, region)
        return None

"""Clipboard access (text + image).

The ``Clipboard`` wrapper is backend-agnostic (unit-tested with a fake backend);
the default Win32 backend uses pywin32 + Pillow and is lazy-loaded.
"""

from __future__ import annotations

from ..exceptions import DriverError


class Clipboard:
    def __init__(self, backend=None):
        self._backend = backend

    @property
    def backend(self):
        if self._backend is None:
            self._backend = Win32ClipboardBackend()
        return self._backend

    def get_text(self) -> str | None:
        return self.backend.get_text()

    def set_text(self, text) -> "Clipboard":
        self.backend.set_text(str(text))
        return self

    def get_image(self):
        return self.backend.get_image()

    def set_image(self, image) -> "Clipboard":
        self.backend.set_image(image)
        return self

    # Convenience property
    @property
    def text(self) -> str | None:
        return self.get_text()

    @text.setter
    def text(self, value) -> None:
        self.set_text(value)


class Win32ClipboardBackend:
    def _wc(self):
        try:
            import win32clipboard
        except Exception as exc:
            raise DriverError("clipboard needs pywin32: pip install humanpc[uia]") from exc
        return win32clipboard

    def get_text(self) -> str | None:
        wc = self._wc()
        wc.OpenClipboard()
        try:
            if wc.IsClipboardFormatAvailable(wc.CF_UNICODETEXT):
                return wc.GetClipboardData(wc.CF_UNICODETEXT)
            return None
        finally:
            wc.CloseClipboard()

    def set_text(self, text: str) -> None:
        wc = self._wc()
        wc.OpenClipboard()
        try:
            wc.EmptyClipboard()
            wc.SetClipboardData(wc.CF_UNICODETEXT, text)
        finally:
            wc.CloseClipboard()

    def get_image(self):
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise DriverError("clipboard images need Pillow: pip install humanpc[capture]") from exc
        data = ImageGrab.grabclipboard()
        # grabclipboard returns an Image, a list of paths, or None.
        from PIL import Image as PILImage

        return data if isinstance(data, PILImage.Image) else None

    def set_image(self, image) -> None:
        import io

        wc = self._wc()
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        dib = output.getvalue()[14:]  # strip the 14-byte BMP file header -> DIB
        output.close()
        wc.OpenClipboard()
        try:
            wc.EmptyClipboard()
            wc.SetClipboardData(wc.CF_DIB, dib)
        finally:
            wc.CloseClipboard()

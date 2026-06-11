from humanpc.system.clipboard import Clipboard


class FakeCB:
    def __init__(self):
        self._text = None
        self._image = None

    def get_text(self):
        return self._text

    def set_text(self, t):
        self._text = t

    def get_image(self):
        return self._image

    def set_image(self, img):
        self._image = img


def test_text_roundtrip():
    cb = Clipboard(FakeCB())
    cb.set_text("hello")
    assert cb.get_text() == "hello"


def test_text_property():
    cb = Clipboard(FakeCB())
    cb.text = "world"
    assert cb.text == "world"


def test_set_text_coerces_to_str():
    cb = Clipboard(FakeCB())
    cb.set_text(123)
    assert cb.get_text() == "123"


def test_image_roundtrip():
    cb = Clipboard(FakeCB())
    sentinel = object()
    cb.set_image(sentinel)
    assert cb.get_image() is sentinel


def test_set_returns_self_for_chaining():
    cb = Clipboard(FakeCB())
    assert cb.set_text("a").set_text("b") is cb

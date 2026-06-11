import pytest

from humanpc.geometry import Point, Rect
from humanpc.targeting import Image, Locator, Match, Resolver


class FakeUIA:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def find(self, **kw):
        self.calls.append(kw)
        return self.result


class FakeOCR:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def find(self, text, **kw):
        self.calls.append(text)
        return self.result


class FakeTemplate:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def find(self, image, **kw):
        self.calls.append(image)
        return self.result


def _m(method):
    return Match(Rect(0, 0, 10, 10), 1.0, method)


def test_point_passthrough():
    assert Resolver().resolve((40, 60)).center == Point(40, 60)


def test_region_tuple_and_rect():
    assert Resolver().resolve((0, 0, 20, 10)).method == "region"
    assert Resolver().resolve(Rect(0, 0, 20, 10)).center == Point(10, 5)


def test_match_passthrough():
    m = _m("uia")
    assert Resolver().resolve(m) is m


def test_text_prefers_uia_and_skips_ocr_on_hit():
    uia, ocr = FakeUIA(_m("uia")), FakeOCR(_m("ocr"))
    assert Resolver(uia=uia, ocr=ocr).resolve("Login").method == "uia"
    assert ocr.calls == []  # not consulted once UIA hits


def test_text_falls_back_to_ocr():
    uia, ocr = FakeUIA(None), FakeOCR(_m("ocr"))
    assert Resolver(uia=uia, ocr=ocr).resolve("Login").method == "ocr"


def test_text_not_found_returns_none():
    assert Resolver(uia=FakeUIA(None), ocr=FakeOCR(None)).resolve("Nope") is None


def test_image_uses_template():
    tf = FakeTemplate(_m("template"))
    assert Resolver(template=tf).resolve(Image("x.png")).method == "template"
    assert tf.calls


def test_locator_uses_uia():
    uia = FakeUIA(_m("uia"))
    r = Resolver(uia=uia)
    assert r.resolve(Locator(name="OK", control_type="Button")).method == "uia"
    assert uia.calls[0]["name"] == "OK"
    assert uia.calls[0]["control_type"] == "Button"


def test_bad_tuple_length_raises():
    with pytest.raises(TypeError):
        Resolver().resolve((1, 2, 3))

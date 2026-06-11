from humanpc.geometry import Point, Rect
from humanpc.targeting.ocr import OCRFinder, Word


def _finder(words):
    return OCRFinder(backend=lambda image: words)


def test_single_word_match():
    words = [Word("File", Rect(0, 0, 40, 20)), Word("Edit", Rect(50, 0, 40, 20))]
    m = _finder(words).find("Edit", image="ignored")
    assert m is not None
    assert m.center == Point(70, 10)
    assert m.method == "ocr"


def test_phrase_match_unions_boxes():
    words = [Word("Sign", Rect(0, 0, 40, 20)), Word("in", Rect(45, 0, 20, 20))]
    m = _finder(words).find("Sign in", image="ignored")
    assert m.bbox == Rect(0, 0, 65, 20)


def test_case_and_punctuation_insensitive():
    words = [Word("LOGIN", Rect(0, 0, 50, 20))]
    assert _finder(words).find("login", image="ignored") is not None


def test_not_found_returns_none():
    words = [Word("File", Rect(0, 0, 40, 20))]
    assert _finder(words).find("Save", image="ignored") is None


def test_region_offset_only_applies_when_capturing():
    words = [Word("OK", Rect(5, 5, 20, 20))]
    # image provided -> no offset even if a region is passed
    m = _finder(words).find("OK", image="ignored", region=Rect(100, 100, 50, 50))
    assert m.bbox == Rect(5, 5, 20, 20)

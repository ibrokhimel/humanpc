import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from humanpc.targeting.template import TemplateFinder
from humanpc.targeting.types import Image


def _needle(seed):
    rng = np.random.RandomState(seed)
    return (rng.rand(30, 40, 3) * 255).astype(np.uint8)


def _haystack_with(needle, at=(80, 120)):
    rng = np.random.RandomState(99)
    hay = (rng.rand(300, 400, 3) * 255).astype(np.uint8)
    y, x = at
    hay[y:y + needle.shape[0], x:x + needle.shape[1]] = needle
    return hay


def test_template_locates_embedded_needle():
    needle = _needle(7)
    hay = _haystack_with(needle, at=(80, 120))
    m = TemplateFinder().find(Image(needle, confidence=0.9), haystack=hay)
    assert m is not None
    assert abs(m.bbox.x - 120) <= 1 and abs(m.bbox.y - 80) <= 1
    assert m.method == "template"
    assert m.confidence > 0.9


def test_template_absent_returns_none():
    needle = _needle(7)
    other = _needle(123)  # different pattern, never embedded
    hay = _haystack_with(needle, at=(80, 120))
    assert TemplateFinder().find(Image(other, confidence=0.9), haystack=hay) is None

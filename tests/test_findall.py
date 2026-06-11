import pytest

from humanpc.geometry import Rect
from humanpc.targeting.ocr import OCRFinder, Word


def _ocr(words):
    return OCRFinder(backend=lambda image: words)


def test_ocr_find_all_returns_each_occurrence():
    words = [
        Word("OK", Rect(0, 0, 20, 20)),
        Word("Cancel", Rect(30, 0, 40, 20)),
        Word("OK", Rect(80, 0, 20, 20)),
    ]
    matches = _ocr(words).find_all("OK", image="ignored")
    assert sorted(m.bbox.x for m in matches) == [0, 80]


def test_ocr_find_all_empty_when_absent():
    assert _ocr([Word("Yes", Rect(0, 0, 20, 20))]).find_all("No", image="ignored") == []


# --- template find_all (real OpenCV) -------------------------------------
np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from humanpc.targeting.template import TemplateFinder  # noqa: E402
from humanpc.targeting.types import Image  # noqa: E402


def test_template_find_all_locates_multiple():
    rng = np.random.RandomState(5)
    needle = (rng.rand(24, 24, 3) * 255).astype(np.uint8)
    hay = (np.random.RandomState(1).rand(300, 400, 3) * 255).astype(np.uint8)
    for y, x in [(40, 60), (200, 300)]:
        hay[y:y + 24, x:x + 24] = needle

    matches = TemplateFinder().find_all(Image(needle, confidence=0.9), haystack=hay)
    assert len(matches) == 2
    corners = sorted((m.bbox.x, m.bbox.y) for m in matches)
    assert any(abs(x - 60) <= 1 and abs(y - 40) <= 1 for x, y in corners)
    assert any(abs(x - 300) <= 1 and abs(y - 200) <= 1 for x, y in corners)

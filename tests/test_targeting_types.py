from humanpc.geometry import Point, Rect
from humanpc.targeting import Image, Locator, Match, Region


def test_match_from_point_centers_and_method():
    m = Match.from_point((100, 50))
    assert m.center == Point(100, 50)
    assert m.method == "coords"


def test_match_from_rect_center_and_size():
    m = Match.from_rect(Rect(10, 20, 30, 40))
    assert m.center == Point(25, 40)
    assert m.size == (30, 40)
    assert m.method == "region"


def test_region_is_rect_alias():
    assert Region is Rect
    assert Region(0, 0, 10, 10).center == Point(5, 5)


def test_image_defaults():
    img = Image("button.png")
    assert img.confidence == 0.8
    assert img.grayscale is True


def test_locator_fields():
    loc = Locator(name="OK", control_type="Button")
    assert loc.name == "OK"
    assert loc.control_type == "Button"

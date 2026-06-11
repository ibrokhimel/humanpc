from humanpc.geometry import Point, Rect, distance, to_point


def test_rect_center_and_edges():
    r = Rect(10, 20, 100, 40)
    assert r.center == Point(60, 40)
    assert r.right == 110
    assert r.bottom == 60
    assert r.size == (100, 40)


def test_rect_contains():
    r = Rect(0, 0, 50, 50)
    assert r.contains((25, 25))
    assert r.contains(Point(0, 0))
    assert not r.contains((60, 25))


def test_point_as_int_rounds():
    assert Point(10.4, 20.6).as_int() == (10, 21)


def test_to_point_accepts_tuple_point_and_rect():
    assert to_point((3, 4)) == Point(3, 4)
    assert to_point(Point(1, 2)) == Point(1, 2)
    assert to_point(Rect(0, 0, 10, 10)) == Point(5, 5)


def test_distance():
    assert distance((0, 0), (3, 4)) == 5

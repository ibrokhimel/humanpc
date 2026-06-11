from humanpc.targeting import parse_target
from humanpc.targeting.types import Image


def test_point():
    assert parse_target("300,200") == (300, 200)


def test_region():
    assert parse_target("10,20,60,24") == (10, 20, 60, 24)


def test_negative_coords():
    assert parse_target("-5,-10") == (-5, -10)


def test_image_path():
    t = parse_target("button.png")
    assert isinstance(t, Image) and t.source == "button.png"


def test_plain_text():
    assert parse_target("Login") == "Login"


def test_non_string_passthrough():
    assert parse_target((1, 2)) == (1, 2)

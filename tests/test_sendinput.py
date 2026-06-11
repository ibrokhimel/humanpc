import sys

import pytest

from humanpc.input.sendinput_driver import _vk_code


def test_vk_letters():
    assert _vk_code("a") == 0x41
    assert _vk_code("Z") == 0x5A


def test_vk_digits():
    assert _vk_code("0") == 0x30


def test_vk_named_keys():
    assert _vk_code("enter") == 0x0D
    assert _vk_code("ctrl") == 0x11
    assert _vk_code("f5") == 0x74


def test_vk_unknown_raises():
    with pytest.raises(KeyError):
        _vk_code("nope")


@pytest.mark.skipif(sys.platform != "win32", reason="SendInput is Windows-only")
def test_driver_constructs_and_reads_position():
    from humanpc.input.sendinput_driver import SendInputDriver

    drv = SendInputDriver()
    pos = drv.position()  # read-only; does not move the cursor
    assert isinstance(pos, tuple) and len(pos) == 2

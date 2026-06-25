"""E) Relative-mouse (opt-in) landing accuracy.

With Config(relative_mouse=True) the Bot injects RELATIVE deltas (which pass
through the OS pointer-acceleration curve) and issues a final correction nudge.
move_to must still land exactly on the target despite acceleration drift.
"""
import ctypes

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.sendinput_driver import SendInputDriver

user32 = ctypes.windll.user32


def epp_state():
    # SPI_GETMOUSE -> [threshold1, threshold2, acceleration on/off]
    arr = (ctypes.c_int * 3)()
    user32.SystemParametersInfoW(0x0003, 0, arr, 0)
    speed = ctypes.c_int()
    user32.SystemParametersInfoW(0x0070, 0, ctypes.byref(speed), 0)  # SPI_GETMOUSESPEED
    return list(arr), speed.value


def main():
    print("=== E) relative mouse landing accuracy ===")
    accel, speed = epp_state()
    print(f"pointer 'enhance precision' (acceleration) ON: {bool(accel[2])}  "
          f"(thresholds={accel[:2]}, mouse speed={speed}/20)")

    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    targets = [(int(sw * 0.5), int(sh * 0.5)),
               (int(sw * 0.7), int(sh * 0.35)),
               (int(sw * 0.35), int(sh * 0.6)),
               (int(sw * 0.6), int(sh * 0.55))]

    bot = Bot(driver=SendInputDriver(), config=Config(seed=3, relative_mouse=True), arm=False)
    results = []
    for t in targets:
        bot.move_to(t)
        pos = bot.position()
        dx, dy = pos[0] - t[0], pos[1] - t[1]
        exact = (dx, dy) == (0, 0)
        results.append(exact)
        print(f"   target {t}  ->  landed {pos}   drift=({dx:+d},{dy:+d})   "
              f"{'EXACT' if exact else 'OFF'}")
    bot.close()

    all_exact = all(results)
    print(f"E RESULT: {'PASS' if all_exact else 'FAIL'}  "
          f"({sum(results)}/{len(results)} exact landings via relative deltas)")


if __name__ == "__main__":
    main()

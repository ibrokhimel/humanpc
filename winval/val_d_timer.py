"""D) High-resolution timer validation.

1. Confirms Config(precision_timing=True) -> the Bot raises the Windows timer tick
   to 1 ms (timeBeginPeriod(1)), observed via NtQueryTimerResolution.
2. Compares precise_sleep(5ms) vs time.sleep(5ms) accuracy.
"""
import ctypes
import statistics
import time

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.driver import NullDriver
from humanpc.hil.precise import begin_high_resolution, end_high_resolution, precise_sleep

ntdll = ctypes.WinDLL("ntdll")


def current_res_ms():
    mn = ctypes.c_ulong()
    mx = ctypes.c_ulong()
    cur = ctypes.c_ulong()
    ntdll.NtQueryTimerResolution(ctypes.byref(mn), ctypes.byref(mx), ctypes.byref(cur))
    # values are in 100-ns units; 10000 == 1 ms
    return mn.value / 10000.0, mx.value / 10000.0, cur.value / 10000.0


def bench(fn, target, n=60):
    errs = []
    for _ in range(n):
        t = time.perf_counter()
        fn(target)
        errs.append((time.perf_counter() - t) * 1000.0)
    return errs


def main():
    print("=== D) high-resolution timer ===")

    end_high_resolution()  # make sure we start from a clean state for this proc
    time.sleep(0.05)
    mn, mx, before = current_res_ms()
    print(f"timer resolution (this process not yet raising it): current={before:.3f} ms "
          f"(coarsest={mn:.3f}, finest={mx:.3f})")

    # 1) The Config path must raise the tick to ~1 ms.
    bot = Bot(driver=NullDriver(), config=Config(precision_timing=True, seed=1))
    _, _, during = current_res_ms()
    print(f"after Bot(Config(precision_timing=True)): current={during:.3f} ms; "
          f"bot._precision={bot._precision}")
    config_raises = bot._precision and during <= 1.5
    bot.close()
    _, _, after = current_res_ms()
    print(f"after bot.close(): current={after:.3f} ms (restored)")
    print(f"  -> timeBeginPeriod(1) via Config: {'CONFIRMED' if config_raises else 'NOT confirmed'}")

    # 2) precise_sleep vs time.sleep at 5 ms, with the 1 ms tick active.
    active = begin_high_resolution()
    try:
        ts = bench(time.sleep, 0.005)
        ps = bench(precise_sleep, 0.005)
    finally:
        end_high_resolution()

    def stat(x):
        return (f"mean={statistics.mean(x):.2f}ms median={statistics.median(x):.2f}ms "
                f"p95={sorted(x)[int(len(x)*0.95)]:.2f}ms max={max(x):.2f}ms")

    print(f"\nrequested 5.00 ms sleeps (timeBeginPeriod active={active}):")
    print(f"  time.sleep(0.005)   : {stat(ts)}")
    print(f"  precise_sleep(0.005): {stat(ps)}")

    sub15 = statistics.median(ps) < 15.0
    accurate = 4.0 <= statistics.median(ps) <= 9.0  # ~5ms, allowing spin/scheduler slack
    print(f"\n  precise_sleep achieves sub-15ms: {sub15}; accurate (~5-9ms median): {accurate}")
    print(f"D RESULT: {'PASS' if (config_raises and sub15 and accurate) else 'FAIL'}")


if __name__ == "__main__":
    main()

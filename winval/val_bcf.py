"""B) keystroke dwell, C) shift dynamics, F) injected-flag reality check.

Installs WH_KEYBOARD_LL + WH_MOUSE_LL hooks, types a string with capitals and
symbols through the native SendInput driver, plus one mouse move, and analyses the
captured low-level event stream:

  B  key-hold dwell = up_time - down_time per character (must be non-zero).
  C  Shift VK (0x10) is pressed before / released after each capital & symbol.
  F  every injected event carries LLKHF_INJECTED / LLMHF_INJECTED (expected, the
     documented limitation), while still carrying our dwExtraInfo signature.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from winhook import (  # noqa: E402
    Capture, VK_PACKET, VK_SHIFT, VK_LSHIFT, VK_RSHIFT, vk_name,
    WM_MOUSEMOVE,
)

from humanpc import Bot  # noqa: E402
from humanpc.config import Config  # noqa: E402
from humanpc.input.sendinput_driver import SendInputDriver  # noqa: E402
from humanpc.hil.typing.keys import needs_shift  # noqa: E402

SIG = 0x68706331  # "hpc1" dwExtraInfo signature stamped on our events
TEXT = "Hello, World! @2026 #HumanPC?"


def char_of(ev):
    if ev["vk"] == VK_PACKET:
        try:
            return chr(ev["scan"])
        except ValueError:
            return "?"
    return None


def main():
    driver = SendInputDriver(extra_info=SIG)
    bot = Bot(driver=driver, config=Config(seed=21, typing_errors=False), arm=False)

    proc = bot.open_app("notepad.exe", wait="Untitled - Notepad")
    time.sleep(1.0)
    try:
        bot.focus("Untitled - Notepad")
    except Exception as e:
        print(f"[warn] focus: {e}")
    time.sleep(0.4)
    bot.hotkey("ctrl", "a")
    time.sleep(0.1)
    bot.press("delete")
    time.sleep(0.3)

    cap = Capture()

    def action():
        bot.type(TEXT)
        time.sleep(0.2)
        # a real cursor move for the mouse-injected-flag + human-motion evidence
        bot.move_to((820, 470))
        time.sleep(0.1)
        bot.move_to((520, 360))

    cap.run(action, timeout=30.0)

    bot.close()
    subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)

    keys = [e for e in cap.keys if e["injected"]]
    mouse = [e for e in cap.mouse if e["injected"]]

    # ---- B) dwell -----------------------------------------------------------
    dwells = []
    open_down = {}
    for e in keys:
        k = (e["vk"], e["scan"])
        if e["down"]:
            open_down[k] = e["t"]
        else:
            if k in open_down:
                dwells.append((char_of(e) or vk_name(e["vk"]), e["t"] - open_down.pop(k)))
    char_dwells = [d for (lab, d) in dwells if lab and len(lab) == 1]

    print("=== B) keystroke dwell (down -> hold -> up) ===")
    for lab, d in dwells[:14]:
        print(f"   {lab!r:>6}  held {d*1000:6.1f} ms")
    if char_dwells:
        import statistics
        nonzero = all(d > 0.005 for d in char_dwells)
        print(f"   chars: n={len(char_dwells)} min={min(char_dwells)*1000:.1f}ms "
              f"median={statistics.median(char_dwells)*1000:.1f}ms "
              f"max={max(char_dwells)*1000:.1f}ms")
        print(f"   all char holds non-zero (>5ms): {nonzero}")
        b_pass = nonzero and statistics.median(char_dwells) > 0.02
    else:
        b_pass = False
    print(f"   B RESULT: {'PASS' if b_pass else 'FAIL'}")

    # ---- C) shift dynamics --------------------------------------------------
    print("\n=== C) shift dynamics around capitals & symbols ===")
    expected_shift = [c for c in TEXT if needs_shift(c)]
    print(f"   chars needing shift: {expected_shift}")
    # ordered injected event labels for a readable trace of the first few shifted chars
    seq = []
    for e in keys:
        if e["vk"] in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            seq.append(("SHIFT", "down" if e["down"] else "up", e["t"]))
        else:
            c = char_of(e)
            if c is not None:
                seq.append((c, "down" if e["down"] else "up", e["t"]))
    print("   trace (first 16 key transitions):")
    for lab, ud, t in seq[:16]:
        print(f"      {t*1000:8.1f} ms  {lab!r:>6} {ud}")

    # verify: for each shifted char, a SHIFT-down precedes its char-down and a
    # SHIFT-up follows its char-up, with shift actually held across the char.
    shift_intervals = []
    cur = None
    for e in keys:
        if e["vk"] in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            if e["down"]:
                cur = [e["t"], None]
            elif cur is not None:
                cur[1] = e["t"]
                shift_intervals.append(tuple(cur))
                cur = None
    covered = 0
    for e in keys:
        c = char_of(e)
        if c is not None and e["down"] and needs_shift(c):
            if any(lo <= e["t"] <= hi for lo, hi in shift_intervals):
                covered += 1
    n_shifted_chars = sum(1 for e in keys if e["down"] and char_of(e) and needs_shift(char_of(e)))
    print(f"   shift held across {covered}/{n_shifted_chars} shifted-char keypresses; "
          f"{len(shift_intervals)} shift hold intervals observed")
    c_pass = n_shifted_chars > 0 and covered == n_shifted_chars
    print(f"   C RESULT: {'PASS' if c_pass else 'FAIL'}")

    # ---- F) injected flag ---------------------------------------------------
    print("\n=== F) injected-flag reality check ===")
    n_key = len(cap.keys)
    n_key_inj = sum(1 for e in cap.keys if e["injected"])
    n_mouse_moves = sum(1 for e in cap.mouse if e["msg"] == WM_MOUSEMOVE)
    n_mouse_inj = sum(1 for e in cap.mouse if e["injected"])
    sig_ok = all(e["extra"] == SIG for e in keys) and all(e["extra"] == SIG for e in mouse)
    sample = keys[0] if keys else None
    print(f"   keyboard events seen: {n_key};  injected (LLKHF_INJECTED): {n_key_inj}")
    print(f"   mouse events seen: {len(cap.mouse)} ({n_mouse_moves} moves); "
          f"injected (LLMHF_INJECTED): {n_mouse_inj}")
    if sample:
        print(f"   sample key flags=0x{sample['flags']:02X} injected={sample['injected']} "
              f"lower_il={sample['lower_il']} dwExtraInfo=0x{sample['extra']:08X}")
    print(f"   every injected event also carries our dwExtraInfo signature 0x{SIG:08X}: {sig_ok}")
    f_detectable = n_key_inj == n_key and n_key > 0 and n_mouse_inj > 0
    print(f"   ALL our events flagged injected (i.e. DETECTABLE, as documented): {f_detectable}")
    print(f"   F RESULT: {'PASS (behaviour confirmed: user-mode SendInput is flagged)' if f_detectable else 'FAIL'}")

    # ---- mouse motion is human, not instant (supports A) -------------------
    print("\n=== mouse motion (supports A: not instant) ===")
    if mouse:
        span = mouse[-1]["t"] - mouse[0]["t"]
        print(f"   {n_mouse_moves} injected move steps over {span*1000:.0f} ms "
              f"(stepped path, not a single jump)")
        xs = [e['x'] for e in mouse if e['msg'] == WM_MOUSEMOVE][:8]
        ys = [e['y'] for e in mouse if e['msg'] == WM_MOUSEMOVE][:8]
        print(f"   first path points: {list(zip(xs, ys))}")

    print("\nSUMMARY  B=%s  C=%s  F=%s" % (
        "PASS" if b_pass else "FAIL",
        "PASS" if c_pass else "FAIL",
        "PASS" if f_detectable else "FAIL"))


if __name__ == "__main__":
    sys.exit(main())

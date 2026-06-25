"""B) dwell + C) shift dynamics validated at the injection boundary.

This session is headless (no live console input device), so injected input is not
delivered to windows or LL hooks. We therefore measure at the driver boundary: a
recording driver timestamps every primitive the *real* Bot typing path emits, so we
can prove (down -> hold(dwell) -> up) with non-zero, realistic hold times and that a
real Shift key event brackets every capital/symbol. Timing uses the real Bot
precise_sleep path on Windows.
"""
import statistics
import time

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.driver import InputDriver
from humanpc.hil.typing.keys import needs_shift


class RecordingDriver(InputDriver):
    def __init__(self):
        self.ev = []          # (op, value, perf_counter)
        self._p = (0, 0)

    def _rec(self, op, val):
        self.ev.append((op, val, time.perf_counter()))

    def move(self, x, y): self._p = (int(x), int(y)); self._rec("move", self._p)
    def mouse_down(self, b="left"): self._rec("mouse_down", b)
    def mouse_up(self, b="left"): self._rec("mouse_up", b)
    def scroll(self, dx, dy): self._rec("scroll", (dx, dy))
    def key_down(self, k): self._rec("key_down", k)
    def key_up(self, k): self._rec("key_up", k)
    def write_char(self, c): self._rec("write_char", c)
    def char_down(self, c): self._rec("char_down", c)
    def char_up(self, c): self._rec("char_up", c)
    def position(self): return self._p


TEXT = "Hello, World! @2026 #HumanPC?"

drv = RecordingDriver()
bot = Bot(driver=drv, config=Config(seed=21, typing_errors=False), arm=False)
t0 = time.perf_counter()
bot.type(TEXT)
total = time.perf_counter() - t0
bot.close()

ev = drv.ev

# ---- B) dwell: every char_down is followed by char_up; measure the hold -----
print("=== B) keystroke dwell at the injection boundary (real Bot path) ===")
dwells = []
shown = 0
for i, (op, val, t) in enumerate(ev):
    if op == "char_down":
        # find the matching char_up (next event for same char)
        for op2, val2, t2 in ev[i + 1:]:
            if op2 == "char_up" and val2 == val:
                d = t2 - t
                dwells.append(d)
                if shown < 12:
                    print(f"   char {val!r:>4}:  held {d*1000:6.1f} ms")
                    shown += 1
                break
nonzero = all(d > 0.005 for d in dwells)
atomic_writes = sum(1 for op, _, _ in ev if op == "write_char")
print(f"   chars held: n={len(dwells)}  min={min(dwells)*1000:.1f}ms "
      f"median={statistics.median(dwells)*1000:.1f}ms max={max(dwells)*1000:.1f}ms")
print(f"   atomic write_char fallbacks used: {atomic_writes} (0 == true split injection)")
print(f"   all holds non-zero (>5ms): {nonzero}")
b_pass = nonzero and atomic_writes == 0 and statistics.median(dwells) > 0.02
print(f"   B RESULT: {'PASS' if b_pass else 'FAIL'}")

# ---- C) shift dynamics: shift_down before, shift_up after each shifted char -
print("\n=== C) shift dynamics at the injection boundary ===")
shifted_chars = [c for c in TEXT if needs_shift(c)]
print(f"   chars needing shift: {shifted_chars}")
# Walk events; a 'key_down shift' opens a held interval until 'key_up shift'.
covered, total_shifted, unicode_used = 0, 0, 0
held = False
i = 0
seq_trace = []
while i < len(ev):
    op, val, t = ev[i]
    if op == "key_down" and val == "shift":
        held = True
        seq_trace.append("SHIFT_down")
    elif op == "key_up" and val == "shift":
        held = False
        seq_trace.append("SHIFT_up")
    elif op == "char_down":
        if needs_shift(val):
            total_shifted += 1
            unicode_used += 1  # char_down == Unicode path (not VK), per driver
            if held:
                covered += 1
            seq_trace.append(f"{val!r}(shift={held})")
    i += 1

print("   sequence (first 12 relevant transitions):")
print("     " + "  ".join(seq_trace[:12]))
print(f"   shifted chars with Shift held across them: {covered}/{total_shifted}")
print(f"   shifted chars still emitted via Unicode char path (not raw VK): {unicode_used}/{total_shifted}")
c_pass = total_shifted > 0 and covered == total_shifted
print(f"   C RESULT: {'PASS' if c_pass else 'FAIL'}")

print(f"\ntyped {len(TEXT)} chars in {total:.2f}s (real precise_sleep timing on Windows)")
print(f"SUMMARY  B={'PASS' if b_pass else 'FAIL'}  C={'PASS' if c_pass else 'FAIL'}")

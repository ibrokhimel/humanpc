"""A) character fidelity at the injection boundary (headless session can't render Notepad).

Types the exact smoke sentence through the real Bot path and reconstructs what the
driver would emit, proving capitals / symbols / spacing / the em dash are all correct.
"""
import time

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.driver import InputDriver

TEXT = "Hello from humanpc — does this look human?"


class Recorder(InputDriver):
    def __init__(self): self.chars = []; self._p = (0, 0)
    def move(self, x, y): self._p = (int(x), int(y))
    def mouse_down(self, b="left"): pass
    def mouse_up(self, b="left"): pass
    def scroll(self, dx, dy): pass
    def key_down(self, k): pass
    def key_up(self, k):
        if k == "backspace" and self.chars: self.chars.pop()
    def write_char(self, c): self.chars.append(c)
    def char_down(self, c): self.chars.append(c)
    def char_up(self, c): pass
    def position(self): return self._p


drv = Recorder()
bot = Bot(driver=drv, config=Config(seed=11, typing_errors=False), arm=False)
t0 = time.perf_counter()
bot.type(TEXT)
elapsed = time.perf_counter() - t0
bot.close()

produced = "".join(drv.chars)
exact = produced == TEXT
print("=== A) character fidelity (injection boundary) ===")
print(f"   requested : {TEXT!r}")
print(f"   produced  : {produced!r}")
print(f"   exact (capitals/symbols/spacing/em-dash): {exact}")
print(f"   typed {len(TEXT)} chars in {elapsed:.2f}s via real timing (not instant: {elapsed > 1.0})")
print(f"   A RESULT (boundary): {'PASS' if exact and elapsed > 1.0 else 'FAIL'}")

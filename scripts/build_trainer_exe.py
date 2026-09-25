"""Build dist/HumanpcTrainer.exe - a one-file trainer for machines without Python.

    python scripts/build_trainer_exe.py

Needs PyInstaller (pip install pyinstaller) and numpy in the build environment.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The trainer only needs tkinter + numpy; keep optional heavy extras out of the exe.
EXCLUDE = ["cv2", "torch", "fastapi", "uvicorn", "starlette", "mcp", "pydantic", "pyautogui",
           "pywinauto", "comtypes", "winocr", "mss", "PIL", "matplotlib", "scipy", "pandas",
           "keyboard", "yaml", "httpx", "pytest", "IPython"]


def main() -> int:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", "HumanpcTrainer", "--paths", str(ROOT),
           "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
           "--specpath", str(ROOT / "build"),
           "--hidden-import", "humanpc.learn.portable"]
    for mod in EXCLUDE:
        cmd += ["--exclude-module", mod]
    cmd.append(str(ROOT / "scripts" / "trainer_entry.py"))
    rc = subprocess.call(cmd)
    if rc == 0:
        exe = ROOT / "dist" / "HumanpcTrainer.exe"
        print(f"\nbuilt {exe} ({exe.stat().st_size / 1e6:.1f} MB)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

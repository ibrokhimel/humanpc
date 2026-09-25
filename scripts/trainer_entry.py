"""PyInstaller entry point for HumanpcTrainer.exe (see build_trainer_exe.py)."""

from humanpc.learn.portable import main

if __name__ == "__main__":
    raise SystemExit(main())

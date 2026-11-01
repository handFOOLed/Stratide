"""Fixed local CLI; no caller-selected commands, executables or clock flags."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from multimodal import main

if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent / "skills" / "exam-paper-parser" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from exam_paper_parser import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

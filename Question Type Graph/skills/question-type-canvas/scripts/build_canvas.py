from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from question_type_graph.canvas import main


if __name__ == "__main__":
    raise SystemExit(main())

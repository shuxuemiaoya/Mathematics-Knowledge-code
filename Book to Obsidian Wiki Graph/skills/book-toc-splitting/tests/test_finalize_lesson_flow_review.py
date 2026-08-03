from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "finalize_lesson_flow_review.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("finalize_lesson_flow_review", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FinalizeLessonFlowTests(unittest.TestCase):
    def test_keeps_complete_worked_example_intact(self) -> None:
        lines = ["例 1"] + [f"line {index}" for index in range(1, 45)]
        block = {
            "id": "example",
            "role": "worked-example",
            "ownership": "retain-parent",
            "start_line": 1,
            "end_line": 45,
        }
        self.assertEqual(MODULE.split_balanced(lines, block, 40), [block])

    def test_entry_context_continuation_becomes_exposition(self) -> None:
        lines = ["# Lesson"] + [f"line {index}" for index in range(1, 22)]
        lines += [""] + [f"more {index}" for index in range(1, 22)]
        block = {
            "id": "entry",
            "role": "entry-context",
            "ownership": "retain-parent",
            "start_line": 1,
            "end_line": len(lines),
        }
        pieces = MODULE.split_balanced(lines, block, 40)
        self.assertEqual(len(pieces), 2)
        self.assertEqual(pieces[0]["role"], "entry-context")
        self.assertEqual(pieces[1]["role"], "exposition")


if __name__ == "__main__":
    unittest.main()

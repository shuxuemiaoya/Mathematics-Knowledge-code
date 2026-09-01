from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))
SCRIPT = SCRIPT_DIRECTORY / "materialize_reference_architecture.py"
SPEC = importlib.util.spec_from_file_location(
    "materialize_reference_architecture", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ExerciseQuestionRangeTests(unittest.TestCase):
    def test_splits_every_question_and_keeps_printed_group_headings_outside(self):
        lines = [
            "#### 习题1.1",
            "![](cover.jpg)",
            "#### 复习巩固",
            "1. 第一题",
            "第一题续文",
            "![](divider.jpg)",
            "#### 综合运用",
            "#### 2. 选择题",
            "第二题选项",
            "3. 第三题",
            "第三题续文",
        ]
        ranges = MODULE.exercise_question_ranges(lines, 1, len(lines))
        self.assertEqual(
            ranges,
            [
                {"question_number": 1, "start_line": 4, "end_line": 6},
                {"question_number": 2, "start_line": 8, "end_line": 9},
                {"question_number": 3, "start_line": 10, "end_line": 11},
            ],
        )

    def test_rejects_missing_or_duplicate_question_numbers(self):
        lines = ["#### 习题5.5", "1. 第一题", "3. 第三题", "3. 重复题"]
        with self.assertRaisesRegex(
            MODULE.MaterializeError, "non-sequential question numbers"
        ):
            MODULE.exercise_question_ranges(lines, 1, len(lines))


class ReferenceExerciseRangeTests(unittest.TestCase):
    def test_incomplete_reference_children_do_not_shrink_source_exercise(self):
        builder = object.__new__(MODULE.Builder)
        reference_root = Path("/tmp/reference-exercise-range")
        organizer_path = reference_root / "习题" / "习题1.1.md"
        question_path = reference_root / "习题" / "原子题" / "习题1.1-T1.md"
        parent = {
            "key": "section",
            "title": "1.1 集合",
            "start_line": 1,
            "end_line": 20,
        }
        source_exercise = {
            "key": "exercise",
            "title": "习题1.1",
            "parent_key": "section",
            "category": "exercise",
            "filename": "习题1.1.md",
            "start_line": 5,
            "end_line": 20,
            "toc_key": None,
            "node_type": "organizer",
            "organizer_type": "section-exercise",
            "emit_title": False,
        }
        builder.reference_root = reference_root
        builder.nodes = {"exercise": source_exercise}
        builder.base_nodes = {"exercise": source_exercise}
        builder.ref_to_key = {}
        builder.order_counter = 0
        builder.lines = [""] * 20
        builder.ref_meta = lambda path: {}
        builder.owned_refs = lambda path: (
            [question_path] if path == organizer_path else []
        )
        builder.reference_category = lambda path: "exercise"
        builder.reference_filename = lambda path, category: path.name
        builder.matching_base_child = lambda title, owner: (
            source_exercise if title == "习题1.1" else None
        )
        builder.matched_reference_range = lambda path, owner: (8, 9)
        builder.proposal_range = lambda path, owner: None
        builder.find_preceding_heading = lambda start, lower, label: 5

        result = builder.build_ref_node(organizer_path, parent)

        self.assertIsNotNone(result)
        self.assertEqual((result["start_line"], result["end_line"]), (5, 20))


if __name__ == "__main__":
    unittest.main()

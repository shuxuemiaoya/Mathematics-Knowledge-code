import importlib.util
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "apply_reviewed_content_repairs.py"
)
SPEC = importlib.util.spec_from_file_location(
    "apply_reviewed_content_repairs", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ReviewedContentRepairTests(unittest.TestCase):
    def test_exact_text_requires_one_match(self):
        repair = {"old": "old", "new": "new"}
        self.assertEqual(
            MODULE.exact_text("before old after", repair),
            "before new after",
        )
        with self.assertRaises(ValueError):
            MODULE.exact_text("old and old", repair)

    def test_insert_after_requires_one_anchor(self):
        repair = {"anchor": "stem", "text": "\npart two"}
        self.assertEqual(
            MODULE.insert_after("stem\nsolution", repair),
            "stem\npart two\nsolution",
        )

    def test_replace_line_can_expand_to_reviewed_block(self):
        repair = {
            "contains": "<table>",
            "new": "| A | B |\n| - | - |",
        }
        self.assertEqual(
            MODULE.replace_line("before\n<table>\nafter\n", repair),
            "before\n| A | B |\n| - | - |\nafter\n",
        )


if __name__ == "__main__":
    unittest.main()

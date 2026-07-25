from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "format_toc_headings.py"
)
SPEC = importlib.util.spec_from_file_location("format_toc_headings", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TocHeadingTests(unittest.TestCase):
    def manifest(self) -> dict:
        return {
            "schema_version": 1,
            "toc_source_ranges": [{"start_line": 1, "end_line": 3}],
            "entries": [
                {"key": "chapter", "title": "第一章 集合", "level": 1},
                {"key": "lesson", "title": "1.1 集合", "level": 2},
            ],
        }

    def test_aligns_toc_and_demotes_non_toc_heading(self) -> None:
        source = (
            "# 目录\n"
            "## 第一章 集合\n"
            "## 1.1 集合\n"
            "# 第一章 集合\n"
            "## 栏目标题\n"
            "# 1.1 集合\n"
            "### 例题\n"
        )
        candidate, report = MODULE.format_headings(source, self.manifest())
        self.assertIn("# 第一章 集合\n", candidate)
        self.assertIn("## 1.1 集合\n", candidate)
        self.assertIn("#### 栏目标题\n", candidate)
        self.assertIn("#### 例题\n", candidate)
        self.assertEqual(report["matched_toc_headings"], 2)
        self.assertEqual(report["demoted_non_toc_headings"], 2)

    def test_rejects_missing_toc_heading(self) -> None:
        source = "# 第一章 集合\n# 第二章 函数\n"
        with self.assertRaises(MODULE.TocFormattingError):
            MODULE.format_headings(source, self.manifest())


if __name__ == "__main__":
    unittest.main()

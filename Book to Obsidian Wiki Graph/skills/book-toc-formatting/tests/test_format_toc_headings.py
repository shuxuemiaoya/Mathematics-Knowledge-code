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

    def test_consolidates_adjacent_ocr_heading_fragments(self) -> None:
        manifest = {
            "schema_version": 1,
            "toc_source_ranges": [],
            "entries": [
                {
                    "key": "chapter",
                    "title": "第一章 集合与常用逻辑用语",
                    "level": 1,
                    "aliases": ["第一章"],
                }
            ],
        }
        source = "# 第一章\n\n## 集合与常用逻辑用语\n\n正文。\n"
        candidate, report = MODULE.format_headings(source, manifest)
        self.assertIn("# 第一章 集合与常用逻辑用语\n", candidate)
        self.assertNotIn("#### 集合与常用逻辑用语", candidate)
        self.assertEqual(report["matched_toc_headings"], 1)
        self.assertEqual(report["composite_toc_headings"], 1)
        self.assertEqual(report["matched"][0]["source_lines"], [1, 3])

    def test_replaces_matching_alias_with_authoritative_toc_title(self) -> None:
        manifest = {
            "schema_version": 1,
            "toc_source_ranges": [],
            "entries": [
                {
                    "key": "chapter",
                    "title": "第二章 一元二次函数、方程和不等式",
                    "level": 1,
                    "aliases": ["一元二次函数、方程和不等式"],
                }
            ],
        }
        candidate, report = MODULE.format_headings(
            "# 一元二次函数、方程和不等式\n", manifest
        )
        self.assertEqual(candidate, "# 第二章 一元二次函数、方程和不等式\n")
        self.assertEqual(
            report["matched"][0]["source_title"],
            "一元二次函数、方程和不等式",
        )

    def test_composite_match_ignores_escaped_markdown_emphasis(self) -> None:
        manifest = {
            "schema_version": 1,
            "toc_source_ranges": [],
            "entries": [
                {
                    "key": "reading",
                    "title": "文献阅读与数学写作* 函数的形成与发展",
                    "level": 2,
                }
            ],
        }
        candidate, report = MODULE.format_headings(
            "## 文献阅读与数学写作\\*\n\n## 函数的形成与发展\n",
            manifest,
        )
        self.assertEqual(
            candidate,
            "## 文献阅读与数学写作* 函数的形成与发展\n",
        )
        self.assertEqual(report["composite_toc_headings"], 1)

    def test_consolidates_heading_with_exact_plain_text_fragment(self) -> None:
        manifest = {
            "schema_version": 1,
            "toc_source_ranges": [],
            "entries": [
                {
                    "key": "discovery",
                    "title": "探究与发现 函数的周期",
                    "level": 2,
                }
            ],
        }
        candidate, report = MODULE.format_headings(
            "## 探究与发现\n\n函数的周期\n\n正文。\n",
            manifest,
        )
        self.assertEqual(
            candidate,
            "## 探究与发现 函数的周期\n\n正文。\n",
        )
        self.assertFalse(report["matched"][0]["second_fragment_was_heading"])

    def test_inserts_reviewed_printed_toc_heading_at_frozen_line(self) -> None:
        manifest = {
            "schema_version": 1,
            "toc_source_ranges": [],
            "entries": [
                {
                    "key": "index",
                    "title": "部分中英文词汇索引",
                    "level": 1,
                    "insertion_line": 2,
                    "insertion_reason": "OCR omitted the printed index heading",
                }
            ],
        }
        source = "正文。\n<table><tr><td>中文</td></tr></table>\n"
        candidate, report = MODULE.format_headings(source, manifest)
        self.assertEqual(
            candidate,
            "正文。\n# 部分中英文词汇索引\n\n<table><tr><td>中文</td></tr></table>\n",
        )
        self.assertEqual(report["matched_toc_headings"], 1)
        self.assertEqual(report["inserted_toc_headings"], 1)
        self.assertTrue(report["matched"][0]["inserted_from_printed_toc"])

    def test_requires_reason_for_reviewed_heading_insertion(self) -> None:
        manifest = {
            "schema_version": 1,
            "toc_source_ranges": [],
            "entries": [
                {
                    "key": "index",
                    "title": "部分中英文词汇索引",
                    "level": 1,
                    "insertion_line": 1,
                }
            ],
        }
        with self.assertRaises(MODULE.TocFormattingError):
            MODULE.format_headings("索引正文。\n", manifest)


if __name__ == "__main__":
    unittest.main()

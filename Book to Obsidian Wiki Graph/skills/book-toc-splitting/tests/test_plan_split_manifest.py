from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "plan_split_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("plan_split_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SplitManifestPlanningTests(unittest.TestCase):
    def build_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        source = root / "formatted.md"
        profile = root / "book-profile.json"
        toc = root / "toc-manifest.json"
        source.write_text(
            (
                "# 第一章 集合\n"
                "## 1.1 集合的概念\n"
                "导语。\n"
                "#### 1.1.1 集合的含义\n"
                "正文。\n"
                "#### 思考\n"
                "问题。\n"
                "#### 习题1.1\n"
                "题目。\n"
                "## 小结\n"
                "总结。\n"
            ),
            encoding="utf-8",
        )
        profile.write_text(
            json.dumps(
                {
                    "book": {"title": "测试教材"},
                    "source": {"sha256": "abc"},
                }
            ),
            encoding="utf-8",
        )
        toc.write_text(
            json.dumps(
                {
                    "source_sha256": "abc",
                    "toc_source_ranges": [],
                    "entries": [
                        {
                            "key": "chapter",
                            "title": "第一章 集合",
                            "level": 1,
                            "category": "knowledge",
                        },
                        {
                            "key": "lesson",
                            "title": "1.1 集合的概念",
                            "level": 2,
                            "category": "knowledge",
                        },
                        {
                            "key": "summary",
                            "title": "小结",
                            "level": 2,
                            "category": "knowledge",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return source, profile, toc

    def test_builds_mandatory_semantic_splits_and_retains_other_headings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, profile, toc = self.build_fixture(Path(temporary))
            manifest = MODULE.build_manifest(source, profile, toc)
            reviews = {
                item["title"]: item
                for item in manifest["semantic_review"]["headings"]
            }
            self.assertEqual(reviews["1.1.1 集合的含义"]["decision"], "split")
            self.assertEqual(reviews["习题1.1"]["decision"], "split")
            self.assertEqual(reviews["思考"]["decision"], "retain")
            semantic_nodes = [
                item
                for item in manifest["nodes"]
                if item["key"].startswith("semantic-")
            ]
            self.assertEqual(
                [(item["start_line"], item["end_line"]) for item in semantic_nodes],
                [(4, 7), (8, 9)],
            )

    def test_contextualizes_repeated_chapter_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, profile, toc = self.build_fixture(Path(temporary))
            manifest = MODULE.build_manifest(source, profile, toc)
            summary = next(
                item for item in manifest["nodes"] if item["toc_key"] == "summary"
            )
            self.assertEqual(summary["title"], "第一章 集合 小结")
            self.assertEqual(summary["filename"], "第一章 集合 小结.md")

    def test_renders_latex_readably_in_filename(self) -> None:
        self.assertEqual(
            MODULE.safe_filename(
                r"探究函数 $y=x+\frac{1}{x}$ 与 $\omega$"
            ),
            "探究函数 y=x+1÷x 与 ω.md",
        )

    def test_long_lesson_requires_content_level_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, profile, toc = self.build_fixture(Path(temporary))
            source.write_text(
                (
                    "# 第一章 集合\n"
                    "## 1.1 集合的概念\n"
                    + "".join(f"教学段落 {index}。\n" for index in range(30))
                    + "## 小结\n"
                    "总结。\n"
                ),
                encoding="utf-8",
            )
            manifest = MODULE.build_manifest(source, profile, toc)
            sections = manifest["semantic_review"]["sections"]
            self.assertEqual(len(sections), 1)
            self.assertEqual(sections[0]["title"], "1.1 集合的概念")
            self.assertEqual(sections[0]["decision"], "review_required")
            self.assertEqual(manifest["semantic_review"]["ranges"], [])

    def test_long_numbered_subsection_also_requires_content_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, profile, toc = self.build_fixture(Path(temporary))
            source.write_text(
                (
                    "# 第一章 集合\n"
                    "## 1.1 集合的概念\n"
                    "#### 1.1.1 集合的含义\n"
                    + "".join(f"教学段落 {index}。\n" for index in range(30))
                    + "## 小结\n"
                    "总结。\n"
                ),
                encoding="utf-8",
            )
            manifest = MODULE.build_manifest(source, profile, toc)
            sections = {
                item["title"]: item
                for item in manifest["semantic_review"]["sections"]
            }
            self.assertIn("1.1 集合的概念", sections)
            self.assertIn("1.1.1 集合的含义", sections)
            self.assertEqual(
                sections["1.1.1 集合的含义"]["decision"],
                "review_required",
            )


if __name__ == "__main__":
    unittest.main()

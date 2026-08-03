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

    def test_numbered_subsections_return_to_numbered_parent_across_h3_insert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "formatted.md"
            profile = root / "book-profile.json"
            toc = root / "toc-manifest.json"
            source.write_text(
                (
                    "# 第三章 曲线\n"
                    "## 3.3 抛物线\n"
                    "#### 3.3.1 标准方程\n"
                    "第一部分。\n"
                    "### 探究与发现\n"
                    "插入材料。\n"
                    "#### 3.3.2 几何性质\n"
                    "第二部分。\n"
                    "#### 习题3.3\n"
                    "练习题。\n"
                    "### 阅读材料\n"
                    "章末材料。\n"
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
                                "title": "第三章 曲线",
                                "level": 1,
                                "category": "knowledge",
                            },
                            {
                                "key": "lesson",
                                "title": "3.3 抛物线",
                                "level": 2,
                                "category": "knowledge",
                            },
                            {
                                "key": "inquiry",
                                "title": "探究与发现",
                                "level": 3,
                                "category": "reading",
                            },
                            {
                                "key": "reading",
                                "title": "阅读材料",
                                "level": 3,
                                "category": "reading",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = MODULE.build_manifest(source, profile, toc)
            nodes = {node["title"]: node for node in manifest["nodes"]}

        self.assertEqual(
            nodes["3.3.1 标准方程"]["parent_key"],
            nodes["3.3 抛物线"]["key"],
        )
        self.assertEqual(nodes["3.3.1 标准方程"]["end_line"], 4)
        self.assertEqual(nodes["探究与发现"]["end_line"], 6)
        self.assertEqual(
            nodes["3.3.2 几何性质"]["parent_key"],
            nodes["3.3 抛物线"]["key"],
        )
        self.assertEqual(nodes["3.3.2 几何性质"]["end_line"], 8)
        self.assertEqual(
            nodes["习题3.3"]["parent_key"],
            nodes["3.3 抛物线"]["key"],
        )
        self.assertEqual(nodes["习题3.3"]["end_line"], 10)


if __name__ == "__main__":
    unittest.main()

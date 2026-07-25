from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "split_book_by_toc.py"
)
SPEC = importlib.util.spec_from_file_location("split_book_by_toc", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TocSplitTests(unittest.TestCase):
    def profile(self, root: Path) -> dict:
        return {
            "book": {"title": "示例教材", "kind": "mathematics-textbook"},
            "paths": {
                "vault_root": str(root / "vault"),
                "book_root": str(root / "vault" / "课本" / "示例教材"),
                "staging_root": str(root / "staging"),
            },
            "categories": [
                {"role": "knowledge", "directory": "知识点", "enabled": True},
                {"role": "concept", "directory": "概念", "enabled": True},
                {"role": "exercise", "directory": "习题", "enabled": True},
            ],
            "links": {"note_mode": "relative", "encode_spaces": True},
        }

    def test_parent_retains_links_at_child_positions(self) -> None:
        lines = [
            "# 第一章 集合",
            "章引言",
            "## 1.1 集合",
            "课前引入",
            "#### 集合",
            "集合正文",
            "#### 列举法",
            "列举法正文",
            "#### 习题1.1",
            "练习正文",
        ]
        nodes = {
            "book": MODULE.SplitNode(
                "book", "示例教材", None, "root", "示例教材.md", 1, 10, None
            ),
            "chapter": MODULE.SplitNode(
                "chapter", "第一章 集合", "book", "knowledge", "第一章 集合.md", 1, 10, "chapter"
            ),
            "lesson": MODULE.SplitNode(
                "lesson", "1.1 集合", "chapter", "knowledge", "1.1 集合.md", 3, 10, "lesson"
            ),
            "set": MODULE.SplitNode(
                "set", "集合", "lesson", "knowledge", "集合.md", 5, 6, None
            ),
            "list": MODULE.SplitNode(
                "list", "列举法", "lesson", "knowledge", "列举法.md", 7, 8, None
            ),
            "exercise": MODULE.SplitNode(
                "exercise", "习题1.1", "lesson", "exercise", "习题1.1.md", 9, 10, None
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            output_root = Path(profile["paths"]["book_root"])
            lesson = MODULE.render_node(
                nodes["lesson"],
                nodes,
                lines,
                set(),
                output_root,
                Path(profile["paths"]["vault_root"]),
                MODULE.category_map(profile),
                profile["links"],
                "示例教材",
            )
        self.assertIn("## 1.1 集合", lesson)
        self.assertIn("课前引入", lesson)
        self.assertIn("[集合](集合.md)", lesson)
        self.assertIn("[列举法](列举法.md)", lesson)
        self.assertIn("[习题1.1](../习题/习题1.1.md)", lesson)
        self.assertNotIn("集合正文", lesson)
        self.assertNotIn("练习正文", lesson)

    def test_vault_root_note_mode_matches_textbook_link_style(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            output_root = Path(profile["paths"]["book_root"])
            parent = MODULE.SplitNode(
                "lesson", "1.1 集合", None, "knowledge", "1.1 集合.md", 1, 2, None
            )
            child = MODULE.SplitNode(
                "topic", "集合", "lesson", "knowledge", "集合.md", 2, 2, None
            )
            link = MODULE.note_link(
                child,
                parent,
                output_root,
                Path(profile["paths"]["vault_root"]),
                MODULE.category_map(profile),
                {"note_mode": "vault-root", "encode_spaces": True},
            )
            self.assertEqual(
                link,
                "[集合](课本/示例教材/知识点/集合.md)",
            )

    def test_textbook_rejects_extra_category(self) -> None:
        profile = self.profile(Path("C:/temp"))
        profile["categories"].append(
            {"role": "reading", "directory": "阅读", "enabled": True}
        )
        manifest = {
            "nodes": [
                {
                    "key": "root",
                    "title": "示例",
                    "parent_key": None,
                    "category": "root",
                    "filename": "示例.md",
                    "start_line": 1,
                    "end_line": 1,
                }
            ]
        }
        with self.assertRaises(MODULE.SplitError):
            MODULE.load_nodes(manifest, profile, 1, set())

    def test_writes_categorized_tree_and_coverage(self) -> None:
        lines = [
            "# 第一章 集合",
            "章引言",
            "## 1.1 集合",
            "课前引入",
            "#### 集合",
            "集合正文",
            "#### 列举法",
            "列举法正文",
            "#### 习题1.1",
            "练习正文",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            source = root / "staging" / "formatted.md"
            source.parent.mkdir(parents=True)
            source.write_text("\n".join(lines) + "\n", encoding="utf-8")
            toc_manifest = {
                "entries": [
                    {"key": "chapter", "title": "第一章 集合"},
                    {"key": "lesson", "title": "1.1 集合"},
                ],
                "toc_source_ranges": [],
            }
            split_manifest = {
                "profile": "profile.json",
                "source_sha256": "a" * 64,
                "semantic_review": {
                    "headings": [
                        {
                            "line": 5,
                            "title": "集合",
                            "decision": "split",
                            "node_key": "set",
                        },
                        {
                            "line": 7,
                            "title": "列举法",
                            "decision": "retain",
                            "reason": "Short continuation kept in the lesson.",
                        },
                        {
                            "line": 9,
                            "title": "习题1.1",
                            "decision": "split",
                            "node_key": "exercise",
                        },
                    ]
                },
                "nodes": [
                    {
                        "key": "book",
                        "title": "示例教材",
                        "parent_key": None,
                        "category": "root",
                        "filename": "示例教材.md",
                        "start_line": 1,
                        "end_line": 10,
                    },
                    {
                        "key": "chapter",
                        "title": "第一章 集合",
                        "parent_key": "book",
                        "category": "knowledge",
                        "filename": "第一章 集合.md",
                        "start_line": 1,
                        "end_line": 10,
                        "toc_key": "chapter",
                    },
                    {
                        "key": "lesson",
                        "title": "1.1 集合",
                        "parent_key": "chapter",
                        "category": "knowledge",
                        "filename": "1.1 集合.md",
                        "start_line": 3,
                        "end_line": 10,
                        "toc_key": "lesson",
                    },
                    {
                        "key": "set",
                        "title": "集合",
                        "parent_key": "lesson",
                        "category": "knowledge",
                        "filename": "集合.md",
                        "start_line": 5,
                        "end_line": 6,
                    },
                    {
                        "key": "exercise",
                        "title": "习题1.1",
                        "parent_key": "lesson",
                        "category": "exercise",
                        "filename": "习题1.1.md",
                        "start_line": 9,
                        "end_line": 10,
                    },
                ],
            }
            output_root = Path(profile["paths"]["book_root"])
            summary = MODULE.write_split(
                source,
                profile,
                toc_manifest,
                split_manifest,
                output_root,
            )
            parent = (
                output_root / "知识点" / "1.1 集合.md"
            ).read_text(encoding="utf-8")
            book_root_note = (
                output_root / "示例教材.md"
            ).read_text(encoding="utf-8")
            chapter = (
                output_root / "知识点" / "第一章 集合.md"
            ).read_text(encoding="utf-8")
            coverage = Path(summary["coverage_manifest"])
        self.assertIn(
            "[第一章 集合](知识点/第一章%20集合.md)",
            book_root_note,
        )
        self.assertIn("[1.1 集合](1.1%20集合.md)", chapter)
        self.assertIn("[集合](集合.md)", parent)
        self.assertIn("[习题1.1](../习题/习题1.1.md)", parent)
        self.assertTrue(coverage.name == "coverage-manifest.json")

    def test_textbook_requires_review_of_every_demoted_heading(self) -> None:
        lines = [
            "# 第一章",
            "## 1.1 示例",
            "#### 1.1.1 子节",
            "正文",
            "#### 习题1.1",
            "题目",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            nodes = {
                "book": MODULE.SplitNode(
                    "book", "示例教材", None, "root", "示例教材.md", 1, 6, None
                )
            }
            with self.assertRaisesRegex(
                MODULE.SplitError, "semantic_review.headings"
            ):
                MODULE.validate_semantic_review(
                    {}, nodes, lines, set(), profile
                )

    def test_numbered_subsection_and_section_exercise_must_split(self) -> None:
        lines = [
            "# 第一章",
            "## 1.1 示例",
            "#### 1.1.1 子节",
            "正文",
            "#### 习题1.1",
            "题目",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            nodes = {
                "book": MODULE.SplitNode(
                    "book", "示例教材", None, "root", "示例教材.md", 1, 6, None
                )
            }
            manifest = {
                "semantic_review": {
                    "headings": [
                        {
                            "line": 3,
                            "title": "1.1.1 子节",
                            "decision": "retain",
                            "reason": "Too short.",
                        },
                        {
                            "line": 5,
                            "title": "习题1.1",
                            "decision": "retain",
                            "reason": "Keep here.",
                        },
                    ]
                }
            }
            with self.assertRaisesRegex(MODULE.SplitError, "must be split"):
                MODULE.validate_semantic_review(
                    manifest, nodes, lines, set(), profile
                )

    def test_vault_root_asset_mode_rewrites_href_after_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_parent = root / "staging"
            target_parent = root / "temporary-output" / "知识点"
            vault_root = root / "vault"
            final_parent = vault_root / "课本" / "示例教材" / "知识点"
            (source_parent / "images").mkdir(parents=True)
            (source_parent / "images" / "figure.png").write_bytes(b"png")
            target_parent.mkdir(parents=True)
            rendered, copied = MODULE.materialize_assets(
                "![](images/figure.png)\n",
                source_parent,
                target_parent,
                final_parent,
                vault_root,
                {
                    "asset_mode": "vault-root",
                    "encode_spaces": True,
                },
            )
            self.assertEqual(copied, 1)
            self.assertEqual(
                rendered,
                "![](/课本/示例教材/知识点/images/figure.png)\n",
            )
            self.assertTrue(
                (target_parent / "images" / "figure.png").is_file()
            )


if __name__ == "__main__":
    unittest.main()

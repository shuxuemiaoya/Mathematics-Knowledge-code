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
            "decomposition": {
                "non_toc_split_default": "retain",
                "semantic_split_confidence_threshold": 0.9,
            },
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
        self.assertIn("- [集合](集合.md)", lesson)
        self.assertIn("- [列举法](列举法.md)", lesson)
        self.assertIn("- [习题1.1](../习题/习题1.1.md)", lesson)
        self.assertNotIn("集合正文", lesson)
        self.assertNotIn("练习正文", lesson)

    def test_lesson_flow_renders_continuous_callouts_and_ordered_links(self) -> None:
        lines = [
            "## 1.1 集合",
            "为什么需要研究集合？",
            "#### 集合的概念",
            "集合正文。",
            "接下来研究集合的表示方法。",
            "请观察下面的表示。",
            "#### 习题1.1",
            "练习正文。",
        ]
        nodes = {
            "lesson": MODULE.SplitNode(
                "lesson", "1.1 集合", "chapter", "knowledge", "1.1 集合.md", 1, 8, "lesson"
            ),
            "topic": MODULE.SplitNode(
                "topic", "集合的概念", "lesson", "knowledge", "集合的概念.md", 3, 4, None
            ),
            "exercise": MODULE.SplitNode(
                "exercise", "习题1.1", "lesson", "exercise", "习题1.1.md", 7, 8, None
            ),
        }
        lesson_flow = {
            "blocks": [
                {
                    "role": "entry-context",
                    "ownership": "retain-parent",
                    "start_line": 1,
                    "end_line": 2,
                },
                {
                    "role": "topic",
                    "ownership": "move-child",
                    "start_line": 3,
                    "end_line": 4,
                    "child_node_key": "topic",
                },
                {
                    "role": "transition",
                    "ownership": "retain-parent",
                    "start_line": 5,
                    "end_line": 6,
                },
                {
                    "role": "practice",
                    "ownership": "move-child",
                    "start_line": 7,
                    "end_line": 8,
                    "child_node_key": "exercise",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            rendered = MODULE.render_node(
                nodes["lesson"],
                nodes,
                lines,
                set(),
                Path(profile["paths"]["book_root"]),
                Path(profile["paths"]["vault_root"]),
                MODULE.category_map(profile),
                profile["links"],
                "示例教材",
                lesson_flow=lesson_flow,
            )
        self.assertEqual(
            rendered,
            (
                "## 1.1 集合\n"
                "\n"
                "> [!info] 情景引入\n"
                "> 为什么需要研究集合？\n"
                "\n"
                "- [集合的概念](集合的概念.md)\n"
                "\n"
                "> [!info] 过渡\n"
                "> 接下来研究集合的表示方法。\n"
                "> 请观察下面的表示。\n"
                "\n"
                "- [习题1.1](../习题/习题1.1.md)\n"
            ),
        )

    def test_plain_question_label_is_not_duplicated_inside_callout(self) -> None:
        rendered = MODULE.render_retained_flow_block(
            "question",
            ["思考", "", "包含关系与属于关系有什么区别？"],
        )
        self.assertEqual(
            rendered,
            [
                "> [!question] 思考",
                "> 包含关系与属于关系有什么区别？",
            ],
        )

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
                "- [集合](/课本/示例教材/知识点/集合.md)",
            )

    def test_root_level_backmatter_keeps_its_own_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            output_root = Path(profile["paths"]["book_root"])
            node = MODULE.SplitNode(
                "index",
                "部分中英文词汇索引",
                "book",
                "root",
                "部分中英文词汇索引.md",
                1,
                2,
                "index",
            )
            nodes = {
                "book": MODULE.SplitNode(
                    "book", "示例教材", None, "root", "示例教材.md", 1, 2, None
                ),
                "index": node,
            }
            rendered = MODULE.render_node(
                node,
                nodes,
                ["# 部分中英文词汇索引", "词条"],
                set(),
                output_root,
                Path(profile["paths"]["vault_root"]),
                MODULE.category_map(profile),
                profile["links"],
                "示例教材",
            )
            self.assertTrue(rendered.startswith("# 部分中英文词汇索引\n"))
            self.assertNotIn("# 示例教材", rendered)

    def test_textbook_accepts_supported_auxiliary_category(self) -> None:
        profile = self.profile(Path("C:/temp"))
        profile["categories"].append(
            {"role": "reading", "directory": "趣味阅读", "enabled": True}
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
        nodes, _ = MODULE.load_nodes(manifest, profile, 1, set())
        self.assertIn("root", nodes)

    def test_textbook_rejects_unsupported_category(self) -> None:
        profile = self.profile(Path("C:/temp"))
        profile["categories"].append(
            {"role": "appendix", "directory": "附录", "enabled": True}
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
                            "reason": "Complete independently reusable teaching arc.",
                            "independent_teaching_arc": True,
                            "confidence": 0.97,
                        },
                        {
                            "line": 7,
                            "title": "列举法",
                            "decision": "retain",
                            "reason": "Short continuation kept in the lesson.",
                            "confidence": 0.98,
                        },
                        {
                            "line": 9,
                            "title": "习题1.1",
                            "decision": "split",
                            "node_key": "exercise",
                            "confidence": 0.99,
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
            "- [第一章 集合](知识点/第一章%20集合.md)",
            book_root_note,
        )
        self.assertIn("- [1.1 集合](1.1%20集合.md)", chapter)
        self.assertIn("- [集合](集合.md)", parent)
        self.assertIn("- [习题1.1](../习题/习题1.1.md)", parent)
        self.assertTrue(coverage.name == "coverage-manifest.json")

    def test_semantic_note_promotes_demoted_entry_heading_to_h3(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            output_root = Path(profile["paths"]["book_root"])
            node = MODULE.SplitNode(
                "topic",
                "1.1.1 子节",
                "lesson",
                "knowledge",
                "1.1.1 子节.md",
                1,
                2,
                None,
            )
            rendered = MODULE.render_node(
                node,
                {"topic": node},
                ["#### 1.1.1 子节", "正文"],
                set(),
                output_root,
                Path(profile["paths"]["vault_root"]),
                MODULE.category_map(profile),
                profile["links"],
                "示例教材",
            )
            self.assertTrue(rendered.startswith("### 1.1.1 子节\n"))

    def test_headerless_semantic_note_gets_synthetic_h3(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            output_root = Path(profile["paths"]["book_root"])
            node = MODULE.SplitNode(
                "topic",
                "集合",
                "lesson",
                "knowledge",
                "集合.md",
                1,
                2,
                None,
            )
            rendered = MODULE.render_node(
                node,
                {"topic": node},
                ["一般地，我们把研究对象统称为元素。", "完整正文。"],
                set(),
                output_root,
                Path(profile["paths"]["vault_root"]),
                MODULE.category_map(profile),
                profile["links"],
                "示例教材",
            )
            self.assertTrue(rendered.startswith("### 集合\n\n"))
            self.assertIn("一般地，我们把研究对象统称为元素。", rendered)

    def test_non_root_note_rejects_malformed_entry_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            output_root = Path(profile["paths"]["book_root"])
            node = MODULE.SplitNode(
                "lesson",
                "1.1 集合",
                "chapter",
                "knowledge",
                "1.1 集合.md",
                1,
                2,
                "lesson",
            )
            with self.assertRaisesRegex(MODULE.SplitError, "must begin"):
                MODULE.render_node(
                    node,
                    {"lesson": node},
                    ["x## 1.1 集合", "正文"],
                    set(),
                    output_root,
                    Path(profile["paths"]["vault_root"]),
                    MODULE.category_map(profile),
                    profile["links"],
                    "示例教材",
                )

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
                            "confidence": 0.99,
                        },
                        {
                            "line": 5,
                            "title": "习题1.1",
                            "decision": "retain",
                            "reason": "Keep here.",
                            "confidence": 0.99,
                        },
                    ]
                }
            }
            with self.assertRaisesRegex(MODULE.SplitError, "must be split"):
                MODULE.validate_semantic_review(
                    manifest, nodes, lines, set(), profile
                )

    def test_unnumbered_non_toc_split_requires_independent_teaching_arc(self) -> None:
        lines = [
            "# 第一章",
            "## 1.1 示例",
            "#### 列举法",
            "正文",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            nodes = {
                "book": MODULE.SplitNode(
                    "book", "示例教材", None, "root", "示例教材.md", 1, 4, None
                ),
                "list": MODULE.SplitNode(
                    "list", "列举法", "book", "knowledge", "列举法.md", 3, 4, None
                ),
            }
            manifest = {
                "semantic_review": {
                    "headings": [
                        {
                            "line": 3,
                            "title": "列举法",
                            "decision": "split",
                            "node_key": "list",
                            "confidence": 0.98,
                        }
                    ]
                }
            }
            with self.assertRaisesRegex(
                MODULE.SplitError, "independence reason"
            ):
                MODULE.validate_semantic_review(
                    manifest, nodes, lines, set(), profile
                )

    def test_low_confidence_decision_requires_review_marker(self) -> None:
        lines = ["# 第一章", "#### 思考", "正文"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            nodes = {
                "book": MODULE.SplitNode(
                    "book", "示例教材", None, "root", "示例教材.md", 1, 3, None
                )
            }
            manifest = {
                "semantic_review": {
                    "headings": [
                        {
                            "line": 2,
                            "title": "思考",
                            "decision": "retain",
                            "reason": "Functional marker stays with its lesson.",
                            "confidence": 0.6,
                        }
                    ]
                }
            }
            with self.assertRaisesRegex(MODULE.SplitError, "routed through review"):
                MODULE.validate_semantic_review(
                    manifest, nodes, lines, set(), profile
                )

    def test_long_teaching_section_cannot_keep_review_required(self) -> None:
        lines = ["# 第一章", "## 1.1 集合"] + [
            f"教学段落 {index}。" for index in range(30)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            nodes = {
                "book": MODULE.SplitNode(
                    "book", "示例教材", None, "root", "示例教材.md", 1, 32, None
                ),
                "lesson": MODULE.SplitNode(
                    "lesson",
                    "1.1 集合",
                    "book",
                    "knowledge",
                    "1.1 集合.md",
                    2,
                    32,
                    "lesson",
                ),
            }
            manifest = {
                "semantic_review": {
                    "headings": [],
                    "sections": [
                        {
                            "node_key": "lesson",
                            "title": "1.1 集合",
                            "start_line": 2,
                            "end_line": 32,
                            "decision": "review_required",
                            "reason": "Needs content review.",
                            "confidence": 0.0,
                        }
                    ],
                    "ranges": [],
                }
            }
            with self.assertRaisesRegex(MODULE.SplitError, "reviewed split or retain"):
                MODULE.validate_semantic_review(
                    manifest, nodes, lines, set(), profile
                )

    def test_reviewed_headerless_semantic_range_passes(self) -> None:
        lines = ["# 第一章", "## 1.1 集合"] + [
            f"教学段落 {index}。" for index in range(30)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = self.profile(root)
            nodes = {
                "book": MODULE.SplitNode(
                    "book", "示例教材", None, "root", "示例教材.md", 1, 32, None
                ),
                "lesson": MODULE.SplitNode(
                    "lesson",
                    "1.1 集合",
                    "book",
                    "knowledge",
                    "1.1 集合.md",
                    2,
                    32,
                    "lesson",
                ),
                "topic": MODULE.SplitNode(
                    "topic",
                    "集合",
                    "lesson",
                    "knowledge",
                    "集合.md",
                    5,
                    15,
                    None,
                ),
            }
            manifest = {
                "semantic_review": {
                    "headings": [],
                    "sections": [
                        {
                            "node_key": "lesson",
                            "title": "1.1 集合",
                            "start_line": 2,
                            "end_line": 32,
                            "decision": "split",
                            "child_node_keys": ["topic"],
                            "reason": "The definition arc is independently reusable.",
                            "confidence": 0.96,
                            "reviewed_entire_section": True,
                        }
                    ],
                    "ranges": [
                        {
                            "node_key": "topic",
                            "title": "集合",
                            "start_line": 5,
                            "end_line": 15,
                            "decision": "split",
                            "reason": "Complete definition and examples form one arc.",
                            "independent_teaching_arc": True,
                            "confidence": 0.96,
                        }
                    ],
                }
            }
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

    def test_recovers_unique_namespaced_html_asset_by_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_parent = root / "staging"
            nested = source_parent / "images" / "book" / "part-001"
            target_parent = root / "temporary-output" / "知识点"
            vault_root = root / "vault"
            final_parent = vault_root / "课本" / "示例教材" / "知识点"
            nested.mkdir(parents=True)
            (nested / "figure.png").write_bytes(b"png")
            target_parent.mkdir(parents=True)
            rendered, copied = MODULE.materialize_assets(
                '<img src="images/figure.png"/>\n',
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
                '<img src="/课本/示例教材/知识点/images/figure.png"/>\n',
            )
            self.assertTrue(
                (target_parent / "images" / "figure.png").is_file()
            )

    def test_flattens_namespaced_source_asset_into_category_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_parent = root / "staging"
            nested = source_parent / "images" / "book" / "part-001"
            target_parent = root / "temporary-output" / "知识点"
            vault_root = root / "vault"
            final_parent = vault_root / "课本" / "示例教材" / "知识点"
            nested.mkdir(parents=True)
            (nested / "hash.png").write_bytes(b"png")
            target_parent.mkdir(parents=True)
            rendered, copied = MODULE.materialize_assets(
                "![](images/book/part-001/hash.png)\n",
                source_parent,
                target_parent,
                final_parent,
                vault_root,
                {"asset_mode": "vault-root", "encode_spaces": True},
            )
            self.assertEqual(copied, 1)
            self.assertEqual(
                rendered,
                "![](/课本/示例教材/知识点/images/hash.png)\n",
            )
            self.assertTrue((target_parent / "images" / "hash.png").is_file())


if __name__ == "__main__":
    unittest.main()

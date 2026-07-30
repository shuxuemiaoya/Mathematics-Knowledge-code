from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "lesson_flow_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("lesson_flow_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LessonFlowManifestTests(unittest.TestCase):
    def fixture(
        self,
        root: Path,
        *,
        link_only: bool = False,
    ) -> tuple[Path, Path, Path]:
        formatted = root / "formatted.md"
        profile = root / "book-profile.json"
        split = root / "split-manifest.json"
        formatted.write_text(
            (
                "# 第一章 集合\n"
                "章引言\n"
                "## 1.1 集合的概念\n"
                "为什么需要集合？\n"
                "#### 集合\n"
                "集合正文。\n"
                "承上启下的过渡。\n"
                "继续说明。\n"
                "#### 习题1.1\n"
                "练习正文。\n"
            ),
            encoding="utf-8",
        )
        profile.write_text(
            json.dumps(
                {
                    "book": {
                        "title": "示例教材",
                        "kind": "mathematics-textbook",
                    },
                    "source": {"sha256": "a" * 64},
                    "decomposition": {
                        "semantic_split_confidence_threshold": 0.9,
                        "max_retained_teaching_block_nonblank_lines": 80,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        topic_start = 4 if link_only else 5
        topic_end = 8 if link_only else 6
        split.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": str(profile.resolve()),
                    "source_sha256": "a" * 64,
                    "input_markdown_sha256": MODULE.sha256_file(formatted),
                    "semantic_review": {
                        "headings": [],
                        "sections": [],
                        "ranges": [],
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
                            "toc_key": None,
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
                            "title": "1.1 集合的概念",
                            "parent_key": "chapter",
                            "category": "knowledge",
                            "filename": "1.1 集合的概念.md",
                            "start_line": 3,
                            "end_line": 10,
                            "toc_key": "lesson",
                        },
                        {
                            "key": "topic",
                            "title": "集合",
                            "parent_key": "lesson",
                            "category": "knowledge",
                            "filename": "集合.md",
                            "start_line": topic_start,
                            "end_line": topic_end,
                            "toc_key": None,
                        },
                        {
                            "key": "exercise",
                            "title": "习题1.1",
                            "parent_key": "lesson",
                            "category": "exercise",
                            "filename": "习题1.1.md",
                            "start_line": 9,
                            "end_line": 10,
                            "toc_key": None,
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return formatted, split, profile

    def reviewed_manifest(
        self,
        formatted: Path,
        split: Path,
        profile: Path,
    ) -> dict:
        payload = MODULE.plan(formatted, split, profile)
        payload["status"] = "passed"
        lesson = payload["lessons"][0]
        lesson["reviewed_entire_lesson"] = True
        lesson["reason"] = "Reviewed the complete lesson in source order."
        lesson["confidence"] = 0.98
        lesson["checks"] = {
            name: "passed" for name in MODULE.CHECK_NAMES
        }
        for block in lesson["blocks"]:
            block["confidence"] = 0.98
            block["reason"] = "Reviewed teaching-function boundary."
        lesson["blocks"][0]["role"] = "entry-context"
        lesson["blocks"][1]["role"] = "topic"
        lesson["blocks"][2]["role"] = "transition"
        lesson["blocks"][3]["role"] = "practice"
        return payload

    def test_plans_source_ordered_review_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(Path(temporary))
            payload = MODULE.plan(formatted, split, profile)
        self.assertEqual(payload["status"], "review_required")
        self.assertEqual(len(payload["lessons"]), 1)
        self.assertEqual(
            [
                (item["start_line"], item["end_line"])
                for item in payload["lessons"][0]["blocks"]
            ],
            [(3, 4), (5, 6), (7, 8), (9, 10)],
        )
        self.assertEqual(
            payload["lessons"][0]["draft_findings"],
            [],
        )

    def test_plan_reports_missing_opening_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(
                Path(temporary),
                link_only=True,
            )
            payload = MODULE.plan(formatted, split, profile)
        self.assertEqual(
            payload["lessons"][0]["draft_findings"][0]["code"],
            "opening-preview-missing",
        )

    def test_includes_numbered_non_toc_teaching_subsection(self) -> None:
        split_manifest = {
            "nodes": [
                {
                    "key": "book",
                    "title": "示例教材",
                    "parent_key": None,
                    "category": "root",
                    "start_line": 1,
                    "end_line": 12,
                    "toc_key": None,
                },
                {
                    "key": "section",
                    "title": "3.1 函数的概念及其表示",
                    "parent_key": "book",
                    "category": "knowledge",
                    "start_line": 1,
                    "end_line": 12,
                    "toc_key": "toc-1",
                },
                {
                    "key": "subsection",
                    "title": "3.1.2 函数的表示法",
                    "parent_key": "section",
                    "category": "knowledge",
                    "start_line": 5,
                    "end_line": 12,
                    "toc_key": None,
                },
            ]
        }
        self.assertEqual(
            [node["key"] for node in MODULE.lesson_nodes(split_manifest)],
            ["section", "subsection"],
        )

    def test_valid_review_preserves_context_transition_and_child_topics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(Path(temporary))
            payload = self.reviewed_manifest(formatted, split, profile)
            result = MODULE.validate(
                payload,
                formatted_markdown=formatted,
                split_manifest_path=split,
                profile_path=profile,
            )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["lesson_count"], 1)
        self.assertEqual(result["logical_block_count"], 4)

    def test_rejects_link_only_lesson_without_retained_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(
                Path(temporary),
                link_only=True,
            )
            payload = MODULE.plan(formatted, split, profile)
            payload["status"] = "passed"
            lesson = payload["lessons"][0]
            lesson["reviewed_entire_lesson"] = True
            lesson["confidence"] = 0.98
            lesson["reason"] = "Reviewed."
            lesson["checks"] = {
                name: "passed" for name in MODULE.CHECK_NAMES
            }
            for block in lesson["blocks"]:
                block["confidence"] = 0.98
                block["reason"] = "Reviewed."
            lesson["blocks"][0]["role"] = "entry-context"
            lesson["blocks"][1]["role"] = "topic"
            lesson["blocks"][2]["role"] = "practice"
            with self.assertRaisesRegex(MODULE.LessonFlowError, "link-only"):
                MODULE.validate(
                    payload,
                    formatted_markdown=formatted,
                    split_manifest_path=split,
                    profile_path=profile,
                )

    def test_rejects_moved_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(Path(temporary))
            payload = self.reviewed_manifest(formatted, split, profile)
            context = payload["lessons"][0]["blocks"][1]
            context["role"] = "context"
            with self.assertRaisesRegex(
                MODULE.LessonFlowError,
                "context must remain",
            ):
                MODULE.validate(
                    payload,
                    formatted_markdown=formatted,
                    split_manifest_path=split,
                    profile_path=profile,
                )

    def test_rejects_lesson_without_explicit_entry_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(Path(temporary))
            payload = self.reviewed_manifest(formatted, split, profile)
            payload["lessons"][0]["blocks"][0]["role"] = "analysis"
            with self.assertRaisesRegex(
                MODULE.LessonFlowError,
                "first block must be entry-context",
            ):
                MODULE.validate(
                    payload,
                    formatted_markdown=formatted,
                    split_manifest_path=split,
                    profile_path=profile,
                )

    def test_rejects_unconfirmed_transition_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(Path(temporary))
            payload = self.reviewed_manifest(formatted, split, profile)
            payload["lessons"][0]["checks"][
                "transitions_preserved"
            ] = "not_applicable"
            with self.assertRaisesRegex(
                MODULE.LessonFlowError,
                "transitions_preserved must pass",
            ):
                MODULE.validate(
                    payload,
                    formatted_markdown=formatted,
                    split_manifest_path=split,
                    profile_path=profile,
                )

    def test_accepts_bounded_retained_exposition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.fixture(Path(temporary))
            payload = self.reviewed_manifest(formatted, split, profile)
            payload["lessons"][0]["blocks"][2]["role"] = "exposition"
            result = MODULE.validate(
                payload,
                formatted_markdown=formatted,
                split_manifest_path=split,
                profile_path=profile,
            )
        self.assertEqual(result["status"], "passed")

    def functional_boundary_fixture(
        self,
        root: Path,
    ) -> tuple[Path, Path, Path]:
        formatted = root / "formatted.md"
        profile = root / "book-profile.json"
        split = root / "split-manifest.json"
        formatted.write_text(
            (
                "## 1.2 集合间的基本关系\n"
                "两个集合之间是否也有类似的关系呢？\n"
                "#### 观察\n"
                "观察下面几个例子，你能发现两个集合之间的关系吗？\n"
                "可以发现，集合 A 的任何一个元素都是集合 B 的元素。\n"
                "一般地，如果集合 A 中任意一个元素都是集合 B 中的元素，就称 A 为 B 的子集。\n"
                "思考\n"
                "包含关系与属于关系有什么区别？\n"
                "例 1 写出集合的所有子集。\n"
                "解：逐一列举。\n"
                "例2 判断集合 A 是否为集合 B 的子集。\n"
                "解：根据定义判断。\n"
                "#### 练习\n"
                "1. 写出集合的所有子集。\n"
            ),
            encoding="utf-8",
        )
        profile.write_text(
            json.dumps(
                {
                    "book": {
                        "title": "示例教材",
                        "kind": "mathematics-textbook",
                    },
                    "source": {"sha256": "b" * 64},
                    "decomposition": {
                        "semantic_split_confidence_threshold": 0.9,
                        "max_retained_teaching_block_nonblank_lines": 80,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        split.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": str(profile.resolve()),
                    "source_sha256": "b" * 64,
                    "input_markdown_sha256": MODULE.sha256_file(formatted),
                    "semantic_review": {
                        "headings": [],
                        "sections": [],
                        "ranges": [],
                    },
                    "nodes": [
                        {
                            "key": "book",
                            "title": "示例教材",
                            "parent_key": None,
                            "category": "root",
                            "filename": "示例教材.md",
                            "start_line": 1,
                            "end_line": 14,
                            "toc_key": None,
                        },
                        {
                            "key": "lesson",
                            "title": "1.2 集合间的基本关系",
                            "parent_key": "book",
                            "category": "knowledge",
                            "filename": "1.2 集合间的基本关系.md",
                            "start_line": 1,
                            "end_line": 14,
                            "toc_key": "lesson",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return formatted, split, profile

    def test_plan_splits_observation_examples_and_practice_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.functional_boundary_fixture(
                Path(temporary)
            )
            payload = MODULE.plan(formatted, split, profile)

        blocks = payload["lessons"][0]["blocks"]
        self.assertEqual(
            [block["start_line"] for block in blocks],
            [1, 3, 5, 6, 7, 9, 11, 13],
        )
        self.assertEqual(
            [block["role"] for block in blocks],
            [
                "entry-context",
                "question",
                "exposition",
                "exposition",
                "question",
                "worked-example",
                "worked-example",
                "practice",
            ],
        )

    def test_rejects_reviewed_block_that_crosses_functional_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.functional_boundary_fixture(
                Path(temporary)
            )
            payload = MODULE.plan(formatted, split, profile)
            payload["status"] = "passed"
            lesson = payload["lessons"][0]
            lesson["reviewed_entire_lesson"] = True
            lesson["reason"] = "Reviewed every functional boundary in source order."
            lesson["confidence"] = 0.98
            lesson["checks"] = {
                name: "passed" for name in MODULE.CHECK_NAMES
            }
            for block in lesson["blocks"]:
                block["confidence"] = 0.98
                block["reason"] = "Reviewed source-function boundary."
            lesson["blocks"] = lesson["blocks"][:4] + [
                {
                    "id": "lesson-merged-question",
                    "role": "question",
                    "ownership": "retain-parent",
                    "start_line": 7,
                    "end_line": 14,
                    "child_node_key": None,
                    "representative_anchor": False,
                    "reason": "Incorrectly merged question, examples, and practice.",
                    "confidence": 0.98,
                }
            ]

            with self.assertRaisesRegex(
                MODULE.LessonFlowError,
                "crosses functional boundary",
            ):
                MODULE.validate(
                    payload,
                    formatted_markdown=formatted,
                    split_manifest_path=split,
                    profile_path=profile,
                )

    def test_accepts_reviewed_functional_boundary_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, profile = self.functional_boundary_fixture(
                Path(temporary)
            )
            payload = MODULE.plan(formatted, split, profile)
            payload["status"] = "passed"
            lesson = payload["lessons"][0]
            lesson["reviewed_entire_lesson"] = True
            lesson["reason"] = "Reviewed every functional boundary in source order."
            lesson["confidence"] = 0.98
            lesson["checks"] = {
                name: "passed" for name in MODULE.CHECK_NAMES
            }
            for block in lesson["blocks"]:
                block["confidence"] = 0.98
                block["reason"] = "Reviewed source-function boundary."

            result = MODULE.validate(
                payload,
                formatted_markdown=formatted,
                split_manifest_path=split,
                profile_path=profile,
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["logical_block_count"], 8)


if __name__ == "__main__":
    unittest.main()

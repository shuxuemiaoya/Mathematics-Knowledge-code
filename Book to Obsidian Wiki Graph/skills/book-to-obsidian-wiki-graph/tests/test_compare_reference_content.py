from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "compare_reference_content.py"
)
SPEC = importlib.util.spec_from_file_location("compare_reference_content", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReferenceContentParityTests(unittest.TestCase):
    def test_same_book_finds_aggregated_topic_and_missing_concept(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "知识点").mkdir(parents=True)
            (reference / "知识点").mkdir(parents=True)
            (current / "概念").mkdir()
            (reference / "概念").mkdir()
            (current / "知识点" / "1.1 集合的概念.md").write_text(
                (
                    "## 1.1 集合的概念\n\n"
                    "一般地，我们把研究对象统称为元素，把一些元素组成的总体叫做集合。\n"
                    "下面继续介绍列举法。\n"
                ),
                encoding="utf-8",
            )
            (reference / "知识点" / "集合.md").write_text(
                (
                    "### 集合\n\n"
                    "一般地，我们把研究对象统称为元素，把一些元素组成的总体叫做集合。\n"
                ),
                encoding="utf-8",
            )
            (current / "概念" / "集合.md").write_text("", encoding="utf-8")
            (reference / "概念" / "集合.md").write_text("", encoding="utf-8")
            (reference / "概念" / "元素.md").write_text("", encoding="utf-8")

            report = MODULE.compare(current, reference)

            self.assertTrue(report["same_book"])
            self.assertEqual(report["status"], "content_review_required")
            topic = report["content_decomposition"]["reference_only_notes"][0]
            self.assertEqual(
                topic["best_current"],
                "知识点/1.1 集合的概念.md",
            )
            self.assertEqual(
                topic["classification"],
                "preserved_inside_current_note",
            )
            self.assertEqual(
                report["concept_title_coverage"]["missing_from_current"],
                ["元素"],
            )

    def test_different_books_only_request_architecture_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "甲书"
            reference = root / "乙书"
            current.mkdir()
            reference.mkdir()
            report = MODULE.compare(current, reference)
            self.assertFalse(report["same_book"])
            self.assertEqual(report["status"], "architecture_only_required")

    def test_style_reference_profile_passes_only_compact_nested_style(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "vault" / "甲书"
            reference = root / "reference" / "乙书"
            (current / "知识点").mkdir(parents=True)
            (reference / "知识点").mkdir(parents=True)
            (current / "知识点" / "函数.md").write_text(
                "# 函数\n\n"
                "> [!example]- 例1 求函数值。\n"
                ">\n"
                "> > [!success]- 解\n"
                "> > 代入即可。\n",
                encoding="utf-8",
            )
            (reference / "知识点" / "集合.md").write_text(
                "# 集合\n",
                encoding="utf-8",
            )
            source = root / "source.md"
            source.write_text("# Source\n", encoding="utf-8")
            profile_path = root / "book-profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "source": {
                            "path": str(source.resolve()),
                            "sha256": MODULE.sha256_file(source),
                        },
                        "paths": {"book_root": str(current.resolve())},
                        "reference": {
                            "path": str(reference.resolve()),
                            "sha256": MODULE.inventory_tree_sha256(reference),
                            "scope": "style-only",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            report = MODULE.compare(
                current.resolve(),
                reference.resolve(),
                profile_path=profile_path,
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(
                report["markdown_structure"]["current_style_issue_count"],
                0,
            )

    def test_renamed_exercise_is_not_reported_as_under_split(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "习题").mkdir(parents=True)
            (reference / "习题").mkdir(parents=True)
            body = "## 习题1.1\n\n1. 设集合 A 与集合 B，求它们的交集与并集。\n"
            (current / "习题" / "习题1.1.md").write_text(body, encoding="utf-8")
            (reference / "习题" / "习题1.1 集合的概念.md").write_text(
                body,
                encoding="utf-8",
            )

            report = MODULE.compare(current, reference)

            item = report["content_decomposition"]["reference_only_notes"][0]
            self.assertEqual(item["classification"], "renamed_equivalent")
            self.assertEqual(
                report["blocking_summary"][
                    "reference_notes_preserved_inside_larger_current_notes"
                ],
                0,
            )

    def test_same_path_content_divergence_is_ranked_and_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "概念").mkdir(parents=True)
            (reference / "概念").mkdir(parents=True)
            (current / "概念" / "集合.md").write_text(
                "# 集合\n\n集合 A 包含于集合 B。\n",
                encoding="utf-8",
            )
            (reference / "概念" / "集合.md").write_text(
                "# 集合\n\n把一些元素组成的总体叫做集合。\n",
                encoding="utf-8",
            )

            report = MODULE.compare(current, reference)

            differences = report["content_decomposition"][
                "common_note_differences"
            ]
            self.assertEqual(len(differences), 1)
            self.assertEqual(differences[0]["path"], "概念/集合.md")
            self.assertEqual(
                differences[0]["classification"],
                "content_divergent",
            )
            self.assertEqual(
                report["blocking_summary"][
                    "common_notes_with_divergent_content"
                ],
                1,
            )
            self.assertEqual(report["status"], "content_review_required")

    def test_reviewed_same_book_differences_can_pass_with_exact_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "概念").mkdir(parents=True)
            (reference / "概念").mkdir(parents=True)
            (current / "概念" / "集合.md").write_text(
                "# 集合\n\n当前来源中的完整定义。\n",
                encoding="utf-8",
            )
            (reference / "概念" / "集合.md").write_text(
                "# 集合\n\n旧参考中的简写定义。\n",
                encoding="utf-8",
            )
            source = root / "source.md"
            source.write_text("# source\n", encoding="utf-8")
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "source": {"sha256": MODULE.sha256_file(source)},
                        "paths": {"book_root": str(current.resolve())},
                        "reference": {
                            "path": str(reference.resolve()),
                            "sha256": MODULE.inventory_tree_sha256(reference),
                            "scope": "same-book-content-and-style",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            review = root / "review.json"
            review.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile": str(profile.resolve()),
                        "source_sha256": MODULE.sha256_file(source),
                        "reference_sha256": MODULE.inventory_tree_sha256(reference),
                        "reference_notes": {},
                        "common_notes": {
                            "概念/集合.md": {
                                "decision": "accept-current",
                                "reason": "Current note copies the complete reviewed definition.",
                            }
                        },
                        "missing_concepts": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = MODULE.compare(
                current.resolve(),
                reference.resolve(),
                profile_path=profile.resolve(),
                review_decisions_path=review.resolve(),
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(
                report["blocking_summary"]["common_notes_with_divergent_content"],
                0,
            )
            self.assertEqual(report["review"]["accepted_common_notes"], 1)

    def test_same_path_equivalent_content_is_not_listed_as_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "知识点").mkdir(parents=True)
            (reference / "知识点").mkdir(parents=True)
            body = "# 集合\n\n把一些元素组成的总体叫做集合。\n"
            (current / "知识点" / "集合.md").write_text(
                body,
                encoding="utf-8",
            )
            (reference / "知识点" / "集合.md").write_text(
                body,
                encoding="utf-8",
            )

            report = MODULE.compare(current, reference)

            self.assertEqual(
                report["content_decomposition"]["common_note_differences"],
                [],
            )
            self.assertEqual(
                report["blocking_summary"][
                    "common_notes_with_divergent_content"
                ],
                0,
            )

    def test_reference_empty_but_current_content_is_nonblocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "习题").mkdir(parents=True)
            (reference / "习题").mkdir(parents=True)
            (current / "习题" / "习题4.5.md").write_text(
                "# 习题4.5\n\n1. 求函数的零点。\n",
                encoding="utf-8",
            )
            (reference / "习题" / "习题4.5.md").write_text(
                "# 习题4.5\n",
                encoding="utf-8",
            )

            report = MODULE.compare(current, reference)
            difference = report["content_decomposition"][
                "common_note_differences"
            ][0]

            self.assertEqual(
                difference["classification"],
                "reference_empty_current_content",
            )
            self.assertEqual(
                report["blocking_summary"][
                    "common_notes_with_divergent_content"
                ],
                0,
            )

    def test_same_text_still_flags_broken_current_callout_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "知识点").mkdir(parents=True)
            (reference / "知识点").mkdir(parents=True)
            (current / "知识点" / "集合.md").write_text(
                "# 集合\n\n> [!think] 思考\n\n正文。\n",
                encoding="utf-8",
            )
            (reference / "知识点" / "集合.md").write_text(
                "# 集合\n\n#### 思考\n\n正文。\n",
                encoding="utf-8",
            )

            report = MODULE.compare(current, reference)

            reasons = {
                item["reason"]
                for item in report["markdown_structure"][
                    "current_callout_issues"
                ]
            }
            self.assertEqual(
                reasons,
                {"legacy-callout-type", "missing-quoted-body"},
            )
            self.assertEqual(report["status"], "content_review_required")

    def test_same_path_functional_topology_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current" / "同一本书"
            reference = root / "reference" / "同一本书"
            (current / "知识点").mkdir(parents=True)
            (reference / "知识点").mkdir(parents=True)
            (current / "知识点" / "1.2 集合间的基本关系.md").write_text(
                "## 1.2 集合间的基本关系\n\n"
                "> [!question] 思考\n"
                "> 关系有什么区别？\n"
                "> 例 1 写出所有子集。\n"
                ">\n"
                "> > [!success]- 解\n"
                "> > 逐一列举。\n"
                "> > 例2 判断包含关系。\n"
                "> > #### 练习\n"
                "> > 1. 完成判断。\n",
                encoding="utf-8",
            )
            (reference / "知识点" / "1.2 集合间的基本关系.md").write_text(
                "## 1.2 集合间的基本关系\n\n"
                "> [!question] 思考\n"
                "关系有什么区别？\n\n"
                "> [!example]- 例 1 写出所有子集。\n"
                ">\n"
                "> > [!success]- 解\n"
                "> > 逐一列举。\n\n"
                "> [!example]- 例2 判断包含关系。\n"
                ">\n"
                "> > [!success]- 解\n"
                "> > 根据定义判断。\n\n"
                "#### 练习\n"
                "1. 完成判断。\n",
                encoding="utf-8",
            )

            report = MODULE.compare(current, reference)

            mismatches = report["markdown_structure"][
                "common_functional_topology_mismatches"
            ]
            self.assertEqual(len(mismatches), 1)
            self.assertEqual(
                mismatches[0]["path"],
                "知识点/1.2 集合间的基本关系.md",
            )
            self.assertEqual(report["status"], "content_review_required")
            self.assertEqual(
                report["blocking_summary"][
                    "common_functional_topology_mismatches"
                ],
                1,
            )


if __name__ == "__main__":
    unittest.main()

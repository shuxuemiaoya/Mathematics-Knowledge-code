from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = SKILL_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


audit_tool = load_script("audit_obsidian_graph")


class GraphAuditTests(unittest.TestCase):
    def make_profiled_book(
        self, root: Path
    ) -> tuple[Path, Path, Path, Path, Path, Path]:
        source = root / "source.md"
        source.write_text("# Source\n", encoding="utf-8")
        source_sha256 = audit_tool.sha256_file(source)
        vault = root / "vault"
        book = vault / "books" / "example"
        (book / "主题").mkdir(parents=True)
        (book / "术语").mkdir()
        (book / "主题" / "集合.md").write_text(
            "# 集合\n\n把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
            encoding="utf-8",
        )
        (book / "术语" / "集合.md").write_text(
            "# 集合\n\n来源：[集合](../主题/集合.md)\n\n"
            "## 定义\n\n把研究对象组成的总体叫做集合。\n",
            encoding="utf-8",
        )
        profile_path = root / "book-profile.json"
        profile = {
            "schema_version": 1,
            "book": {"title": "Example"},
            "source": {"path": str(source), "sha256": source_sha256},
            "paths": {
                "vault_root": str(vault.resolve()),
                "book_root": str(book.resolve()),
                "staging_root": str(root.resolve()),
            },
            "categories": [
                {
                    "role": "knowledge",
                    "directory": "主题",
                    "enabled": True,
                    "flat": False,
                },
                {
                    "role": "concept",
                    "directory": "术语",
                    "enabled": True,
                    "flat": True,
                },
            ],
            "links": {"markdown_only": True},
            "formatting": {
                "blank_before_top_level_callout": True,
                "callout_body_mode": "quoted-body",
            },
            "canvas": {
                "enabled": False,
                "node_colors": {},
                "edge_colors": {},
            },
            "workspace": {"backup_policy": "none"},
        }
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False), encoding="utf-8"
        )
        coverage_path = root / "coverage-manifest.json"
        coverage_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": str(profile_path.resolve()),
                    "source_sha256": source_sha256,
                    "units": [
                        {
                            "source_key": "block-1",
                            "source_order": 1,
                            "status": "assigned",
                            "target": "主题/集合.md",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        concept_path = root / "concept-manifest.json"
        concept_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": str(profile_path.resolve()),
                    "source_sha256": source_sha256,
                    "concepts": [
                        {
                            "name": "集合",
                            "target": "术语/集合.md",
                            "linked_from": ["主题/集合.md"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return (
            source,
            vault,
            book,
            profile_path,
            coverage_path,
            concept_path,
        )

    def test_profile_mapped_concept_directory_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                expected_source_sha256=audit_tool.sha256_file(source),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertEqual(report["counts"]["concept_files"], 1)

    def test_frontmatter_does_not_hide_note_or_concept_headings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            frontmatter = "---\n类别: 知识点\n来源: Example\n---\n\n"
            knowledge = book / "主题" / "集合.md"
            concept = book / "术语" / "集合.md"
            knowledge.write_text(
                frontmatter + knowledge.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            concept.write_text(
                frontmatter + concept.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                expected_source_sha256=audit_tool.sha256_file(source),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertNotIn("invalid-note-entry-heading", codes)
            self.assertNotIn("malformed-concept-note-structure", codes)

    def test_rejects_wikilink_and_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n[[残留链接]]\n\n[missing](不存在.md)\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("residual-wikilinks", codes)
            self.assertIn("missing-markdown-link", codes)
            self.assertIn("orphan-concept", codes)

    def test_latex_interval_condition_is_not_a_markdown_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, _ = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n"
                r"在区间 $\left[-\frac{\pi}{2},\frac{\pi}{2}\right]"
                r"(k \in \mathbf{Z})$ 上递增。"
                "\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                stage="split",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertNotIn("missing-markdown-link", codes)
            self.assertEqual(report["counts"]["standard_links"], 1)

    def test_display_math_before_interval_does_not_confuse_inline_scan(self) -> None:
        text = (
            "$$\ny=x^2\n$$\n"
            r"在 $\left[-\pi,\pi\right](k \in \mathbf{Z})$ 上。"
        )
        matches = audit_tool.matches_outside_math(
            audit_tool.MARKDOWN_LINK_RE, text
        )
        self.assertEqual(matches, [])

    def test_markdown_link_with_inline_math_still_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, _ = items
            target = book / "主题" / "4.1.1 $n$ 次方根.md"
            target.write_text("# 4.1.1\n", encoding="utf-8")
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n"
                "[4.1.1 $n$ 次方根](4.1.1%20$n$%20次方根.md)\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                stage="split",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertNotIn("missing-markdown-link", codes)

    def test_embedded_markdown_note_is_a_note_link_not_an_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n![集合概念](../术语/集合.md)\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            self.assertEqual(report["counts"]["embedded_note_links"], 1)
            self.assertEqual(report["counts"]["image_references"], 0)
            self.assertEqual(report["counts"]["missing_markdown_links"], 0)
            self.assertEqual(report["counts"]["missing_images"], 0)
            self.assertEqual(report["counts"]["standard_links"], 2)

    def test_rejects_unstandardized_functional_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n#### 思考\n\n问题。\n\n例 1 求解。\n\n解：答案。\n\n"
                "把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("unstandardized-functional-blocks", codes)
            self.assertEqual(
                report["counts"]["unstandardized_functional_blocks"], 2
            )

    def test_rejects_plain_standalone_functional_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n思考\n\n问题。\n\n"
                "把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="formatting",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("unstandardized-functional-blocks", codes)
            self.assertEqual(
                report["counts"]["unstandardized_functional_blocks"], 1
            )

    def test_example_cross_reference_is_not_a_residual_worked_example(self) -> None:
        self.assertFalse(
            audit_tool.is_unstandardized_worked_example(
                "例 1 中命题（1）给出了一个充分条件。"
            )
        )
        self.assertFalse(
            audit_tool.is_unstandardized_worked_example(
                "例7的结果还可以表示为："
            )
        )
        self.assertTrue(
            audit_tool.is_unstandardized_worked_example("例 1 求方程的解。")
        )

    def test_split_gate_allows_raw_blocks_without_concept_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, _ = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n#### 思考\n\n问题。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                stage="split",
            )
            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertEqual(report["stage"], "split")

    def test_quoted_body_callout_accepts_continuous_lesson_body(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n> [!question] 思考\n> 这段正文属于完整容器。\n\n"
                "把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="formatting",
            )
            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertEqual(report["counts"]["callout_body_violations"], 0)

    def test_quoted_body_callout_rejects_unquoted_lesson_body(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n> [!question] 思考\n\n这段正文错误地落在容器外。\n\n"
                "把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="formatting",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("callout-body-discontinuous", codes)
            self.assertEqual(report["counts"]["callout_body_violations"], 1)

    def test_nested_callout_requires_quoted_body(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n> [!example]- 例 1\n> 题干。\n>\n"
                "> > [!success]- 解\n解答错误地落在嵌套容器外。\n\n"
                "把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="formatting",
            )
            reasons = {
                item.get("reason")
                for item in report["errors"]
                if item["code"] == "callout-body-discontinuous"
            }
            self.assertIn("missing-nested-quoted-body", reasons)

    def test_callout_semantic_scope_rejects_swallowed_lesson_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n"
                "> [!info] 情景引入\n"
                "> 开场问题。\n"
                ">\n"
                "> #### 观察\n"
                "> 观察集合。\n"
                ">\n"
                "> 一般地，把研究对象组成的总体叫做[集合](../术语/集合.md)。\n\n"
                "> [!question] 思考\n"
                "> 思考\n"
                "> 例 1 写出所有子集。\n"
                ">\n"
                "> > [!success]- 解\n"
                "> > 逐一列举。\n"
                "> > 例2 判断包含关系。\n"
                "> > #### 练习\n"
                "> > 1. 完成判断。\n",
                encoding="utf-8",
            )

            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="formatting",
            )

            semantic = [
                item
                for item in report["errors"]
                if item["code"] == "callout-semantic-scope"
            ]
            reasons = {item["reason"] for item in semantic}
            self.assertIn("functional-heading-inside-callout", reasons)
            self.assertIn(
                "formal-definition-inside-question-or-situation-callout",
                reasons,
            )
            self.assertIn("duplicate-functional-label-inside-callout", reasons)
            self.assertIn("worked-example-inside-non-example-callout", reasons)
            self.assertIn("practice-inside-callout", reasons)
            self.assertGreaterEqual(
                report["counts"]["callout_semantic_scope_violations"],
                5,
            )

    def test_callout_semantic_scope_allows_symmetric_axis_question(self) -> None:
        text = (
            "> [!question] 思考\n"
            "> 顶点在原点，对称轴是坐标轴，并且经过点 M 的抛物线有几条？"
            "求出这些抛物线的标准方程。\n"
        )

        issues = audit_tool.callout_semantic_scope_issues(
            Path("抛物线的离心率.md"),
            text,
        )

        self.assertEqual(issues, [])

    def test_content_consistency_flags_ocr_omissions_and_flat_reasoning(self) -> None:
        text = (
            "# 指数函数的概念\n\n"
            "一般地，函数 $y=a^x (a>0$，且 $a\\ne1$ 叫做指数函数。\n\n"
            "> [!example]- 例2 求下列函数的定义域：（1）$y=2^x$\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > （1）定义域为 $R$；（2）定义域为 $R$。\n\n"
            "> [!info] 问题 1\n"
            "> 观察函数。\n"
            "> 分析：比较定义域。\n"
        )
        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)
        reasons = {item["reason"] for item in issues}
        self.assertIn("unbalanced-parentheses-in-formal-definition", reasons)
        self.assertIn("solution-subpart-missing-from-example-stem", reasons)
        self.assertIn("reasoning-label-not-nested", reasons)

    def test_content_consistency_reads_all_stem_subparts_on_one_line(self) -> None:
        text = (
            "> [!example]- 例 1 求值：\n"
            "> （1）$a$；（2）$b$；（3）$c$；（4）$d$。\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > （1）1；（2）2；（3）3；（4）4。\n"
        )

        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)

        self.assertNotIn(
            "solution-subpart-missing-from-example-stem",
            {item["reason"] for item in issues},
        )

    def test_content_consistency_allows_numbered_proof_steps_for_single_stem(self) -> None:
        text = (
            "> [!example]- 例 1 证明命题成立。\n"
            ">\n"
            "> > [!success]- 证明\n"
            "> > （1）充分性：由条件可得结论。\n"
            "> > （2）必要性：由结论可得条件。\n"
        )

        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)

        self.assertNotIn(
            "solution-subpart-missing-from-example-stem",
            {item["reason"] for item in issues},
        )

    def test_content_consistency_ignores_numbered_method_summary_after_solution(
        self,
    ) -> None:
        text = (
            "> [!example]- 例 6 求下列距离。\n"
            "> （1）求点到直线的距离；（2）求直线到平面的距离。\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > （1）距离为 $a$。\n"
            "> > （2）距离为 $b$。\n"
            "> > 与平面向量方法类似，可得三步曲：\n"
            "> > （1）建立向量联系；\n"
            "> > （2）进行向量运算；\n"
            "> > （3）翻译成几何结论。\n"
        )

        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)

        self.assertNotIn(
            "solution-subpart-missing-from-example-stem",
            {item["reason"] for item in issues},
        )

    def test_content_consistency_ignores_steps_introduced_by_anru_buzhou(self) -> None:
        text = (
            "> [!example]- 例 7 作出函数图象。\n"
            "> （1）求定义域；（2）求导；（3）作图。\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > （1）定义域为 R。\n"
            "> > （2）导数为 $f'(x)$。\n"
            "> > （3）图象如图。\n"
            "> > 通常，可以按如下步骤画出函数图象：\n"
            "> > （1）确定定义域；（2）求导；（3）列表；（4）描点；（5）连线。\n"
        )

        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)

        self.assertNotIn(
            "solution-subpart-missing-from-example-stem",
            {item["reason"] for item in issues},
        )

    def test_content_consistency_ignores_case_classes_after_solution(self) -> None:
        text = (
            "> [!example]- 例 8 计算符合条件的序号数。\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > 5 位序号可以分为三类：\n"
            "> > （1）首位非零；（2）末位非零；（3）其余情形。\n"
        )

        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)

        self.assertNotIn(
            "solution-subpart-missing-from-example-stem",
            {item["reason"] for item in issues},
        )

    def test_content_consistency_ignores_function_arguments_as_subparts(self) -> None:
        text = (
            "> [!example]- 例 2 （1）比较两个模型。\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > （1）当 $x=0$ 时比较。\n"
            "> > （2）计算 $g(14)$ 与 $h(10000)$。\n"
        )

        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)
        issue = next(
            item
            for item in issues
            if item["reason"] == "solution-subpart-missing-from-example-stem"
        )

        self.assertEqual(issue["missing_subparts"], [2])

    def test_content_consistency_ignores_derivative_constants_and_percentages(self) -> None:
        text = (
            "> [!example]- 例 5 求下列变化率：\n"
            "> （1）90%；（2）98%。\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > （1）$c'(90)=52.84$。\n"
            "> > （2）$c'(98)=1321$，且 $(3)'=0$。\n"
        )

        issues = audit_tool.content_consistency_issues(Path("知识点/样例.md"), text)

        self.assertNotIn(
            "solution-subpart-missing-from-example-stem",
            {item["reason"] for item in issues},
        )

    def test_formatting_gate_rejects_ocr_damage_and_plain_running_header(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n"
                "第二章 一元二次函数、方程和不等式\n\n"
                "$$x^2-1 2x+2 0<0$$\n\n"
                "<table><tr><td>根</td><td>\\(x_1=2$</td></tr></table>\n\n"
                "把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )

            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="formatting",
            )

            codes = {item["code"] for item in report["errors"]}
            self.assertIn("plain-running-chapter-headers", codes)
            self.assertIn("suspicious-ocr-spaced-digits-in-math", codes)
            self.assertIn("malformed-html-table-content", codes)
            self.assertEqual(report["counts"]["plain_running_headers"], 1)
            self.assertEqual(
                report["counts"]["suspicious_ocr_math_fragments"], 2
            )
            self.assertEqual(report["counts"]["malformed_table_blocks"], 1)

    def test_split_gate_defers_ocr_content_quality_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, _ = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n"
                "216 第五章 三角函数\n\n"
                "$$x=1 2$$\n\n"
                "<table><tr><td>\\(x$</td></tr></table>\n",
                encoding="utf-8",
            )

            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                stage="split",
            )

            codes = {item["code"] for item in report["errors"]}
            self.assertNotIn("plain-running-chapter-headers", codes)
            self.assertNotIn("suspicious-ocr-spaced-digits-in-math", codes)
            self.assertNotIn("malformed-html-table-content", codes)

    def test_new_textbook_profile_requires_lesson_flow_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile_path, coverage, _ = items
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["book"]["kind"] = "mathematics-textbook"
            profile["decomposition"] = {
                "require_lesson_flow_manifest": True
            }
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False),
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile_path.resolve(),
                coverage_manifest=coverage.resolve(),
                stage="split",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("lesson-flow-manifest-not-provided", codes)

    def test_concepts_gate_requires_concept_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, _ = items
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                stage="concepts",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("concept-manifest-not-provided", codes)

    def test_rejects_malformed_entry_heading_and_concept_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "x## 集合\n\n把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )
            (book / "术语" / "集合.md").write_text(
                "把研究对象组成的总体叫做集合。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="concepts",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("invalid-note-entry-heading", codes)
            self.assertIn("malformed-concept-note-structure", codes)

    def test_rejects_teaching_boundary_inside_concept_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "术语" / "集合.md").write_text(
                "# 集合\n\n来源：[集合](../主题/集合.md)\n\n"
                "## 定义\n\n"
                "> [!question] 探究\n"
                "> 哪些对象应当归入总体？\n\n"
                "把研究对象组成的总体叫做集合。\n",
                encoding="utf-8",
            )

            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="concepts",
            )

            codes = {item["code"] for item in report["errors"]}
            self.assertIn("concept-definition-crosses-teaching-boundary", codes)
            self.assertEqual(
                report["counts"]["concept_definition_boundary_violations"],
                1,
            )

    def test_vault_root_note_mode_requires_leading_slash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile_path, coverage, _ = items
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["links"]["note_mode"] = "vault-root"
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False), encoding="utf-8"
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile_path.resolve(),
                coverage_manifest=coverage.resolve(),
                stage="split",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("non-vault-root-note-link", codes)

    def test_final_gate_requires_profile_enabled_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile_path, coverage, concepts = items
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["canvas"]["enabled"] = True
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False), encoding="utf-8"
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile_path.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
                stage="final",
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("required-canvas-missing", codes)

    def test_canvas_audit_rejects_residual_wikilinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canvas = root / "example.canvas"
            canvas.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "legacy",
                                "type": "text",
                                "text": "[[books/example/topic|Topic]]",
                                "x": 0,
                                "y": 0,
                                "width": 200,
                                "height": 60,
                            }
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            summary, errors, _ = audit_tool.audit_canvas(
                canvas,
                root,
                root,
            )

            self.assertEqual(summary["wikilinks"], 1)
            self.assertIn(
                "canvas-residual-wikilinks",
                {item["code"] for item in errors},
            )


if __name__ == "__main__":
    unittest.main()

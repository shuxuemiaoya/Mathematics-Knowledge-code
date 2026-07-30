import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "standardize_markdown.py"
SPEC = importlib.util.spec_from_file_location("standardize_markdown", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class StandardizeMarkdownTests(unittest.TestCase):
    def test_converts_complete_callouts_and_preserves_stem(self):
        source = (
            "## 章节\n\n#### 思考\n\n问题正文\n\n"
            "例 1 求 $x$。\n\n解：保留过程。\n"
        )
        output, changes = MODULE.standardize_text(source)
        self.assertIn("> [!question] 思考\n> 问题正文", output)
        self.assertIn(
            "> [!example]- 例 1 求 $x$。\n>\n> > [!success]- 解\n"
            "> > 保留过程。",
            output,
        )
        self.assertEqual(changes["converted_headings"], 1)
        self.assertEqual(changes["converted_examples"], 1)
        self.assertTrue(all(MODULE.invariants(source, output).values()))

    def test_quotes_formula_image_html_table_and_blank_lines(self):
        source = (
            "#### 探究\n\n观察下图。\n\n"
            "$$y=x^2$$\n\n"
            "<img src=\"images/a.png\" />\n\n"
            "<table>\n<tr><td>1</td></tr>\n</table>\n"
        )
        output, _ = MODULE.standardize_text(source)
        self.assertIn("> [!question] 探究", output)
        self.assertIn("> $$y=x^2$$", output)
        self.assertIn('> <img src="images/a.png" />', output)
        self.assertIn("> <table>\n> <tr><td>1</td></tr>\n> </table>", output)
        self.assertIn(">\n> $$y=x^2$$", output)
        self.assertTrue(MODULE.valid_quoted_callouts(output))

    def test_nested_callout_requires_parent_and_quotes_every_line(self):
        source = (
            "例2 证明结论。\n\n分析：先观察。\n\n"
            "解：\n\n$$x=1$$\n\n<img src=\"images/a.png\" />\n"
        )
        output, _ = MODULE.standardize_text(source)
        self.assertIn("> > [!tip]- 分析\n> > 先观察。", output)
        self.assertIn(
            "> > [!success]- 解\n> >\n> > $$x=1$$\n> >\n"
            '> > <img src="images/a.png" />',
            output,
        )
        self.assertTrue(MODULE.valid_quoted_callouts(output))

    def test_adjacent_examples_and_practice_remain_separate_top_level_blocks(self):
        source = (
            "## 1.2 集合间的基本关系\n\n"
            "例 1 写出所有子集。\n\n"
            "解：逐一列举。\n\n"
            "例2 判断包含关系。\n\n"
            "解：根据定义判断。\n\n"
            "#### 练习\n\n"
            "1. 完成判断。\n"
        )

        output, _ = MODULE.standardize_text(source)

        self.assertEqual(output.count("> [!example]-"), 2)
        self.assertEqual(output.count("> > [!success]- 解"), 2)
        self.assertIn("\n#### 练习\n\n1. 完成判断。", output)
        self.assertNotIn("> #### 练习", output)
        self.assertNotIn("> > #### 练习", output)
        self.assertTrue(MODULE.valid_quoted_callouts(output))

    def test_plain_problem_context_becomes_info_container(self):
        source = "问题 1 某地人口增长如下。\n\n观察数据。\n\n#### 思考\n\n为什么？\n"
        output, _ = MODULE.standardize_text(source)
        self.assertIn("> [!info] 问题 1\n> 某地人口增长如下。\n>\n> 观察数据。", output)
        self.assertIn("> [!question] 思考\n> 为什么？", output)

    def test_context_analysis_is_nested_like_reference_style(self):
        source = (
            "问题 1 观察三个函数。\n\n"
            "分析：先比较定义域，再归纳共同特征。\n"
        )
        output, _ = MODULE.standardize_text(source)
        self.assertIn("> [!info] 问题 1\n> 观察三个函数。", output)
        self.assertIn(
            "> > [!tip]- 分析\n"
            "> > 先比较定义域，再归纳共同特征。",
            output,
        )

    def test_compacts_existing_example_callout_stem(self):
        source = (
            "# 章节\n\n"
            "> [!example]- 例 2\n"
            "> 求函数值。\n"
            ">\n"
            "> > [!success]- 解\n"
            "> > 代入即可。\n"
        )
        output, changes = MODULE.standardize_text(source)
        self.assertIn("> [!example]- 例 2 求函数值。\n>", output)
        self.assertNotIn("> [!example]- 例 2\n> 求函数值。", output)
        self.assertEqual(changes["compacted_example_stems"], 1)
        self.assertTrue(MODULE.valid_quoted_callouts(output))

    def test_nests_reasoning_in_existing_context_callout(self):
        source = (
            "# 章节\n\n"
            "> [!info] 问题 1\n"
            "> 观察三个函数。\n"
            ">\n"
            "> 分析：比较定义域。\n"
            "> 再归纳共同特征。\n"
        )
        output, changes = MODULE.standardize_text(source)
        self.assertIn(
            "> > [!tip]- 分析\n"
            "> > 比较定义域。\n"
            "> > 再归纳共同特征。",
            output,
        )
        self.assertEqual(changes["nested_existing_reasoning_blocks"], 1)
        self.assertTrue(MODULE.valid_quoted_callouts(output))

    def test_plain_standalone_functional_label_ends_previous_context(self):
        source = (
            "问题 1 情景正文。\n\n推导。\n\n思考\n\n这个结论正确吗？\n\n"
            "问题 2 下一情景。\n"
        )
        output, _ = MODULE.standardize_text(source)
        self.assertIn("> [!info] 问题 1\n> 情景正文。\n>\n> 推导。", output)
        self.assertIn("> [!question] 思考\n> 这个结论正确吗？", output)
        self.assertIn("> [!info] 问题 2\n> 下一情景。", output)
        self.assertNotIn("> 思考", output)

    def test_context_cross_reference_remains_ordinary_question(self):
        source = (
            "问题 1 第一情景。\n\n推导。\n\n"
            "问题 1 和问题 2 中的函数相同吗？\n\n"
            "问题 3 下一情景。\n"
        )
        output, changes = MODULE.standardize_text(source)
        self.assertIn("> [!info] 问题 1\n> 第一情景。\n>\n> 推导。", output)
        self.assertIn("\n\n问题 1 和问题 2 中的函数相同吗？\n\n", output)
        self.assertIn("> [!info] 问题 3\n> 下一情景。", output)
        self.assertNotIn("> 问题 1 和问题 2", output)

    def test_splits_inline_solution_out_of_analysis(self):
        source = "例1 求值。\n\n分析：先确定参数。解：代入可得 $x=1$。\n"
        output, _ = MODULE.standardize_text(source)
        self.assertIn("> > [!tip]- 分析\n> > 先确定参数。", output)
        self.assertIn("> > [!success]- 解\n> > 代入可得 $x=1$。", output)

    def test_example_instruction_prove_is_kept_as_parent_stem(self):
        source = "例3 证明\n\n(1) 公式一；\n\n(2) 公式二。\n\n证明：由公式可得。\n"
        output, _ = MODULE.standardize_text(source)
        self.assertIn("> [!example]- 例3 证明\n> (1) 公式一；", output)
        self.assertIn("> > [!success]- 证明\n> > 由公式可得。", output)

    def test_keeps_exercises_and_h1_h3(self):
        source = "# 章\n\n### 节\n\n#### 练习\n\n1. 题目\n"
        output, _ = MODULE.standardize_text(source)
        self.assertEqual(output, source)

    def test_latex_interval_is_not_a_protected_markdown_link(self):
        before = "$x\\in\\left[0,+\\infty\\right](k\\in\\mathbf Z)$\n\n\n"
        after, _ = MODULE.standardize_text(before)
        self.assertTrue(MODULE.invariants(before, after)["links"])

    def test_removes_ornament_and_category_running_header_headings(self):
        source = (
            "### 1.1.1 示例\n\n#### ● ●\n\n正文。\n\n"
            "#### 人民教育出版社\n\n后文。\n"
        )
        output, changes = MODULE.standardize_text(
            source,
            remove_running_headers=True,
        )
        self.assertNotIn("● ●", output)
        self.assertNotIn("#### 人民教育出版社", output)
        self.assertIn("正文。", output)
        self.assertIn("后文。", output)
        self.assertEqual(changes["removed_artifact_headings"], 2)

    def test_removes_plain_chapter_running_headers_in_category_notes(self):
        source = (
            "### 子节\n\n104 第四章 指数函数与对数函数\n\n正文。\n"
            "第五章 三角函数\n"
        )
        output, changes = MODULE.standardize_text(
            source,
            remove_running_headers=True,
        )
        self.assertNotIn("第四章 指数函数与对数函数", output)
        self.assertNotIn("第五章 三角函数", output)
        self.assertIn("正文。", output)
        self.assertEqual(changes["removed_artifact_headings"], 2)

    def test_repairs_spaced_digits_only_inside_math(self):
        source = (
            "页码 1 0 不改。\n\n"
            "$L=1 0\\lg(1 0^{-1 2})$\n\n"
            "$$y=0. 0 3t+1 . 1 1$$\n"
        )
        output, changes = MODULE.standardize_text(source)
        self.assertIn("页码 1 0 不改。", output)
        self.assertIn("$L=10\\lg(10^{-12})$", output)
        self.assertIn("$$y=0.03t+1.11$$", output)
        self.assertGreater(changes["repaired_ocr_math_fragments"], 0)

    def test_does_not_convert_example_cross_reference(self):
        source = "例 1 中命题（1）给出了一个充分条件。\n\n例7的结果还可以表示为：\n"
        output, changes = MODULE.standardize_text(source)
        self.assertEqual(output, source)
        self.assertEqual(changes["converted_examples"], 0)

    def test_new_textbook_run_requires_lesson_flow_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = root / "book"
            book.mkdir()
            (book / "lesson.md").write_text(
                "# Lesson\n",
                encoding="utf-8",
            )
            profile = root / "book-profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "book": {"kind": "mathematics-textbook"},
                        "source": {"sha256": "a" * 64},
                        "paths": {"book_root": str(book.resolve())},
                        "decomposition": {
                            "require_lesson_flow_manifest": True
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "requires a lesson-flow manifest",
            ):
                MODULE.run(profile, root / "report.json")


if __name__ == "__main__":
    unittest.main()

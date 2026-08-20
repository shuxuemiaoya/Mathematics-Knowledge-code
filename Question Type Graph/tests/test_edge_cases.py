from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from question_type_graph.answers import (
    extract_composite_short_answer,
    extract_choice_answer,
    extract_nonchoice_answer_prefix,
    format_answer_callout,
    parse_answer_blocks,
    strategy_candidates,
)
from question_type_graph.audit import (
    answer_without_question_errors,
    has_duplicate_leading_heading,
    path_has_forbidden_colon,
    question_has_fragmented_html_table,
    question_count_expectation_errors,
    question_requires_choice_answer,
    question_sequence_errors,
    valid_solution_note,
)
from question_type_graph.common import (
    ConfigurationError,
    prune_empty_directories,
    safe_name,
    sha256_text,
    write_json_atomic,
)
from question_type_graph.content import (
    apply_reviewed_recovered_question_fragments,
    apply_reviewed_recovered_questions,
    apply_reviewed_semantic_line_exclusions,
    apply_reviewed_virtual_span_relocations,
    compile_question_patterns,
    compile_role_rules,
    plan_content,
    plan_note,
    render_question,
    split_authoritative_solution_body,
    split_worked_example_body,
    split_inline_question_headers,
)
from question_type_graph.hierarchy import apply_hierarchy, normalize_generated_output, plan_hierarchy
from question_type_graph.inventory import build_adapter_draft, build_inventory, inventory_markdown, parse_index_entry
from question_type_graph.profile import create_profile
from question_type_graph.supplement import apply_supplement, plan_supplement


class TestEdgeCases(unittest.TestCase):
    def test_reviewed_semantic_line_exclusion_preserves_frozen_raw(self) -> None:
        raw_lines = [
            "【例题选讲】",
            "[例 1](1)重复的短文本块",
            "[例1](1)完整题干 答案 2 解析 正文",
        ]
        virtual_lines = [
            {"text": line, "raw_line": index, "raw_column": 1}
            for index, line in enumerate(raw_lines, 1)
        ]
        adapter = {
            "content": {
                "reviewed_semantic_line_exclusions": [
                    {
                        "context": "examples-1",
                        "raw_line": 2,
                        "source_page": 6,
                        "source_bbox": [1, 2, 3, 4],
                        "anchor_text": "[例 1](1)重复的短文本块",
                        "reason": "overlapping OCR duplicate",
                        "reviewer_confirmed": True,
                    }
                ]
            }
        }
        result = apply_reviewed_semantic_line_exclusions(
            virtual_lines, raw_lines, "examples-1", adapter
        )
        self.assertEqual(
            [line["text"] for line in result],
            ["【例题选讲】", "[例1](1)完整题干 答案 2 解析 正文"],
        )
        self.assertEqual(raw_lines[1], "[例 1](1)重复的短文本块")
        self.assertEqual(
            adapter["_reviewed_semantic_line_exclusions_applied"][0][
                "source_page"
            ],
            6,
        )

    def test_reviewed_question_count_expectation_blocks_missing_packet(self) -> None:
        questions = [
            {"context_key": "examples-2", "question_kind": "worked-example"}
            for _ in range(7)
        ]
        expectations = [
            {"context": "examples-2", "kind": "worked-example", "count": 8}
        ]
        self.assertEqual(
            question_count_expectation_errors(questions, expectations),
            [
                {
                    "kind": "question-count-expectation-mismatch",
                    "context": "examples-2",
                    "question_kind": "worked-example",
                    "expected": 8,
                    "actual": 7,
                }
            ],
        )

    def test_duplicate_leading_heading_is_blocking_audit_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            note = Path(tmp_dir) / "topic.md"
            note.write_text(
                "# 专题01 五组秒杀公式模型\n\n## 专题01  五组秒杀公式模型\n正文。\n",
                encoding="utf-8",
            )
            self.assertTrue(has_duplicate_leading_heading(note))
            note.write_text(
                "# 专题01 五组秒杀公式模型\n\n正文。\n",
                encoding="utf-8",
            )
            self.assertFalse(has_duplicate_leading_heading(note))

    def test_composite_short_answer_uses_ordered_explicit_headers(self) -> None:
        body = "\n".join(
            [
                "答案 B 解析 第一问解析。",
                "后续推导不作为答案。",
                "答案 $[2,+\\infty)$ 解析 第二问解析。",
            ]
        )

        self.assertEqual(
            extract_composite_short_answer(body),
            "(1) B；(2) $[2,+\\infty)$",
        )
        self.assertIsNone(extract_composite_short_answer("解析：没有显式答案"))

    def test_recovered_question_fragments_enhance_virtual_copy_only(self) -> None:
        raw_lines = [
            "16. 分别求下列函数的导数:",
            "y = e^x \\ln x; (2) y=x^2",
            "14. 值为（ A.1 B.2 C.3 D.4",
        ]
        virtual_lines = [
            {
                "text": text,
                "raw_line": index,
                "raw_column": 1,
                "subline": 0,
            }
            for index, text in enumerate(raw_lines, 1)
        ]
        q14_column = raw_lines[2].index("A.1") + 1
        adapter = {
            "content": {
                "recovered_question_fragments": [
                    {
                        "context": "unit",
                        "raw_line": 2,
                        "raw_column": 1,
                        "position": "before",
                        "text": "(1) ",
                        "source_page": 5,
                        "source_bbox": [1, 2, 3, 4],
                        "anchor_text": raw_lines[1],
                        "reviewer_confirmed": True,
                    },
                    {
                        "context": "unit",
                        "raw_line": 3,
                        "raw_column": q14_column,
                        "position": "before",
                        "text": "）",
                        "source_page": 5,
                        "source_bbox": [5, 6, 7, 8],
                        "anchor_pattern": r"值为（ A\.1",
                        "reviewer_confirmed": True,
                    },
                ]
            }
        }

        enhanced = apply_reviewed_recovered_question_fragments(
            virtual_lines, raw_lines, "unit", adapter
        )

        self.assertEqual(raw_lines[1], "y = e^x \\ln x; (2) y=x^2")
        self.assertTrue(enhanced[1]["text"].startswith("(1) y = e^x"))
        self.assertIn("值为（ ）A.1", enhanced[2]["text"])
        recoveries = enhanced[1]["recovered_question_fragments"]
        self.assertEqual(recoveries[0]["source_page"], 5)
        self.assertEqual(recoveries[0]["source_bbox"], [1, 2, 3, 4])

    def test_worked_examples_are_atomic_important_and_separate_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph = root / "graph"
            graph.mkdir()
            source = graph / "unit.md"
            source.write_text(
                "## 研究密钥\n公式结论。\n\n"
                "例 1.1 求函数值。\n## 解析\n由定义计算，得到完整结论。\n\n"
                "变式1: 求另一个函数值。\n分析：同理可得另一个完整结论。\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(graph),
                "content": {
                    "question_folder": "训练题",
                    "question_title_template": "题 {number}",
                    "question_patterns": [
                        r"^(?P<number>例\s*\d+(?:\.\d+)?)\s*",
                        r"^(?P<number>变式\s*\d+)\s*[：:]?\s*",
                    ],
                    "inline_question_patterns": [],
                    "question_kind_rules": [
                        {
                            "kind": "worked-example",
                            "pattern": r"^(?:例|变式)",
                            "answer_handling": "separate-authoritative",
                            "preserve_internal_headings": True,
                            "folder": "例题",
                        }
                    ],
                    "worked_example_solution_patterns": [
                        r"^\s*(?:#{1,6}\s*)?(?:分析|解析)(?:\s|[：:]|$)"
                    ],
                    "question_scopes": [
                        {"contexts": ["unit"], "kinds": ["worked-example"]}
                    ],
                    "roles": [],
                    "unknown_label_policy": "retain",
                },
            }
            note = {
                "key": "unit",
                "title": "Unit",
                "path": str(source),
                "content_source": str(source),
                "answer_context": "unit",
            }

            _, questions, review = plan_note(
                note,
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual(review, [])
            self.assertEqual(len(questions), 2)
            self.assertTrue(all(q["question_kind"] == "worked-example" for q in questions))
            self.assertTrue(all(q["answer_handling"] == "separate-authoritative" for q in questions))
            self.assertTrue(all(q["metadata"] == {"重要程度": "重要"} for q in questions))
            self.assertIn("/例题/", questions[0]["output"])
            first_body = source.read_text(encoding="utf-8").split("变式1", 1)[0]
            question_body, answer_body, solution_offset = split_worked_example_body(
                first_body, adapter
            )
            rendered = render_question(questions[0], question_body)
            self.assertIn('question_kind: "worked-example"', rendered)
            self.assertIn('answer_handling: "separate-authoritative"', rendered)
            self.assertIn('重要程度: "重要"', rendered)
            self.assertIn("answer_status: matched", rendered)
            self.assertNotIn("## 解析", rendered)
            self.assertIn("## 解析", answer_body)
            self.assertIsNotNone(solution_offset)

    def test_worked_example_stem_word_jiexishi_is_not_a_solution_boundary(self) -> None:
        body = "4. 函数的解析式可能为（ ）\nA. 甲 B. 乙\n【答案】B\n【解析】由图可得。\n"
        adapter = {
            "content": {
                "worked_example_solution_patterns": [r"^\s*【答案】"]
            }
        }

        question, answer, offset = split_worked_example_body(body, adapter)

        self.assertIn("解析式可能为", question)
        self.assertIn("A. 甲 B. 乙", question)
        self.assertTrue(answer.startswith("【答案】B"))
        self.assertEqual(offset, 2)

    def test_interleaved_teacher_edition_keeps_subpart_stems_together(self) -> None:
        body = (
            "[例2] (1) 求参数。\n"
            "答案 1 解析：由条件可得。\n"
            "(2) 选择正确结论（ ）\n"
            "A. 甲 B. 乙\n"
            "答案 B 解析：逐项验证。\n"
        )
        adapter = {"content": {"worked_example_solution_backtrack_fence": True}}
        config = {
            "solution_layout": "interleaved",
            "solution_start_patterns": [r"^\s*答案\b"],
            "solution_resume_patterns": [r"^\s*\(\d+\)"],
        }

        question, answer, offset = split_authoritative_solution_body(
            body, adapter, config
        )

        self.assertIn("[例2] (1) 求参数。", question)
        self.assertIn("(2) 选择正确结论", question)
        self.assertIn("A. 甲 B. 乙", question)
        self.assertNotIn("答案 1", question)
        self.assertNotIn("答案 B", question)
        self.assertIn("答案 1 解析：由条件可得。", answer)
        self.assertIn("答案 B 解析：逐项验证。", answer)
        self.assertNotIn("(2) 选择正确结论", answer)
        self.assertEqual(offset, 1)

    def test_interleaved_example_packet_atomizes_independent_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            graph = Path(tmp_dir) / "graph"
            graph.mkdir()
            source = graph / "unit.md"
            source.write_text(
                "[例 1] (1) 第一题（ ）\nA. 甲 B. 乙\n"
                "答案 A 解析：第一题解析。\n"
                "(2) 第二题（ ）\nA. 丙 B. 丁\n"
                "答案 B 解析：第二题解析。\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(graph),
                "content": {
                    "question_folder": "题目",
                    "question_title_template": "题_{number}",
                    "question_patterns": [r"^\[(?P<number>例\s*\d+)\]\s*"],
                    "inline_question_patterns": [],
                    "question_kind_rules": [
                        {
                            "kind": "worked-example",
                            "pattern": r"^\[例\s*\d+\]",
                            "answer_handling": "separate-authoritative",
                            "solution_layout": "interleaved",
                            "solution_start_patterns": [r"^\s*答案\b"],
                            "solution_resume_patterns": [r"^\s*\(\d+\)"],
                            "atomize_interleaved_subquestions": True,
                            "atomized_subquestion_patterns": [
                                r"^\s*(?:\[例\s*\d+\]\s*)?\((?P<part>\d+)\)"
                            ],
                            "atomized_number_template": "{number}({part})",
                            "folder": "例题",
                        }
                    ],
                    "question_scopes": [
                        {"contexts": ["unit"], "kinds": ["worked-example"]}
                    ],
                    "roles": [],
                    "unknown_label_policy": "retain",
                },
            }
            note = {
                "key": "unit",
                "title": "Unit",
                "path": str(source),
                "content_source": str(source),
                "answer_context": "unit",
            }

            _, questions, review = plan_note(
                note,
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual(review, [])
            self.assertEqual([q["number"] for q in questions], ["例 1(1)", "例 1(2)"])
            self.assertEqual(len(questions), 2)
            self.assertTrue(all(q["answer_body_sha256"] for q in questions))
            self.assertEqual(questions[0]["source_markdown_line"], None)

    def test_shared_stem_example_with_one_solution_remains_composite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            graph = Path(tmp_dir) / "graph"
            graph.mkdir()
            source = graph / "unit.md"
            source.write_text(
                "[例 8] (1) 求面积最大值。\n"
                "(2) 求数量积范围。\n"
                "解析 (1) 先求面积。\n"
                "(2) 再求数量积。\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(graph),
                "content": {
                    "question_folder": "题目",
                    "question_title_template": "题_{number}",
                    "question_patterns": [r"^\[(?P<number>例\s*\d+)\]\s*"],
                    "inline_question_patterns": [],
                    "question_kind_rules": [
                        {
                            "kind": "worked-example",
                            "pattern": r"^\[例\s*\d+\]",
                            "answer_handling": "separate-authoritative",
                            "solution_layout": "interleaved",
                            "solution_start_patterns": [r"^\s*解析\b"],
                            "solution_resume_patterns": [r"^\s*\(\d+\)"],
                            "atomize_interleaved_subquestions": True,
                            "atomized_subquestion_patterns": [
                                r"^\s*(?:\[例\s*\d+\]\s*)?\((?P<part>\d+)\)"
                            ],
                            "atomized_number_template": "{number}({part})",
                            "folder": "例题",
                        }
                    ],
                    "question_scopes": [
                        {"contexts": ["unit"], "kinds": ["worked-example"]}
                    ],
                    "roles": [],
                    "unknown_label_policy": "retain",
                },
            }
            note = {
                "key": "unit",
                "title": "Unit",
                "path": str(source),
                "content_source": str(source),
                "answer_context": "unit",
            }

            _, questions, review = plan_note(
                note,
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual(review, [])
            self.assertEqual([q["number"] for q in questions], ["例 8"])
            self.assertIn("(2) 求数量积范围", questions[0]["body"])
            self.assertEqual(questions[1]["source_start_line"], 4)

    def test_inline_solved_exercise_can_be_authoritative_without_importance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph = root / "graph"
            graph.mkdir()
            source = graph / "unit.md"
            source.write_text(
                "## 对点训练\n"
                "1. 求导数（ ）\nA. 甲 B. 乙\n"
                "1. 答案 B 解析：直接求导。\n",
                encoding="utf-8",
            )
            solution_line = "1. 答案 B 解析：直接求导。"
            adapter = {
                "_graph_root": str(graph),
                "content": {
                    "question_folder": "训练题",
                    "question_title_template": "题 {number}",
                    "question_patterns": [
                        r"^(?P<number>\d+)[.．、](?!\s*(?:答案|解析)\b)\s*"
                    ],
                    "inline_question_patterns": [],
                    "question_kind_rules": [
                        {
                            "kind": "inline-solved-exercise",
                            "pattern": r"^\d+[.．、]",
                            "answer_handling": "separate-authoritative",
                            "solution_layout": "tail",
                            "solution_start_patterns": [
                                r"^\s*\d+[.．、]\s*(?:答案|解析)\b"
                            ],
                            "sequence_policy": "continuous",
                        }
                    ],
                    "question_scopes": [
                        {"contexts": ["unit"], "kinds": ["inline-solved-exercise"]}
                    ],
                    "recovered_question_fragments": [
                        {
                            "context": "unit",
                            "raw_line": 4,
                            "raw_column": len(solution_line),
                            "position": "after",
                            "text": "（PDF补全）",
                            "source_page": 1,
                            "anchor_text": solution_line,
                            "reviewer_confirmed": True,
                        }
                    ],
                    "roles": [],
                    "unknown_label_policy": "retain",
                },
            }
            note = {
                "key": "unit",
                "title": "Unit",
                "path": str(source),
                "content_source": str(source),
                "answer_context": "unit",
            }

            _, questions, review = plan_note(
                note,
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual(review, [])
            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0]["question_kind"], "inline-solved-exercise")
            self.assertEqual(questions[0]["answer_handling"], "separate-authoritative")
            self.assertEqual(questions[0]["metadata"], {})
            self.assertEqual(questions[0]["sequence_policy"], "continuous")
            self.assertEqual(
                questions[0]["recovered_question_fragments"][0]["destination"],
                "answer",
            )
            self.assertIn("求导数", source.read_text(encoding="utf-8"))
            self.assertIsNotNone(questions[0]["answer_body_sha256"])

    def test_reviewed_question_scope_ignores_numbered_theory_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph = root / "graph"
            graph.mkdir()
            source = graph / "unit.md"
            source.write_text(
                "## Theory\n1. This is a numbered instruction.\n\n"
                "## Practice\n1. This is the exercise.\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(graph),
                "content": {
                    "question_folder": "questions",
                    "question_title_template": "Question {number}",
                    "question_patterns": [r"^(?P<number>\d+)[.]\s*"],
                    "roles": [
                        {"role": "theory", "depth": 0, "pattern": r"^Theory$", "heading_only": True},
                        {"role": "practice", "depth": 0, "pattern": r"^Practice$", "heading_only": True},
                    ],
                    "question_scopes": [{"roles": ["practice"]}],
                    "unknown_label_policy": "retain",
                },
            }
            note = {
                "key": "unit",
                "title": "Unit",
                "path": str(source),
                "content_source": str(source),
                "answer_context": "unit",
            }

            _, questions, review = plan_note(
                note,
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual(review, [])
            self.assertEqual(len(questions), 1)
            self.assertIn("This is the exercise", source.read_text(encoding="utf-8"))
            self.assertEqual(adapter["_scope_excluded_candidates"][0]["raw_line"], 2)

    def test_html_table_audit_allows_balanced_data_table_but_blocks_fragments(self) -> None:
        self.assertFalse(
            question_has_fragmented_html_table(
                "Question text\n<table><tr><td>x</td><td>1</td></tr></table>"
            )
        )
        self.assertTrue(question_has_fragmented_html_table("Question text</td><td>next"))

    def test_unmatched_authoritative_answer_blocks_terminal_question_loss(self) -> None:
        errors = answer_without_question_errors(
            [
                {
                    "kind": "unmatched-answer",
                    "answer_id": "section-4:71:1764:0",
                    "context": "section-4",
                    "number": "71",
                },
                {
                    "kind": "missing-answer",
                    "question_id": "section-4:question:5:10",
                    "context": "section-4",
                    "number": "5",
                },
            ]
        )

        self.assertEqual(
            errors,
            [
                {
                    "kind": "answer-without-question",
                    "answer_id": "section-4:71:1764:0",
                    "context": "section-4",
                    "number": "71",
                }
            ],
        )

    def test_implicit_choice_answer_is_recovered_from_authoritative_conclusion(self) -> None:
        body = (
            "解析: A 与 D 表示同一集合，B、C 不满足题意。\n"
            "所以 A=D, 故选:D"
        )

        self.assertEqual(extract_choice_answer(body), "D")
        rendered = format_answer_callout(body, callout_title="全练一本通解析")
        self.assertIn("> > [!success]- **【答案】** D", rendered)
        self.assertIn("> > [!note]- **【分析】**", rendered)
        self.assertIn("> > [!note]- **【解析】**", rendered)

    def test_answer_analysis_and_explanation_are_nested_collapsible_callouts(self) -> None:
        rendered = format_answer_callout(
            "分析 考察奇函数在对称区间上的性质。\n\n"
            "解析 令 $g(x)=f(x)-2$，则 $g(x)$ 为奇函数。",
            callout_title="例题解析",
        )

        self.assertIn("> [!faq]- 例题解析", rendered)
        self.assertIn("> > [!success]- **【答案】** 详见解析", rendered)
        self.assertIn("> > [!note]- **【分析】**", rendered)
        self.assertIn("> > 分析 考察奇函数在对称区间上的性质。", rendered)
        self.assertIn("> > [!note]- **【解析】**", rendered)
        self.assertIn("> > 解析 令 $g(x)=f(x)-2$，则 $g(x)$ 为奇函数。", rendered)

    def test_bracketed_answer_prefix_and_later_detailed_solution_are_parsed(self) -> None:
        rendered = format_answer_callout(
            "【答案】C\n\n【解析】\n\n【分析】先判断奇偶性。\n\n"
            "【详解】代入特殊点即可排除其余选项。"
        )

        self.assertIn("**【答案】** C", rendered)
        analysis_block, explanation_block = rendered.split(
            "> > [!note]- **【解析】**", 1
        )
        self.assertIn("> > 【分析】先判断奇偶性。", analysis_block)
        self.assertIn("> > 【详解】代入特殊点即可排除其余选项。", explanation_block)

    def test_long_bracketed_answer_prefix_is_not_duplicated(self) -> None:
        long_answer = "推导步骤。" * 100
        rendered = format_answer_callout(
            f"【答案】{long_answer}\n【解析】\n【分析】先概括思路。\n详细推导。"
        )

        self.assertEqual(rendered.count(long_answer), 1)
        self.assertIn("> > 【分析】先概括思路。", rendered)

    def test_choice_answer_extraction_does_not_guess_from_capital_letters(self) -> None:
        body = "解析: 集合 A 与集合 D 相等，但此处没有保留权威选项结论。"

        self.assertIsNone(extract_choice_answer(body))
        self.assertIn("**【答案】** 详见解析", format_answer_callout(body))

    def test_choice_conclusion_wins_over_ocr_damaged_header(self) -> None:
        body = "【21】D\n推导得到最小值为 4，故选：C。"

        self.assertEqual(extract_choice_answer(body), "C")
        self.assertIn("**【答案】** C", format_answer_callout(body))

    def test_geometry_point_labels_are_not_choice_options(self) -> None:
        body = "过点 P 作直线，分别交于点 A、B 和点 C、D，证明交点在定直线上。"

        self.assertFalse(question_requires_choice_answer(body))

    def test_full_width_colon_is_stable_in_generated_name(self) -> None:
        self.assertEqual(safe_name("角度3：公式法.md"), "角度3_公式法.md")

    def test_generated_name_replaces_every_non_alphanumeric_character(self) -> None:
        self.assertEqual(
            safe_name("▶ 题型 1：（向量）+方法.md"),
            "__题型_1__向量__方法.md",
        )
        self.assertEqual(safe_name("一.向量"), "一_向量")

    def test_empty_generated_directories_are_pruned_without_deleting_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            empty_leaf = root / "stale" / "nested"
            empty_leaf.mkdir(parents=True)
            kept = root / "current"
            kept.mkdir()
            note = kept / "note.md"
            note.write_text("keep", encoding="utf-8")

            removed = prune_empty_directories(root)

            self.assertFalse((root / "stale").exists())
            self.assertTrue(note.is_file())
            self.assertNotIn(str(root.resolve()), removed)

    def test_ascii_colon_is_removed_from_every_hierarchy_path_component(self) -> None:
        self.assertEqual(
            normalize_generated_output("第十节 专题:离心率/题型 1:定义.md"),
            "第十节_专题_离心率/题型_1_定义.md",
        )

    def test_final_path_guard_rejects_ascii_and_full_width_colons(self) -> None:
        self.assertTrue(path_has_forbidden_colon(Path("chapter/题型：定义.md")))
        self.assertTrue(path_has_forbidden_colon(Path("chapter/topic:definition.md")))
        self.assertFalse(path_has_forbidden_colon(Path("chapter/题型_定义.md")))

    def test_nonchoice_answer_prefix_is_split_from_analysis(self) -> None:
        body = "【12】$$\n\\frac{3}{2}\n$$\n解析：由条件整理可得该结果。"

        answer, analysis = extract_nonchoice_answer_prefix(body)

        self.assertEqual(answer, "$$ \\frac{3}{2} $$")
        self.assertEqual(analysis, "由条件整理可得该结果。")
        rendered = format_answer_callout(body)
        self.assertIn("**【答案】** $$ \\frac{3}{2} $$", rendered)
        self.assertNotIn("> $$  ", rendered)

    def test_answer_prefix_keeps_leading_asset_with_analysis(self) -> None:
        body = "【12】$\\sqrt3$\n![](images/diagram.png)\n解析：由图可得。"

        answer, analysis = extract_nonchoice_answer_prefix(body)

        self.assertEqual(answer, "$\\sqrt3$")
        self.assertTrue(analysis.startswith("![](images/diagram.png)"))

    def test_nonchoice_without_separable_result_gets_explicit_fallback(self) -> None:
        rendered = format_answer_callout("【8】证明过程从这里开始，最后得到结论。")

        self.assertIn("**【答案】** 详见解析", rendered)
        self.assertIn("**【解析】**", rendered)

    def test_solution_audit_requires_explicit_choice_answer_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            note = Path(tmp_dir) / "Q00000001A1.md"
            note.write_text(
                "---\nanswer_for: Q00000001\nanswer_provenance: authoritative\n"
                "answer_source_body_sha256: source-hash\n---\n"
                "> [!faq]- 解析\n> **【解析】**  \n> 由条件可得应选 D。\n",
                encoding="utf-8",
            )
            record = {
                "provenance": "authoritative",
                "source_body_sha256": "source-hash",
            }

            valid, reason = valid_solution_note(
                note,
                record,
                require_choice_answer=True,
                expected_choice_answer="D",
            )

            self.assertFalse(valid)
            self.assertEqual(reason, "solution-choice-answer-missing")

    def test_adapter_draft_applies_frozen_preset_without_approving_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "questions.md"
            source.write_text("# Unit\n1. Question.\n", encoding="utf-8")
            preset = root / "preset.json"
            write_json_atomic(
                preset,
                {
                    "status": "passed",
                    "reviewer_confirmed": True,
                    "content": {"question_folder": "Preset Questions"},
                },
            )
            staging = root / "staging"
            vault = root / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={source}"],
                "Preset",
                staging,
                vault,
                vault / "graph",
                "en",
                None,
                False,
                preset,
            )
            write_json_atomic(profile_path, profile)

            draft = build_adapter_draft(profile_path)

            self.assertEqual(draft["content"]["question_folder"], "Preset Questions")
            self.assertEqual(draft["status"], "review_required")
            self.assertFalse(draft["reviewer_confirmed"])

    def test_supplement_rejects_placeholders_and_requires_reviewed_solution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "questions.md"
            source.write_text("1. Question.\n", encoding="utf-8")
            staging = root / "staging"
            vault = root / "vault"
            graph = vault / "graph"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={source}"], "Supplement", staging, vault, graph, "en", None, False
            )
            write_json_atomic(profile_path, profile)
            question = graph / "questions" / "Q00000001.md"
            question.parent.mkdir(parents=True, exist_ok=True)
            question.write_text(
                "---\nquestion_id: q1\nquestion_number: 1\nanswer_status: unmatched\n---\n"
                "<!-- question-source:start -->\n1. Question.\n<!-- question-source:end -->\n",
                encoding="utf-8",
            )
            manifest_path = staging / "supplement.json"
            manifest = {
                "schema_version": 1,
                "questions": [
                    {
                        "question_id": "q1",
                        "question_stem": "Q00000001",
                        "file_path": str(question),
                        "solution": "待模型生成完整解析",
                        "reviewer_confirmed": True,
                    }
                ],
            }
            write_json_atomic(manifest_path, manifest)

            blocked = apply_supplement(profile_path, manifest_path)
            self.assertEqual(blocked["status"], "review_required")
            self.assertFalse((question.parent / "answers" / "Q00000001A1.md").exists())

            manifest["questions"][0]["solution"] = "Because both sides are equal, the required value is 1."
            write_json_atomic(manifest_path, manifest, overwrite=True)
            completed = apply_supplement(profile_path, manifest_path)
            answer_text = (question.parent / "answers" / "Q00000001A1.md").read_text(encoding="utf-8")
            self.assertEqual(completed["status"], "completed")
            self.assertIn("answer_provenance: ai-generated-reviewed", answer_text)
            self.assertIn("**【答案】** 详见解析", answer_text)

    def test_supplement_plan_preserves_reviewed_solution_for_unchanged_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "questions.md"
            source.write_text("1. Question.\n", encoding="utf-8")
            staging = root / "staging"
            vault = root / "vault"
            graph = vault / "graph"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={source}"], "Supplement", staging, vault, graph, "en", None, False
            )
            write_json_atomic(profile_path, profile)
            question = graph / "questions" / "Q00000001.md"
            question.parent.mkdir(parents=True, exist_ok=True)
            question.write_text(
                "---\nquestion_id: q1\nquestion_number: 1\nanswer_status: unmatched\n---\n"
                "<!-- question-source:start -->\n1. Question.\n<!-- question-source:end -->\n",
                encoding="utf-8",
            )
            manifest_path = staging / "supplement.json"
            write_json_atomic(
                manifest_path,
                {
                    "questions": [
                        {
                            "question_id": "q1",
                            "question_body": "1. Question.",
                            "solution": "A reviewed and substantive worked solution.",
                            "reviewer_confirmed": True,
                        }
                    ]
                },
            )

            replanned = plan_supplement(profile_path, manifest_path)

            self.assertTrue(replanned["questions"][0]["reviewer_confirmed"])
            self.assertEqual(
                replanned["questions"][0]["solution"],
                "A reviewed and substantive worked solution.",
            )

    def test_supplement_plan_loads_durable_reviewed_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "questions.md"
            source.write_text("1. Question.\n", encoding="utf-8")
            staging = root / "staging"
            vault = root / "vault"
            graph = vault / "graph"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={source}"], "Supplement", staging, vault, graph, "en", None, False
            )
            write_json_atomic(profile_path, profile)
            question = graph / "questions" / "Q00000001.md"
            question.parent.mkdir(parents=True, exist_ok=True)
            question.write_text(
                "---\nquestion_id: q1\nquestion_number: 1\nanswer_status: unmatched\n---\n"
                "<!-- question-source:start -->\n1. Question.\n<!-- question-source:end -->\n",
                encoding="utf-8",
            )
            write_json_atomic(
                staging / "reviewed-supplement-overrides.json",
                {
                    "questions": [
                        {
                            "question_id": "q1",
                            "question_body_sha256": sha256_text("1. Question."),
                            "solution": "A durable reviewed worked solution.",
                            "reviewer_confirmed": True,
                        }
                    ]
                },
            )

            replanned = plan_supplement(profile_path, staging / "supplement.json")

            self.assertEqual(
                replanned["questions"][0]["solution"],
                "A durable reviewed worked solution.",
            )

    def test_inline_answer_splitting_preserves_raw_context_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "answers.md"
            path.write_text("## A\n1. First 【2】Second\n## B\n1. Third\n", encoding="utf-8")
            adapter = {
                "answers": {
                    "contexts": [
                        {"key": "A", "pattern": r"^## A$"},
                        {"key": "B", "start_line": 3},
                    ],
                    "answer_patterns": [r"^【?(?P<number>\d+)】?[.、]?\s*"],
                    "inline_answer_patterns": [r"【(?P<number>\d+)】"],
                    "matching_strategies": ["hierarchy-number"],
                }
            }

            answers, review = parse_answer_blocks(path, adapter)

            self.assertEqual(review, [])
            self.assertEqual(
                [(item["number"], item["context"], item["line"], item["subline"]) for item in answers],
                [("1", "A", 2, 0), ("2", "A", 2, 1), ("1", "B", 4, 0)],
            )

    def test_reviewed_implicit_answer_recovers_dropped_ocr_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "answers.md"
            path.write_text(
                "# Unit\n解析: first publisher solution\n【2】B\n解析: second\n",
                encoding="utf-8",
            )
            adapter = {
                "answers": {
                    "contexts": [
                        {"key": "unit", "start_line": 1, "anchor_text": "# Unit"}
                    ],
                    "implicit_answers": [
                        {
                            "context": "unit",
                            "number": "1",
                            "start_line": 2,
                            "anchor_text": "解析: first publisher solution",
                        }
                    ],
                    "answer_patterns": [r"【(?P<number>\d+)】"],
                }
            }

            answers, review = parse_answer_blocks(path, adapter)

            self.assertEqual(review, [])
            self.assertEqual([item["number"] for item in answers], ["1", "2"])
            self.assertEqual(
                answers[0]["evidence"], {"implicit_header": "reviewed-ocr-omission"}
            )

    def test_reviewed_implicit_answer_targets_inline_raw_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "answers.md"
            raw = "【38】first 【38】second 【40】third"
            path.write_text(f"# Unit\n{raw}\n", encoding="utf-8")
            second_column = raw.index("【38】", 1) + 1
            adapter = {
                "answers": {
                    "contexts": [{"key": "unit", "start_line": 1}],
                    "implicit_answers": [
                        {
                            "context": "unit",
                            "number": "39",
                            "start_line": 2,
                            "raw_column": second_column,
                            "anchor_text": raw,
                        }
                    ],
                    "answer_patterns": [r"^【(?P<number>\d+)】"],
                    "inline_answer_patterns": [r"【(?P<number>\d+)】"],
                }
            }

            answers, review = parse_answer_blocks(path, adapter)

            self.assertEqual(review, [])
            self.assertEqual(
                [(item["number"], item["raw_column"]) for item in answers],
                [("38", 1), ("39", second_column), ("40", raw.index("【40】") + 1)],
            )

    def test_reviewed_implicit_answer_can_split_unmarked_inline_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "answers.md"
            raw = "【1】答案一。这里开始答案二，随后仍有解析。"
            second_column = raw.index("这里开始答案二") + 1
            path.write_text(raw, encoding="utf-8")
            adapter = {
                "answers": {
                    "answer_patterns": [r"^【(?P<number>\d+)】"],
                    "contexts": [{"key": "lesson", "start_line": 1}],
                    "implicit_answers": [
                        {
                            "context": "lesson",
                            "number": "2",
                            "start_line": 1,
                            "raw_column": second_column,
                            "anchor_pattern": "这里开始答案二",
                            "reviewer_confirmed": True,
                        }
                    ],
                }
            }

            answers, review = parse_answer_blocks(path, adapter)

            self.assertEqual(review, [])
            self.assertEqual(
                [(item["number"], item["raw_column"]) for item in answers],
                [("1", 1), ("2", second_column)],
            )
            self.assertNotIn("这里开始答案二", answers[0]["body"])
            self.assertIn("这里开始答案二", answers[1]["body"])

    def test_reviewed_pdf_answer_recovery_restores_omitted_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "answers.md"
            path.write_text("# Unit\n【1】A\n【69】详见解析\n", encoding="utf-8")
            adapter = {
                "answers": {
                    "answer_patterns": [r"^【(?P<number>\d+)】"],
                    "contexts": [{"key": "unit", "start_line": 1}],
                    "ignore_ranges": [{"start_line": 3, "end_line": 3}],
                    "recovered_answers": [
                        {
                            "context": "unit",
                            "number": "2",
                            "body": "【2】答案\n解析：PDF 中可见的完整解析",
                            "after_line": 3,
                            "source_page": 8,
                            "anchor_text": "【69】详见解析",
                            "reviewer_confirmed": True,
                        }
                    ],
                }
            }

            answers, review = parse_answer_blocks(path, adapter)

            self.assertEqual(review, [])
            self.assertEqual([item["number"] for item in answers], ["1", "2"])
            self.assertEqual(
                answers[1]["evidence"], {"reviewed_pdf_recovery": "8"}
            )
            self.assertIn("完整解析", answers[1]["body"])

    def test_reviewed_choice_answer_override_renders_explicit_field(self) -> None:
        rendered = format_answer_callout(
            "解析: the source derivation proves the first option.",
            reviewed_choice_answer="A",
        )

        self.assertIn("**【答案】** A", rendered)

    def test_reviewed_short_answer_override_renders_source_backed_result(self) -> None:
        rendered = format_answer_callout(
            "解析: 由条件计算可得最终结果。",
            reviewed_short_answer=r"$2-4\mathrm{i}$",
        )

        self.assertIn(r"**【答案】** $2-4\mathrm{i}$", rendered)
        self.assertIn("**【解析】**", rendered)

    def test_reviewed_question_number_override_corrects_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            note = root / "unit.md"
            note.write_text("heading\n【47】misread question\n", encoding="utf-8")
            adapter = {
                "_graph_root": str(root),
                "content": {
                    "question_folder": "questions",
                    "question_title_template": "Question {number}",
                    "question_number_overrides": [
                        {
                            "context": "unit",
                            "number": "37",
                            "start_line": 2,
                            "anchor_text": "【47】misread question",
                        }
                    ],
                },
            }
            note_entry = {
                "key": "unit",
                "path": str(note),
                "content_source": str(note),
                "title": "Unit",
                "answer_context": "unit",
            }
            patterns = [re.compile(r"^【(?P<number>\d+)】")]

            _, questions, review = plan_note(note_entry, [], patterns, adapter)

            self.assertEqual(review, [])
            self.assertEqual(questions[0]["number"], "37")
            self.assertEqual(questions[0]["evidence"]["reviewed_number_override"], "47")

    def test_reviewed_number_shift_range_repairs_source_number_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            note = root / "unit.md"
            note.write_text("【1】First\n【1】Reset\n【2】Tail\n", encoding="utf-8")
            adapter = {
                "_graph_root": str(root),
                "content": {
                    "question_folder": "questions",
                    "question_title_template": "Question {number}",
                    "question_number_shift_ranges": [
                        {
                            "context": "unit",
                            "start_line": 2,
                            "end_line": 3,
                            "offset": 1,
                            "anchor_text": "【1】Reset",
                            "end_anchor_text": "【2】Tail",
                            "reviewer_confirmed": True,
                        }
                    ],
                },
            }
            note_entry = {
                "key": "unit",
                "path": str(note),
                "content_source": str(note),
                "title": "Unit",
                "answer_context": "unit",
            }
            patterns = [re.compile(r"^【(?P<number>\d+)】")]

            _, questions, review = plan_note(note_entry, [], patterns, adapter)

            self.assertEqual(review, [])
            self.assertEqual([item["number"] for item in questions], ["1", "2", "3"])

            answers = root / "answers.md"
            answers.write_text("# Unit\n【1】A\n【1】B\n【2】C\n", encoding="utf-8")
            parsed, answer_review = parse_answer_blocks(
                answers,
                {
                    "answers": {
                        "answer_patterns": [r"^【(?P<number>\d+)】"],
                        "contexts": [{"key": "unit", "start_line": 1}],
                        "answer_number_shift_ranges": [
                            {
                                "context": "unit",
                                "start_line": 3,
                                "end_line": 4,
                                "offset": 1,
                                "anchor_text": "【1】B",
                                "end_anchor_text": "【2】C",
                                "reviewer_confirmed": True,
                            }
                        ],
                    }
                },
            )

            self.assertEqual(answer_review, [])
            self.assertEqual([item["number"] for item in parsed], ["1", "2", "3"])

    def test_inventory_proposes_multiple_indexes_wrapped_entries_and_layout_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "inventory.md"
            source.write_text(
                "Long wrapped title\ncontinued ........ 3\nSecond ........ 8\n\n\n\n"
                "Alternate index    12\nAnother entry    14\n\n"
                "left column    right column\n![](images/page.png)\n",
                encoding="utf-8",
            )

            inventory = inventory_markdown(source)

            self.assertEqual(len(inventory["index_candidates"]), 2)
            self.assertEqual(inventory["index_candidates"][0]["status"], "review_required")
            self.assertEqual(inventory["layout_signals"], {
                "image_count": 1,
                "table_line_count": 0,
                "wide_spacing_line_count": 3,
            })

    def test_index_entry_preserves_descriptor_and_multiple_parenthesized_references(self) -> None:
        parsed = parse_index_entry("2.4 Generic topic …… Core Advanced (17) (203)")

        self.assertEqual(parsed, {
            "title": "2.4 Generic topic",
            "descriptor": "Core Advanced",
            "references": [17, 203],
            "literal": "2.4 Generic topic …… Core Advanced (17) (203)",
        })

    def test_markdown_only_inventory_works_before_run_and_names_arrangement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "questions.md"
            source.write_text("#### Pattern A\n\n#### Pattern B\n", encoding="utf-8")
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile([f"questions={source}"], "Inventory", staging, vault, vault / "graph", "en", None, False)
            staging.mkdir(parents=True, exist_ok=True)
            write_json_atomic(profile_path, profile)

            inventory = build_inventory(profile_path)

            self.assertEqual(inventory["source_arrangement"], "question-only")
            self.assertEqual(inventory["sources"][0]["status"], "review_required")
            self.assertEqual(inventory["sources"][0]["heading_count"], 2)
            self.assertEqual(inventory["sources"][0]["repeated_label_candidates"][0]["literal"], "Pattern")
            draft = build_adapter_draft(profile_path, inventory)
            self.assertEqual(draft["status"], "review_required")
            self.assertFalse(draft["reviewer_confirmed"])
            self.assertEqual(draft["hierarchy"]["entries"], [])

    def test_reviewed_folder_templates_remain_adapter_controlled(self) -> None:
        outputs = [
            "Chapter/Section/Section.md",
            "Section.md",
            "roles/section/Section.md",
        ]
        for output in outputs:
            with self.subTest(output=output):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    source = tmp_path / "source.md"
                    source.write_text("# Section\n\n1. Question.\n", encoding="utf-8")
                    staging = tmp_path / "staging"
                    vault = tmp_path / "vault"
                    profile_path = staging / "profile.json"
                    profile = create_profile([f"questions={source}"], "Layouts", staging, vault, vault / "graph", "en", None, False)
                    staging.mkdir(parents=True, exist_ok=True)
                    write_json_atomic(profile_path, profile)
                    raw = Path(profile["sources"][0]["markdown_path"])
                    raw.parent.mkdir(parents=True, exist_ok=True)
                    raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                    adapter = {
                        "schema_version": 1,
                        "status": "passed",
                        "reviewer_confirmed": True,
                        "profile": str(profile_path.resolve()),
                        "hierarchy": {
                            "source_role": "questions",
                            "root_output": "index.md",
                            "no_toc_authority": {
                                "status": "passed",
                                "reviewer_confirmed": True,
                                "reason": "Synthetic layout fixture has no TOC",
                            },
                            "entries": [{"key": "section", "title": "Section", "level": 1, "start_line": 1, "output": output}],
                        },
                        "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": []},
                    }
                    adapter_path = staging / "adapter.json"
                    write_json_atomic(adapter_path, adapter)

                    manifest = plan_hierarchy(profile_path, adapter_path)

                    self.assertEqual(manifest["entries"][0]["output"], output)

    def test_primary_authority_ledger_blocks_missing_toc_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source.md"
            source.write_text("Index\nUnit One\n1.1 Topic …… Core (1) (20)\n\n# Unit One\n\n## Core\n1. Q\n", encoding="utf-8")
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile([f"questions={source}"], "Ledger", staging, vault, vault / "graph", "en", None, False)
            write_json_atomic(profile_path, profile)
            raw = Path(profile["sources"][0]["markdown_path"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            adapter = {
                "schema_version": 1,
                "status": "passed",
                "reviewer_confirmed": True,
                "profile": str(profile_path.resolve()),
                "hierarchy": {
                    "source_role": "questions",
                    "root_output": "index.md",
                    "primary_authority": {
                        "status": "passed",
                        "reviewer_confirmed": True,
                        "start_line": 2,
                        "end_line": 3,
                        "entries": [
                            {"key": "unit", "title": "Unit One", "level": 1, "source_line": 2},
                            {"key": "topic", "title": "1.1 Topic", "level": 2, "source_line": 3},
                        ],
                    },
                    "entries": [{"key": "unit", "title": "Unit One", "level": 1, "start_line": 5, "output": "unit.md"}],
                },
                "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": []},
            }
            adapter_path = staging / "adapter.json"
            write_json_atomic(adapter_path, adapter)

            manifest = plan_hierarchy(profile_path, adapter_path)

            self.assertEqual(manifest["status"], "review_required")
            self.assertEqual(manifest["review_items"], [
                {"kind": "missing-primary-authority-entry", "key": "topic", "title": "1.1 Topic"}
            ])

    def test_hierarchy_cannot_bypass_authority_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source.md"
            source.write_text("# Unit\n1. Q\n", encoding="utf-8")
            staging = tmp_path / "staging"
            profile_path = staging / "profile.json"
            profile = create_profile([f"questions={source}"], "Authority", staging, tmp_path, tmp_path / "graph", "en", None, False)
            write_json_atomic(profile_path, profile)
            raw = Path(profile["sources"][0]["markdown_path"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            adapter = {
                "schema_version": 1,
                "status": "passed",
                "reviewer_confirmed": True,
                "profile": str(profile_path.resolve()),
                "hierarchy": {
                    "source_role": "questions",
                    "root_output": "index.md",
                    "entries": [{"key": "u", "title": "Unit", "start_line": 1, "level": 1, "output": "u.md"}],
                },
                "content": {
                    "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
                    "roles": [],
                },
            }
            adapter_path = staging / "adapter.json"
            write_json_atomic(adapter_path, adapter)

            with self.assertRaisesRegex(ConfigurationError, "exactly one"):
                plan_hierarchy(profile_path, adapter_path)

    def test_structural_toc_node_can_share_reviewed_boundary_with_content_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source.md"
            source.write_text("Index\nUnit One\n1.1 Topic …… Core (1) (20)\n\n# Unit One\n\n## Core\n1. Q\n", encoding="utf-8")
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile([f"questions={source}"], "Structural", staging, vault, vault / "graph", "en", None, False)
            write_json_atomic(profile_path, profile)
            raw = Path(profile["sources"][0]["markdown_path"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            (raw.parent / "images").mkdir()
            (raw.parent / "images" / "asset.png").write_bytes(b"asset")
            adapter = {
                "schema_version": 1,
                "status": "passed",
                "reviewer_confirmed": True,
                "profile": str(profile_path.resolve()),
                "hierarchy": {
                    "source_role": "questions",
                    "root_output": "index.md",
                    "primary_authority": {
                        "status": "passed",
                        "reviewer_confirmed": True,
                        "start_line": 2,
                        "end_line": 3,
                        "entries": [
                            {"key": "unit", "title": "Unit One", "level": 1, "source_line": 2},
                            {"key": "topic", "title": "1.1 Topic", "level": 2, "source_line": 3},
                        ],
                    },
                    "entries": [
                        {"key": "unit", "start_line": 5, "output": "unit/unit.md"},
                        {
                            "key": "topic",
                            "structural_only": True,
                            "emit_title": True,
                            "body_anchor": {
                                "kind": "reviewed-boundary",
                                "start_line": 7,
                                "evidence": "first reviewed content band",
                                "reviewer_confirmed": True,
                            },
                            "output": "unit/topic/topic.md",
                        },
                        {
                            "key": "band",
                            "title": "Core",
                            "level": 3,
                            "start_line": 7,
                            "output": "unit/topic/core.md",
                            "supplemental": True,
                        },
                    ],
                },
                "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": []},
            }
            adapter_path = staging / "adapter.json"
            manifest_path = staging / "hierarchy.json"
            write_json_atomic(adapter_path, adapter)
            manifest = plan_hierarchy(profile_path, adapter_path)
            write_json_atomic(manifest_path, manifest)

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["entries"][1]["parent"], "unit")
            self.assertEqual(manifest["entries"][2]["parent"], "topic")
            apply_hierarchy(profile_path, adapter_path, manifest_path, overwrite=True)
            unit_text = (vault / "graph" / "unit" / "unit.md").read_text(encoding="utf-8")
            topic_text = (vault / "graph" / "unit" / "topic" / "topic.md").read_text(encoding="utf-8")
            self.assertIn("![[graph/unit/topic/topic.md]]", unit_text)
            self.assertNotIn("- ![[", unit_text)
            self.assertTrue(topic_text.startswith("## 1.1 Topic\n\n![[graph/unit/topic/core.md]]"))
            self.assertNotIn("- ![[", topic_text)
            content_manifest = plan_content(profile_path, adapter_path, staging / "hierarchy-coverage-manifest.json")
            self.assertEqual(content_manifest["status"], "passed")
            self.assertEqual(len(content_manifest["questions"]), 1)
            self.assertTrue(all(item["source_note"] != str(vault / "graph" / "unit" / "topic" / "topic.md") for item in content_manifest["questions"]))

    def test_alternate_labels_are_adapter_roles_and_unknown_labels_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            note = tmp_path / "section.md"
            note.write_text("#### Pattern Algebra\n\n1. Q\n\n#### Mystery Label\n", encoding="utf-8")
            adapter = {
                "_graph_root": str(tmp_path),
                "content": {
                    "unknown_label_policy": "review",
                    "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
                    "roles": [{"role": "question-type", "depth": 0, "pattern": r"Pattern (?P<title>.+)"}],
                },
            }

            labels, questions, review = plan_note(
                {"key": "section", "path": str(note), "answer_context": "section"},
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual(labels[0]["role"], "question-type")
            self.assertEqual(len(questions), 1)
            self.assertEqual(review, [{"kind": "unknown-label", "source_note": str(note), "line": 5, "text": "Mystery Label"}])

    def test_existing_child_embed_is_a_content_range_barrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            note = tmp_path / "parent.md"
            note.write_text(
                "## Parent\n\n#### Type Intro\nContext retained here.\n![[graph/child.md]]\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(tmp_path),
                "content": {
                    "unknown_label_policy": "retain",
                    "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
                    "roles": [{"role": "question-type", "depth": 0, "pattern": r"Type (?P<title>.+)"}],
                },
            }

            labels, questions, review = plan_note(
                {"key": "parent", "title": "Parent", "path": str(note), "answer_context": "parent"},
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual(labels[0]["end_line"], 4)
            self.assertEqual(questions, [])
            self.assertEqual(review, [])

    def test_question_line_cannot_also_become_a_functional_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            note = tmp_path / "section.md"
            note.write_text("#### Type Algebra\n1. Question body.\n", encoding="utf-8")
            adapter = {
                "_graph_root": str(tmp_path),
                "content": {
                    "unknown_label_policy": "retain",
                    "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
                    "roles": [
                        {"role": "question-type", "depth": 1, "pattern": r"Type (?P<title>.+)"},
                        {"role": "neutral-context", "depth": 0, "pattern": r"(?P<title>.+)"},
                    ],
                },
            }

            labels, questions, review = plan_note(
                {"key": "section", "title": "Section", "path": str(note), "answer_context": "section"},
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual([label["role"] for label in labels], ["question-type"])
            self.assertEqual([question["number"] for question in questions], ["1"])
            self.assertEqual(review, [])

    def test_exercise_roles_can_detach_from_knowledge_guide_into_reviewed_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            note = tmp_path / "Section.md"
            note.write_text(
                "## Knowledge Guide\n"
                "## 1. Concept\n"
                "Theory body.\n"
                "## Basic Point 1: Shapes\n"
                "1. Question body.\n"
                "## 2. Exercise Method\n"
                "Method body.\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(tmp_path),
                "content": {
                    "unknown_label_policy": "retain",
                    "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
                    "roles": [
                        {"role": "knowledge_guide", "depth": 0, "pattern": r"Knowledge Guide"},
                        {"role": "knowledge-item", "depth": 1, "pattern": r"\d+[.] .+", "heading_only": True},
                        {"role": "basic-point", "depth": 1, "pattern": r"Basic Point \d+: .+"},
                    ],
                    "detached_role_folders": [
                        {
                            "from_ancestor_role": "knowledge_guide",
                            "roles": ["basic-point"],
                            "folder": "Questions",
                        }
                    ],
                },
            }

            labels, questions, review = plan_note(
                {"key": "section", "title": "Section", "path": str(note), "answer_context": "section"},
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            guide, concept, exercise, method = labels
            self.assertEqual(concept["parent"], guide["key"])
            self.assertIsNone(exercise["parent"])
            self.assertEqual(method["parent"], exercise["key"])
            self.assertEqual(guide["end_line"], exercise["start_line"] - 1)
            self.assertEqual(exercise["end_line"], method["end_line"])
            self.assertEqual(Path(exercise["output"]).parent.parent.name, "Questions")
            self.assertEqual(questions[0]["owner"], exercise["key"])
            self.assertEqual(review, [])

    def test_reviewed_answer_strategies_never_use_fuzzy_similarity_as_acceptance(self) -> None:
        question = {
            "number": "1",
            "context_key": "unit-a",
            "evidence": {"reference": "R-17", "source_page": "42", "stem": "Exact stem"},
        }
        answers = [
            {"id": "a", "number": "9", "context": "elsewhere", "evidence": {"reference": "R-17", "source_page": "42", "stem": "Exact stem"}},
            {"id": "b", "number": "1", "context": "unit-a", "evidence": {"reference": "R-18", "source_page": "43", "stem": "Similar but not exact"}},
        ]

        self.assertEqual([item["id"] for item in strategy_candidates("explicit-reference", question, "Exact stem", answers)[1]], ["a"])
        self.assertEqual([item["id"] for item in strategy_candidates("hierarchy-number", question, "Exact stem", answers)[1]], ["b"])
        self.assertEqual(strategy_candidates("source-page-number", question, "Exact stem", answers)[1], [])
        self.assertEqual([item["id"] for item in strategy_candidates("normalized-stem-exact", question, "Exact stem", answers)[1]], ["a"])

    def test_inline_question_headers_are_split_with_raw_coordinates(self) -> None:
        patterns = compile_question_patterns(
            {"content": {"question_patterns": [r"【(?P<number>\d+)】"]}}
        )

        virtual = split_inline_question_headers(
            ["A. previous choice 【20】Next question", "【21】Following question"], patterns
        )

        self.assertEqual(
            [item["text"] for item in virtual],
            ["A. previous choice", "【20】Next question", "【21】Following question"],
        )
        self.assertEqual(
            [(item["raw_line"], item["raw_column"]) for item in virtual],
            [(1, 1), (1, 20), (2, 1)],
        )

    def test_question_html_table_recovers_column_roles_and_number_order(self) -> None:
        adapter = {
            "content": {
                "question_patterns": [r"【(?P<number>\d+)】"],
                "roles": [
                    {
                        "role": "basic-point",
                        "depth": 1,
                        "pattern": r"▶?Basic point\s*\d+:.+",
                    }
                ],
            }
        }
        patterns = compile_question_patterns(adapter)
        rules = compile_role_rules(adapter)
        table = (
            "<table><tr><td>【10】Left ten</td><td>▶Basic point3:Right block</td></tr>"
            "<tr><td>【11】Left eleven</td><td>Right strategy</td></tr>"
            "<tr><td rowspan=\"2\">【12】Left twelve</td><td>【13】Right thirteen<img src=\"r13.jpg\"/></td></tr>"
            "<tr><td>【14】Right fourteen</td></tr></table>"
        )

        virtual = split_inline_question_headers([table], patterns, rules)

        self.assertEqual(
            [item["text"] for item in virtual],
            [
                "【10】Left ten",
                "【11】Left eleven",
                "【12】Left twelve",
                "▶Basic point3:Right block",
                "Right strategy",
                "【13】Right thirteen<img src=\"r13.jpg\"/>",
                "【14】Right fourteen",
            ],
        )
        self.assertTrue(all("<td" not in item["text"] for item in virtual))

    def test_question_sequence_audit_blocks_gaps_duplicates_and_reordering(self) -> None:
        questions = [
            {"id": "q1", "context_key": "unit", "number": "1"},
            {"id": "q3", "context_key": "unit", "number": "3"},
            {"id": "q2", "context_key": "unit", "number": "2"},
            {"id": "q2b", "context_key": "unit", "number": "2"},
        ]

        errors = question_sequence_errors(questions)

        self.assertEqual(
            [(item["expected"], item["actual"]) for item in errors],
            [(2, 3), (4, 2), (3, 2)],
        )

    def test_reviewed_virtual_span_relocation_repairs_column_spillover(self) -> None:
        raw_lines = ["【5】Five", "## Model 2", "【7】Seven", "Unit【6】Six", "【8】Eight"]
        patterns = compile_question_patterns(
            {"content": {"question_patterns": [r"【(?P<number>\d+)】"]}}
        )
        virtual = split_inline_question_headers(raw_lines, patterns)
        adapter = {
            "content": {
                "virtual_span_relocations": [
                    {
                        "context": "unit",
                        "start_line": 4,
                        "start_column": 1,
                        "end_before_line": 5,
                        "before_line": 2,
                        "anchor_text": "Unit【6】Six",
                        "reviewer_confirmed": True,
                    }
                ]
            }
        }

        relocated = apply_reviewed_virtual_span_relocations(
            virtual, raw_lines, "unit", adapter
        )

        self.assertEqual(
            [item["text"] for item in relocated],
            ["【5】Five", "Unit", "【6】Six", "## Model 2", "【7】Seven", "【8】Eight"],
        )

    def test_reviewed_pdf_question_recovery_inserts_missing_tail(self) -> None:
        raw_lines = ["【1】One", "<table>【2】Two</table>"]
        patterns = [re.compile(r"^【(?P<number>\d+)】")]
        virtual = split_inline_question_headers(raw_lines, patterns)
        recovered = apply_reviewed_recovered_questions(
            virtual,
            raw_lines,
            "unit",
            {
                "content": {
                    "recovered_questions": [
                        {
                            "context": "unit",
                            "number": "3",
                            "body": "【3】Recovered from PDF",
                            "after_line": 2,
                            "source_page": 7,
                            "anchor_pattern": "【2】",
                            "reviewer_confirmed": True,
                        }
                    ]
                }
            },
            patterns,
        )

        self.assertEqual(recovered[-1]["text"], "【3】Recovered from PDF")
        self.assertEqual(recovered[-1]["evidence"]["reviewed_pdf_recovery"], "7")

    def test_heading_only_role_does_not_split_numbered_question_subparts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            note = tmp_path / "section.md"
            note.write_text(
                "## 1. Knowledge\nDefinition\n## Basic point 2\n【4】Question\n"
                "(1) first subpart\n(2) second subpart\n【5】Next question\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(tmp_path),
                "content": {
                    "unknown_label_policy": "retain",
                    "question_patterns": [r"【(?P<number>\d+)】"],
                    "roles": [
                        {
                            "role": "knowledge-item",
                            "depth": 1,
                            "pattern": r"\d+[.] .+|[(]\d+[)] .+",
                            "heading_only": True,
                        },
                        {"role": "basic-point", "depth": 1, "pattern": r"Basic point \d+"},
                    ],
                },
            }

            labels, questions, review = plan_note(
                {"key": "section", "path": str(note), "answer_context": "section"},
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual([item["title"] for item in labels], ["1. Knowledge", "Basic point 2"])
            self.assertEqual([item["number"] for item in questions], ["4", "5"])
            self.assertEqual(questions[0]["end_line"], 6)
            self.assertEqual(review, [])

    def test_nested_and_restarted_numbering_is_scoped_by_reviewed_context(self) -> None:
        patterns = compile_question_patterns(
            {
                "content": {
                    "question_patterns": [
                        r"^(?P<number>\d+(?:[.]\d+)*)[)]\s+",
                        r"^(?P<number>[①②③④⑤])\s+",
                    ]
                }
            }
        )
        self.assertEqual(patterns[0].match("2.1) Nested").group("number"), "2.1")
        self.assertEqual(patterns[1].match("① Restarted in another section").group("number"), "①")

    def test_repeated_functional_blocks_own_answer_context_and_zero_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            note = tmp_path / "section.md"
            note.write_text("<!-- source-part:2 pages:201-400 -->\n#### Training\n1. First\n0.618 is prose\n#### Training\n1. Second\n", encoding="utf-8")
            adapter = {
                "_graph_root": str(tmp_path),
                "content": {
                    "unknown_label_policy": "retain",
                    "question_patterns": [r"^(?P<number>\d+)[.]\s*"],
                    "roles": [{"role": "training-band", "depth": 0, "pattern": r"Training", "answer_context": True}],
                },
            }
            labels, questions, review = plan_note(
                {"key": "section", "path": str(note), "answer_context": "section"},
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual([item["answer_context"] for item in labels], [
                "section:training-band:1",
                "section:training-band:2",
            ])
            self.assertEqual([item["context_key"] for item in questions], [
                "section:training-band:1",
                "section:training-band:2",
            ])
            self.assertEqual([item["kind"] for item in review], ["invalid-question-number"])
            self.assertTrue(all(item["source_part"] == {"line": 1, "part": 2, "start_page": 201, "end_page": 400} for item in questions))


if __name__ == "__main__":
    unittest.main()

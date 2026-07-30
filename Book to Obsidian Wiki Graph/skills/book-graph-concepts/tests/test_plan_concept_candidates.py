from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "plan_concept_candidates.py"
)
SPEC = importlib.util.spec_from_file_location("plan_concept_candidates", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConceptCandidatePlanningTests(unittest.TestCase):
    def test_uses_reviewed_terms_but_rejects_unrelated_later_term(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = root / "book"
            reviewed = root / "reviewed"
            (book / "知识点").mkdir(parents=True)
            reviewed.mkdir()
            for term in ("Venn图", "包含"):
                (reviewed / f"{term}.md").write_text(term, encoding="utf-8")
            (book / "知识点" / "集合.md").write_text(
                (
                    "# 集合\n\n"
                    "这种图称为Venn图．这样，集合 A 与集合 B 有包含关系。\n"
                ),
                encoding="utf-8",
            )
            payload = MODULE.plan_candidates(book, reviewed)
            self.assertEqual(
                [item["name"] for item in payload["concepts"]],
                ["Venn图"],
            )
            self.assertEqual(
                [item["name"] for item in payload["rejected"]],
                ["包含"],
            )

    def test_extends_definition_through_following_formula(self) -> None:
        lines = [
            "一般地，这种集合称为并集，即",
            "",
            "$$",
            "A \\cup B",
            "$$",
            "",
            "下一段。",
        ]
        self.assertEqual(MODULE.definition_range(lines, 1), (1, 5))

    def test_prefers_defined_term_at_end_of_cue_phrase(self) -> None:
        terms = ["函数", "零点"]
        line = "我们把使方程成立的实数叫做二次函数的零点（zero）。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"零点"},
        )

    def test_keeps_explicit_alternative_term(self) -> None:
        terms = ["非负整数集", "自然数集"]
        line = "全体非负整数组成的集合称为非负整数集（或自然数集）。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"非负整数集", "自然数集"},
        )

    def test_stops_before_later_clause_term(self) -> None:
        terms = ["空集", "子集"]
        line = "我们把不含任何元素的集合叫做空集，并规定空集是任何集合的子集。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"空集"},
        )

    def test_recognizes_just_say_definition(self) -> None:
        terms = ["属于", "集合"]
        line = "如果 a 是集合 A 的元素，就说 a 属于集合 A，记作 a∈A。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"属于"},
        )

    def test_recognizes_called_is_definition(self) -> None:
        terms = ["增函数"]
        line = "特别地，当函数在定义域上单调递增时，我们就称它是增函数。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"增函数"},
        )

    def test_say_is_prefers_defined_compound_over_generic_noun(self) -> None:
        terms = ["函数", "反函数"]
        line = "这时就说函数 x=g(y) 是函数 y=f(x) 的反函数。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"反函数"},
        )

    def test_say_is_scans_past_formula_before_defined_term(self) -> None:
        terms = ["函数", "反函数"]
        line = (
            "这时就说函数 $x=\\log_{\\sqrt[730]{1/2}}y$ "
            "是函数 $y=(1/2)^{x/5730}$ 的反函数。"
        )
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"反函数"},
        )

    def test_recognizes_parallel_definition_terms(self) -> None:
        terms = ["充分条件", "必要条件"]
        line = "并且说，p 是 q 的充分条件，q 是 p 的必要条件。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            {"充分条件", "必要条件"},
        )

    def test_quantifier_name_does_not_create_false_called_is_cue(self) -> None:
        terms = ["真命题", "假命题"]
        line = "要判定全称量词命题是真命题，需要证明它对每个元素成立。"
        self.assertEqual(
            MODULE.candidate_terms_for_line(line, terms),
            set(),
        )

    def test_records_current_source_review_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = root / "book"
            reviewed = root / "reviewed"
            book.mkdir()
            reviewed.mkdir()
            (reviewed / "例中特例.md").write_text("", encoding="utf-8")
            (book / "正文.md").write_text(
                "# 正文\n\n这个对象叫做例中特例。\n",
                encoding="utf-8",
            )
            payload = MODULE.plan_candidates(
                book,
                reviewed,
                rejected_terms={"例中特例"},
            )
            self.assertEqual(payload["concepts"], [])
            self.assertIn(
                "not a complete formal definition",
                payload["rejected"][0]["reason"],
            )

    def test_direct_definition_outranks_earlier_generic_discourse_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = root / "book"
            reviewed = root / "reviewed"
            (book / "知识点").mkdir(parents=True)
            reviewed.mkdir()
            (reviewed / "集合.md").write_text("", encoding="utf-8")
            (book / "知识点" / "1.2 集合间的基本关系.md").write_text(
                "# 1.2 集合间的基本关系\n\n"
                "这时我们说集合 A 包含于集合 B。\n",
                encoding="utf-8",
            )
            (book / "知识点" / "集合.md").write_text(
                "# 集合\n\n"
                "一般地，我们把研究对象统称为元素，"
                "把一些元素组成的总体叫做集合（set）。\n",
                encoding="utf-8",
            )

            payload = MODULE.plan_candidates(book, reviewed)

            self.assertEqual(len(payload["concepts"]), 1)
            self.assertEqual(
                payload["concepts"][0]["definition_source"],
                "知识点/集合.md",
            )

    def test_general_definition_outranks_earlier_concrete_example(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = root / "book"
            reviewed = root / "reviewed"
            (book / "知识点").mkdir(parents=True)
            reviewed.mkdir()
            (reviewed / "偶函数.md").write_text("", encoding="utf-8")
            (book / "知识点" / "奇偶性.md").write_text(
                (
                    "# 奇偶性\n\n"
                    "实际上，对所有实数 x 都有 "
                    "$f(-x)=(-x)^2=x^2=f(x)$，"
                    "这时称函数 $f(x)=x^2$ 为偶函数。\n\n"
                    "一般地，设函数 $f(x)$ 的定义域为 D，如果对任意 "
                    "$x\\in D$ 都有 $f(-x)=f(x)$，"
                    "那么函数 $f(x)$ 就叫做偶函数。\n"
                ),
                encoding="utf-8",
            )

            payload = MODULE.plan_candidates(book, reviewed)

            self.assertEqual(
                payload["concepts"][0]["definition_start_line"],
                5,
            )

    def test_formula_without_equation_is_flagged_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = root / "book"
            reviewed = root / "reviewed"
            (book / "知识点").mkdir(parents=True)
            reviewed.mkdir()
            (reviewed / "半角公式.md").write_text("", encoding="utf-8")
            (book / "知识点" / "变换.md").write_text(
                "# 变换\n\n"
                "将两个等式相除，称之为半角公式，"
                "符号由 $\\frac{\\alpha}{2}$ 所在象限决定。\n",
                encoding="utf-8",
            )

            payload = MODULE.plan_candidates(book, reviewed)
            candidate = payload["concepts"][0]

            self.assertEqual(candidate["confidence"], "low")
            self.assertFalse(candidate["reviewed"])
            self.assertIn(
                "formula-definition-has-no-equation",
                candidate["review_flags"],
            )

    def test_rejects_definition_term_inside_multiline_display_math(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = root / "book"
            reviewed = root / "reviewed"
            book.mkdir()
            reviewed.mkdir()
            (reviewed / "实数集.md").write_text("", encoding="utf-8")
            (book / "正文.md").write_text(
                (
                    "# 正文\n\n"
                    "$$\n"
                    "\\mathrm{全体实数组成的集合称为实数集}\n"
                    "$$\n"
                ),
                encoding="utf-8",
            )
            payload = MODULE.plan_candidates(book, reviewed)
            self.assertEqual(payload["concepts"], [])
            self.assertEqual(payload["rejected"][0]["name"], "实数集")


if __name__ == "__main__":
    unittest.main()

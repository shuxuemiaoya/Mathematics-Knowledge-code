from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

import pytest
from pypdf import PdfWriter


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "exam-paper-parser"
    / "scripts"
    / "exam_paper_parser.py"
)
SPEC = importlib.util.spec_from_file_location("exam_paper_parser", SCRIPT)
assert SPEC and SPEC.loader
parser = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = parser
SPEC.loader.exec_module(parser)


def standard_markdown() -> str:
    return """# 2026年测试卷

## 一、单选题：本题共1小题

1. 若 $x=1$，则 $x+1=$

A. 0  B. 1  C. 2  D. 3

【答案】C

【解析】

代入 $x=1$，计算得到 $x+1=2$。

## 二、填空题：本题共1小题

2. 计算 $2+2=$____。

【答案】4

【分析】直接使用整数加法。

【小问 1 详解】由整数加法法则可得 $2+2=4$。
"""


def test_safe_component_and_section_label() -> None:
    assert parser.safe_component("2026卷（解析版）") == "2026卷_解析版_"
    assert parser.safe_component(parser.clean_section_title("一、单选题：本题共9小题")) == "一_单选题"


def test_standard_split_keeps_global_ledger() -> None:
    _, sections, questions = parser.parse_sections(standard_markdown())
    assert [item["number"] for item in questions] == [1, 2]
    assert [item["detected_count"] for item in sections] == [1, 1]
    assert "A. 0" in questions[0]["question_body"]
    assert "【答案】C" in questions[0]["solution_body"]


def test_pdf_text_answer_recovery_is_explicit() -> None:
    fields = parser.solution_fields(
        "【解析】\n逐项检验后可知该结论成立。\n",
        True,
        {"answer": "B", "source_page": 6, "evidence": "【答案】B"},
    )
    assert fields["answer"] == "B"
    assert fields["answer_source"] == "pdf-text-recovery"
    assert fields["answer_source_page"] == 6


def test_analysis_marker_can_contain_summary_and_full_explanation() -> None:
    fields = parser.solution_fields(
        "【答案】C\n\n【解析】\n\n【分析】先判断函数性质。\n\n代入特殊点排除其余选项，故选择 C。\n",
        True,
        None,
    )
    assert fields["analysis"] == "先判断函数性质。"
    assert fields["explanation"] == "代入特殊点排除其余选项，故选择 C。"


def test_subquestion_details_are_not_folded_into_analysis() -> None:
    fields = parser.solution_fields(
        """【答案】(1) $\\pi$ (2) 1

【解析】

【分析】（1）使用周期公式；

（2）结合函数性质求最值。

【小问 1 详解】

由周期公式得 $T=\\pi$。

【小问 2 详解】

由函数性质可得最大值为 1。
""",
        False,
        None,
    )
    assert fields["analysis"] == "（1）使用周期公式；\n\n（2）结合函数性质求最值。"
    assert "【分析】" not in fields["analysis"]
    assert "【小问 1 详解】" not in fields["analysis"]
    assert fields["explanation"].startswith("【小问 1 详解】")
    assert "由周期公式得 $T=\\pi$。" in fields["explanation"]
    assert "【小问 2 详解】" in fields["explanation"]
    assert fields["detail_markers"] == ["【小问 1 详解】", "【小问 2 详解】"]


def test_inline_answer_marker_after_last_option_is_split() -> None:
    markdown = """## 一、多项选择题：本题共1小题

1. 下列说法正确的是（）
A. 甲 B. 乙 C. 丙 D. 丁 【答案】BC 【解析】
【分析】逐项检验。
【详解】检验可知 B、C 正确，A、D 错误。
"""
    _, _, questions = parser.parse_sections(markdown)
    assert "【答案】" not in questions[0]["question_body"]
    fields = parser.solution_fields(questions[0]["solution_body"], True, None)
    assert fields["answer"] == "BC"
    assert fields["answer_source"] == "explicit-answer"
    assert questions[0]["source_start_line"] == 3
    assert questions[0]["source_solution_line"] == 4


def test_nonstandard_input_stops_for_review() -> None:
    with pytest.raises(parser.ReviewRequired):
        parser.parse_sections("## 一、单选题：本题共1小题\n\n1. 只有题干，没有解析。\n")


def test_provenance_loader_normalizes_mineru_page_index(tmp_path: Path) -> None:
    source = tmp_path / "content_list.json"
    parser.write_json(source, [{"page_idx": 5, "bbox": [1, 2, 3, 4], "text": "7. 测试题"}])
    blocks = parser.load_provenance_blocks(source)
    assert blocks[0]["source_page"] == 6
    assert blocks[0]["block_id"] == "source:b0"


def test_registry_uses_qtg_lock_and_avoids_existing_qids(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    existing = vault / "existing" / "Q00000009.md"
    parser.write_text(existing, "existing\n")
    registry = vault / ".question-type-graph" / "question-id-registry.json"
    allocated = parser.allocate_qids(registry, ["identity-a", "identity-b"], vault)
    assert allocated == {"identity-a": "Q00000010", "identity-b": "Q00000011"}
    assert registry.with_suffix(".json.lock").is_file()
    assert parser.allocate_qids(registry, ["identity-a"], vault)["identity-a"] == "Q00000010"


def test_end_to_end_generation_and_tamper_audit(tmp_path: Path) -> None:
    source = tmp_path / "2026年测试卷.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with source.open("wb") as stream:
        writer.write(stream)
    markdown = tmp_path / "raw.md"
    parser.write_text(markdown, standard_markdown())
    vault = tmp_path / "vault"
    args = argparse.Namespace(
        title=None,
        vault_root=str(vault),
        output_root=str(vault / "高中" / "真题" / "按年份分类"),
        graph_root=None,
        staging_root=None,
        registry=None,
        overwrite=False,
        provenance=None,
    )

    result = parser.parse_paper(source, markdown, None, args, {"cache_hit": True})
    assert result["status"] == "passed"
    assert result["metrics"]["question_count"] == 2
    assert result["metrics"]["llm_calls"] == 0
    assert "canvas_path" not in result

    manifest = parser.load_json(Path(result["manifest"]))
    graph_root = Path(manifest["graph_root"])
    assert "canvas_path" not in manifest
    assert not list(graph_root.rglob("*.canvas"))
    assert [item["answer"] for item in manifest["questions"]] == ["C", "4"]
    assert all(Path(item["question_path"]).parent == graph_root / "questions" for item in manifest["questions"])
    assert all(Path(item["answer_path"]).parent == graph_root / "questions" / "answers" for item in manifest["questions"])
    assert not [d for d in graph_root.iterdir() if d.is_dir() and d.name not in ("images", "questions")]
    root_text = Path(manifest["root_note"]).read_text(encoding="utf-8")
    assert "## 一、单选题" in root_text
    assert "## 二、填空题" in root_text
    for item in manifest["questions"]:
        assert parser.vault_embed(Path(item["question_path"]), vault) in root_text

    second_answer = Path(manifest["questions"][1]["answer_path"])
    original_answer = second_answer.read_text(encoding="utf-8")
    parser.write_text(
        second_answer,
        original_answer.replace(
            "> > 直接使用整数加法。",
            "> > 直接使用整数加法。\n> > 【小问 1 详解】",
            1,
        ),
    )
    mixed_detail = parser.audit_manifest(Path(result["manifest"]), overwrite=False)
    assert mixed_detail["status"] == "review_required"
    assert any(item["kind"] == "detail-in-analysis" for item in mixed_detail["errors"])
    parser.write_text(second_answer, original_answer)

    rogue_canvas = graph_root / "rogue.canvas"
    parser.write_text(rogue_canvas, "{}\n")
    with_canvas = parser.audit_manifest(Path(result["manifest"]), overwrite=False)
    assert with_canvas["status"] == "review_required"
    assert any(item["kind"] == "unexpected-canvas" for item in with_canvas["errors"])
    rogue_canvas.unlink()

    first_question = Path(manifest["questions"][0]["question_path"])
    original = first_question.read_text(encoding="utf-8")
    parser.write_text(first_question, original.replace("若 $x=1$", "若 $x=2$", 1))
    tampered = parser.audit_manifest(Path(result["manifest"]), overwrite=False)
    assert tampered["status"] == "review_required"
    assert any(item["kind"] == "question-content-drift" for item in tampered["errors"])


def test_standardize_paper_title() -> None:
    # 1. Strip timestamps and redundant suffixes
    raw1 = "2020-2021学年内蒙古包头四中高二（下）月考数学试卷（文科）（4月份）_答案分开版本_202604252130011.pdf"
    assert parser.standardize_paper_title(raw1) == "2020-2021学年内蒙古包头四中高二（下）月考数学试卷（文科）（4月份）"

    # 2. Convert decorative symbols and ASCII parentheses
    raw2 = "2025-2026学年内蒙古自治区包头市第九十三中学高二(上)期中数学试题❖_答案分开版本_202604252124031.pdf"
    assert parser.standardize_paper_title(raw2) == "2025-2026学年内蒙古自治区包头市第九十三中学高二（上）期中数学试题"

    # 3. Standardize tilde year format and Kangxi radical
    raw3 = "2022~2023学年内蒙古包头⻘山高二上学期期末数学试卷_解析版_202604252128034.pdf"
    assert parser.standardize_paper_title(raw3) == "2022-2023学年内蒙古包头青山高二上学期期末数学试卷"

    # 4. Anonymous xPad PDF title recovery from first page
    xpad_pdf = Path("/Volumes/Whw/数学妙呀资料/高中/课堂同步/试卷/内蒙古试卷集/xPad_paper_70504P08582800797_1775438799487.pdf")
    if xpad_pdf.is_file():
        assert "北重三中" in parser.standardize_paper_title(xpad_pdf)
        assert "青山" in parser.standardize_paper_title(xpad_pdf)


def test_answer_separated_sections_with_resetting_numbers() -> None:
    sample_text = """# 2026年测试卷

## 一、选择题
1. 若 $x=1$，则 $x+1=$
A. 0 B. 1 C. 2 D. 3
2. 若 $y=2$，则 $y+1=$
A. 0 B. 1 C. 2 D. 3

## 二、填空题
1. 计算 $1+1=$____。
2. 计算 $2+2=$____。

## 三、解答题
1. 求函数 $f(x)=x^2$ 的最小值。

## 一、选择题
1、【答案】C
2、【答案】D

## 二、填空题
1、故答案为：2。
2、故答案为：4。

## 三、解答题
1、【答案】
当 $x=0$ 时取到最小值 0。
"""
    lines, sections, questions = parser.parse_sections(sample_text)
    assert len(sections) == 3
    assert [s["clean_title"] for s in sections] == ["一、选择题", "二、填空题", "三、解答题"]
    assert len(questions) == 5
    assert [q["number"] for q in questions] == [1, 2, 3, 4, 5]
    assert [q["section_index"] for q in questions] == [0, 0, 1, 1, 2]
    assert [q["local_number"] for q in questions] == [1, 2, 1, 2, 1]
    # Check answers matched
    assert "2" in questions[2]["solution_body"]
    assert "4" in questions[3]["solution_body"]
    assert "最小值 0" in questions[4]["solution_body"]


def test_paper_metadata_attribute_extraction() -> None:
    t1 = "2022-2023学年内蒙古包头一中高二（上）期中数学试卷（理科）"
    m1 = parser.analyze_paper_metadata_rules(t1)
    assert m1["年份"] == "2022-2023"
    assert m1["学校"] == "包头一中"
    assert m1["地区"] == "内蒙古包头"
    assert m1["年级"] == "高二"
    assert m1["学期"] == "上"
    assert m1["考试种类"] == "期中"

    t2 = "2022-2023学年内蒙古呼和浩特市新城区土默特中学高一（下）第一次月考数学试卷"
    m2 = parser.analyze_paper_metadata_rules(t2)
    assert m2["年份"] == "2022-2023"
    assert m2["学校"] == "土默特中学"
    assert m2["地区"] == "内蒙古呼和浩特"
    assert m2["年级"] == "高一"
    assert m2["学期"] == "下"
    assert m2["考试种类"] == "第一次月考"

    t3 = "2022-2023学年内蒙古赤峰二中高一（下）第二次月考数学试卷"
    m3 = parser.analyze_paper_metadata_rules(t3)
    assert m3["考试种类"] == "第二次月考"

    t4 = "2020-2021学年内蒙古包头四中高二（下）第三次月考数学试卷"
    m4 = parser.analyze_paper_metadata_rules(t4)
    assert m4["考试种类"] == "第三次月考"

    t5 = "2021-2022学年内蒙古包头市高二（上）期末数学试卷（理科）"
    m5 = parser.analyze_paper_metadata_rules(t5)
    assert m5["考试种类"] == "期末"


def test_choice_answer_extraction_latex_support() -> None:
    sol = "由全称命题可知... 故选： $C$ ."
    ans = parser.extract_choice_answer(sol)
    assert ans == "C"

    sol2 = "化简得答案 故选： $B.$"
    ans2 = parser.extract_choice_answer(sol2)
    assert ans2 == "B"

    # Multiple choice
    sol3 = "综合上述分析，故选：ACD."
    ans3 = parser.extract_choice_answer(sol3)
    assert ans3 == "ACD"


def test_fill_in_answer_proposition_deduction() -> None:
    sol = (
        "当 $m = 0, n > 0$ 则方程为两条直线，故 $p_4$ 为真命题，\n\n"
        "① $p_{1}\\vee p_{4}$ 为真命题，② $p_{1}\\wedge p_{2}$ 为假命题，"
        "③ $\\neg p_{2}\\wedge p_{3}$ 为真命题，④ $\\neg p_{3}\\vee\\neg p_{4}$ 为假命题."
    )
    q = "则下述命题中所有真命题的序号是____。"
    ans = parser.extract_fill_answer(sol, q)
    assert ans == "①③"


def test_choice_and_fill_in_forbid_xiangjianjiexi() -> None:
    # Choice question cannot have 详见解析
    with pytest.raises(parser.ReviewRequired):
        parser.solution_fields("本题解析详见推导过程。", choice=True, recovered=None)

    # Fill-in question cannot have 详见解析
    with pytest.raises(parser.ReviewRequired):
        parser.solution_fields("本题直接代入公式计算得到结果。", choice=False, recovered=None, fill_in=True)



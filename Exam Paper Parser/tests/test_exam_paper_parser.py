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

【详解】由整数加法法则可得 $2+2=4$。
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
    assert Path(manifest["sections"][0]["note_path"]).parent.name == "一_单选题"

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

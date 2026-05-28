from math_knowledge_tools.md_formatter.exercise import ExerciseFormatter
from math_knowledge_tools.md_formatter.textbook import TextbookFormatter


def test_textbook_formatter_converts_callouts_and_common_math():
    source = "# 探究\n\n设 $A^{\\prime}$ 为点 A 的对应点。\n"

    formatted = TextbookFormatter().format_string(source)

    assert "> [!explore] 探究" in formatted
    assert "$A'$" in formatted


def test_exercise_formatter_tags_answers_and_options():
    source = "1. 选择题\nA. 1B. 2\n答案：A\n解析：因为如此。"

    formatted = ExerciseFormatter().format_string(source)

    assert "##### 1." in formatted
    assert "$\\quad$A." in formatted
    assert '<span class="fake-tag">答案</span>' in formatted
    assert '<span class="fake-tag">解析</span>' in formatted


def test_dry_run_reports_change_without_writing(tmp_path):
    path = tmp_path / "sample.md"
    source = "**1.** 选择题\n答案：A\n"
    path.write_text(source, encoding="utf-8")

    changed = ExerciseFormatter().process_file(path, dry_run=True)

    assert changed is True
    assert path.read_text(encoding="utf-8") == source

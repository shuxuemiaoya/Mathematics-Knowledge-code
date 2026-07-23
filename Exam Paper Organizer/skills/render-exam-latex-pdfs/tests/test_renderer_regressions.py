from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "render_exam_pdfs.py"
SPEC = importlib.util.spec_from_file_location("render_exam_pdfs", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RendererTransformRegressionTests(unittest.TestCase):
    def test_answer_layout_preserves_function_derivative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tex = Path(temporary) / "fixture.tex"
            tex.write_text(
                "question f'(1) (1)\n"
                "\\beginExamAnswers\n"
                "answer f'(1) (1) （2） A　B\n",
                encoding="utf-8",
            )
            result = MODULE.apply_answer_booklet_layout(tex)
            rendered = tex.read_text(encoding="utf-8")

        self.assertIn("answer f'(1)", rendered)
        self.assertIn("\\noindent（1）", rendered)
        self.assertIn("\\noindent（2）", rendered)
        self.assertIn("A\\quad{}B", rendered)
        self.assertEqual(result["subpart_breaks"], 2)
        self.assertEqual(result["answer_separators"], 1)

    def test_answer_layout_does_not_touch_question_booklet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tex = Path(temporary) / "fixture.tex"
            original = "question A　B (1)\n"
            tex.write_text(original, encoding="utf-8")
            result = MODULE.apply_answer_booklet_layout(tex)
            rendered = tex.read_text(encoding="utf-8")

        self.assertEqual(rendered, original)
        self.assertEqual(result["answer_separators"], 0)

    def test_url_encoded_image_path_resolves_without_markdown_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "images" / "figure one.png"
            image.parent.mkdir()
            image.write_bytes(b"fixture")
            tex = root / "fixture.tex"
            tex.write_text(
                "\\includegraphics{figure%20one.png}\n",
                encoding="utf-8",
            )
            result = MODULE.resolve_latex_image_paths(tex, [root])
            rendered = tex.read_text(encoding="utf-8")

        self.assertFalse(result["unresolved"])
        self.assertIn(image.resolve().as_posix(), rendered)

    def test_templates_keep_pandoc_table_and_title_helpers(self) -> None:
        paper = (SKILL_DIR / "assets" / "期末试卷最简版.tex").read_text(encoding="utf-8")
        solutions = (SKILL_DIR / "assets" / "exam-solutions-template.tex").read_text(
            encoding="utf-8"
        )
        for template in (paper, solutions):
            self.assertIn("\\usepackage{calc}", template)
            self.assertIn("\\providecommand{\\real}[1]{#1}", template)
            self.assertIn("\\providecommand{\\toprule}", template)
            self.assertIn("\\newcommand{\\ExamMainTitle}", template)
            self.assertIn("\\newcommand{\\beginExamAnswers}", template)


@unittest.skipUnless(
    shutil.which("pandoc") and shutil.which("xelatex"),
    "Pandoc and XeLaTeX are required for the integration smoke test.",
)
class RendererIntegrationSmokeTests(unittest.TestCase):
    def test_both_templates_compile_regression_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            paper = folder / "fixture（题解整合版）.md"
            solutions = folder / "fixture（题解整合版）（解析版）.md"
            markdown = """---
title: Fixture Title
---

# Fixture Title

## 数学

1. 已知 $f'(1)=2$，选择正确结论。

   - A. 甲
   - B. 乙
   - C. 丙
   - D. 丁

| 项目 | 数值 |
|---|---:|
| $f'(1)$ | 2 |

<div style="page-break-after: always;"></div>

<!-- answer-section -->

# 数学参考答案

1. A　2. B
"""
            solution_markdown = markdown.replace(
                "1. 已知 $f'(1)=2$，选择正确结论。\n",
                """1. 已知 $f'(1)=2$，选择正确结论。

   <!-- exam-solution:start id="1" -->
   **答案：** A　**分析：** 使用导数定义。

   **详细解析：** 保留 $f'(1)$，并检查（1）中的条件。
   <!-- exam-solution:end id="1" -->
""",
            )
            paper.write_text(markdown, encoding="utf-8")
            solutions.write_text(solution_markdown, encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPT),
                str(folder),
                "--paper",
                str(paper),
                "--solutions",
                str(solutions),
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=180,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(len(summary["editions"]), 2)
            for edition in summary["editions"]:
                self.assertGreater(edition["pdf_bytes"], 0)
                if edition["page_count"] is not None:
                    self.assertGreater(edition["page_count"], 0)
                self.assertTrue(Path(edition["pdf"]).is_file())

            paper_tex = Path(summary["editions"][0]["tex"]).read_text(encoding="utf-8")
            self.assertEqual(paper_tex.count("Fixture Title"), 1)


if __name__ == "__main__":
    unittest.main()

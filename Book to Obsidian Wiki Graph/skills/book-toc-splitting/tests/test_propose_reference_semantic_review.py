from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "propose_reference_semantic_review.py"
)
SPEC = importlib.util.spec_from_file_location(
    "propose_reference_semantic_review", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReferenceSemanticReviewProposalTests(unittest.TestCase):
    def make_manifest(self, path: Path, end_line: int) -> Path:
        manifest = path / "split-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "nodes": [
                        {
                            "key": "lesson",
                            "title": "函数的表示法",
                            "category": "knowledge",
                            "start_line": 1,
                            "end_line": end_line,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return manifest

    def test_partial_reference_body_match_remains_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference" / "知识点"
            reference.mkdir(parents=True)
            formatted = root / "formatted.md"
            source_text = (
                "# 函数的表示法\n\n"
                "依法纳税是每个公民应尽的义务，个人所得税按照税率计算。\n\n"
                "后续正文转向另一个没有关系的教学主题。\n"
            )
            formatted.write_text(source_text, encoding="utf-8")
            (reference / "选择恰当的方法表示问题中的函数关系.md").write_text(
                (
                    "依法纳税是每个公民应尽的义务，个人所得税按照税率计算。\n"
                    "接下来还应包括完整的分段函数计算、图象、解答和两道练习题，"
                    "这些内容在候选范围中全部缺失。\n"
                ),
                encoding="utf-8",
            )
            manifest = self.make_manifest(
                root, len(source_text.splitlines())
            )

            report = MODULE.propose(formatted, manifest, reference.parent)
            suggestion = report["suggestions"][0]

            self.assertEqual(suggestion["status"], "ambiguous")
            self.assertLess(suggestion["matched_reference_ratio"], 0.85)
            self.assertIn(
                "incomplete-reference-body-match",
                suggestion["review_flags"],
            )

    def test_complete_reference_body_match_is_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference" / "知识点"
            reference.mkdir(parents=True)
            formatted = root / "formatted.md"
            body = (
                "依法纳税是每个公民应尽的义务，个人所得税按照税率计算，"
                "并根据应纳税所得额写出完整的分段函数。\n"
            )
            source_text = "# 函数的表示法\n\n" + body
            formatted.write_text(source_text, encoding="utf-8")
            (reference / "选择恰当的方法表示问题中的函数关系.md").write_text(
                body,
                encoding="utf-8",
            )
            manifest = self.make_manifest(
                root, len(source_text.splitlines())
            )

            report = MODULE.propose(formatted, manifest, reference.parent)
            suggestion = report["suggestions"][0]

            self.assertEqual(suggestion["status"], "review_candidate")
            self.assertGreaterEqual(
                suggestion["matched_reference_ratio"], 0.85
            )
            self.assertEqual(suggestion["review_flags"], [])


if __name__ == "__main__":
    unittest.main()

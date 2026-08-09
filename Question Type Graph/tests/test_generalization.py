from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from question_type_graph.common import write_json_atomic
from question_type_graph.content import plan_content
from question_type_graph.hierarchy import plan_hierarchy
from question_type_graph.mineru import PdfPart, build_payload
from question_type_graph.profile import create_profile


class TestGeneralization(unittest.TestCase):
    def test_mineru_payload_is_forced_and_format_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            part = tmp_path / "part.pdf"
            part.write_bytes(b"pdf")
            payload = build_payload([PdfPart(part, 1, 1, 1, 1, "stable")], "ch")
            self.assertEqual(payload, {
                "files": [{"name": "part.pdf", "data_id": "stable", "is_ocr": True}],
                "model_version": "vlm",
                "language": "ch",
                "enable_formula": True,
                "enable_table": True,
            })

    def test_numbering_patterns_are_adapter_controlled(self) -> None:
        cases = [
            (r"^(?P<number>\d+)[.]\s+", "12. Arabic", "12"),
            (r"^第(?P<number>[一二三四五六七八九十]+)题\s*", "第三题 Chinese", "三"),
            (r"^(?P<number>[①②③④⑤])\s*", "② Circled", "②"),
        ]
        for pattern, line, number in cases:
            with self.subTest(pattern=pattern, line=line):
                m = re.match(pattern, line)
                self.assertIsNotNone(m)
                self.assertEqual(m.group("number"), number)

    def test_no_toc_hierarchy_accepts_reviewed_start_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source.md"
            source.write_text("Preface\nUnit without TOC\n1. Question.\n", encoding="utf-8")
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile([f"questions={source}"], "No TOC", staging, vault, vault / "graph", "en", None, False)
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
                        "reason": "Reviewer confirmed the source has no TOC",
                    },
                    "entries": [{"key": "u", "title": "Unit without TOC", "start_line": 2, "level": 1, "output": "u/u.md"}],
                },
                "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": [], "unknown_label_policy": "retain"},
            }
            adapter_path = staging / "format-adapter.json"
            write_json_atomic(adapter_path, adapter)

            manifest = plan_hierarchy(profile_path, adapter_path)

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["entries"][0]["start_line"], 2)

    def test_reusable_code_has_no_sample_book_constants(self) -> None:
        root = Path(__file__).resolve().parents[1] / "lib"
        text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
        forbidden = ["必刷题", "集合与常用逻辑用语", "高中必刷题数学必修第一册"]
        for value in forbidden:
            self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main()

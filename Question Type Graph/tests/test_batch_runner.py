"""Tests for Universal Batch Pipeline Runner."""

import tempfile
import unittest
from pathlib import Path

from question_type_graph.batch import (
    auto_confirm_manifests,
    derive_book_title,
    discover_source_files,
    process_single_source,
)
from question_type_graph.common import write_json_atomic


class TestBatchRunner(unittest.TestCase):
    def test_derive_book_title(self) -> None:
        self.assertEqual(derive_book_title(Path("必修第一册第一课时（答案解析）.pdf")), "必修第一册第一课时")
        self.assertEqual(derive_book_title(Path("老唐说题圆锥曲线（教师版）.pdf")), "老唐说题圆锥曲线")
        self.assertEqual(derive_book_title(Path("高考数学真题(解析版).pdf")), "高考数学真题")

    def test_discover_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f1 = tmp_path / "paper1.pdf"
            f2 = tmp_path / "paper2.md"
            f3 = tmp_path / "sub" / "paper3.pdf"
            f3.parent.mkdir(parents=True)
            f1.touch()
            f2.touch()
            f3.touch()

            found = discover_source_files(tmp_path)
            self.assertEqual(len(found), 3)

            pdf_only = discover_source_files(tmp_path, patterns=["*.pdf"])
            self.assertEqual(len(pdf_only), 2)

    def test_auto_confirm_manifests_without_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            manifest = tmp_path / "question-type-manifest.json"
            write_json_atomic(manifest, {
                "schema_version": 1,
                "status": "review_required",
                "reviewer_confirmed": False,
                "review": [{"kind": "question-minor-note", "message": "info"}],
            })
            confirmed = auto_confirm_manifests(tmp_path)
            self.assertIn("question-type-manifest.json", confirmed)

            # Blocked manifest with question-sequence-discontinuity
            blocked_manifest = tmp_path / "hierarchy-manifest.json"
            write_json_atomic(blocked_manifest, {
                "schema_version": 1,
                "status": "review_required",
                "reviewer_confirmed": False,
                "review": [{"kind": "question-sequence-discontinuity", "missing": 3}],
            })
            confirmed2 = auto_confirm_manifests(tmp_path)
            self.assertNotIn("hierarchy-manifest.json", confirmed2)


if __name__ == "__main__":
    unittest.main()

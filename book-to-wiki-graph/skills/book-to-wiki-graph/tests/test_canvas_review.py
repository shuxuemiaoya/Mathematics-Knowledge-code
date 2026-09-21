from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import canvas_review


class CanvasReviewTests(unittest.TestCase):
    def test_prepare_binds_every_png_and_finalize_requires_logic_first_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canvas = root / "overview.canvas"
            png = root / "overview.png"
            manifest = root / "book-graph.json"
            index = root / "canvas-index.json"
            canvas.write_text(json.dumps({"nodes": [{"id": "n", "type": "text", "text": "Book", "x": 0, "y": 0, "width": 100, "height": 60}], "edges": []}), encoding="utf-8")
            png.write_bytes(b"\x89PNG\r\n\x1a\nreview")
            manifest.write_text(json.dumps({"nodes": [], "relations": []}), encoding="utf-8")
            index.write_text(json.dumps({
                "schema_version": 3, "manifest": str(manifest), "book_root": str(root),
                "atlas": {"role": "book-atlas", "root_key": "root", "path": "overview.canvas", "png_path": "overview.png"},
                "chapter_maps": [], "section_maps": [],
            }), encoding="utf-8")
            jobs_path = root / "canvas-review-jobs.json"
            # The prepared job only needs the PNG/Canvas bytes; its index does
            # not need to be a complete graph for this isolated contract test.
            jobs = canvas_review.prepare(index, jobs_path)
            self.assertEqual(len(jobs["jobs"]), 1)
            decision = {
                "job_id": jobs["jobs"][0]["job_id"],
                "image_observations": ["PNG 已检查，节点边界清晰"],
                "logic": {"score": 1.0, "missing_relations": [], "wrong_relations": [], "orphan_nodes": [], "port_violations": []},
                "visual": {"score": 0.9, "visual_issues": []},
                "verdict": "passed", "confidence": 0.98,
                "actions": [{"priority": "logic", "action": "no-change", "evidence": "无逻辑修改"}],
            }
            draft_path = root / "canvas-review-draft.json"
            draft_path.write_text(json.dumps({
                "reviewer": {"type": "codex-agent", "model": "test"},
                "decisions": [decision],
            }, ensure_ascii=False), encoding="utf-8")
            decisions_path = root / "canvas-review-decisions.json"
            decisions = canvas_review.seal_decisions(jobs_path, draft_path, decisions_path)
            self.assertEqual(
                decisions["decisions"][0]["png_sha256"],
                jobs["jobs"][0]["png_sha256"],
            )
            report = canvas_review.validate(jobs_path, decisions_path)
            self.assertEqual(report["status"], "passed", report)
            final = canvas_review.finalize(jobs_path, decisions_path, root / "review")
            self.assertEqual(final["status"], "passed", final)
            self.assertTrue((root / "review" / "canvas-review-final.json").is_file())


if __name__ == "__main__":
    unittest.main()

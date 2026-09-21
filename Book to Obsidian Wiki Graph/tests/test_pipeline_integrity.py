"""Cross-component regressions for the 2026-09 workflow audit (no network)."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(skill, name):
    path = ROOT / "skills" / skill / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location("integrity_" + name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


split = module("book-toc-splitting", "split_book_by_toc")
audit = module("book-graph-audit", "audit_obsidian_graph")
metadata = module("book-graph-metadata", "tag_book_metadata")
markdown = module("book-graph-markdown", "standardize_markdown")
runtime = module("book-to-obsidian-wiki-graph", "pipeline_runtime")
pdf = module("book-pdf-to-markdown", "book_pdf_to_markdown")
concepts = module("book-graph-concepts", "apply_concept_candidates")
toc = module("book-toc-formatting", "format_toc_headings")
repairs = module("book-graph-markdown", "apply_reviewed_content_repairs")
from book_graph_integrity import content_sha256, parse_frontmatter, corpus_snapshot


def dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source.md"
        self.source.write_text("# 演示书\n\n## 条件\n\n若 $x>0$，则 $x^2>0$。\n\n"
                               "<table>\n<tr><td>1</td></tr>\n</table>\n", encoding="utf-8")
        self.vault = self.root / "vault"
        self.book = self.vault / "演示书"
        self.stage = self.root / "staging"
        self.profile_path = self.stage / "book-profile.json"
        self.profile = {"schema_version": 1, "book": {"title": "演示书", "kind": "general"},
            "source": {"path": str(self.source), "kind": "markdown", "sha256": runtime.sha256_file(self.source)},
            "paths": {"book_root": str(self.book), "vault_root": str(self.vault), "staging_root": str(self.stage)},
            "categories": [{"role": "content", "directory": "内容", "enabled": True}],
            "links": {"note_mode": "relative"}, "canvas": {"enabled": False}, "workspace": {"backup_policy": "none"}}
        dump(self.profile_path, self.profile)
        identity = {"schema_version": 1, "profile": str(self.profile_path), "source_sha256": self.profile["source"]["sha256"],
                    "input_markdown_sha256": runtime.sha256_file(self.source)}
        self.toc = {**identity, "toc_source_ranges": [], "entries": [
            {"key": "book", "title": "演示书", "level": 1}, {"key": "chapter", "title": "条件", "level": 2}]}
        self.manifest = {**identity, "semantic_review": {"headings": []}, "nodes": [
            {"key": "book", "title": "演示书", "category": "root", "parent_key": None,
             "filename": "演示书.md", "start_line": 1, "end_line": 9, "toc_key": "book"},
            {"key": "chapter", "title": "条件", "category": "content", "parent_key": "book",
             "filename": "条件.md", "start_line": 3, "end_line": 9, "toc_key": "chapter"}]}

    def split_book(self):
        return split.write_split(self.source, self.profile, self.toc, self.manifest, self.book)

    def audit_book(self, stage="pre-canvas"):
        return audit.audit_book(self.book, self.vault, profile_path=self.profile_path,
            coverage_manifest=self.stage / "coverage-manifest.json", stage=stage)

    def test_general_book_split_format_metadata_final_without_concepts(self):
        self.split_book()
        for gate in ("split", "concepts"):
            result = self.audit_book(gate)
            self.assertEqual(result["status"], "passed", result["errors"])
        markdown.run(self.profile_path, self.stage / "markdown-report.json")
        metadata.process_book_metadata(self.book, self.profile_path, self.stage / "metadata-report.json")
        result = self.audit_book("final")
        self.assertEqual(result["status"], "passed", result["errors"])
        fields, _ = parse_frontmatter((self.book / "内容/条件.md").read_text())
        self.assertNotIn("年级", fields)
        self.assertNotIn("难度", fields)
        self.assertFalse((self.book / "概念").exists())

    def test_final_rejects_deleted_condition_changed_formula_table_or_order(self):
        self.split_book()
        metadata.process_book_metadata(self.book, self.profile_path, self.stage / "metadata-report.json")
        note = self.book / "内容/条件.md"
        original = note.read_text()
        changes = [original.replace("若 $x>0$，", ""), original.replace("$x^2>0$", "$x^2<0$"),
                   original.replace("<td>1</td>", "<td>2</td>"),
                   original.replace("若 $x>0$，则 $x^2>0$。", "则 $x^2>0$。若 $x>0$，")]
        for changed in changes:
            with self.subTest(changed=changed):
                note.write_text(changed)
                result = self.audit_book("final")
                self.assertIn("coverage-content-changed", {e["code"] for e in result["errors"]})
        note.write_text(original)
        self.assertEqual(self.audit_book("final")["status"], "passed")

    def test_coverage_rejects_missing_unit_and_missing_source_lines(self):
        self.split_book()
        path = self.stage / "coverage-manifest.json"
        payload = json.loads(path.read_text())
        payload["units"].pop()
        dump(path, payload)
        result = self.audit_book("split")
        codes = {e["code"] for e in result["errors"]}
        self.assertIn("coverage-expected-keys-mismatch", codes)
        self.assertIn("coverage-source-evidence-invalid", codes)

    def test_split_rejects_partial_root(self):
        self.manifest["nodes"][0]["start_line"] = 2
        with self.assertRaisesRegex(split.SplitError, "complete source"):
            self.split_book()

    def test_split_does_not_freeze_a_lossy_render_as_the_baseline(self):
        original = split.render_node
        def lossy(*args, **kwargs):
            return original(*args, **kwargs).replace("若 $x>0$，", "")
        with patch.object(split, "render_node", side_effect=lossy):
            with self.assertRaisesRegex(split.SplitError, "loses or reorders"):
                self.split_book()
        self.assertFalse(self.book.exists())

    def test_split_recovers_after_directory_publish_before_coverage_write(self):
        real_write = split.atomic_write
        def fail_coverage(path, text):
            if path.name == "coverage-manifest.json":
                raise OSError("injected disk failure")
            return real_write(path, text)
        with patch.object(split, "atomic_write", side_effect=fail_coverage):
            with self.assertRaisesRegex(OSError, "injected"):
                self.split_book()
        self.assertTrue(self.book.is_dir())
        self.split_book()
        self.assertEqual(self.audit_book("split")["status"], "passed")
        (self.book / "内容/条件.md").write_text("human edit")
        with self.assertRaisesRegex(split.SplitError, "drift"):
            self.split_book()

    def test_formatter_checks_math_tables_code_and_order(self):
        source = "#### 思考\n\n若 $x>0$，则成立。\n\n<table><tr><td>1</td></tr></table>\n"
        result, _ = markdown.standardize_text(source)
        self.assertTrue(all(markdown.invariants(source, result).values()))
        for changed in (result.replace("x>0", "x<0"), result.replace("<td>1", "<td>2"), result.replace("若", "")):
            self.assertFalse(markdown.invariants(source, changed)["source_order"])
        self.assertNotEqual(content_sha256("```py\nx = 1\n```"), content_sha256("```py\nx = 2\n```"))
        self.assertNotEqual(content_sha256("$$\\text{a b}$$"), content_sha256("$$\\text{ab}$$"))
        quoted = "> [!question] 思考\n> $$\n> x>0\n>\n> y>0\n> $$\n"
        self.assertEqual(content_sha256("#### 思考\n$$\nx>0\n\ny>0\n$$\n"), content_sha256(quoted))

    def test_yaml_preserves_nested_types_aliases_tags_and_body(self):
        text = "---\naliases:\n  - 集合\n  - 'A: B'\ntags: [math, book]\ncustom:\n  active: true\n  count: 3\nsummary: |\n  第一行\n  第二行\n---\n\n正文 $x>0$。\n"
        fields, body = parse_frontmatter(text)
        output = metadata.format_frontmatter(fields, body)
        self.assertEqual(parse_frontmatter(output), (fields, body))
        self.assertEqual(metadata.infer_grade("数学 必修第二册", ""), "高一")
        with self.assertRaises(ValueError):
            parse_frontmatter("---\ntags: [a]\ntags: [b]\n---\ntext")

    def test_final_rejects_missing_or_invalid_metadata(self):
        self.split_book()
        self.assertIn("metadata-invalid", {e["code"] for e in self.audit_book("final")["errors"]})
        metadata.process_book_metadata(self.book, self.profile_path, self.stage / "metadata-report.json")
        note = self.book / "内容/条件.md"
        note.write_text(note.read_text().replace("节点类型: 内容", "节点类型: []"))
        self.assertIn("metadata-invalid", {e["code"] for e in self.audit_book("final")["errors"]})

    def test_reviewed_repair_requires_bound_report_and_preserves_original_baseline(self):
        self.split_book()
        target = self.book / "内容/条件.md"
        recipe = self.stage / "repairs.json"
        report = self.stage / "repair-report.json"
        coverage_before = (self.stage / "coverage-manifest.json").read_bytes()
        dump(recipe, {"profile": str(self.profile_path), "source_sha256": self.profile["source"]["sha256"],
            "reviewer_confirmed": True, "repairs": [{"path": "内容/条件.md", "before_sha256": runtime.sha256_file(target),
            "operation": "replace-text", "old": "若", "new": "如果", "reason": "edition correction",
            "evidence": "reviewed same-edition page 1"}]})
        argv = ["repair", str(self.profile_path), str(recipe), str(report), "--reviewer-confirmed"]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(repairs.main(), 0)
        self.assertEqual((self.stage / "coverage-manifest.json").read_bytes(), coverage_before)
        self.assertEqual(self.audit_book("split")["status"], "failed")
        result = audit.audit_book(self.book, self.vault, profile_path=self.profile_path,
            coverage_manifest=self.stage / "coverage-manifest.json", stage="split", content_repair_reports=[report])
        self.assertEqual(result["status"], "passed", result["errors"])
        recipe.write_text(recipe.read_text() + " ")
        result = audit.audit_book(self.book, self.vault, profile_path=self.profile_path,
            coverage_manifest=self.stage / "coverage-manifest.json", stage="split", content_repair_reports=[report])
        self.assertIn("content-repair-evidence-invalid", {e["code"] for e in result["errors"]})

    def test_interrupted_running_stage_can_restart_but_live_process_cannot(self):
        state = runtime.init_state(self.profile_path)
        runtime.begin_stage(state, "markdown-registration", [])
        runtime.validate_resume(state)
        self.assertEqual(state["stages"][1]["status"], "failed")
        stage = runtime.begin_stage(state, "markdown-registration", [])
        self.assertEqual(stage["attempts"], 2)
        stage["execution"] = {"host": socket.gethostname(), "pid": os.getpid()}
        with self.assertRaisesRegex(runtime.PipelineError, "still running"):
            runtime.validate_resume(state)

    def test_real_toc_report_rejects_modified_output(self):
        state = runtime.init_state(self.profile_path)
        runtime.begin_stage(state, "markdown-registration", [])
        runtime.complete_stage(state, "markdown-registration", [("file", self.source)])
        runtime.begin_stage(state, "toc-formatting", [])
        manifest_path = self.stage / "toc-manifest.json"
        candidate = self.stage / "formatted.md"
        report = self.stage / "toc-format-report.json"
        dump(manifest_path, self.toc)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(toc.main([str(self.source), str(manifest_path), str(candidate),
                                      "--profile", str(self.profile_path), "--report", str(report)]), 0)
        original = candidate.read_text()
        candidate.write_text(original.replace("x>0", "x<0"))
        declared = [("file", candidate), ("toc-manifest", manifest_path), ("toc-format-report", report)]
        with self.assertRaisesRegex(runtime.IdentityError, "candidate digest"):
            runtime.complete_stage(state, "toc-formatting", declared)
        candidate.write_text(original)
        runtime.complete_stage(state, "toc-formatting", declared)

    def test_report_snapshot_rejects_later_note_change(self):
        self.split_book()
        path = self.stage / "audit.json"
        dump(path, self.audit_book("split"))
        runtime.validate_handoff_bindings({}, [("audit-report", path)], self.profile)
        (self.book / "内容/条件.md").write_text("changed")
        with self.assertRaisesRegex(runtime.IdentityError, "stale"):
            runtime.validate_handoff_bindings({}, [("audit-report", path)], self.profile)

    def test_audit_rejects_manifest_modified_after_review(self):
        self.split_book()
        path = self.stage / "audit.json"
        dump(path, self.audit_book("split"))
        coverage = self.stage / "coverage-manifest.json"
        payload = json.loads(coverage.read_text())
        payload["units"].pop()
        dump(coverage, payload)
        with self.assertRaisesRegex(runtime.IdentityError, "input evidence changed"):
            runtime.validate_handoff_bindings({}, [("audit-report", path)], self.profile)

    def test_coordinator_completes_all_general_book_stages(self):
        state = runtime.init_state(self.profile_path)
        runtime.begin_stage(state, "markdown-registration", [])
        runtime.complete_stage(state, "markdown-registration", [("file", self.source)])
        runtime.begin_stage(state, "toc-formatting", [])
        toc_path, candidate, toc_report = [self.stage / name for name in ("toc.json", "formatted.md", "toc-report.json")]
        dump(toc_path, self.toc)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(toc.main([str(self.source), str(toc_path), str(candidate),
                                      "--profile", str(self.profile_path), "--report", str(toc_report)]), 0)
        runtime.complete_stage(state, "toc-formatting", [("file", candidate), ("toc-manifest", toc_path), ("toc-format-report", toc_report)])
        self.source = candidate
        self.manifest["input_markdown_sha256"] = runtime.sha256_file(candidate)
        split_path = self.stage / "split-manifest.json"
        dump(split_path, self.manifest)
        runtime.begin_stage(state, "toc-splitting", [])
        self.split_book()
        split_audit = self.stage / "split-audit.json"
        dump(split_audit, self.audit_book("split"))
        runtime.complete_stage(state, "toc-splitting", [("directory", self.book), ("split-manifest", split_path),
            ("coverage-manifest", self.stage / "coverage-manifest.json"), ("audit-report", split_audit)])
        for name, gate in (("concepts", "concepts"), ("markdown-standardization", "formatting"), ("pre-canvas-audit", "pre-canvas")):
            runtime.begin_stage(state, name, [])
            artifacts = []
            if name == "markdown-standardization":
                report = self.stage / "markdown-report.json"
                markdown.run(self.profile_path, report)
                artifacts.append(("markdown-report", report))
            path = self.stage / (name + "-audit.json")
            dump(path, self.audit_book(gate))
            runtime.complete_stage(state, name, [*artifacts, ("audit-report", path)])
        runtime.begin_stage(state, "metadata-tagging", [])
        report = self.stage / "metadata-report.json"
        metadata.process_book_metadata(self.book, self.profile_path, report)
        runtime.complete_stage(state, "metadata-tagging", [("metadata-report", report)])
        runtime.begin_stage(state, "final-audit", [])
        report = self.stage / "final-audit.json"
        result = self.audit_book("final")
        self.assertEqual(result["status"], "passed", result["errors"])
        dump(report, result)
        runtime.complete_stage(state, "final-audit", [("audit-report", report), ("tree", self.book)])
        self.assertEqual(state["status"], "completed")
        runtime.validate_resume(state)
        self.assertEqual(state["status"], "completed")

    def concept_fixture(self):
        source = self.book / "内容/定义.md"
        source.parent.mkdir(parents=True)
        source.write_text("# 定义\n\n总体叫做集合。\n")
        self.profile["categories"].append({"role": "concept", "directory": "概念", "enabled": True})
        self.profile["links"]["note_mode"] = "vault-root"
        dump(self.profile_path, self.profile)
        coverage = self.stage / "coverage.json"
        candidates = self.stage / "candidates.json"
        manifest = self.stage / "concept-manifest.json"
        dump(coverage, {"units": [{"source_key": "definition", "target": "内容/定义.md"}]})
        dump(candidates, {"status": "approved", "concepts": [{"name": "集合", "reviewed": True,
            "definition_source": "内容/定义.md", "source_note_sha256": runtime.sha256_file(source),
            "definition_start_line": 3, "definition_end_line": 3, "anchor_text": "总体叫做集合", "link_text": "集合"}]})
        return source, coverage, candidates, manifest

    def test_concept_transaction_recovers_partial_write_and_is_idempotent(self):
        source, coverage, candidates, manifest = self.concept_fixture()
        real_write = concepts.atomic_write
        def fail_source(path, text):
            if path == source:
                raise OSError("injected source write failure")
            return real_write(path, text)
        with patch.object(concepts, "atomic_write", side_effect=fail_source):
            with self.assertRaises(OSError):
                concepts.apply_candidates(self.profile_path, coverage, candidates, manifest)
        self.assertTrue((self.book / "概念/集合.md").exists())
        self.assertNotIn("[集合]", source.read_text())
        concepts.apply_candidates(self.profile_path, coverage, candidates, manifest)
        snapshot = corpus_snapshot(self.book)
        concepts.apply_candidates(self.profile_path, coverage, candidates, manifest)
        self.assertEqual(corpus_snapshot(self.book), snapshot)
        self.assertEqual(source.read_text().count("[集合]"), 1)
        source.write_text(source.read_text() + "人工补充\n")
        with self.assertRaisesRegex(ValueError, "drift"):
            concepts.apply_candidates(self.profile_path, coverage, candidates, manifest)

    def test_concept_rejects_stale_reviewed_source(self):
        source, coverage, candidates, manifest = self.concept_fixture()
        source.write_text(source.read_text() + "changed")
        with self.assertRaisesRegex(ValueError, "digest"):
            concepts.apply_candidates(self.profile_path, coverage, candidates, manifest)
        self.assertFalse((self.book / "概念").exists())

    def test_pdf_conversion_fails_before_publish_when_output_omits_pages(self):
        source = self.root / "book.pdf"
        source.write_bytes(b"mock PDF")
        target = self.stage / "raw.md"
        part = pdf.PdfPart(source, 1, 1, 1, 100, "part1")
        class Client:
            def request_upload_urls(self, parts): return "batch1", ["upload"]
            def upload(self, url, part): pass
            def poll(self, batch): return [{"data_id": "part1", "state": "done", "full_zip_url": "zip"}]
            def download(self, url, path):
                path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("full.md", "Only the first page survived.")
                    archive.writestr("book_content_list.json", json.dumps([{"page_idx": 0, "text": "Only page 1"}]))
        with patch.object(pdf, "pdf_page_count", return_value=100), patch.object(pdf, "prepare_parts", return_value=[part]), \
             patch.object(pdf, "load_settings", return_value=None), patch.object(pdf, "MineruClient", return_value=Client()):
            with self.assertRaisesRegex(pdf.ConversionError, "coverage unverified"):
                pdf.convert(source, target, self.profile_path, argparse.Namespace(overwrite=False))
        self.assertFalse(target.exists())

    def test_output_page_inventory_accepts_complete_indices_and_explicit_empty_page(self):
        path = self.root / "result.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("middle.json", json.dumps({"pdf_info": [
                {"page_idx": 0, "para_blocks": [{"text": "body"}]}, {"page_idx": 1, "para_blocks": []}]}))
        self.assertEqual(pdf.output_page_evidence(path, 2)["page_indices"], [0, 1])

    def test_pdf_report_completes_gate_and_detects_changed_assets(self):
        source = self.root / "book.pdf"
        source.write_bytes(b"mock PDF")
        target = self.stage / "raw.md"
        part = pdf.PdfPart(source, 1, 1, 1, 2, "part1")
        self.profile["source"] = {"path": str(source), "kind": "pdf", "sha256": runtime.sha256_file(source)}
        dump(self.profile_path, self.profile)
        class Client:
            def request_upload_urls(self, parts): return "batch1", ["upload"]
            def upload(self, url, part): pass
            def poll(self, batch): return [{"data_id": "part1", "state": "done", "full_zip_url": "zip"}]
            def download(self, url, path):
                path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("full.md", "First page.\n\nSecond page.")
                    archive.writestr("book_content_list.json", json.dumps([
                        {"page_idx": 0, "text": "First page."}, {"page_idx": 1, "text": "Second page."}]))
        state = runtime.init_state(self.profile_path)
        runtime.begin_stage(state, "pdf-conversion", [])
        with patch.object(pdf, "pdf_page_count", return_value=2), patch.object(pdf, "prepare_parts", return_value=[part]), \
             patch.object(pdf, "load_settings", return_value=None), patch.object(pdf, "MineruClient", return_value=Client()):
            result = pdf.convert(source, target, self.profile_path, argparse.Namespace(overwrite=False))
        artifacts = [("file", target), ("pdf-conversion-report", target.with_suffix(".conversion-report.json"))]
        runtime.complete_stage(state, "pdf-conversion", artifacts)
        asset_root = Path(result["asset_root"])
        asset_root.mkdir(parents=True)
        (asset_root / "unreviewed.png").write_bytes(b"changed")
        with self.assertRaisesRegex(runtime.IdentityError, "assets changed"):
            runtime.validate_handoff_bindings({}, artifacts, self.profile)


if __name__ == "__main__":
    unittest.main()

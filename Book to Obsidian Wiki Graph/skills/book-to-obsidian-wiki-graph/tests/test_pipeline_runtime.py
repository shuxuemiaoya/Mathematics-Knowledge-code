from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "pipeline_runtime.py"
)
SPEC = importlib.util.spec_from_file_location("pipeline_runtime", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PipelineRuntimeTests(unittest.TestCase):
    def make_profile(
        self,
        root: Path,
        *,
        canvas: bool = False,
        reference_scope: str | None = None,
        canvas_style_reference: bool = False,
    ) -> tuple[Path, Path, Path, Path]:
        source = root / "source.md"
        source.write_text("# Example\n", encoding="utf-8")
        vault = root / "vault"
        book = vault / "books" / "example"
        staging = root / "staging"
        (book / "知识点").mkdir(parents=True)
        (book / "习题").mkdir()
        (book / "概念").mkdir()
        staging.mkdir()
        profile_path = staging / "book-profile.json"
        profile = {
            "schema_version": 1,
            "book": {
                "title": "Example",
                "kind": "mathematics-textbook",
            },
            "source": {
                "path": str(source.resolve()),
                "kind": "markdown",
                "sha256": MODULE.sha256_file(source),
            },
            "paths": {
                "vault_root": str(vault.resolve()),
                "book_root": str(book.resolve()),
                "staging_root": str(staging.resolve()),
            },
            "categories": [
                {
                    "role": "knowledge",
                    "directory": "知识点",
                    "enabled": True,
                    "flat": False,
                },
                {
                    "role": "concept",
                    "directory": "概念",
                    "enabled": True,
                    "flat": True,
                },
                {
                    "role": "exercise",
                    "directory": "习题",
                    "enabled": True,
                    "flat": False,
                },
            ],
            "links": {"markdown_only": True},
            "formatting": {"blank_before_top_level_callout": True},
            "canvas": {
                "enabled": canvas,
                "node_colors": {},
                "edge_colors": {},
            },
            "workspace": {"backup_policy": "none"},
        }
        if reference_scope is not None:
            reference = root / "reference"
            reference.mkdir()
            (reference / "样例.md").write_text("# 样例\n", encoding="utf-8")
            profile["reference"] = {
                "path": str(reference.resolve()),
                "sha256": MODULE.inventory_tree_sha256(reference),
                "scope": reference_scope,
            }
        if canvas_style_reference:
            style_canvas = root / "sibling.canvas"
            style_canvas.write_text(
                '{"nodes": [], "edges": []}\n', encoding="utf-8"
            )
            profile["canvas"]["style_reference"] = {
                "path": str(style_canvas.resolve()),
                "sha256": MODULE.sha256_file(style_canvas),
                "scope": "same-series-style",
            }
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False), encoding="utf-8"
        )
        return source, vault, book, profile_path

    def test_state_is_same_run_only_and_uses_markdown_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, _, _, profile = self.make_profile(Path(temporary))
            state = MODULE.init_state(profile)
        self.assertEqual(state["reuse_policy"], "same-run-only")
        self.assertEqual(state["stages"][0]["status"], "completed")
        self.assertEqual(state["stages"][1]["name"], "markdown-registration")
        self.assertEqual(state["stages"][1]["status"], "pending")
        self.assertFalse(
            state["test_options"]["preserve_stage_artifacts"]
        )
        self.assertIsNone(state["test_options"]["checkpoint_root"])

    def test_intake_records_source_inventory_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, profile = self.make_profile(root)
            inventory = root / "staging" / "source-inventory.json"
            inventory.write_text('{"status":"passed"}\n', encoding="utf-8")
            state = MODULE.init_state(profile)

        output_paths = {
            record["path"] for record in state["stages"][0]["outputs"]
        }
        self.assertIn(str(inventory.resolve()), output_paths)

    def test_test_options_are_auto_discovered_and_checkpoint_intake(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, vault, _, profile = self.make_profile(root)
            checkpoint_root = root / "durable-checkpoints"
            options = vault / MODULE.TEST_OPTIONS_FILENAME
            options.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "preserve_stage_artifacts": True,
                        "checkpoint_root": str(checkpoint_root),
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                return_code = MODULE.main(["init", str(profile)])
            result = json.loads(output.getvalue())
            state = MODULE.read_json(Path(result["state"]))
            manifest = Path(result["checkpoint"])
            manifest_exists = manifest.is_file()

        self.assertEqual(return_code, 0)
        self.assertTrue(state["test_options"]["preserve_stage_artifacts"])
        self.assertTrue(manifest_exists)
        self.assertEqual(manifest.parent.name, "attempt-01")
        self.assertEqual(manifest.parent.parent.name, "01-intake")
        self.assertEqual(
            manifest.parents[2].name,
            state["test_options"]["run_id"],
        )

    def test_explicitly_disabled_test_options_create_no_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, vault, _, profile = self.make_profile(root)
            options = vault / MODULE.TEST_OPTIONS_FILENAME
            options.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "preserve_stage_artifacts": False,
                    }
                ),
                encoding="utf-8",
            )
            state = MODULE.init_state(profile)
            checkpoint = MODULE.capture_stage_checkpoint(
                root / "staging" / "pipeline-state.json",
                state,
                "intake",
            )

        self.assertFalse(MODULE.checkpoint_enabled(state))
        self.assertIsNone(state["test_options"]["checkpoint_root"])
        self.assertIsNone(state["test_options"]["run_id"])
        self.assertIsNone(checkpoint)

    def test_checkpoint_restores_a_completed_stage_for_mid_run_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, vault, book, profile = self.make_profile(root)
            checkpoint_root = root / "durable-checkpoints"
            options = vault / MODULE.TEST_OPTIONS_FILENAME
            options.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "preserve_stage_artifacts": True,
                        "checkpoint_root": str(checkpoint_root),
                    }
                ),
                encoding="utf-8",
            )
            state_path = root / "staging" / "pipeline-state.json"
            state = MODULE.init_state(profile)
            MODULE.write_json_atomic(state_path, state)
            MODULE.capture_stage_checkpoint(state_path, state, "intake")
            raw = root / "staging" / "source.raw.md"
            raw.write_text("# Raw\n", encoding="utf-8")
            MODULE.begin_stage(
                state,
                "markdown-registration",
                [("book-profile", profile)],
            )
            MODULE.complete_stage(
                state,
                "markdown-registration",
                [("file", raw)],
            )
            MODULE.write_json_atomic(state_path, state)
            MODULE.capture_stage_checkpoint(
                state_path,
                state,
                "markdown-registration",
            )
            manifest = (
                checkpoint_root
                / state["test_options"]["run_id"]
                / "02-markdown-registration"
                / "attempt-01"
                / "checkpoint-manifest.json"
            )
            shutil.rmtree(root / "staging")
            shutil.rmtree(book)
            restored = MODULE.restore_stage_checkpoint(manifest)
            restored_state = MODULE.read_json(Path(restored["restored_state"]))
            raw_exists = raw.is_file()
            book_exists = book.is_dir()

        self.assertEqual(restored["restored_stage"], "markdown-registration")
        self.assertEqual(restored["next_stage"], "toc-formatting")
        self.assertTrue(raw_exists)
        self.assertFalse(book_exists)
        self.assertEqual(
            restored_state["stages"][1]["status"],
            "completed",
        )

    def test_post_split_checkpoint_restores_that_stage_corpus_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, vault, book, profile = self.make_profile(root)
            options = vault / MODULE.TEST_OPTIONS_FILENAME
            options.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "preserve_stage_artifacts": True,
                        "checkpoint_root": str(root / "durable-checkpoints"),
                    }
                ),
                encoding="utf-8",
            )
            note = book / "知识点" / "集合.md"
            note.write_text("# 集合\n", encoding="utf-8")
            state_path = root / "staging" / "pipeline-state.json"
            state = MODULE.init_state(profile)
            for stage in state["stages"][1:4]:
                stage["status"] = "completed"
                stage["attempts"] = 1
            state["stages"][3]["outputs"] = [
                MODULE.artifact_record("directory", book)
            ]
            MODULE.write_json_atomic(state_path, state)
            MODULE.capture_stage_checkpoint(
                state_path,
                state,
                "toc-splitting",
            )
            manifest = (
                root
                / "durable-checkpoints"
                / state["test_options"]["run_id"]
                / "04-toc-splitting"
                / "attempt-01"
                / "checkpoint-manifest.json"
            )
            shutil.rmtree(book)
            restored = MODULE.restore_stage_checkpoint(manifest)
            restored_note = note.read_text(encoding="utf-8")

        self.assertEqual(restored["restored_stage"], "toc-splitting")
        self.assertEqual(restored["next_stage"], "concepts")
        self.assertEqual(restored_note, "# 集合\n")

    def test_reference_profile_requires_passing_parity_at_final_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, _, profile_path = self.make_profile(
                root,
                reference_scope="style-only",
            )
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            state = MODULE.init_state(profile_path)
            self.assertEqual(state["status"], "active")
            required = MODULE.required_output_kinds("final-audit", profile)
            self.assertIn("reference-parity-report", required)
            payload = {
                "schema_version": 1,
                "stage": "reference-content-parity",
                "status": "content_review_required",
                "profile": str(profile_path.resolve()),
                "source_sha256": MODULE.sha256_file(source),
                "same_book": False,
                "reference": profile["reference"],
                "blocking_summary": {"current_style_structure_issues": 1},
            }
            errors = MODULE.artifact_errors(
                payload,
                "reference-parity-report",
                expected_profile=profile_path.resolve(),
                expected_source_sha256=MODULE.sha256_file(source),
            )
            self.assertEqual(errors, [])
            self.assertIn(
                "reference-parity-report",
                MODULE.PASS_STATUS_KINDS,
            )

    def test_lesson_flow_profile_requires_manifest_at_split_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, profile_path = self.make_profile(root)
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["decomposition"] = {
                "require_lesson_flow_manifest": True
            }
            required = MODULE.required_output_kinds(
                "toc-splitting",
                profile,
            )
        self.assertIn("lesson-flow-manifest", required)
        self.assertIn("lesson-flow-manifest", MODULE.PASS_STATUS_KINDS)

    def test_canvas_style_reference_requires_bound_passing_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, book, profile_path = self.make_profile(
                root,
                canvas=True,
                canvas_style_reference=True,
            )
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertIn(
                "canvas-style-report",
                MODULE.required_output_kinds("canvas", profile),
            )
            candidate = book / "example.canvas"
            candidate.write_text(
                '{"nodes": [], "edges": []}\n', encoding="utf-8"
            )
            graph_manifest = root / "staging" / "graph-manifest.json"
            graph_manifest.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "profile": str(profile_path.resolve()),
                        "source_sha256": MODULE.sha256_file(source),
                        "nodes": [],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )
            style_report = root / "staging" / "canvas-style-report.json"
            report_payload = {
                "schema_version": 1,
                "stage": "canvas-style-parity",
                "status": "passed",
                "profile": str(profile_path.resolve()),
                "source_sha256": MODULE.sha256_file(source),
                "reference": profile["canvas"]["style_reference"],
                "candidate": {
                    "path": str(candidate.resolve()),
                    "sha256": MODULE.sha256_file(candidate),
                },
                "metrics": {"reference": {}, "candidate": {}},
                "blocking_differences": [],
            }
            style_report.write_text(
                json.dumps(report_payload), encoding="utf-8"
            )
            state = MODULE.init_state(profile_path)
            canvas_stage = next(
                stage for stage in state["stages"] if stage["name"] == "canvas"
            )
            canvas_stage["status"] = "running"
            canvas_stage["started_at"] = MODULE.utc_now()

            completed = MODULE.complete_stage(
                state,
                "canvas",
                [("file", candidate), ("graph-manifest", graph_manifest)],
                report=("canvas-style-report", style_report),
            )

            self.assertEqual(completed["status"], "completed")

            report_payload["candidate"]["sha256"] = "b" * 64
            style_report.write_text(
                json.dumps(report_payload), encoding="utf-8"
            )
            state = MODULE.init_state(profile_path)
            canvas_stage = next(
                stage for stage in state["stages"] if stage["name"] == "canvas"
            )
            canvas_stage["status"] = "running"
            canvas_stage["started_at"] = MODULE.utc_now()
            with self.assertRaisesRegex(
                MODULE.IdentityError, "candidate digest"
            ):
                MODULE.complete_stage(
                    state,
                    "canvas",
                    [("file", candidate), ("graph-manifest", graph_manifest)],
                    report=("canvas-style-report", style_report),
                )

            report_payload["candidate"]["sha256"] = MODULE.sha256_file(
                candidate
            )
            report_payload["status"] = "style_review_required"
            report_payload["blocking_differences"] = [{"code": "layout"}]
            style_report.write_text(
                json.dumps(report_payload), encoding="utf-8"
            )
            state = MODULE.init_state(profile_path)
            canvas_stage = next(
                stage for stage in state["stages"] if stage["name"] == "canvas"
            )
            canvas_stage["status"] = "running"
            canvas_stage["started_at"] = MODULE.utc_now()
            with self.assertRaisesRegex(
                MODULE.PipelineError, "report status is not passed"
            ):
                MODULE.complete_stage(
                    state,
                    "canvas",
                    [("file", candidate), ("graph-manifest", graph_manifest)],
                    report=("canvas-style-report", style_report),
                )

    def test_same_book_reference_rejects_unreviewed_split_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, _, profile_path = self.make_profile(
                root,
                reference_scope="same-book-content-and-style",
            )
            payload = {
                "schema_version": 1,
                "profile": str(profile_path.resolve()),
                "source_sha256": MODULE.sha256_file(source),
                "input_markdown_sha256": "c" * 64,
                "semantic_review": {"headings": []},
                "nodes": [],
            }

            errors = MODULE.artifact_errors(
                payload,
                "split-manifest",
                expected_profile=profile_path.resolve(),
                expected_source_sha256=MODULE.sha256_file(source),
            )

        self.assertTrue(
            any("requires adopted semantic review" in error for error in errors)
        )

    def test_same_book_reference_accepts_reviewed_split_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, _, profile_path = self.make_profile(
                root,
                reference_scope="same-book-content-and-style",
            )
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            proposal = root / "staging" / "reference-semantic-proposals.json"
            proposal.write_text('{"status":"review_required"}\n', encoding="utf-8")
            payload = {
                "schema_version": 1,
                "profile": str(profile_path.resolve()),
                "source_sha256": MODULE.sha256_file(source),
                "input_markdown_sha256": "c" * 64,
                "semantic_review": {
                    "headings": [],
                    "reference": {
                        "status": "passed",
                        "reviewer_confirmed": True,
                        "scope": "same-book-content-and-style",
                        "path": profile["reference"]["path"],
                        "sha256": profile["reference"]["sha256"],
                        "proposal_report": str(proposal.resolve()),
                        "proposal_report_sha256": MODULE.sha256_file(proposal),
                    },
                },
                "nodes": [],
            }

            errors = MODULE.artifact_errors(
                payload,
                "split-manifest",
                expected_profile=profile_path.resolve(),
                expected_source_sha256=MODULE.sha256_file(source),
            )

        self.assertEqual(errors, [])

    def test_toc_manifest_does_not_require_future_formatted_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, _, profile_path = self.make_profile(root)
            payload = {
                "schema_version": 1,
                "profile": str(profile_path.resolve()),
                "source_sha256": MODULE.sha256_file(source),
                "input_markdown_sha256": MODULE.sha256_file(source),
                "toc_source_ranges": [{"start_line": 1, "end_line": 1}],
                "entries": [
                    {
                        "key": "chapter-1",
                        "title": "第一章",
                        "level": 1,
                        "category": "knowledge",
                        "filename": "第一章.md",
                    }
                ],
            }
            errors = MODULE.artifact_errors(
                payload,
                "toc-manifest",
                expected_profile=profile_path.resolve(),
                expected_source_sha256=MODULE.sha256_file(source),
            )
        self.assertEqual(errors, [])

    def test_resume_invalidates_changed_output_and_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, profile = self.make_profile(root)
            state = MODULE.init_state(profile)
            raw = root / "staging" / "source.raw.md"
            raw.write_text("# Raw\n", encoding="utf-8")
            MODULE.begin_stage(
                state,
                "markdown-registration",
                [("book-profile", profile)],
            )
            MODULE.complete_stage(
                state,
                "markdown-registration",
                [("file", raw)],
            )
            self.assertEqual(state["stages"][1]["status"], "completed")

            raw.write_text("# Changed\n", encoding="utf-8")
            MODULE.validate_resume(state)

        self.assertEqual(state["stages"][1]["status"], "pending")
        self.assertEqual(state["stages"][2]["status"], "pending")
        self.assertEqual(
            state["resume_events"][-1]["invalidated_from"],
            "markdown-registration",
        )

    def test_resume_allows_downstream_changes_in_mutable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, book, profile = self.make_profile(root)
            state = MODULE.init_state(profile)
            stage = state["stages"][1]
            stage["status"] = "completed"
            stage["outputs"] = [MODULE.artifact_record("directory", book)]
            (book / "知识点" / "later.md").write_text(
                "# Later\n", encoding="utf-8"
            )
            MODULE.validate_resume(state)

        self.assertEqual(stage["status"], "completed")

    def test_resume_invalidates_changed_final_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, book, profile = self.make_profile(root)
            state = MODULE.init_state(profile)
            for stage in state["stages"]:
                stage["status"] = "completed"
            final_stage = state["stages"][-1]
            final_stage["outputs"] = [MODULE.artifact_record("tree", book)]
            (book / "知识点" / "changed.md").write_text(
                "# Changed\n", encoding="utf-8"
            )
            MODULE.validate_resume(state)

        self.assertEqual(final_stage["status"], "pending")
        self.assertEqual(
            state["resume_events"][-1]["invalidated_from"],
            "final-audit",
        )

    def test_concept_schema_rejects_missing_definition_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, _, profile = self.make_profile(root)
            payload = {
                "schema_version": 1,
                "profile": str(profile.resolve()),
                "source_sha256": MODULE.sha256_file(source),
                "concepts": [{"name": "集合", "target": "概念/集合.md"}],
            }
            errors = MODULE.artifact_errors(
                payload,
                "concept-manifest",
                expected_profile=profile.resolve(),
                expected_source_sha256=MODULE.sha256_file(source),
            )
        self.assertTrue(any("linked_from" in error for error in errors))

    def test_review_queue_routes_only_ambiguous_items_to_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, _, profile = self.make_profile(root)
            queue = MODULE.make_review_queue(
                {
                    "candidates": [
                        {
                            "id": "high",
                            "stage": "concepts",
                            "kind": "concept",
                            "confidence": 0.98,
                            "source": "知识点/集合.md",
                            "proposal": {"name": "集合"},
                        },
                        {
                            "id": "low",
                            "stage": "concepts",
                            "kind": "concept",
                            "confidence": 0.70,
                            "source": "知识点/函数.md",
                            "proposal": {"name": "函数"},
                        },
                        {
                            "id": "ambiguous",
                            "stage": "toc-splitting",
                            "kind": "split",
                            "confidence": 0.99,
                            "ambiguous": True,
                            "source": "知识点/角.md",
                            "proposal": {"decision": "retain"},
                        },
                    ]
                },
                profile_path=profile,
                source_sha256=MODULE.sha256_file(source),
                threshold=0.9,
            )
        routes = {item["id"]: item["route"] for item in queue["items"]}
        self.assertEqual(routes["high"], "auto_ready")
        self.assertEqual(routes["low"], "needs_review")
        self.assertEqual(routes["ambiguous"], "needs_review")
        self.assertEqual(len(MODULE.unresolved_review_items(queue)), 2)
        revised = MODULE.decide_review_item(
            queue,
            "ambiguous",
            "revised",
            "Split into a child note.",
        )
        self.assertEqual(revised["decision"], "revised")
        self.assertEqual(queue["counts"]["unresolved"], 1)

    def test_note_workplan_has_one_owner_and_merges_complete_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, book, profile = self.make_profile(root)
            notes = [
                book / "知识点" / "集合.md",
                book / "知识点" / "函数.md",
                book / "习题" / "习题1.md",
            ]
            for index, note in enumerate(notes, 1):
                note.write_text(f"# Note {index}\n" * index, encoding="utf-8")
            workplan = MODULE.make_note_workplan(
                profile,
                workers=2,
                roles={"knowledge", "exercise"},
                tasks=["concept-planning", "markdown-planning"],
            )
            workplan_path = root / "staging" / "note-workplan.json"
            MODULE.write_json_atomic(workplan_path, workplan)
            result_directory = root / "results"
            result_directory.mkdir()
            for job in workplan["jobs"]:
                result = {
                    "schema_version": 1,
                    "job_id": job["id"],
                    "source": job["path"],
                    "source_sha256": job["sha256"],
                    "status": "passed",
                    "outputs": [job["relative_path"] + ".plan.json"],
                    "candidates": [],
                }
                MODULE.write_json_atomic(
                    result_directory / f"{job['id']}.json", result
                )
            merged = MODULE.merge_note_results(
                workplan_path, result_directory
            )

        self.assertEqual(len(workplan["jobs"]), 3)
        self.assertEqual(
            len({job["path"] for job in workplan["jobs"]}), 3
        )
        self.assertEqual(merged["metrics"]["jobs"], 3)
        self.assertEqual(merged["metrics"]["failed"], 0)

    def test_apply_records_component_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, profile = self.make_profile(root)
            state_path = root / "staging" / "pipeline-state.json"
            MODULE.write_json_atomic(state_path, MODULE.init_state(profile))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                return_code = MODULE.main(
                    [
                        "apply",
                        str(state_path),
                        "markdown-registration",
                        "--input",
                        f"book-profile={profile}",
                        "--command",
                        sys.executable,
                        "-c",
                        "import sys; sys.exit(7)",
                    ]
                )
            result = json.loads(output.getvalue())
            state = MODULE.read_json(state_path)

        self.assertEqual(return_code, 1)
        self.assertEqual(result["returncode"], 7)
        self.assertEqual(state["stages"][1]["status"], "failed")
        self.assertEqual(len(state["telemetry"]["failures"]), 1)


if __name__ == "__main__":
    unittest.main()

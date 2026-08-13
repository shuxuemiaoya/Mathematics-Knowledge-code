from __future__ import annotations

import json
import re
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from question_type_graph.coordinator import artifact_paths, run_pipeline
from question_type_graph.answers import apply_matches
from question_type_graph.profile import create_profile
from question_type_graph.common import write_json_atomic
from question_type_graph.supplement import apply_supplement
from question_type_graph.runtime import status_state


def make_adapter(profile_path: Path, answers: bool = True, combined: bool = False) -> dict:
    value = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "profile": str(profile_path.resolve()),
        "hierarchy": {
            "source_role": "combined" if combined else "questions",
            "root_output": "index.md",
            "no_toc_authority": {
                "status": "passed",
                "reviewer_confirmed": True,
                "reason": "Synthetic fixture has no printed TOC",
            },
            "entries": [
                {"key": "u1", "title": "Unit One", "level": 1, "output": "Unit One/Unit One.md", "answer_context": "s1"},
                {"key": "s1", "title": "Section 1", "level": 2, "output": "Unit One/Section 1/Section 1.md", "answer_context": "s1"},
            ],
        },
        "content": {
            "unknown_label_policy": "retain",
            "question_folder": "Questions",
            "question_title_template": "Question {number}",
            "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
            "roles": [
                {"role": "training-band", "depth": 0, "pattern": r"Training"},
                {"role": "question-type", "depth": 1, "pattern": r"Type (?P<title>.+)"},
                {"role": "subtype", "depth": 2, "pattern": r"Angle (?P<title>.+)"},
                {"role": "mistake-point", "depth": 1, "pattern": r"Mistake (?P<title>.+)"},
            ],
        },
        "answers": {
            "source_role": "combined" if combined else "answers",
            "contexts": [{"key": "s1", "pattern": r"^## Section 1 Answers$"}],
            "answer_patterns": [r"^(?P<number>\d+)[.]\s+"],
            "ignore_ranges": [],
        },
    }
    if combined:
        value["hierarchy"]["region"] = {"start_line": 1, "end_line": 11}
        value["answers"]["region"] = {"start_line": 12, "end_line": 19}
    if not answers:
        value["answers"] = {}
    return value


def get_args(overwrite: bool = False) -> Namespace:
    return Namespace(
        skip_conversion=False,
        overwrite=overwrite,
        env_file="unused",
        base_url=None,
        mineru_language=None,
        poll_interval=0.01,
        max_polls=1,
        request_timeout=1.0,
    )


class TestPipeline(unittest.TestCase):
    def test_canvas_artifact_uses_generated_filename_policy(self) -> None:
        profile = {
            "title": "天津卷（解析版）",
            "paths": {
                "staging_root": "/tmp/staging",
                "graph_root": "/tmp/graph",
            },
            "format": {
                "inventory": "/tmp/staging/inventory.json",
                "adapter": "/tmp/staging/adapter.json",
            },
        }

        self.assertEqual(
            artifact_paths(profile)["canvas"].name,
            "天津卷_解析版_.canvas",
        )

    def test_note_properties_move_to_frontmatter_and_retained_section_stays_inline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            questions = root / "questions.md"
            questions.write_text(
                "# Unit One\n\nGuide Alice\n\nModules: Algebra, Geometry.\n\n"
                "## Introduction\n\nThis introduction belongs to the unit.\n\n"
                "## Training\n\n1. First question.\n",
                encoding="utf-8",
            )
            staging = root / "staging"
            vault = root / "vault"
            graph = vault / "graph"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={questions}"],
                "InlineIntroduction",
                staging,
                vault,
                graph,
                "en",
                None,
                False,
            )
            write_json_atomic(profile_path, profile)
            adapter = make_adapter(profile_path, answers=False)
            adapter["hierarchy"]["entries"] = [
                {"key": "u1", "title": "Unit One", "level": 1, "output": "Unit One/Unit One.md"}
            ]
            adapter["content"]["roles"] = [
                {"role": "training-band", "depth": 0, "pattern": r"Training"}
            ]
            adapter["content"]["note_properties"] = [
                {"name": "guide", "pattern": r"^Guide\s+(?P<value>.+)$", "required": True},
                {
                    "name": "modules",
                    "pattern": r"^Modules:\s*(?P<value>.+?)\.$",
                    "required": True,
                },
            ]
            write_json_atomic(staging / "format-adapter.json", adapter)

            args = get_args()
            args.env_file = None
            result = run_pipeline(profile_path, args)
            unit = next(graph.rglob("Unit_One.md"))
            text = unit.read_text(encoding="utf-8")

            self.assertEqual(result["status"], "passed")
            self.assertTrue(text.startswith('---\nguide: "Alice"\nmodules: "Algebra, Geometry"\n---\n'))
            self.assertNotIn("Guide Alice", text)
            self.assertNotIn("Modules:", text)
            self.assertIn("## Introduction\n\nThis introduction belongs to the unit.", text)
            self.assertFalse(any(path.name == "Introduction.md" for path in graph.rglob("*.md")))

    def test_first_run_creates_unapproved_adapter_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            questions = root / "questions.md"
            questions.write_text("# Unit\n\n1. Question.\n", encoding="utf-8")
            staging = root / "staging"
            vault = root / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={questions}"], "Draft", staging, vault, vault / "graph", "en", None, False
            )
            write_json_atomic(profile_path, profile)

            result = run_pipeline(profile_path, get_args())
            draft = json.loads(Path(result["adapter_draft"]).read_text(encoding="utf-8"))
            state = json.loads((staging / "pipeline-state.json").read_text(encoding="utf-8"))

            self.assertEqual(result["next_stage"], "format-adapter-review")
            self.assertEqual(draft["status"], "review_required")
            self.assertFalse(draft["reviewer_confirmed"])
            self.assertTrue(Path(result["review_worksheet"]).is_file())
            self.assertEqual(state["runs"][0]["run_id"], "run-000001")
            self.assertEqual(state["runs"][0]["status"], "review_required")
            self.assertTrue(Path(state["runs"][0]["manifest"]).is_file())
            self.assertTrue(state["stages"]["preflight"]["attempt_history"])
            self.assertTrue(
                Path(state["stages"]["preflight"]["attempt_history"][0]["manifest"]).is_file()
            )

    def test_missing_authoritative_answer_routes_through_reviewed_supplement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            questions = root / "questions.md"
            answers = root / "answers.md"
            questions.write_text(
                "# Unit One\n\n## Section 1\n\n#### Type Direct\n\n"
                "1. First question.\n\n2. Second question.\n",
                encoding="utf-8",
            )
            answers.write_text(
                "# Solutions\n\n## Section 1 Answers\n\n1. A\nFirst analysis.\n",
                encoding="utf-8",
            )
            staging = root / "staging"
            vault = root / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={questions}", f"answers={answers}"],
                "SupplementFlow",
                staging,
                vault,
                vault / "graph",
                "en",
                None,
                False,
            )
            write_json_atomic(profile_path, profile)
            adapter = make_adapter(profile_path)
            adapter["content"]["roles"] = [
                {"role": "question-type", "depth": 0, "pattern": r"Type (?P<title>.+)"}
            ]
            write_json_atomic(staging / "format-adapter.json", adapter)

            answer_review = run_pipeline(profile_path, get_args())
            self.assertEqual(answer_review["next_stage"], "answer-review")
            answer_manifest_path = staging / "answer-match-manifest.json"
            answer_manifest = json.loads(answer_manifest_path.read_text(encoding="utf-8"))
            answer_manifest["status"] = "passed"
            answer_manifest["reviewer_confirmed"] = True
            write_json_atomic(answer_manifest_path, answer_manifest, overwrite=True)

            supplement_review = run_pipeline(profile_path, get_args())
            self.assertEqual(supplement_review["next_stage"], "solution-supplement-review")
            supplement_path = Path(supplement_review["manifest"])
            supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
            self.assertEqual(supplement["unmatched_count"], 1)
            supplement["questions"][0]["solution"] = (
                "Substitute the given values and simplify; the required result follows directly."
            )
            supplement["questions"][0]["reviewer_confirmed"] = True
            write_json_atomic(supplement_path, supplement, overwrite=True)

            applied = apply_supplement(profile_path, supplement_path)
            completed = run_pipeline(profile_path, get_args())

            self.assertEqual(applied["status"], "completed")
            self.assertEqual(completed["status"], "passed")
            self.assertEqual(status_state(staging / "pipeline-state.json")["status"], "completed")

    def test_result_only_authoritative_answer_keeps_source_note_and_adds_reviewed_explanation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            questions = root / "questions.md"
            answers = root / "answers.md"
            questions.write_text(
                "# Unit One\n\n## Section 1\n\n#### Type Direct\n\n"
                "1. Which ordering is correct?\nA. First ordering\nB. Second ordering\n",
                encoding="utf-8",
            )
            answers.write_text(
                "# Solutions\n\n## Section 1 Answers\n\n1. A\n",
                encoding="utf-8",
            )
            staging = root / "staging"
            vault = root / "vault"
            graph = vault / "graph"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={questions}", f"answers={answers}"],
                "ResultOnly",
                staging,
                vault,
                graph,
                "en",
                None,
                False,
            )
            write_json_atomic(profile_path, profile)
            adapter = make_adapter(profile_path)
            adapter["content"]["roles"] = [
                {"role": "question-type", "depth": 0, "pattern": r"Type (?P<title>.+)"}
            ]
            write_json_atomic(staging / "format-adapter.json", adapter)

            supplement_review = run_pipeline(profile_path, get_args())
            self.assertEqual(supplement_review["next_stage"], "solution-supplement-review")
            supplement_path = Path(supplement_review["manifest"])
            supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
            self.assertEqual(supplement["supplement_required_count"], 1)
            self.assertEqual(
                supplement["questions"][0]["supplement_reason"],
                "authoritative-solution-incomplete",
            )
            supplement["questions"][0]["solution"] = (
                "1. A 【解析】Compare the two stated orderings directly; only option A "
                "satisfies every required relation."
            )
            supplement["questions"][0]["reviewer_confirmed"] = True
            write_json_atomic(supplement_path, supplement, overwrite=True)

            applied = apply_supplement(profile_path, supplement_path)
            completed = run_pipeline(profile_path, get_args())
            question = next(graph.rglob("Q[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].md"))
            question_text = question.read_text(encoding="utf-8")
            answer_dir = question.parent / "answers"

            self.assertEqual(applied["status"], "completed")
            self.assertEqual(completed["status"], "passed")
            self.assertTrue((answer_dir / f"{question.stem}A1.md").is_file())
            self.assertTrue((answer_dir / f"{question.stem}A2.md").is_file())
            self.assertIn(f"![[{question.stem}A1]]", question_text)
            self.assertIn(f"![[{question.stem}A2]]", question_text)
            self.assertIn("answer_provenance: authoritative", (answer_dir / f"{question.stem}A1.md").read_text(encoding="utf-8"))
            self.assertIn("answer_provenance: ai-generated-reviewed", (answer_dir / f"{question.stem}A2.md").read_text(encoding="utf-8"))

    def test_full_separate_question_and_answer_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            questions = tmp_path / "questions.md"
            answers = tmp_path / "answers.md"
            questions.write_text(
                "# Unit One\n\n## Section 1\n\n#### Training\n\n#### Type Algebra\n\n1. First question?\n   (1) Keep this subpart.\n\n#### Angle Variant\n\n2. Second question?\n\n#### Mistake Common\n\n3. Third question?\n",
                encoding="utf-8",
            )
            answers.write_text(
                "# Solutions\n\n## Section 1 Answers\n\n1. A\nExact analysis one.\n\n2. B\nExact analysis two.\n\n3. C\nExact analysis three.\n",
                encoding="utf-8",
            )
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            graph = vault / "graph"
            profile_path = staging / "question-type-profile.json"
            profile = create_profile(
                [f"questions={questions}", f"answers={answers}"],
                "Synthetic",
                staging,
                vault,
                graph,
                "en",
                None,
                True,
            )
            write_json_atomic(profile_path, profile)
            staging.mkdir(parents=True, exist_ok=True)
            write_json_atomic(staging / "format-adapter.json", make_adapter(profile_path))

            result = run_pipeline(profile_path, get_args())

            self.assertEqual(result["status"], "passed")
            manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["questions"]), 3)
            self.assertEqual(manifest["questions"][0]["source_markdown_line"], 9)
            self.assertTrue({node["role"] for node in manifest["functional_nodes"]} >= {
                "training-band",
                "question-type",
                "subtype",
                "mistake-point",
            })
            first = Path(manifest["questions"][0]["output"]).read_text(encoding="utf-8")
            self.assertIn("First question?", first)
            q_title = manifest["questions"][0]["title"]
            self.assertIn(f"![[{q_title}A1]]", first)
            ans_note = list(vault.rglob(f"*{q_title}A1*"))[0].read_text(encoding="utf-8")
            self.assertIn("Exact analysis one.", ans_note)
            question_preamble = first.split("<!-- question-source:start -->", 1)[0]
            self.assertIsNone(re.search(r"(?m)^#{1,6}\s+", question_preamble))
            nodes = {node["key"]: node for node in manifest["functional_nodes"]}
            owner = nodes[manifest["questions"][0]["owner"]]
            owner_text = Path(owner["output"]).read_text(encoding="utf-8")
            question_target = Path(manifest["questions"][0]["output"]).resolve().relative_to(vault.resolve()).as_posix()
            self.assertIn(f"![[{question_target}]]", owner_text)
            self.assertNotIn(f"- ![[{question_target}]]", owner_text)
            canvas = json.loads((graph / "Synthetic.canvas").read_text(encoding="utf-8"))
            self.assertTrue(all("Question 1" not in str(node) for node in canvas["nodes"]))

            first_question_code = manifest["questions"][0]["title"]
            state_before_resume = json.loads((staging / "pipeline-state.json").read_text(encoding="utf-8"))
            resumed = run_pipeline(profile_path, get_args())
            resumed_manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
            state_after_resume = json.loads((staging / "pipeline-state.json").read_text(encoding="utf-8"))
            self.assertEqual(resumed["status"], "passed")
            self.assertEqual(resumed_manifest["questions"][0]["title"], first_question_code)
            for stage in ("pdf-conversion", "hierarchy-segmentation", "content-segmentation", "answer-matching", "canvas"):
                self.assertEqual(
                    state_after_resume["stages"][stage]["attempts"],
                    state_before_resume["stages"][stage]["attempts"],
                )

            (staging / "content-application-report.json").unlink()
            rebuilt = run_pipeline(profile_path, get_args())
            rebuilt_manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(rebuilt["status"], "passed")
            self.assertEqual(rebuilt_manifest["questions"][0]["title"], first_question_code)

            answer_manifest_path = staging / "answer-match-manifest.json"
            answer_manifest = json.loads(answer_manifest_path.read_text(encoding="utf-8"))
            removed_match = answer_manifest["matches"].pop()
            write_json_atomic(answer_manifest_path, answer_manifest, overwrite=True)
            stale_answer = Path(removed_match["question_path"]).parent / "answers" / f"{Path(removed_match['question_path']).stem}A1.md"
            self.assertTrue(stale_answer.is_file())

            apply_matches(profile_path, answer_manifest_path, overwrite=True)

            self.assertFalse(stale_answer.exists())
            removed_question_text = Path(removed_match["question_path"]).read_text(encoding="utf-8")
            self.assertNotIn(f"![[{Path(removed_match['question_path']).stem}A1]]", removed_question_text)
            self.assertIn("answer_status: unmatched", removed_question_text)

    def test_answerless_question_only_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            questions = tmp_path / "questions.md"
            questions.write_text("# Unit One\n\n## Section 1\n\n#### Type Direct\n\n1. Question only.\n", encoding="utf-8")
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "question-type-profile.json"
            profile = create_profile([f"questions={questions}"], "Answerless", staging, vault, vault / "graph", "en", None, False)
            write_json_atomic(profile_path, profile)
            staging.mkdir(parents=True, exist_ok=True)
            adapter = make_adapter(profile_path, answers=False)
            adapter["content"]["roles"] = [{"role": "question-type", "depth": 0, "pattern": r"Type (?P<title>.+)"}]
            write_json_atomic(staging / "format-adapter.json", adapter)

            result = run_pipeline(profile_path, get_args())

            self.assertEqual(result["status"], "passed")
            answer_manifest = json.loads((staging / "answer-match-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(answer_manifest["mode"], "unavailable")
            content_manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
            question_note = Path(content_manifest["questions"][0]["output"]).read_text(encoding="utf-8")
            self.assertIn("answer_status: unavailable", question_note)

    def test_combined_source_uses_non_overlapping_regions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            combined = tmp_path / "combined.md"
            combined.write_text(
                "# Unit One\n\n## Section 1\n\n#### Type Direct\n\n1. Question one.\n\n2. Question two.\n\n<!-- question region end -->\n## Section 1 Answers\n\n1. A\nAnalysis one.\n\n2. B\nAnalysis two.\n",
                encoding="utf-8",
            )
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "question-type-profile.json"
            profile = create_profile([f"combined={combined}"], "Combined", staging, vault, vault / "graph", "en", None, False)
            write_json_atomic(profile_path, profile)
            staging.mkdir(parents=True, exist_ok=True)
            adapter = make_adapter(profile_path, combined=True)
            adapter["hierarchy"]["region"]["end_line"] = 11
            adapter["answers"]["region"] = {
                "start_line": 12,
                "end_line": len(combined.read_text(encoding="utf-8").splitlines()),
            }
            adapter["content"]["roles"] = [{"role": "question-type", "depth": 0, "pattern": r"Type (?P<title>.+)"}]
            write_json_atomic(staging / "format-adapter.json", adapter)

            result = run_pipeline(profile_path, get_args())

            self.assertEqual(result["status"], "passed")
            manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["questions"]), 2)


if __name__ == "__main__":
    unittest.main()

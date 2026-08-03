from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from question_type_graph.coordinator import run_pipeline
from question_type_graph.profile import create_profile
from question_type_graph.common import write_json_atomic


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


def args(overwrite: bool = False) -> Namespace:
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


def test_full_separate_question_and_answer_pipeline(tmp_path: Path) -> None:
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

    result = run_pipeline(profile_path, args())

    assert result["status"] == "passed", result
    manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["questions"]) == 3
    assert {node["role"] for node in manifest["functional_nodes"]} >= {
        "training-band",
        "question-type",
        "subtype",
        "mistake-point",
    }
    first = Path(manifest["questions"][0]["output"]).read_text(encoding="utf-8")
    assert "First question?" in first
    assert "Keep this subpart." in first
    assert "Exact analysis one." in first
    canvas = json.loads((graph / "Synthetic.canvas").read_text(encoding="utf-8"))
    assert all("Question 1" not in str(node) for node in canvas["nodes"])


def test_answerless_question_only_pipeline(tmp_path: Path) -> None:
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

    result = run_pipeline(profile_path, args())

    assert result["status"] == "passed", result
    answer_manifest = json.loads((staging / "answer-match-manifest.json").read_text(encoding="utf-8"))
    assert answer_manifest["mode"] == "unavailable"
    content_manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
    question_note = Path(content_manifest["questions"][0]["output"]).read_text(encoding="utf-8")
    assert "answer_status: unavailable" in question_note


def test_combined_source_uses_non_overlapping_regions(tmp_path: Path) -> None:
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
    adapter["answers"]["region"] = {"start_line": 12, "end_line": 19}
    adapter["content"]["roles"] = [{"role": "question-type", "depth": 0, "pattern": r"Type (?P<title>.+)"}]
    write_json_atomic(staging / "format-adapter.json", adapter)

    result = run_pipeline(profile_path, args())

    assert result["status"] == "passed", result
    manifest = json.loads((staging / "question-type-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["questions"]) == 2

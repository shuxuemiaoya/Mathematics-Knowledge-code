from __future__ import annotations

from pathlib import Path

import pytest

from question_type_graph.answers import strategy_candidates
from question_type_graph.common import write_json_atomic
from question_type_graph.content import compile_question_patterns, compile_role_rules, plan_content, plan_note
from question_type_graph.hierarchy import apply_hierarchy, plan_hierarchy
from question_type_graph.inventory import build_inventory, inventory_markdown, parse_index_entry
from question_type_graph.profile import create_profile


def test_inventory_proposes_multiple_indexes_wrapped_entries_and_layout_review(tmp_path: Path) -> None:
    source = tmp_path / "inventory.md"
    source.write_text(
        "Long wrapped title\ncontinued ........ 3\nSecond ........ 8\n\n\n\n"
        "Alternate index    12\nAnother entry    14\n\n"
        "left column    right column\n![](images/page.png)\n",
        encoding="utf-8",
    )

    inventory = inventory_markdown(source)

    assert len(inventory["index_candidates"]) == 2
    assert inventory["index_candidates"][0]["status"] == "review_required"
    assert inventory["layout_signals"] == {
        "image_count": 1,
        "table_line_count": 0,
        "wide_spacing_line_count": 3,
    }


def test_index_entry_preserves_descriptor_and_multiple_parenthesized_references() -> None:
    parsed = parse_index_entry("2.4 Generic topic …… Core Advanced (17) (203)")

    assert parsed == {
        "title": "2.4 Generic topic",
        "descriptor": "Core Advanced",
        "references": [17, 203],
        "literal": "2.4 Generic topic …… Core Advanced (17) (203)",
    }


def test_markdown_only_inventory_works_before_run_and_names_arrangement(tmp_path: Path) -> None:
    source = tmp_path / "questions.md"
    source.write_text("#### Pattern A\n\n#### Pattern B\n", encoding="utf-8")
    staging = tmp_path / "staging"
    vault = tmp_path / "vault"
    profile_path = staging / "profile.json"
    profile = create_profile([f"questions={source}"], "Inventory", staging, vault, vault / "graph", "en", None, False)
    staging.mkdir(parents=True, exist_ok=True)
    write_json_atomic(profile_path, profile)

    inventory = build_inventory(profile_path)

    assert inventory["source_arrangement"] == "question-only"
    assert inventory["sources"][0]["status"] == "review_required"
    assert inventory["sources"][0]["heading_count"] == 2
    assert inventory["sources"][0]["repeated_label_candidates"][0]["literal"] == "Pattern"


@pytest.mark.parametrize(
    "output",
    [
        "Chapter/Section/Section.md",
        "Section.md",
        "roles/section/Section.md",
    ],
)
def test_reviewed_folder_templates_remain_adapter_controlled(tmp_path: Path, output: str) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Section\n\n1. Question.\n", encoding="utf-8")
    staging = tmp_path / "staging"
    vault = tmp_path / "vault"
    profile_path = staging / "profile.json"
    profile = create_profile([f"questions={source}"], "Layouts", staging, vault, vault / "graph", "en", None, False)
    staging.mkdir(parents=True, exist_ok=True)
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
                "reason": "Synthetic layout fixture has no TOC",
            },
            "entries": [{"key": "section", "title": "Section", "level": 1, "start_line": 1, "output": output}],
        },
        "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": []},
    }
    adapter_path = staging / "adapter.json"
    write_json_atomic(adapter_path, adapter)

    manifest = plan_hierarchy(profile_path, adapter_path)

    assert manifest["entries"][0]["output"] == output


def test_primary_authority_ledger_blocks_missing_toc_entries(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("Index\nUnit One\n1.1 Topic …… Core (1) (20)\n\n# Unit One\n\n## Core\n1. Q\n", encoding="utf-8")
    staging = tmp_path / "staging"
    vault = tmp_path / "vault"
    profile_path = staging / "profile.json"
    profile = create_profile([f"questions={source}"], "Ledger", staging, vault, vault / "graph", "en", None, False)
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
            "primary_authority": {
                "status": "passed",
                "reviewer_confirmed": True,
                "start_line": 2,
                "end_line": 3,
                "entries": [
                    {"key": "unit", "title": "Unit One", "level": 1, "source_line": 2},
                    {"key": "topic", "title": "1.1 Topic", "level": 2, "source_line": 3},
                ],
            },
            "entries": [{"key": "unit", "title": "Unit One", "level": 1, "start_line": 5, "output": "unit.md"}],
        },
        "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": []},
    }
    adapter_path = staging / "adapter.json"
    write_json_atomic(adapter_path, adapter)

    manifest = plan_hierarchy(profile_path, adapter_path)

    assert manifest["status"] == "review_required"
    assert manifest["review_items"] == [
        {"kind": "missing-primary-authority-entry", "key": "topic", "title": "1.1 Topic"}
    ]


def test_hierarchy_cannot_bypass_authority_review(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Unit\n1. Q\n", encoding="utf-8")
    staging = tmp_path / "staging"
    profile_path = staging / "profile.json"
    profile = create_profile([f"questions={source}"], "Authority", staging, tmp_path, tmp_path / "graph", "en", None, False)
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
            "entries": [{"key": "u", "title": "Unit", "start_line": 1, "level": 1, "output": "u.md"}],
        },
    }
    adapter_path = staging / "adapter.json"
    write_json_atomic(adapter_path, adapter)

    manifest = plan_hierarchy(profile_path, adapter_path)
    assert manifest["status"] == "review_required"
    assert manifest["review_items"][0]["kind"] == "missing-hierarchy-authority"


def test_structural_toc_node_can_share_reviewed_boundary_with_content_child(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("Index\nUnit One\n1.1 Topic …… Core (1) (20)\n\n# Unit One\n\n## Core\n1. Q\n", encoding="utf-8")
    staging = tmp_path / "staging"
    vault = tmp_path / "vault"
    profile_path = staging / "profile.json"
    profile = create_profile([f"questions={source}"], "Structural", staging, vault, vault / "graph", "en", None, False)
    write_json_atomic(profile_path, profile)
    raw = Path(profile["sources"][0]["markdown_path"])
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (raw.parent / "images").mkdir()
    (raw.parent / "images" / "asset.png").write_bytes(b"asset")
    adapter = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "profile": str(profile_path.resolve()),
        "hierarchy": {
            "source_role": "questions",
            "root_output": "index.md",
            "primary_authority": {
                "status": "passed",
                "reviewer_confirmed": True,
                "start_line": 2,
                "end_line": 3,
                "entries": [
                    {"key": "unit", "title": "Unit One", "level": 1, "source_line": 2},
                    {"key": "topic", "title": "1.1 Topic", "level": 2, "source_line": 3},
                ],
            },
            "entries": [
                {"key": "unit", "start_line": 5, "output": "unit/unit.md"},
                {
                    "key": "topic",
                    "structural_only": True,
                    "emit_title": True,
                    "body_anchor": {
                        "kind": "reviewed-boundary",
                        "start_line": 7,
                        "evidence": "first reviewed content band",
                        "reviewer_confirmed": True,
                    },
                    "output": "unit/topic/topic.md",
                },
                {
                    "key": "band",
                    "title": "Core",
                    "level": 3,
                    "start_line": 7,
                    "output": "unit/topic/core.md",
                    "supplemental": True,
                },
            ],
        },
        "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": []},
    }
    adapter_path = staging / "adapter.json"
    manifest_path = staging / "hierarchy.json"
    write_json_atomic(adapter_path, adapter)
    manifest = plan_hierarchy(profile_path, adapter_path)
    write_json_atomic(manifest_path, manifest)

    assert manifest["status"] == "passed"
    assert manifest["entries"][1]["parent"] == "unit"
    assert manifest["entries"][2]["parent"] == "topic"
    apply_hierarchy(profile_path, adapter_path, manifest_path, overwrite=True)
    unit_text = (vault / "graph" / "unit" / "unit.md").read_text(encoding="utf-8")
    topic_text = (vault / "graph" / "unit" / "topic" / "topic.md").read_text(encoding="utf-8")
    assert "![[graph/unit/topic/topic.md]]" in unit_text
    assert "- ![[" not in unit_text
    assert topic_text.startswith("## 1.1 Topic\n\n![[graph/unit/topic/core.md]]")
    assert "- ![[" not in topic_text
    content_manifest = plan_content(profile_path, adapter_path, staging / "hierarchy-coverage-manifest.json")
    assert content_manifest["status"] == "passed"
    assert len(content_manifest["questions"]) == 1
    assert all(item["source_note"] != str(vault / "graph" / "unit" / "topic" / "topic.md") for item in content_manifest["questions"])


def test_alternate_labels_are_adapter_roles_and_unknown_labels_block(tmp_path: Path) -> None:
    note = tmp_path / "section.md"
    note.write_text("#### Pattern Algebra\n\n1. Q\n\n#### Mystery Label\n", encoding="utf-8")
    adapter = {
        "_graph_root": str(tmp_path),
        "content": {
            "unknown_label_policy": "review",
            "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
            "roles": [{"role": "question-type", "depth": 0, "pattern": r"Pattern (?P<title>.+)"}],
        },
    }

    labels, questions, review = plan_note(
        {"key": "section", "path": str(note), "answer_context": "section"},
        compile_role_rules(adapter),
        compile_question_patterns(adapter),
        adapter,
    )

    assert labels[0]["role"] == "question-type"
    assert len(questions) == 1
    assert review == [{"kind": "unknown-label", "source_note": str(note), "line": 5, "text": "Mystery Label"}]


def test_existing_child_embed_is_a_content_range_barrier(tmp_path: Path) -> None:
    note = tmp_path / "parent.md"
    note.write_text(
        "## Parent\n\n#### Type Intro\nContext retained here.\n![[graph/child.md]]\n",
        encoding="utf-8",
    )
    adapter = {
        "_graph_root": str(tmp_path),
        "content": {
            "unknown_label_policy": "retain",
            "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
            "roles": [{"role": "question-type", "depth": 0, "pattern": r"Type (?P<title>.+)"}],
        },
    }

    labels, questions, review = plan_note(
        {"key": "parent", "title": "Parent", "path": str(note), "answer_context": "parent"},
        compile_role_rules(adapter),
        compile_question_patterns(adapter),
        adapter,
    )

    assert labels[0]["end_line"] == 4
    assert questions == []
    assert review == []


def test_question_line_cannot_also_become_a_functional_node(tmp_path: Path) -> None:
    note = tmp_path / "section.md"
    note.write_text("#### Type Algebra\n1. Question body.\n", encoding="utf-8")
    adapter = {
        "_graph_root": str(tmp_path),
        "content": {
            "unknown_label_policy": "retain",
            "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
            "roles": [
                {"role": "question-type", "depth": 1, "pattern": r"Type (?P<title>.+)"},
                {"role": "neutral-context", "depth": 0, "pattern": r"(?P<title>.+)"},
            ],
        },
    }

    labels, questions, review = plan_note(
        {"key": "section", "title": "Section", "path": str(note), "answer_context": "section"},
        compile_role_rules(adapter),
        compile_question_patterns(adapter),
        adapter,
    )

    assert [label["role"] for label in labels] == ["question-type"]
    assert [question["number"] for question in questions] == ["1"]
    assert review == []


def test_reviewed_answer_strategies_never_use_fuzzy_similarity_as_acceptance() -> None:
    question = {
        "number": "1",
        "context_key": "unit-a",
        "evidence": {"reference": "R-17", "source_page": "42", "stem": "Exact stem"},
    }
    answers = [
        {"id": "a", "number": "9", "context": "elsewhere", "evidence": {"reference": "R-17", "source_page": "42", "stem": "Exact stem"}},
        {"id": "b", "number": "1", "context": "unit-a", "evidence": {"reference": "R-18", "source_page": "43", "stem": "Similar but not exact"}},
    ]

    assert [item["id"] for item in strategy_candidates("explicit-reference", question, "Exact stem", answers)[1]] == ["a"]
    assert [item["id"] for item in strategy_candidates("hierarchy-number", question, "Exact stem", answers)[1]] == ["b"]
    assert strategy_candidates("source-page-number", question, "Exact stem", answers)[1] == []
    assert [item["id"] for item in strategy_candidates("normalized-stem-exact", question, "Exact stem", answers)[1]] == ["a"]


def test_nested_and_restarted_numbering_is_scoped_by_reviewed_context() -> None:
    patterns = compile_question_patterns(
        {
            "content": {
                "question_patterns": [
                    r"^(?P<number>\d+(?:[.]\d+)*)[)]\s+",
                    r"^(?P<number>[①②③④⑤])\s+",
                ]
            }
        }
    )
    assert patterns[0].match("2.1) Nested").group("number") == "2.1"
    assert patterns[1].match("① Restarted in another section").group("number") == "①"


def test_repeated_functional_blocks_own_answer_context_and_zero_is_rejected(tmp_path: Path) -> None:
    note = tmp_path / "section.md"
    note.write_text("<!-- source-part:2 pages:201-400 -->\n#### Training\n1. First\n0.618 is prose\n#### Training\n1. Second\n", encoding="utf-8")
    adapter = {
        "_graph_root": str(tmp_path),
        "content": {
            "unknown_label_policy": "retain",
            "question_patterns": [r"^(?P<number>\d+)[.]\s*"],
            "roles": [{"role": "training-band", "depth": 0, "pattern": r"Training", "answer_context": True}],
        },
    }
    labels, questions, review = plan_note(
        {"key": "section", "path": str(note), "answer_context": "section"},
        compile_role_rules(adapter),
        compile_question_patterns(adapter),
        adapter,
    )

    assert [item["answer_context"] for item in labels] == [
        "section:training-band:1",
        "section:training-band:2",
    ]
    assert [item["context_key"] for item in questions] == [
        "section:training-band:1",
        "section:training-band:2",
    ]
    assert [item["kind"] for item in review] == ["invalid-question-number"]
    assert all(item["source_part"] == {"line": 1, "part": 2, "start_page": 201, "end_page": 400} for item in questions)

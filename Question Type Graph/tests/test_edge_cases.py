from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from question_type_graph.answers import parse_answer_blocks, strategy_candidates
from question_type_graph.common import ConfigurationError, write_json_atomic
from question_type_graph.content import (
    compile_question_patterns,
    compile_role_rules,
    plan_content,
    plan_note,
    split_inline_question_headers,
)
from question_type_graph.hierarchy import apply_hierarchy, plan_hierarchy
from question_type_graph.inventory import build_adapter_draft, build_inventory, inventory_markdown, parse_index_entry
from question_type_graph.profile import create_profile
from question_type_graph.supplement import apply_supplement


class TestEdgeCases(unittest.TestCase):
    def test_adapter_draft_applies_frozen_preset_without_approving_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "questions.md"
            source.write_text("# Unit\n1. Question.\n", encoding="utf-8")
            preset = root / "preset.json"
            write_json_atomic(
                preset,
                {
                    "status": "passed",
                    "reviewer_confirmed": True,
                    "content": {"question_folder": "Preset Questions"},
                },
            )
            staging = root / "staging"
            vault = root / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={source}"],
                "Preset",
                staging,
                vault,
                vault / "graph",
                "en",
                None,
                False,
                preset,
            )
            write_json_atomic(profile_path, profile)

            draft = build_adapter_draft(profile_path)

            self.assertEqual(draft["content"]["question_folder"], "Preset Questions")
            self.assertEqual(draft["status"], "review_required")
            self.assertFalse(draft["reviewer_confirmed"])

    def test_supplement_rejects_placeholders_and_requires_reviewed_solution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "questions.md"
            source.write_text("1. Question.\n", encoding="utf-8")
            staging = root / "staging"
            vault = root / "vault"
            graph = vault / "graph"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={source}"], "Supplement", staging, vault, graph, "en", None, False
            )
            write_json_atomic(profile_path, profile)
            question = graph / "questions" / "Q00000001.md"
            question.parent.mkdir(parents=True, exist_ok=True)
            question.write_text(
                "---\nquestion_id: q1\nquestion_number: 1\nanswer_status: unmatched\n---\n"
                "<!-- question-source:start -->\n1. Question.\n<!-- question-source:end -->\n",
                encoding="utf-8",
            )
            manifest_path = staging / "supplement.json"
            manifest = {
                "schema_version": 1,
                "questions": [
                    {
                        "question_id": "q1",
                        "question_stem": "Q00000001",
                        "file_path": str(question),
                        "solution": "待模型生成完整解析",
                        "reviewer_confirmed": True,
                    }
                ],
            }
            write_json_atomic(manifest_path, manifest)

            blocked = apply_supplement(profile_path, manifest_path)
            self.assertEqual(blocked["status"], "review_required")
            self.assertFalse((question.parent / "answers" / "Q00000001A1.md").exists())

            manifest["questions"][0]["solution"] = "Because both sides are equal, the required value is 1."
            write_json_atomic(manifest_path, manifest, overwrite=True)
            completed = apply_supplement(profile_path, manifest_path)
            answer_text = (question.parent / "answers" / "Q00000001A1.md").read_text(encoding="utf-8")
            self.assertEqual(completed["status"], "completed")
            self.assertIn("answer_provenance: ai-generated-reviewed", answer_text)

    def test_inline_answer_splitting_preserves_raw_context_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "answers.md"
            path.write_text("## A\n1. First 【2】Second\n## B\n1. Third\n", encoding="utf-8")
            adapter = {
                "answers": {
                    "contexts": [
                        {"key": "A", "pattern": r"^## A$"},
                        {"key": "B", "start_line": 3},
                    ],
                    "answer_patterns": [r"^【?(?P<number>\d+)】?[.、]?\s*"],
                    "inline_answer_patterns": [r"【(?P<number>\d+)】"],
                    "matching_strategies": ["hierarchy-number"],
                }
            }

            answers, review = parse_answer_blocks(path, adapter)

            self.assertEqual(review, [])
            self.assertEqual(
                [(item["number"], item["context"], item["line"], item["subline"]) for item in answers],
                [("1", "A", 2, 0), ("2", "A", 2, 1), ("1", "B", 4, 0)],
            )

    def test_reviewed_implicit_answer_recovers_dropped_ocr_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "answers.md"
            path.write_text(
                "# Unit\n解析: first publisher solution\n【2】B\n解析: second\n",
                encoding="utf-8",
            )
            adapter = {
                "answers": {
                    "contexts": [
                        {"key": "unit", "start_line": 1, "anchor_text": "# Unit"}
                    ],
                    "implicit_answers": [
                        {
                            "context": "unit",
                            "number": "1",
                            "start_line": 2,
                            "anchor_text": "解析: first publisher solution",
                        }
                    ],
                    "answer_patterns": [r"【(?P<number>\d+)】"],
                }
            }

            answers, review = parse_answer_blocks(path, adapter)

            self.assertEqual(review, [])
            self.assertEqual([item["number"] for item in answers], ["1", "2"])
            self.assertEqual(
                answers[0]["evidence"], {"implicit_header": "reviewed-ocr-omission"}
            )

    def test_inventory_proposes_multiple_indexes_wrapped_entries_and_layout_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "inventory.md"
            source.write_text(
                "Long wrapped title\ncontinued ........ 3\nSecond ........ 8\n\n\n\n"
                "Alternate index    12\nAnother entry    14\n\n"
                "left column    right column\n![](images/page.png)\n",
                encoding="utf-8",
            )

            inventory = inventory_markdown(source)

            self.assertEqual(len(inventory["index_candidates"]), 2)
            self.assertEqual(inventory["index_candidates"][0]["status"], "review_required")
            self.assertEqual(inventory["layout_signals"], {
                "image_count": 1,
                "table_line_count": 0,
                "wide_spacing_line_count": 3,
            })

    def test_index_entry_preserves_descriptor_and_multiple_parenthesized_references(self) -> None:
        parsed = parse_index_entry("2.4 Generic topic …… Core Advanced (17) (203)")

        self.assertEqual(parsed, {
            "title": "2.4 Generic topic",
            "descriptor": "Core Advanced",
            "references": [17, 203],
            "literal": "2.4 Generic topic …… Core Advanced (17) (203)",
        })

    def test_markdown_only_inventory_works_before_run_and_names_arrangement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "questions.md"
            source.write_text("#### Pattern A\n\n#### Pattern B\n", encoding="utf-8")
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile([f"questions={source}"], "Inventory", staging, vault, vault / "graph", "en", None, False)
            staging.mkdir(parents=True, exist_ok=True)
            write_json_atomic(profile_path, profile)

            inventory = build_inventory(profile_path)

            self.assertEqual(inventory["source_arrangement"], "question-only")
            self.assertEqual(inventory["sources"][0]["status"], "review_required")
            self.assertEqual(inventory["sources"][0]["heading_count"], 2)
            self.assertEqual(inventory["sources"][0]["repeated_label_candidates"][0]["literal"], "Pattern")
            draft = build_adapter_draft(profile_path, inventory)
            self.assertEqual(draft["status"], "review_required")
            self.assertFalse(draft["reviewer_confirmed"])
            self.assertEqual(draft["hierarchy"]["entries"], [])

    def test_reviewed_folder_templates_remain_adapter_controlled(self) -> None:
        outputs = [
            "Chapter/Section/Section.md",
            "Section.md",
            "roles/section/Section.md",
        ]
        for output in outputs:
            with self.subTest(output=output):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
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

                    self.assertEqual(manifest["entries"][0]["output"], output)

    def test_primary_authority_ledger_blocks_missing_toc_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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
                    "entries": [{"key": "unit", "title": "Unit One", "level": 1, "start_line": 5, "output": "unit.md"}],
                },
                "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": []},
            }
            adapter_path = staging / "adapter.json"
            write_json_atomic(adapter_path, adapter)

            manifest = plan_hierarchy(profile_path, adapter_path)

            self.assertEqual(manifest["status"], "review_required")
            self.assertEqual(manifest["review_items"], [
                {"kind": "missing-primary-authority-entry", "key": "topic", "title": "1.1 Topic"}
            ])

    def test_hierarchy_cannot_bypass_authority_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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
                    "root_output": "index.md",
                    "entries": [{"key": "u", "title": "Unit", "start_line": 1, "level": 1, "output": "u.md"}],
                },
                "content": {
                    "question_patterns": [r"^(?P<number>\d+)[.]\s+"],
                    "roles": [],
                },
            }
            adapter_path = staging / "adapter.json"
            write_json_atomic(adapter_path, adapter)

            with self.assertRaisesRegex(ConfigurationError, "exactly one"):
                plan_hierarchy(profile_path, adapter_path)

    def test_structural_toc_node_can_share_reviewed_boundary_with_content_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["entries"][1]["parent"], "unit")
            self.assertEqual(manifest["entries"][2]["parent"], "topic")
            apply_hierarchy(profile_path, adapter_path, manifest_path, overwrite=True)
            unit_text = (vault / "graph" / "unit" / "unit.md").read_text(encoding="utf-8")
            topic_text = (vault / "graph" / "unit" / "topic" / "topic.md").read_text(encoding="utf-8")
            self.assertIn("![[graph/unit/topic/topic.md]]", unit_text)
            self.assertNotIn("- ![[", unit_text)
            self.assertTrue(topic_text.startswith("## 1.1 Topic\n\n![[graph/unit/topic/core.md]]"))
            self.assertNotIn("- ![[", topic_text)
            content_manifest = plan_content(profile_path, adapter_path, staging / "hierarchy-coverage-manifest.json")
            self.assertEqual(content_manifest["status"], "passed")
            self.assertEqual(len(content_manifest["questions"]), 1)
            self.assertTrue(all(item["source_note"] != str(vault / "graph" / "unit" / "topic" / "topic.md") for item in content_manifest["questions"]))

    def test_alternate_labels_are_adapter_roles_and_unknown_labels_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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

            self.assertEqual(labels[0]["role"], "question-type")
            self.assertEqual(len(questions), 1)
            self.assertEqual(review, [{"kind": "unknown-label", "source_note": str(note), "line": 5, "text": "Mystery Label"}])

    def test_existing_child_embed_is_a_content_range_barrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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

            self.assertEqual(labels[0]["end_line"], 4)
            self.assertEqual(questions, [])
            self.assertEqual(review, [])

    def test_question_line_cannot_also_become_a_functional_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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

            self.assertEqual([label["role"] for label in labels], ["question-type"])
            self.assertEqual([question["number"] for question in questions], ["1"])
            self.assertEqual(review, [])

    def test_reviewed_answer_strategies_never_use_fuzzy_similarity_as_acceptance(self) -> None:
        question = {
            "number": "1",
            "context_key": "unit-a",
            "evidence": {"reference": "R-17", "source_page": "42", "stem": "Exact stem"},
        }
        answers = [
            {"id": "a", "number": "9", "context": "elsewhere", "evidence": {"reference": "R-17", "source_page": "42", "stem": "Exact stem"}},
            {"id": "b", "number": "1", "context": "unit-a", "evidence": {"reference": "R-18", "source_page": "43", "stem": "Similar but not exact"}},
        ]

        self.assertEqual([item["id"] for item in strategy_candidates("explicit-reference", question, "Exact stem", answers)[1]], ["a"])
        self.assertEqual([item["id"] for item in strategy_candidates("hierarchy-number", question, "Exact stem", answers)[1]], ["b"])
        self.assertEqual(strategy_candidates("source-page-number", question, "Exact stem", answers)[1], [])
        self.assertEqual([item["id"] for item in strategy_candidates("normalized-stem-exact", question, "Exact stem", answers)[1]], ["a"])

    def test_inline_question_headers_are_split_with_raw_coordinates(self) -> None:
        patterns = compile_question_patterns(
            {"content": {"question_patterns": [r"【(?P<number>\d+)】"]}}
        )

        virtual = split_inline_question_headers(
            ["A. previous choice 【20】Next question", "【21】Following question"], patterns
        )

        self.assertEqual(
            [item["text"] for item in virtual],
            ["A. previous choice", "【20】Next question", "【21】Following question"],
        )
        self.assertEqual(
            [(item["raw_line"], item["raw_column"]) for item in virtual],
            [(1, 1), (1, 20), (2, 1)],
        )

    def test_heading_only_role_does_not_split_numbered_question_subparts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            note = tmp_path / "section.md"
            note.write_text(
                "## 1. Knowledge\nDefinition\n## Basic point 2\n【4】Question\n"
                "(1) first subpart\n(2) second subpart\n【5】Next question\n",
                encoding="utf-8",
            )
            adapter = {
                "_graph_root": str(tmp_path),
                "content": {
                    "unknown_label_policy": "retain",
                    "question_patterns": [r"【(?P<number>\d+)】"],
                    "roles": [
                        {
                            "role": "knowledge-item",
                            "depth": 1,
                            "pattern": r"\d+[.] .+|[(]\d+[)] .+",
                            "heading_only": True,
                        },
                        {"role": "basic-point", "depth": 1, "pattern": r"Basic point \d+"},
                    ],
                },
            }

            labels, questions, review = plan_note(
                {"key": "section", "path": str(note), "answer_context": "section"},
                compile_role_rules(adapter),
                compile_question_patterns(adapter),
                adapter,
            )

            self.assertEqual([item["title"] for item in labels], ["1. Knowledge", "Basic point 2"])
            self.assertEqual([item["number"] for item in questions], ["4", "5"])
            self.assertEqual(questions[0]["end_line"], 6)
            self.assertEqual(review, [])

    def test_nested_and_restarted_numbering_is_scoped_by_reviewed_context(self) -> None:
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
        self.assertEqual(patterns[0].match("2.1) Nested").group("number"), "2.1")
        self.assertEqual(patterns[1].match("① Restarted in another section").group("number"), "①")

    def test_repeated_functional_blocks_own_answer_context_and_zero_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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

            self.assertEqual([item["answer_context"] for item in labels], [
                "section:training-band:1",
                "section:training-band:2",
            ])
            self.assertEqual([item["context_key"] for item in questions], [
                "section:training-band:1",
                "section:training-band:2",
            ])
            self.assertEqual([item["kind"] for item in review], ["invalid-question-number"])
            self.assertTrue(all(item["source_part"] == {"line": 1, "part": 2, "start_page": 201, "end_page": 400} for item in questions))


if __name__ == "__main__":
    unittest.main()

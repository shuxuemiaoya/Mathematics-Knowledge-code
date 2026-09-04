from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import init_book
import run_relation_model
import semantic_relations
from semantic_atomization import seal_artifact
import validate_book_graph


class SemanticRelationTests(unittest.TestCase):
    def fixture(self, root: Path) -> dict[str, Path]:
        source_lines = [
            "# Book",
            "## Chapter",
            "Known idea.",
            "A question caused by the known idea.",
            "New idea answering that question.",
            "A complete worked example.",
            "A complete exercise.",
        ]
        staging, book = root / "staging", root / "book"
        staging.mkdir(parents=True)
        book.mkdir(parents=True)
        source = staging / "source.md"
        source.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
        profile = init_book.create_profile(source, staging, book)
        profile.pop("atomization")
        profile.pop("markdown_rendering")
        profile_path = staging / "book-profile.json"
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        nodes: list[dict[str, Any]] = [
            {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
            {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/Chapter/Chapter.md", "heading_ranges": [[2, 2]], "children": ["known", "scenario", "new", "example", "exercise"]},
            {"key": "known", "title": "Known", "layer": "atom", "parent_key": "chapter", "category": "knowledge", "filename": "原子层/知识点/Known.md", "source_range": [3, 3]},
            {"key": "scenario", "title": "Question", "layer": "atom", "parent_key": "chapter", "category": "scenario", "filename": "原子层/情景引入/Question.md", "source_range": [4, 4]},
            {"key": "new", "title": "New", "layer": "atom", "parent_key": "chapter", "category": "knowledge", "filename": "原子层/知识点/New.md", "source_range": [5, 5]},
            {"key": "example", "title": "Example", "layer": "atom", "parent_key": "chapter", "category": "worked-example", "filename": "原子层/例题/Example.md", "source_range": [6, 6]},
            {"key": "exercise", "title": "Exercise", "layer": "atom", "parent_key": "chapter", "category": "exercise", "filename": "原子层/习题/Exercise.md", "source_range": [7, 7]},
        ]
        manifest = {
            "schema_version": 1,
            "profile": str(profile_path),
            "source_sha256": profile["source"]["sha256"],
            "source_markdown": str(source),
            "source_markdown_sha256": validate_book_graph.sha256_file(source),
            "review": {"status": "passed", "reviewed_entire_book": True, "toc_hierarchy": "passed", "source_coverage": "passed", "atom_link_free": "passed"},
            "excluded_ranges": [],
            "nodes": nodes,
            "source_order": ["known", "scenario", "new", "example", "exercise"],
            "relations": [],
        }
        manifest_path = staging / "book-graph.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        by_key = {node["key"]: node for node in nodes}
        for node in nodes:
            path = book / node["filename"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if node["layer"] == "atom":
                start, end = node["source_range"]
                path.write_text("\n".join(source_lines[start - 1 : end]) + "\n", encoding="utf-8")
            else:
                links = []
                for child_key in node["children"]:
                    child = by_key[child_key]
                    target = book / child["filename"]
                    href = os.path.relpath(target, path.parent).replace("\\", "/").replace(" ", "%20")
                    links.append(f"![{child['title']}]({href})")
                path.write_text(f"# {node['title']}\n\n" + "\n\n".join(links) + "\n", encoding="utf-8")
        return {"staging": staging, "book": book, "source": source, "profile": profile_path, "manifest": manifest_path}

    def relation(self, left: str, right: str, relation_type: str, tier: str, left_line: int, right_line: int, confidence: float = 0.98) -> dict[str, Any]:
        return {
            "from_key": left,
            "to_key": right,
            "type": relation_type,
            "tier": tier,
            "evidence_kind": "pedagogical-inference",
            "evidence_ranges": [
                {"node_key": left, "source_range": [left_line, left_line]},
                {"node_key": right, "source_range": [right_line, right_line]},
            ],
            "rationale": "The two source-backed teaching units form this learning step.",
            "confidence": confidence,
        }

    def decisions(self, jobs: dict[str, Any], relations: list[dict[str, Any]]) -> dict[str, Any]:
        decisions = []
        for job in jobs["jobs"]:
            keys = {atom["atom_key"] for atom in job["atoms"]}
            signatures = []
            for atom in job["atoms"]:
                key = atom["atom_key"]
                signatures.append(
                    {
                        "atom_key": key,
                        "role": (
                            "core" if atom["category"] in {"knowledge", "scenario"}
                            else "bridge" if atom["category"] == "worked-example"
                            else "satellite"
                        ),
                        "teaches": [atom["title"]],
                        "assumes": ["Known"] if key in {"scenario", "new"} else [],
                    }
                )
            decisions.append({"job_id": job["job_id"], "packet_sha256": job["packet_sha256"], "concept_signatures": signatures, "relations": [item for item in relations if item["from_key"] in keys and item["to_key"] in keys]})
        return seal_artifact({"schema_version": 1, "kind": "round-1-relations", "jobs_sha256": jobs["artifact_sha256"], "reviewer": {"type": "agent"}, "status": "complete", "decisions": decisions})

    def round2(self, audits: dict[str, Any], relations: list[dict[str, Any]]) -> dict[str, Any]:
        atom_to_chapter = audits["atom_to_chapter"]
        decisions = []
        for audit in audits["audits"]:
            if audit["scope"] == "chapter":
                selected = [item for item in relations if atom_to_chapter[item["from_key"]] == audit["scope_key"] and atom_to_chapter[item["to_key"]] == audit["scope_key"]]
            else:
                selected = [item for item in relations if atom_to_chapter[item["from_key"]] != atom_to_chapter[item["to_key"]]]
            decisions.append(
                {
                    "audit_id": audit["audit_id"],
                    "packet_sha256": audit["packet_sha256"],
                    "reviewed_candidate_ids": [item["candidate_id"] for item in audit["candidate_pairs"]],
                    "relations": selected,
                    "independent_atoms": [],
                }
            )
        return seal_artifact({"schema_version": 1, "kind": "round-2-relations", "round_2_jobs_sha256": audits["artifact_sha256"], "reviewer": {"type": "agent"}, "status": "complete", "decisions": decisions})

    def passed_relations(self) -> list[dict[str, Any]]:
        return [
            self.relation("known", "scenario", "motivates", "backbone", 3, 4),
            self.relation("scenario", "new", "motivates", "backbone", 4, 5),
            self.relation("new", "example", "illustrates", "supporting", 5, 6),
            self.relation("new", "exercise", "practices", "supporting", 5, 7),
        ]

    def test_two_pass_relations_capture_prompted_scenario_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.fixture(Path(temporary))
            jobs = semantic_relations.prepare_relation_jobs(items["manifest"])
            relations = self.passed_relations()
            round1 = self.decisions(jobs, relations)
            self.assertEqual(semantic_relations.validate_round1_payload(jobs, round1)["status"], "passed")
            audits = semantic_relations.prepare_audit_jobs(jobs, round1)
            round2 = self.round2(audits, relations)
            final, queue = semantic_relations.finalize_relations(jobs, round1, audits, round2)
            self.assertEqual(final["status"], "passed", queue["items"])
            self.assertEqual(final["unresolved_count"], 0)
            self.assertEqual([item["type"] for item in final["relations"]].count("motivates"), 2)

            for name, payload in (("relation-jobs.json", jobs), ("round-1-relations.json", round1), ("round-2-jobs.json", audits), ("round-2-relations.json", round2)):
                path = items["staging"] / name
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # Re-finalize from path-tagged artifacts so applied bindings are auditable.
            final, _ = semantic_relations.finalize_relations(
                semantic_relations.load_tagged(items["staging"] / "relation-jobs.json", "relation-jobs"),
                semantic_relations.load_tagged(items["staging"] / "round-1-relations.json", "round-1-relations"),
                semantic_relations.load_tagged(items["staging"] / "round-2-jobs.json", "round-2-relation-jobs"),
                semantic_relations.load_tagged(items["staging"] / "round-2-relations.json", "round-2-relations"),
            )
            final_path = items["staging"] / "relation-final.json"
            final_path.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output = items["staging"] / "book-graph.star-map.json"
            profile_output = items["staging"] / "book-profile.star-map.json"
            report = semantic_relations.apply_relation_final(items["manifest"], final_path, output, profile_output)
            self.assertEqual(report["relations"], 4)
            applied = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(applied["relation_review"]["featured_example_keys"], ["example"])
            validation = validate_book_graph.validate_graph(output, items["book"])
            self.assertEqual(validation["status"], "passed", validation["errors"])

    def test_low_confidence_and_one_sided_inference_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.fixture(Path(temporary))
            jobs = semantic_relations.prepare_relation_jobs(items["manifest"])
            relation = self.relation("known", "scenario", "motivates", "backbone", 3, 4, confidence=0.80)
            relation["evidence_ranges"] = relation["evidence_ranges"][:1]
            decisions = self.decisions(jobs, [relation])
            next(item for item in decisions["decisions"][0]["concept_signatures"] if item["atom_key"] == "exercise")["role"] = "bridge"
            report = semantic_relations.validate_round1_payload(jobs, decisions)
            self.assertEqual(report["status"], "failed")
            self.assertIn("relation-inference-needs-both-endpoints", {item["code"] for item in report["errors"]})
            self.assertIn("relation-bridge-role-category-invalid", {item["code"] for item in report["errors"]})
            self.assertIn("relation-confidence-below-threshold", {item["code"] for item in report["review_items"]})

    def test_backbone_cycle_and_orphan_satellites_require_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.fixture(Path(temporary))
            jobs = semantic_relations.prepare_relation_jobs(items["manifest"])
            relations = [
                self.relation("known", "scenario", "motivates", "backbone", 3, 4),
                self.relation("scenario", "new", "motivates", "backbone", 4, 5),
                self.relation("new", "known", "prerequisite", "backbone", 5, 3),
            ]
            round1 = self.decisions(jobs, relations)
            audits = semantic_relations.prepare_audit_jobs(jobs, round1)
            final, queue = semantic_relations.finalize_relations(jobs, round1, audits, self.round2(audits, relations))
            self.assertEqual(final["status"], "review_required")
            codes = {item["code"] for item in queue["items"]}
            self.assertIn("relation-backbone-cycle", codes)
            self.assertIn("relation-orphan-teaching-atom", codes)

    def test_external_runner_requires_execute_and_exact_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "jobs.json"
            output_path = Path(temporary) / "out.json"
            input_path.write_text("{}", encoding="utf-8")
            with self.assertRaises(run_relation_model.RelationModelError):
                run_relation_model.run_packets(input_path, output_path, 1, "", "secret", False)


if __name__ == "__main__":
    unittest.main()

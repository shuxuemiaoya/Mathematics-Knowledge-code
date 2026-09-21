from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import migrate_scoped_introductions as migration


class ScopedIntroductionMigrationTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_merges_fragments_and_rebinds_relation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.md"
            source.write_text(
                "# Book\n## Chapter\n导语第一段。\n\n![](images/intro.png)\n### Section\n第一个知识点。\n",
                encoding="utf-8",
            )
            profile = root / "book-profile.json"
            self.write_json(profile, {
                "schema_version": 1,
                "paths": {"staging_root": str(root), "book_root": str(root / "book")},
                "atomization": {"mode": "llm-category-aware-graph"},
                "markdown_rendering": {}, "canvas": {},
            })
            base = root / "base.json"
            base_payload = {
                "schema_version": 1, "profile": str(profile),
                "source_markdown": str(source),
                "source_markdown_sha256": migration.sha256_file(source),
                "review": {"status": "passed", "reviewed_entire_book": True},
                "nodes": [
                    {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "heading_ranges": [[1, 1]], "children": ["chapter"]},
                    {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "heading_ranges": [[2, 2]], "children": ["section"]},
                    {"key": "section", "title": "Section", "layer": "organizer", "parent_key": "chapter", "heading_ranges": [[6, 6]], "children": []},
                ],
                "source_order": [], "relations": [],
            }
            self.write_json(base, base_payload)
            intro_one = {
                "atom_id": "intro-1", "owner_key": "chapter", "source_range": [3, 3],
                "category": "scenario", "title": "Chapter·章节导语",
                "scenario_role": "chapter-introduction", "confidence": 0.98,
            }
            intro_two = {
                "atom_id": "intro-2", "owner_key": "chapter", "source_range": [5, 5],
                "category": "scenario", "title": "Chapter·章节导语（续 2）",
                "scenario_role": "chapter-introduction", "confidence": 0.98,
            }
            knowledge = {
                "atom_id": "knowledge-1", "owner_key": "section", "source_range": [7, 7],
                "category": "knowledge", "title": "第一个知识点", "confidence": 0.98,
            }
            atomization_path = root / "atomization-final.json"
            atomization = migration.seal({
                "schema_version": 4, "kind": "atomization-final", "status": "passed",
                "source_markdown": str(source), "source_markdown_sha256": migration.sha256_file(source),
                "base_manifest": str(base), "base_manifest_sha256": migration.sha256_file(base),
                "scope_root_keys": ["chapter"], "unresolved_count": 0,
                "atoms": [intro_one, intro_two, knowledge], "knowledge_signatures": [],
                "local_relations": [], "derived_card_candidates": [], "bindings": {},
                "reviewer": {}, "atomization": {"mode": "llm-category-aware-graph"},
                "feedback_cycle": {"cycle": 0, "max_cycles": 2, "history": []},
            })
            self.write_json(atomization_path, atomization)
            first_key = migration.virtual_atom_key(intro_one)
            second_key = migration.virtual_atom_key(intro_two)
            knowledge_key = migration.virtual_atom_key(knowledge)
            relation_path = root / "relation-final.json"
            relation = migration.seal({
                "schema_version": 3, "kind": "relation-final-v2", "status": "passed",
                "manifest": str(base), "manifest_sha256": migration.sha256_file(base),
                "source_markdown_sha256": migration.sha256_file(source),
                "atomization_final": str(atomization_path),
                "atomization_final_sha256": atomization["artifact_sha256"],
                "feedback_cycle": {"cycle": 0, "max_cycles": 2, "history": []},
                "relation_analysis": {"mode": "llm-three-pass"}, "bindings": {}, "reviewer": {},
                "concepts": [{
                    "key": "concept-1", "preferred_label": "主题", "aliases": [],
                    "definition": "这一概念具有完整且可复用的数学定义。", "kind": "concept",
                    "member_proposal_ids": ["p1"],
                    "evidence": [{"atom_key": first_key, "source_range": [3, 3]}],
                    "source_chapters": ["chapter"], "first_source_order": 3,
                }],
                "atom_concept_links": [
                    {"key": "l1", "atom_key": first_key, "concept_key": "concept-1", "role": "motivates", "evidence_ranges": [[3, 3]], "confidence": 0.97},
                    {"key": "l2", "atom_key": second_key, "concept_key": "concept-1", "role": "motivates", "evidence_ranges": [[5, 5]], "confidence": 0.97},
                ],
                "concept_relations": [],
                "relations": [
                    {"key": "r1", "from_key": first_key, "to_key": second_key, "type": "motivates", "tier": "supporting", "evidence_kind": "pedagogical-inference", "evidence_ranges": [{"node_key": first_key, "source_range": [3, 3]}, {"node_key": second_key, "source_range": [5, 5]}], "rationale": "旧片段链", "confidence": 0.97, "basis_keys": [], "candidate_sources": ["legacy"]},
                    {"key": "r2", "from_key": second_key, "to_key": knowledge_key, "type": "motivates", "tier": "supporting", "evidence_kind": "pedagogical-inference", "evidence_ranges": [{"node_key": second_key, "source_range": [5, 5]}, {"node_key": knowledge_key, "source_range": [7, 7]}], "rationale": "导向知识", "confidence": 0.97, "basis_keys": [], "candidate_sources": ["legacy"]},
                ],
                "formulas": [],
                "atom_roles": [
                    {"atom_key": first_key, "role": "core", "rationale": "章节导语"},
                    {"atom_key": second_key, "role": "core", "rationale": "章节导语"},
                    {"atom_key": knowledge_key, "role": "core", "rationale": "知识主线"},
                ],
                "independent_atoms": [], "independent_components": [],
                "boundary_feedback": [], "unresolved_count": 0,
            })
            self.write_json(relation_path, relation)

            output = root / "migrated"
            report = migration.migrate(base, atomization_path, relation_path, output)
            self.assertEqual(report["counts"]["groups"], 1)
            self.assertEqual(report["counts"]["removed_fragments"], 1)
            migrated_atoms = json.loads((output / "atomization-final.json").read_text())["atoms"]
            scenarios = [item for item in migrated_atoms if item.get("scenario_role") == "chapter-introduction"]
            self.assertEqual(len(scenarios), 1)
            self.assertEqual(scenarios[0]["source_range"], [3, 5])
            migrated_relation = json.loads((output / "relation-final.json").read_text())
            merged_key = migration.virtual_atom_key(scenarios[0])
            self.assertFalse(any(item["from_key"] == item["to_key"] for item in migrated_relation["relations"]))
            self.assertTrue(any(
                item["from_key"] == merged_key and item["to_key"] == knowledge_key
                for item in migrated_relation["relations"]
            ))


if __name__ == "__main__":
    unittest.main()

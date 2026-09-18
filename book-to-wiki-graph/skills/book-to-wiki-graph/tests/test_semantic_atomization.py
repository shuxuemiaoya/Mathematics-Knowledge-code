from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import init_book
import materialize_book
import run_atomization_model
import semantic_atomization as semantic
import validate_book_graph


class SemanticAtomizationTests(unittest.TestCase):
    def make_base(self, root: Path) -> dict[str, Path]:
        lines = [
            "# Book", "## 第一章", "### 第一节",
            "观察并思考：观察纸张折叠和灯光投影形成的图形，记录点、线、面在运动中的变化，比较不同操作产生的共同特征，并说明这些现象如何帮助我们认识几何体。",
            "尝试用自己的语言说明观察结果，不要脱离前面的操作情境。",
            "点动成线，线动成面，面动成体。这个结论来自连续观察，运动描述、图形变化、符号说明和结论应作为一个教学过程理解。",
            "定义中的对象、条件、符号和解释在这里继续展开，说明每个条件为何不可缺少。",
            "由此得到紧邻结论，并进一步说明结论的适用范围和容易混淆的反例。",
            "棱柱的上下底面互相平行且形状相同，侧面都是平行四边形。这是具有完整条件、表示和辨析说明的正式定义，可以独立命名和复用。",
            "例 1：识别图中的棱柱，并说明判断依据。", "分析：先检查底面，再检查侧面。",
            "解：该图形满足棱柱定义，因此是棱柱。", "结论：判断时需要同时使用定义中的全部条件。",
            "1. 判断下列图形是不是棱柱，并说明理由。", "（1）图形甲；", "（2）图形乙。",
        ]
        source = root / "source.md"
        source.write_text("\n".join(lines) + "\n", encoding="utf-8")
        staging, book = root / "base-staging", root / "base-book"
        staging.mkdir()
        profile = init_book.create_profile(source, staging, book)
        # Most tests retain the v0.5 two-pass compatibility path. The focused
        # role-review test below exercises the new required v0.6 gate.
        profile["atomization"]["mode"] = "llm-two-pass"
        profile["atomization"].pop("teaching_role_audit", None)
        profile["atomization"].pop("role_correction_confidence_threshold", None)
        profile_path = staging / "book-profile.json"
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        old = [
            ("old-scenario", "scenario", [4, 5]), ("old-fragment", "knowledge", [6, 6]),
            ("old-definition", "knowledge", [7, 8]), ("old-independent", "knowledge", [9, 9]),
            ("old-example", "worked-example", [10, 13]), ("old-exercise", "exercise", [14, 16]),
        ]
        nodes: list[dict[str, Any]] = [
            {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
            {"key": "chapter", "title": "第一章", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/第一章/第一章.md", "heading_ranges": [[2, 2]], "children": ["lesson"]},
            {"key": "lesson", "title": "第一节", "layer": "organizer", "parent_key": "chapter", "organizer_level": 3, "filename": "组织层/Book/第一章/第一节/第一节.md", "heading_ranges": [[3, 3]], "children": [item[0] for item in old]},
        ]
        for index, (key, category, source_range) in enumerate(old):
            directory = {"knowledge": "知识点", "scenario": "情景引入", "worked-example": "例题", "exercise": "习题"}[category]
            nodes.append({"key": key, "title": key, "layer": "atom", "parent_key": "lesson", "category": category, "filename": f"原子层/{directory}/{index}.md", "source_range": source_range})
        manifest = {
            "schema_version": 1, "profile": str(profile_path.resolve()), "source_sha256": profile["source"]["sha256"],
            "source_markdown": str(source.resolve()), "source_markdown_sha256": semantic.sha256_file(source),
            "review": {"status": "passed", "reviewed_entire_book": True, "toc_hierarchy": "passed", "source_coverage": "passed", "atom_link_free": "passed"},
            "excluded_ranges": [], "nodes": nodes, "source_order": [item[0] for item in old], "relations": [],
        }
        manifest_path = staging / "book-graph.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"source": source, "staging": staging, "profile": profile_path, "manifest": manifest_path}

    def atom(self, atom_id: str, source_range: list[int], category: str, title: str, confidence: float = 0.98, **extra: Any) -> dict[str, Any]:
        result = {"atom_id": atom_id, "owner_key": "lesson", "source_range": source_range, "category": category, "title": title, "boundary_reason": "Both boundaries separate independently reusable teaching units.", "cohesion_reason": "These exact source lines form one complete teaching unit.", "confidence": confidence}
        result.update(extra)
        return result

    def write_artifact(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        sealed = semantic.seal_artifact(payload)
        path.write_text(json.dumps(sealed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sealed["_path"] = str(path.resolve())
        return sealed

    def attach_organizer_review(self, base: dict[str, Path]) -> None:
        manifest = json.loads(base["manifest"].read_text(encoding="utf-8"))
        review = semantic.seal_artifact({
            "schema_version": 1,
            "kind": "organizer-review",
            "status": "passed",
            "base_manifest_sha256": semantic.sha256_file(base["manifest"]),
            "source_markdown_sha256": semantic.sha256_file(base["source"]),
            "reviewer": {"type": "fixture"},
            "demote_organizer_keys": [],
            "content_runs": [{"owner_key": "lesson", "create_organizer": False, "source_range": [4, 16]}],
            "renumber_parent_keys": [],
        })
        review_path = base["staging"] / "organizer-review.json"
        review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["organizer_review"] = {
            "status": "passed", "path": str(review_path), "sha256": review["artifact_sha256"],
            "demoted_organizer_keys": [], "synthesized_organizer_keys": [],
        }
        base["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def passed(self, root: Path) -> dict[str, Any]:
        base = self.make_base(root)
        jobs = self.write_artifact(base["staging"] / "atomization-jobs.json", semantic.prepare_jobs(base["manifest"], ["chapter"]))
        job = jobs["jobs"][0]
        round1_atoms = [self.atom("r1-prompt", [4, 5], "scenario", "观察提示"), self.atom("r1-fragment", [6, 7], "knowledge", "点线面体"), self.atom("r1-misaligned", [8, 9], "knowledge", "结论和下一定义"), self.atom("r1-example", [10, 13], "worked-example", "例 1"), self.atom("r1-exercise", [14, 16], "exercise", "习题 1")]
        round1 = self.write_artifact(base["staging"] / "round-1-decisions.json", {"schema_version": 1, "kind": "round-1-decisions", "jobs_sha256": jobs["artifact_sha256"], "reviewer": {"type": "codex-agent", "model": "current-agent"}, "decisions": [{"job_id": job["job_id"], "packet_sha256": job["packet_sha256"], "atoms": round1_atoms}]})
        audit_jobs = self.write_artifact(base["staging"] / "round-2-jobs.json", semantic.prepare_audit_jobs(jobs, round1))
        audit = audit_jobs["audits"][0]
        final_atoms = [self.atom("final-unit", [4, 8], "knowledge", "从观察到点线面体"), self.atom("final-definition", [9, 9], "knowledge", "棱柱定义", standalone_kind="formal-definition", standalone_reason="This is a complete formal definition with all necessary conditions and independent reuse value."), self.atom("final-example", [10, 13], "worked-example", "例 1"), self.atom("final-exercise", [14, 16], "exercise", "习题 1")]
        boundary_reviews = [{"boundary_id": boundary["boundary_id"], "action": semantic.actual_boundary_action(final_atoms, boundary), "reason": "Independent second-pass review of this exact adjacency.", "confidence": 0.98} for boundary in audit["boundaries"]]
        round2 = self.write_artifact(base["staging"] / "round-2-decisions.json", {"schema_version": 1, "kind": "round-2-decisions", "round_2_jobs_sha256": audit_jobs["artifact_sha256"], "reviewer": {"type": "codex-agent", "model": "current-agent"}, "decisions": [{"audit_id": audit["audit_id"], "packet_sha256": audit["packet_sha256"], "boundary_reviews": boundary_reviews, "atoms": final_atoms}]})
        final, queue = semantic.finalize_payload(jobs, round1, audit_jobs, round2)
        final_path = base["staging"] / "atomization-final.json"
        final_path.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (base["staging"] / "atomization-review-queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {**base, "jobs": jobs, "round1": round1, "audit_jobs": audit_jobs, "round2": round2, "final": final, "final_path": final_path, "queue": queue}

    def test_two_pass_repairs_fragmentation_and_audits_every_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.passed(Path(temporary))
            self.assertEqual(items["final"]["status"], "passed", items["queue"])
            self.assertEqual([atom["source_range"] for atom in items["final"]["atoms"]], [[4, 8], [9, 9], [10, 13], [14, 16]])
            reviews = items["round2"]["decisions"][0]["boundary_reviews"]
            self.assertEqual(len(reviews), len(items["audit_jobs"]["audits"][0]["boundaries"]))
            self.assertTrue({"merge", "resegment", "keep"}.issubset({item["action"] for item in reviews}))

    def test_category_aware_round_requires_signatures_relations_and_derived_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.make_base(root)
            profile = json.loads(base["profile"].read_text(encoding="utf-8"))
            profile["atomization"] = dict(semantic.DEFAULT_ATOMIZATION)
            self.assertEqual(profile["atomization"]["knowledge_boundary_authority"], "llm-exclusive")
            self.assertEqual(profile["atomization"]["provisional_atom_policy"], "coverage-context-only")
            self.assertEqual(profile["atomization"]["parallel_definition_policy"], "split-when-independently-reusable")
            base["profile"].write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            self.attach_organizer_review(base)
            jobs = semantic.prepare_jobs(base["manifest"], ["chapter"])
            job = jobs["jobs"][0]
            self.assertEqual(job["instructions"]["boundary_authority"], "LLM has exclusive authority over knowledge boundaries and atom count. Baseline atoms are non-binding coverage/context hints only; ignore their titles and internal boundaries unless an explicit hard boundary is independently proven.")
            self.assertIn("全称量词 and 存在量词", job["instructions"]["parallel_definitions"])
            atoms = [
                self.atom("k", [4, 9], "knowledge", "从观察到棱柱定义"),
                self.atom("w", [10, 13], "worked-example", "棱柱判断例题"),
                self.atom("e", [14, 16], "exercise", "棱柱练习"),
            ]
            decision = {
                "job_id": job["job_id"], "packet_sha256": job["packet_sha256"], "atoms": atoms,
                "knowledge_signatures": [{"atom_id": "k", "teaches": ["点线面体与棱柱条件"], "assumes": [], "outputs": ["棱柱判断依据"], "global_relation_needed": False, "independent_reason": ""}],
                "local_relations": [{"from_atom_id": "k", "to_atom_id": "w", "type": "illustrates", "tier": "supporting", "evidence_kind": "pedagogical-inference", "evidence": [{"atom_id": "k", "source_range": [9, 9]}, {"atom_id": "w", "source_range": [10, 13]}], "rationale": "例题完整应用前面建立的棱柱判断条件。", "confidence": 0.99, "recall_source": ["organizer-neighborhood"]}],
                "derived_card_candidates": [{"candidate_id": "c1", "from_atom_id": "k", "category": "concept", "title": "棱柱", "source_range": [9, 9], "selection_reason": "该连续原文给出可复用的棱柱定义与条件。", "confidence": 0.99, "expression": "", "variables": [], "conditions": [], "example_role": ""}],
            }
            round1 = semantic.seal_artifact({"schema_version": 2, "kind": "round-1-decisions", "jobs_sha256": jobs["artifact_sha256"], "reviewer": {"type": "agent"}, "decisions": [decision]})
            report = semantic.validate_round1_payload(jobs, round1)
            self.assertNotEqual(report["status"], "failed", report["structural_errors"])
            decision.pop("knowledge_signatures")
            stale = semantic.seal_artifact({"schema_version": 2, "kind": "round-1-decisions", "jobs_sha256": jobs["artifact_sha256"], "reviewer": {"type": "agent"}, "decisions": [decision]})
            invalid = semantic.validate_round1_payload(jobs, stale)
            self.assertEqual(invalid["status"], "failed")
            self.assertIn("knowledge-signatures-missing", {item["code"] for item in invalid["structural_errors"]})

    def test_example_solution_and_exercise_subparts_remain_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.passed(Path(temporary))
            by_category = {atom["category"]: atom for atom in items["final"]["atoms"]}
            self.assertEqual(by_category["worked-example"]["source_range"], [10, 13])
            self.assertEqual(by_category["exercise"]["source_range"], [14, 16])

    def test_category_aware_materialization_creates_noncovering_derived_cards_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.make_base(root)
            profile = json.loads(base["profile"].read_text(encoding="utf-8"))
            profile["atomization"] = dict(semantic.DEFAULT_ATOMIZATION)
            base["profile"].write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            self.attach_organizer_review(base)
            atoms = [
                self.atom("k", [4, 9], "knowledge", "从观察到棱柱定义"),
                self.atom("w", [10, 13], "worked-example", "棱柱判断例题"),
                self.atom("e", [14, 16], "exercise", "棱柱练习"),
            ]
            final = semantic.seal_artifact({
                "schema_version": 2, "kind": "atomization-final", "status": "passed", "unresolved_count": 0,
                "base_manifest": str(base["manifest"]), "base_manifest_sha256": semantic.sha256_file(base["manifest"]),
                "source_markdown": str(base["source"]), "source_markdown_sha256": semantic.sha256_file(base["source"]),
                "scope_root_keys": ["chapter"], "atomization": dict(semantic.DEFAULT_ATOMIZATION), "atoms": atoms,
                "knowledge_signatures": [{"atom_id": "k", "teaches": ["棱柱"], "assumes": [], "outputs": ["判断棱柱"]}],
                "local_relations": [], "derived_card_candidates": [], "bindings": {}, "reviewer": {},
            })
            final_path = base["staging"] / "atomization-final-v7.json"
            final_path.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
            keys = {atom["atom_id"]: materialize_book.final_key(atom) for atom in atoms}
            relation = semantic.seal_artifact({
                "schema_version": 3, "kind": "relation-final-v2", "status": "passed", "unresolved_count": 0,
                "manifest": str(base["manifest"]), "manifest_sha256": semantic.sha256_file(base["manifest"]),
                "source_markdown_sha256": semantic.sha256_file(base["source"]), "atomization_final": str(final_path), "atomization_final_sha256": final["artifact_sha256"],
                "relation_analysis": profile["relation_analysis"], "bindings": {}, "reviewer": {}, "boundary_feedback": [],
                "concepts": [
                    {"key": "c1", "preferred_label": "立体图形", "aliases": [], "definition": "由平面图形围成的空间图形。", "kind": "concept", "member_proposal_ids": ["p1"], "evidence": [{"atom_key": keys["k"], "source_range": [4, 4]}], "source_chapters": ["chapter"], "first_source_order": 4},
                    {"key": "c2", "preferred_label": "棱柱", "aliases": [], "definition": "上下底面平行且相同的立体图形。", "kind": "definition", "member_proposal_ids": ["p2"], "evidence": [{"atom_key": keys["k"], "source_range": [8, 9]}], "source_chapters": ["chapter"], "first_source_order": 9},
                ],
                "atom_concept_links": [
                    {"key": "l1", "atom_key": keys["k"], "concept_key": "c1", "role": "introduces", "evidence_ranges": [[4, 4]], "confidence": 0.99},
                    {"key": "l2", "atom_key": keys["k"], "concept_key": "c2", "role": "introduces", "evidence_ranges": [[9, 9]], "confidence": 0.99},
                    {"key": "l3", "atom_key": keys["w"], "concept_key": "c2", "role": "applies", "evidence_ranges": [[10, 13]], "confidence": 0.99},
                    {"key": "l4", "atom_key": keys["e"], "concept_key": "c2", "role": "practices", "evidence_ranges": [[14, 16]], "confidence": 0.99},
                ], "concept_relations": [],
                "relations": [{"key": "r1", "from_key": keys["k"], "to_key": keys["w"], "type": "illustrates", "tier": "supporting", "evidence_kind": "explicit", "evidence_ranges": [{"node_key": keys["k"], "source_range": [9, 9]}, {"node_key": keys["w"], "source_range": [10, 13]}], "rationale": "完整例题直接使用前面给出的棱柱判断条件。", "confidence": 0.99, "basis_keys": [], "candidate_sources": ["test"]}],
                "formulas": [{"key": "f1", "title": "棱柱判断条件", "expression": "上下底面平行且全等", "variables": [], "conditions": ["侧面为平行四边形"], "derived_from_key": keys["k"], "source_range": [6, 6], "selection_reason": "该条件可独立复用。", "confidence": 0.99}],
                "atom_roles": [{"atom_key": keys["k"], "role": "core"}, {"atom_key": keys["w"], "role": "bridge"}, {"atom_key": keys["e"], "role": "satellite"}], "independent_atoms": [], "independent_components": [],
            })
            relation_path = base["staging"] / "relation-final-v7.json"
            relation_path.write_text(json.dumps(relation, ensure_ascii=False), encoding="utf-8")
            output_manifest = base["staging"] / "book-graph-v7.json"
            materialize_book.materialize(base["manifest"], final_path, root / "book-v7", output_manifest, output_profile=base["staging"] / "book-profile-v7.json", overwrite=False, relation_final_path=relation_path)
            graph = json.loads(output_manifest.read_text(encoding="utf-8"))
            self.assertEqual(len(graph["source_order"]), 3)
            self.assertEqual(len(graph["derived_order"]), 2)
            self.assertEqual({next(node for node in graph["nodes"] if node["key"] == key)["category"] for key in graph["derived_order"]}, {"concept", "formula"})
            self.assertEqual(len(graph["derived_indexes"]), 2)
            indexed = [key for spec in graph["derived_indexes"] for key in spec["derived_keys"]]
            self.assertNotEqual(indexed, graph["derived_order"])
            validation = validate_book_graph.validate_graph(output_manifest, root / "book-v7")
            self.assertEqual(validation["status"], "passed", validation["errors"])
            for key in graph["derived_order"]:
                node = next(node for node in graph["nodes"] if node["key"] == key)
                text = (root / "book-v7" / node["filename"]).read_text(encoding="utf-8")
                self.assertFalse(any(line.startswith("#") for line in text.splitlines()))
                for property_name in ("atom_key", "owner_key", "source_sha256", "review_status"):
                    self.assertIn(f"{property_name}:", text)
            concept_names = {
                Path(node["filename"]).name
                for node in graph["nodes"] if node.get("category") == "concept"
            }
            self.assertEqual(concept_names, {"棱柱.md"})
            for spec in graph["derived_indexes"]:
                index_text = (root / "book-v7" / spec["filename"]).read_text(encoding="utf-8")
                self.assertEqual(validate_book_graph.frontmatter_scalar(index_text, "node_type"), "organizer")
                self.assertEqual(
                    validate_book_graph.frontmatter_scalar(index_text, "parent_organizer_key"),
                    spec["chapter_key"],
                )
                self.assertEqual(
                    validate_book_graph.frontmatter_scalar(index_text, "children_count"),
                    len(spec["derived_keys"]),
                )
            concept = next(item for item in graph["concepts"] if item["key"] == "c2")
            concept_node = next(node for node in graph["nodes"] if node.get("concept_key") == "c2")
            self.assertEqual(concept["evidence"][0]["source_range"], [8, 9])
            self.assertEqual(concept_node["source_range"], [9, 9])

    def test_teaching_role_review_resegments_a_mixed_question_atom(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            items = self.passed(root)
            items["final"]["atoms"][0]["title"] = "观察并思考这个很长的问题：你能说明这些现象如何帮助我们认识几何体并得到点线面体的完整结论吗？"
            items["final"] = semantic.seal_artifact({key: value for key, value in items["final"].items() if key != "artifact_sha256"})
            items["final_path"].write_text(json.dumps(items["final"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            jobs_path = items["staging"] / "atom-role-jobs.json"
            jobs_path.write_text(json.dumps(semantic.prepare_role_review(items["final_path"]), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            jobs = semantic.load_tagged(jobs_path, "atom-role-jobs")
            required = [atom for atom in jobs["atoms"] if atom["requires_decision"]]
            self.assertEqual([atom["atom_id"] for atom in required], ["final-unit"])
            replacements = [
                self.atom("role-scenario", [4, 5], "scenario", "观察图形运动的情景"),
                self.atom("role-knowledge", [6, 8], "knowledge", "点、线、面、体的运动关系"),
            ]
            replacements[1]["standalone_kind"] = "law"
            replacements[1]["standalone_reason"] = "这三行共同给出可独立复用的点线面体运动规律。"
            decisions_path = items["staging"] / "atom-role-decisions.json"
            decisions = self.write_artifact(decisions_path, {
                "schema_version": 1, "kind": "atom-role-decisions",
                "atom_role_jobs_sha256": jobs["artifact_sha256"],
                "reviewer": {"type": "codex-agent", "model": "test"},
                "decisions": [{"atom_id": "final-unit", "action": "replace", "rationale": "The opening is a complete scenario and the remaining lines form a distinct reusable conclusion.", "confidence": 0.99, "replacement_atoms": replacements}],
            })
            final, queue = semantic.finalize_role_review(semantic.load_tagged(items["final_path"], "atomization-final"), jobs, decisions)
            self.assertEqual(queue["unresolved_count"], 0)
            self.assertEqual([atom["category"] for atom in final["atoms"][:2]], ["scenario", "knowledge"])
            self.assertEqual(final["role_review"]["status"], "passed")
            reviewed_path = items["staging"] / "atomization-final.role-reviewed.json"
            reviewed_path.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output_book, output_manifest = root / "role-book", root / "role-staging" / "book-graph.json"
            materialize_book.materialize(items["manifest"], reviewed_path, output_book, output_manifest)
            validation = validate_book_graph.validate_graph(output_manifest, output_book)
            self.assertEqual(validation["status"], "passed", validation["errors"])

    def test_low_confidence_short_knowledge_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.passed(Path(temporary))
            audit = items["audit_jobs"]["audits"][0]
            bad_atoms = [self.atom("bad", [4, 4], "knowledge", "碎片", confidence=0.89), self.atom("rest", [5, 16], "knowledge", "其余内容")]
            boundary_reviews = [{"boundary_id": boundary["boundary_id"], "action": semantic.actual_boundary_action(bad_atoms, boundary), "reason": "Blocking test review.", "confidence": 0.98} for boundary in audit["boundaries"]]
            bad_round2 = self.write_artifact(Path(temporary) / "bad-round2.json", {"schema_version": 1, "kind": "round-2-decisions", "round_2_jobs_sha256": items["audit_jobs"]["artifact_sha256"], "reviewer": {"type": "codex-agent", "model": "current-agent"}, "decisions": [{"audit_id": audit["audit_id"], "packet_sha256": audit["packet_sha256"], "boundary_reviews": boundary_reviews, "atoms": bad_atoms}]})
            final, queue = semantic.finalize_payload(items["jobs"], items["round1"], items["audit_jobs"], bad_round2)
            self.assertEqual(final["status"], "review_required")
            self.assertTrue({"low-confidence", "short-knowledge-not-independent"}.issubset({item["code"] for item in queue["items"]}))

    def test_image_paths_do_not_inflate_normalized_teaching_length(self) -> None:
        hashed_asset = "![](images/" + "a" * 300 + ".jpg)"
        self.assertEqual(semantic.normalized_char_count([hashed_asset, "定义。"]), 3)

    def test_post_knowledge_reflection_is_scenario_semantic_but_stored_as_thought_question(self) -> None:
        lines = ["举例说明，用自然语言、列举法和描述法表示集合时各自的特点."]
        atom = self.atom(
            "reflection", [1, 1], "scenario", "思考：三种集合表示方法的特点",
            scenario_role="reflection-question",
        )
        issues = semantic.quality_issues(atom, lines, semantic.DEFAULT_ATOMIZATION, "test", final=True)
        self.assertEqual(issues, [])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            items = self.passed(root)
            target = next(value for value in items["final"]["atoms"] if value["atom_id"] == "final-exercise")
            target.update({
                "category": "scenario",
                "title": "思考：三种集合表示方法的特点",
                "scenario_role": "reflection-question",
            })
            items["final"] = semantic.seal_artifact({key: value for key, value in items["final"].items() if key != "artifact_sha256"})
            items["final_path"].write_text(json.dumps(items["final"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output_book, output_manifest = root / "thought-book", root / "thought-staging" / "book-graph.json"
            materialize_book.materialize(items["manifest"], items["final_path"], output_book, output_manifest)
            graph = json.loads(output_manifest.read_text(encoding="utf-8"))
            node = next(value for value in graph["nodes"] if value.get("atomization_id") == "final-exercise")
            self.assertEqual(node["category"], "scenario")
            self.assertEqual(node["scenario_role"], "reflection-question")
            self.assertRegex(node["filename"], r"^原子层/思考题/\d{4,}-T\.md$")
            profile = json.loads(items["profile"].read_text(encoding="utf-8"))
            frontmatter = materialize_book.atom_frontmatter(node, {value["key"]: value for value in graph["nodes"]}, "book", profile)
            self.assertIn('scenario_role: "reflection-question"', frontmatter)
            validation = validate_book_graph.validate_graph(output_manifest, output_book)
            self.assertEqual(validation["status"], "passed", validation["errors"])

    def test_short_scenario_requires_a_real_teaching_role(self) -> None:
        bridge = self.atom(
            "bridge", [1, 1], "scenario", "集合表示方式引入",
            scenario_role="knowledge-motivation",
        )
        valid_lines = ["从上面的例子看到，我们可以用自然语言描述一个集合。除此之外，还可以用什么方式表示集合呢？"]
        self.assertEqual(semantic.quality_issues(bridge, valid_lines, semantic.DEFAULT_ATOMIZATION, "test", final=True), [])
        invalid_lines = ["观察并思考。"]
        codes = {
            item["code"] for item in semantic.quality_issues(
                bridge, invalid_lines, semantic.DEFAULT_ATOMIZATION, "test", final=True,
            )
        }
        self.assertIn("knowledge-motivation-not-a-bridge", codes)

    def test_short_section_scope_question_is_a_section_introduction(self) -> None:
        lines = ["我们知道，实数有加、减、乘、除等运算。集合是否也有类似的运算呢？"]
        introduction = self.atom(
            "section-intro", [1, 1], "scenario", "集合运算引入",
            scenario_role="section-introduction",
        )
        self.assertEqual(
            semantic.quality_issues(
                introduction, lines, semantic.DEFAULT_ATOMIZATION, "test", final=True,
            ),
            [],
        )

    def test_section_scope_question_cannot_be_absorbed_into_first_knowledge(self) -> None:
        lines = [
            "我们知道，实数有加、减、乘、除等运算。集合是否也有类似的运算呢？",
            "并集把属于集合 A 或属于集合 B 的所有元素组成一个新的集合；这里继续给出符号、条件、图示、辨析和完整结论，使它成为一个可独立复用的教学单元。",
        ]
        knowledge = self.atom("union", [1, 2], "knowledge", "并集")
        codes = {
            item["code"] for item in semantic.quality_issues(
                knowledge, lines, semantic.DEFAULT_ATOMIZATION, "test", final=True,
            )
        }
        self.assertIn("section-introduction-absorbed-into-knowledge", codes)

    def test_scoped_chapter_introduction_is_one_complete_atom(self) -> None:
        lines = [
            "周期现象广泛存在。", "函数可以描述变化规律。",
            "本章将研究三角函数。", "![章导图](chapter.png)",
        ]
        fragments = [
            self.atom("s1", [1, 1], "scenario", "第五章导语", scenario_role="chapter-introduction"),
            self.atom("s2", [2, 2], "scenario", "第五章导语 续 2", scenario_role="chapter-introduction"),
            self.atom("s3", [3, 3], "scenario", "第五章导语 续 3", scenario_role="chapter-introduction"),
            self.atom("s4", [4, 4], "scenario", "第五章导图", scenario_role="chapter-introduction"),
        ]
        for atom in fragments:
            atom["owner_key"] = "chapter-5"
        codes = {item["code"] for item in semantic.scoped_scenario_issues(fragments, lines)}
        self.assertIn("scoped-introduction-fragmented", codes)
        self.assertIn("scoped-introduction-continuation-title", codes)
        self.assertIn("scoped-introduction-media-only-fragment", codes)
        combined = self.atom(
            "chapter-intro", [1, 4], "scenario", "第五章导语",
            scenario_role="chapter-introduction",
        )
        combined["owner_key"] = "chapter-5"
        self.assertEqual(semantic.scoped_scenario_issues([combined], lines), [])

    def test_book_introduction_is_a_supported_scenario_role(self) -> None:
        atom = self.atom(
            "preface", [1, 1], "scenario", "读者导读",
            scenario_role="book-introduction",
        )
        errors: list[dict[str, Any]] = []
        semantic.validate_atom(atom, "preface", "lesson", ["本书将帮助读者建立完整知识结构。"], errors)
        self.assertEqual(errors, [])

    def test_materialized_book_introduction_precedes_chapter_organizers(self) -> None:
        base = {
            "nodes": [
                {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
                {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/Chapter/Chapter.md", "heading_ranges": [[4, 4]], "children": ["draft"]},
                {"key": "draft", "title": "Draft", "layer": "atom", "parent_key": "chapter", "category": "knowledge", "filename": "_draft/draft.md", "source_range": [5, 5]},
            ]
        }
        final = {
            "scope_root_keys": ["chapter"],
            "atoms": [
                self.atom("preface", [2, 3], "scenario", "读者导读", scenario_role="book-introduction"),
                self.atom("chapter-knowledge", [5, 5], "knowledge", "Chapter knowledge", standalone_kind="formal-definition", standalone_reason="Complete reusable definition."),
            ],
        }
        final["atoms"][0]["owner_key"] = "book"
        final["atoms"][1]["owner_key"] = "chapter"
        output_nodes, _root = materialize_book.prepare_nodes(base, final)
        by_key = {node["key"]: node for node in output_nodes}
        self.assertEqual(by_key["book"]["children"][0], materialize_book.final_key(final["atoms"][0]))
        self.assertEqual(by_key["book"]["children"][1], "chapter")

    def test_category_aware_prepare_requires_organizer_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = self.make_base(Path(temporary))
            profile = json.loads(base["profile"].read_text(encoding="utf-8"))
            profile["atomization"] = dict(semantic.DEFAULT_ATOMIZATION)
            base["profile"].write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(semantic.AtomizationError, "organizer review"):
                semantic.prepare_jobs(base["manifest"], ["chapter"])

    def test_prepare_splits_one_owner_at_its_retained_printed_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text(
                "# Book\n## Chapter\n圆周运动如何刻画位置变化？\n### 5.1.1 任意角\n角可以记录旋转的方向与大小。\n",
                encoding="utf-8",
            )
            staging, book = root / "staging", root / "book"
            staging.mkdir()
            profile = init_book.create_profile(source, staging, book)
            profile["atomization"]["mode"] = "llm-two-pass"
            profile["atomization"].pop("teaching_role_audit", None)
            profile_path = staging / "book-profile.json"
            profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            nodes = [
                {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
                {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/Chapter/Chapter.md", "heading_ranges": [[2, 2]], "children": ["angle"]},
                {"key": "angle", "title": "5.1.1 任意角", "layer": "organizer", "parent_key": "chapter", "organizer_level": 3, "filename": "组织层/Book/Chapter/Angle.md", "heading_ranges": [[4, 4]], "children": ["motivation", "knowledge"]},
                {"key": "motivation", "title": "圆周运动问题", "layer": "atom", "parent_key": "angle", "category": "scenario", "filename": "_draft/motivation.md", "source_range": [3, 3]},
                {"key": "knowledge", "title": "任意角", "layer": "atom", "parent_key": "angle", "category": "knowledge", "filename": "_draft/knowledge.md", "source_range": [5, 5]},
            ]
            manifest = {
                "schema_version": 1, "profile": str(profile_path),
                "source_markdown": str(source), "source_markdown_sha256": semantic.sha256_file(source),
                "nodes": nodes, "source_order": ["motivation", "knowledge"], "relations": [],
            }
            manifest_path = staging / "book-graph.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            jobs = semantic.prepare_jobs(manifest_path, ["chapter"])
            angle_jobs = [job for job in jobs["jobs"] if job["owner_key"] == "angle"]
            self.assertEqual([job["source_range"] for job in angle_jobs], [[3, 3], [5, 5]])
            self.assertEqual(len({job["run_id"] for job in angle_jobs}), 2)

    def test_printed_instructional_section_cannot_contain_only_exercises(self) -> None:
        nodes = {
            "angle": {"key": "angle", "title": "5.1.1 任意角", "layer": "organizer", "heading_ranges": [[10, 10]], "children": ["practice"]},
            "practice": {"key": "practice", "title": "练习 1", "layer": "organizer", "parent_key": "angle", "heading_ranges": [[20, 20]], "children": ["e"]},
            "e": {"key": "e", "layer": "atom", "parent_key": "practice", "category": "exercise"},
        }
        issues = validate_book_graph.validate_instructional_organizer_content(nodes)
        self.assertIn("instructional-organizer-exercise-only", {item["code"] for item in issues})
        self.assertEqual(
            validate_book_graph.validate_instructional_organizer_content({"practice": nodes["practice"], "e": nodes["e"]}),
            [],
        )

    def test_section_introduction_must_be_first_before_topic_organizers(self) -> None:
        nodes = {
            "section": {"key": "section", "layer": "organizer", "children": ["union", "intro", "exercise"]},
            "union": {"key": "union", "layer": "organizer", "parent_key": "section", "children": ["knowledge"]},
            "intro": {"key": "intro", "layer": "atom", "parent_key": "section", "category": "scenario", "scenario_role": "section-introduction"},
            "exercise": {"key": "exercise", "layer": "organizer", "parent_key": "section", "children": ["problem"]},
            "knowledge": {"key": "knowledge", "layer": "atom", "parent_key": "union", "category": "knowledge"},
            "problem": {"key": "problem", "layer": "atom", "parent_key": "exercise", "category": "exercise"},
        }
        codes = {
            item["code"] for item in validate_book_graph.validate_section_introduction_placement(nodes)
        }
        self.assertIn("section-introduction-order-invalid", codes)
        nodes["section"]["children"] = ["intro", "union", "exercise"]
        self.assertEqual(validate_book_graph.validate_section_introduction_placement(nodes), [])

    def test_definition_card_prefers_the_defining_sentence_over_preceding_examples(self) -> None:
        lines = [
            "四大洋组成的集合可以表示为若干元素。",
            "把集合的所有元素一一列举并用花括号括起来的方法叫做列举法。",
        ]
        selected = materialize_book.definition_evidence_range([1, 2], lines, [1, 2])
        self.assertEqual(selected, [2, 2])
        self.assertEqual(materialize_book.render_definition_source(lines, selected), lines[1] + "\n")

    def test_materialization_and_review_binding_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            items = self.passed(root)
            output_book, output_manifest = root / "output-book", root / "output-staging" / "book-graph.json"
            report = materialize_book.materialize(items["manifest"], items["final_path"], output_book, output_manifest)
            self.assertEqual(report["status"], "passed")
            graph = json.loads(output_manifest.read_text(encoding="utf-8"))
            first = next(node for node in graph["nodes"] if node.get("atomization_id") == "final-unit")
            body = (output_book / first["filename"]).read_text(encoding="utf-8")
            source_lines = items["source"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(body, "\n".join(source_lines[3:8]) + "\n")
            category_codes = {"knowledge": "K", "worked-example": "W", "exercise": "E", "scenario": "S"}
            for atom in (node for node in graph["nodes"] if node.get("layer") == "atom"):
                self.assertRegex(Path(atom["filename"]).name, rf"^\d{{4,}}-{category_codes[atom['category']]}\.md$")
                self.assertNotIn(atom["title"], Path(atom["filename"]).name)
            by_key = {node["key"]: node for node in graph["nodes"]}
            lesson = by_key["lesson"]
            chapter = by_key["chapter"]
            book = by_key["book"]
            self.assertEqual(lesson["filename"], "组织层/Book/第一章/第一节.md")
            self.assertFalse((output_book / "组织层/Book/第一章/第一节").exists())
            self.assertIn("# 第一章\n\n![第一章]", (output_book / book["filename"]).read_text(encoding="utf-8"))
            self.assertIn("## 第一节\n\n![第一节]", (output_book / chapter["filename"]).read_text(encoding="utf-8"))
            lesson_body = (output_book / lesson["filename"]).read_text(encoding="utf-8")
            lesson_content = "\n".join(validate_book_graph.strip_frontmatter(lesson_body))
            self.assertNotRegex(lesson_content, r"(?m)^#{1,6}(?:\s+|$)")
            self.assertTrue(lesson_content.lstrip().startswith("!["))
            for organizer in (book, chapter, lesson):
                text = (output_book / organizer["filename"]).read_text(encoding="utf-8")
                properties = validate_book_graph.frontmatter_keys(text)
                self.assertTrue({
                    "organizer_key", "parent_organizer_key", "source_pdf",
                    "organizer_level", "hierarchy_path", "children_count",
                    "descendant_atom_count", "updated_at", "review_status",
                }.issubset(properties))
                self.assertEqual(
                    validate_book_graph.frontmatter_scalar(text, "organizer_key"),
                    organizer["key"],
                )
                self.assertEqual(
                    validate_book_graph.frontmatter_scalar(text, "organizer_level"),
                    organizer["organizer_level"],
                )
            root_text = (output_book / book["filename"]).read_text(encoding="utf-8")
            self.assertIsNone(validate_book_graph.frontmatter_scalar(root_text, "parent_organizer_key"))
            self.assertEqual(validate_book_graph.frontmatter_scalar(root_text, "organizer_role"), "root")
            validation = validate_book_graph.validate_graph(output_manifest, output_book)
            self.assertEqual(validation["status"], "passed", validation["errors"])

            broken = (output_book / chapter["filename"]).read_text(encoding="utf-8").replace(
                f"organizer_level: {chapter['organizer_level']}\n", "", 1,
            )
            (output_book / chapter["filename"]).write_text(broken, encoding="utf-8")
            invalid = validate_book_graph.validate_graph(output_manifest, output_book)
            self.assertIn("organizer-metadata-missing", {item["code"] for item in invalid["errors"]})

    def test_materialization_escapes_special_characters_in_link_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            items = self.passed(root)
            items["final"]["atoms"][0]["title"] = "例题, [分组] 与 \\ 符号"
            items["final"] = semantic.seal_artifact({key: value for key, value in items["final"].items() if key != "artifact_sha256"})
            items["final_path"].write_text(json.dumps(items["final"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output_book = root / "special-output"
            output_manifest = root / "special-staging" / "book-graph.json"
            materialize_book.materialize(items["manifest"], items["final_path"], output_book, output_manifest)
            validation = validate_book_graph.validate_graph(output_manifest, output_book)
            self.assertEqual(validation["status"], "passed", validation["errors"])
            organizer = next(node for node in json.loads(output_manifest.read_text(encoding="utf-8"))["nodes"] if node.get("layer") == "organizer" and node.get("parent_key") == "book")
            organizer_body = (output_book / organizer["filename"]).read_text(encoding="utf-8")
            self.assertNotIn("%2C", organizer_body)

    def test_stale_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.passed(Path(temporary))
            items["source"].write_text("changed\n", encoding="utf-8")
            report = semantic.validate_round1_payload(items["jobs"], items["round1"])
            self.assertEqual(report["status"], "failed")
            self.assertIn("source-markdown-digest-mismatch", {item["code"] for item in report["structural_errors"]})

    def test_external_runner_requires_execute_and_uses_structured_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.make_base(root)
            jobs = semantic.prepare_jobs(base["manifest"], ["chapter"])
            jobs_path = root / "jobs.json"
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(run_atomization_model.ModelRunnerError):
                run_atomization_model.run_packets(jobs_path, root / "none.json", 1, "test-model", "secret", False)
            captured: dict[str, Any] = {}
            def transport(request: Any, timeout: float) -> bytes:
                captured.update(json.loads(request.data.decode("utf-8")))
                packet = jobs["jobs"][0]
                decision = {"job_id": packet["job_id"], "packet_sha256": packet["packet_sha256"], "atoms": [self.atom("api", packet["source_range"], "knowledge", "完整单元")]}
                return json.dumps({"status": "completed", "output": [{"content": [{"type": "output_text", "text": json.dumps(decision, ensure_ascii=False)}]}]}).encode()
            report = run_atomization_model.run_packets(jobs_path, root / "api.json", 1, "test-model", "secret", True, transport=transport)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(captured["text"]["format"]["type"], "json_schema")
            self.assertNotIn("secret", json.dumps(captured))


if __name__ == "__main__":
    unittest.main()

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

    def test_example_solution_and_exercise_subparts_remain_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.passed(Path(temporary))
            by_category = {atom["category"]: atom for atom in items["final"]["atoms"]}
            self.assertEqual(by_category["worked-example"]["source_range"], [10, 13])
            self.assertEqual(by_category["exercise"]["source_range"], [14, 16])

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
            self.assertNotRegex(lesson_body, r"(?m)^#{1,6}(?:\s+|$)")
            self.assertTrue(lesson_body.startswith("!["))
            validation = validate_book_graph.validate_graph(output_manifest, output_book)
            self.assertEqual(validation["status"], "passed", validation["errors"])

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

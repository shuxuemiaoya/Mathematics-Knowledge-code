from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
BOOK_SCRIPTS = Path(__file__).resolve().parents[2] / "book-to-wiki-graph" / "scripts"
sys.path.insert(0, str(BOOK_SCRIPTS))

import export_neo4j
import knowledge_relations as kr
import run_embeddings
import run_relation_model
import sync_neo4j
import build_canvas


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class KnowledgeRelationMapperTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, dict]:
        source = root / "source.md"
        source.write_text("点表示位置。\n已有的点引发对连线的思考。\n线由点运动形成并表示路径。\n例题用连线方法解决路线问题。\n练习一：画出两点之间的线。\n", encoding="utf-8")
        profile = root / "book-profile.json"
        profile.write_text(json.dumps({"relation_analysis": kr.DEFAULT_CONFIG}, ensure_ascii=False), encoding="utf-8")
        nodes = [
            {"key": "root", "layer": "organizer", "title": "数学", "parent_key": None, "children": ["chapter"], "heading_ranges": [[1, 1]], "filename": "组织层/数学.md"},
            {"key": "chapter", "layer": "organizer", "title": "第一章", "parent_key": "root", "children": ["section"], "heading_ranges": [[1, 1]], "filename": "组织层/第一章.md"},
            {"key": "section", "layer": "organizer", "title": "点与线", "parent_key": "chapter", "children": ["k1", "s1", "k2", "w1", "e1"], "heading_ranges": [[1, 1]], "filename": "组织层/点与线.md"},
            {"key": "k1", "layer": "atom", "category": "knowledge", "title": "点", "parent_key": "section", "children": [], "source_range": [1, 1], "filename": "原子层/知识点/0001-K.md"},
            {"key": "s1", "layer": "atom", "category": "scenario", "title": "由点思考连线", "parent_key": "section", "children": [], "source_range": [2, 2], "filename": "原子层/情景引入/0002-S.md"},
            {"key": "k2", "layer": "atom", "category": "knowledge", "title": "线", "parent_key": "section", "children": [], "source_range": [3, 3], "filename": "原子层/知识点/0003-K.md"},
            {"key": "w1", "layer": "atom", "category": "worked-example", "title": "连线方法", "parent_key": "section", "children": [], "source_range": [4, 4], "filename": "原子层/例题/0004-W.md"},
            {"key": "e1", "layer": "atom", "category": "exercise", "title": "画线练习", "parent_key": "section", "children": [], "source_range": [5, 5], "filename": "原子层/习题/0005-E.md"},
        ]
        manifest = root / "book-graph.json"
        payload = {"profile": str(profile), "source_markdown": str(source), "source_markdown_sha256": digest(source), "book_title": "数学", "nodes": nodes, "relations": []}
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return manifest, payload

    def round1(self, jobs: dict) -> dict:
        job = jobs["jobs"][0]
        atoms = {item["atom_key"]: item for item in job["atoms"]}
        decisions = [{
            "job_id": job["job_id"], "packet_sha256": job["packet_sha256"],
            "concepts": [
                {"proposal_id": "p-point", "preferred_label": "点", "aliases": ["几何点"], "definition": "表示位置而不计大小的几何对象。", "kind": "concept", "evidence": [{"atom_key": "k1", "source_range": atoms["k1"]["source_range"]}]},
                {"proposal_id": "p-line", "preferred_label": "线", "aliases": ["几何线"], "definition": "由点运动形成并可表示路径的几何对象。", "kind": "concept", "evidence": [{"atom_key": "k2", "source_range": atoms["k2"]["source_range"]}]},
            ],
            "atom_concept_links": [
                {"atom_key": "k1", "concept_ref": "p-point", "role": "introduces", "evidence_ranges": [atoms["k1"]["source_range"]], "confidence": 0.99},
                {"atom_key": "s1", "concept_ref": "p-point", "role": "triggered_by", "evidence_ranges": [atoms["s1"]["source_range"]], "confidence": 0.99},
                {"atom_key": "s1", "concept_ref": "p-line", "role": "motivates", "evidence_ranges": [atoms["s1"]["source_range"]], "confidence": 0.99},
                {"atom_key": "k2", "concept_ref": "p-line", "role": "introduces", "evidence_ranges": [atoms["k2"]["source_range"]], "confidence": 0.99},
                {"atom_key": "w1", "concept_ref": "p-line", "role": "applies", "evidence_ranges": [atoms["w1"]["source_range"]], "confidence": 0.99},
                {"atom_key": "e1", "concept_ref": "p-line", "role": "practices", "evidence_ranges": [atoms["e1"]["source_range"]], "confidence": 0.99},
            ],
            "atom_roles": [
                {"atom_key": "k1", "role": "core", "rationale": "首次建立点的基本概念。"},
                {"atom_key": "s1", "role": "core", "rationale": "承接旧知并提出连线问题。"},
                {"atom_key": "k2", "role": "core", "rationale": "首次建立线的基本概念。"},
                {"atom_key": "w1", "role": "bridge", "rationale": "展示可复用的连线路线方法。"},
                {"atom_key": "e1", "role": "satellite", "rationale": "用于练习已经建立的线概念。"},
            ],
        }]
        return kr.seal_artifact({"schema_version": 2, "kind": "round-1-concepts", "concept_jobs_sha256": jobs["artifact_sha256"], "reviewer": {"type": "agent", "model": "test"}, "decisions": decisions})

    @staticmethod
    def candidate(jobs: dict, kind: str, left: str, right: str) -> dict:
        for job in jobs["jobs"]:
            for item in job["candidates"]:
                if item["kind"] == kind and {item["left_key"], item["right_key"]} == {left, right}:
                    return item
        raise AssertionError(f"candidate not found: {kind} {left} {right}")

    def round2(self, jobs: dict) -> tuple[dict, list[dict], list[dict]]:
        concept_candidate = self.candidate(jobs, "concept-relation", "p-point", "p-line")
        pairs = [("k1", "s1", "motivates", "backbone"), ("s1", "k2", "motivates", "backbone"), ("k2", "w1", "illustrates", "supporting"), ("k2", "e1", "practices", "supporting")]
        atoms = {item["atom_key"]: item for item in jobs["atoms"]}
        relations = []
        for left, right, relation_type, tier in pairs:
            candidate = self.candidate(jobs, "atom-relation", left, right)
            relations.append({"candidate_id": candidate["candidate_id"], "from_key": left, "to_key": right, "type": relation_type, "tier": tier, "evidence_kind": "pedagogical-inference", "evidence": [{"atom_key": left, "source_range": atoms[left]["source_range"]}, {"atom_key": right, "source_range": atoms[right]["source_range"]}], "rationale": "两端正文共同表明明确的教学推进关系。", "confidence": 0.99, "basis_candidate_ids": [concept_candidate["candidate_id"]] if (left, right) == ("s1", "k2") else []})
        concept_relations = [{"candidate_id": concept_candidate["candidate_id"], "from_ref": "p-point", "to_ref": "p-line", "type": "develops", "tier": "backbone", "evidence_kind": "pedagogical-inference", "evidence": [{"atom_key": "k1", "source_range": atoms["k1"]["source_range"]}, {"atom_key": "k2", "source_range": atoms["k2"]["source_range"]}], "rationale": "点作为基础对象进一步发展出线的形成认识。", "confidence": 0.99}]
        decisions = []
        for job in jobs["jobs"]:
            merge_decisions = [{"candidate_id": item["candidate_id"], "action": "keep-separate", "confidence": 0.99, "rationale": "定义不同且承担不同数学对象角色。"} for item in job["candidates"] if item["kind"] == "concept-merge"]
            candidate_ids = {item["candidate_id"] for item in job["candidates"]}
            decisions.append({"job_id": job["job_id"], "packet_sha256": job["packet_sha256"], "reviewed_candidate_ids": sorted(candidate_ids), "merge_decisions": merge_decisions, "concept_relations": [item for item in concept_relations if item["candidate_id"] in candidate_ids], "relations": [item for item in relations if item["candidate_id"] in candidate_ids]})
        payload = kr.seal_artifact({"schema_version": 2, "kind": "round-2-relations-v2", "relation_jobs_sha256": jobs["artifact_sha256"], "reviewer": {"type": "agent", "model": "test"}, "decisions": decisions})
        return payload, concept_relations, relations

    def test_three_pass_pipeline_maps_scenario_method_and_exercise(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, _ = self.fixture(Path(temporary))
            concept_jobs = kr.prepare_concept_jobs(manifest)
            round1 = self.round1(concept_jobs)
            self.assertEqual(kr.validate_concept_payload(concept_jobs, round1)["status"], "passed")
            relation_jobs = kr.prepare_relation_jobs(concept_jobs, round1)
            channels = {channel for job in relation_jobs["jobs"] for item in job["candidates"] for channel in item["channels"]}
            self.assertTrue({"source-window", "organizer-neighborhood", "teaches-assumes", "shared-concept", "lexical-atom"}.issubset(channels))
            round2, concept_relations, relations = self.round2(relation_jobs)
            self.assertEqual(kr.validate_round2_payload(relation_jobs, round2)["status"], "passed")
            audit_jobs = kr.prepare_audit_jobs(relation_jobs, round2)
            audit = audit_jobs["audits"][0]
            report1 = kr.validate_concept_payload(concept_jobs, round1)
            final_concepts = [{"member_proposal_ids": [item["proposal_id"]], "preferred_label": item["preferred_label"], "aliases": item["aliases"], "definition": item["definition"], "kind": item["kind"]} for item in report1["concepts"]]
            round3 = kr.seal_artifact({"schema_version": 2, "kind": "round-3-audit", "graph_audit_jobs_sha256": audit_jobs["artifact_sha256"], "reviewer": {"type": "agent", "model": "test"}, "decisions": [{"audit_id": audit["audit_id"], "packet_sha256": audit["packet_sha256"], "reviewed_issue_ids": [item["issue_id"] for item in audit["issues"]], "concepts": final_concepts, "atom_concept_links": report1["atom_concept_links"], "concept_relations": concept_relations, "relations": relations, "independent_atoms": [], "independent_components": []}]})
            final, queue, quality, review = kr.finalize_relations(concept_jobs, round1, relation_jobs, round2, audit_jobs, round3)
            self.assertEqual(final["status"], "passed", queue["items"])
            self.assertEqual(final["unresolved_count"], 0)
            self.assertEqual(len(final["concepts"]), 2)
            self.assertIn("未解决项：0", review)
            self.assertEqual(quality["counts"]["components"], 1)

    def test_activity_title_and_low_merge_confidence_enter_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, _ = self.fixture(Path(temporary))
            jobs = kr.prepare_concept_jobs(manifest)
            round1 = self.round1(jobs)
            round1["decisions"][0]["concepts"][0]["preferred_label"] = "观察·思考"
            round1 = kr.seal_artifact({key: value for key, value in round1.items() if key != "artifact_sha256"})
            report = kr.validate_concept_payload(jobs, round1)
            self.assertEqual(report["status"], "review_required")
            self.assertIn("concept-label-is-activity", {item["code"] for item in report["review_items"]})

    def test_embedding_artifact_is_optional_bound_and_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = self.fixture(root)
            jobs = kr.prepare_concept_jobs(manifest)
            round1 = self.round1(jobs)
            embedding = kr.seal_artifact({"schema_version": 1, "kind": "relation-embeddings", "concept_jobs_sha256": jobs["artifact_sha256"], "round_1_concepts_sha256": round1["artifact_sha256"], "model": "mock", "vectors": {"k1": [1.0, 0.0], "k2": [0.99, 0.01], "p-point": [1.0, 0.0], "p-line": [0.99, 0.01]}})
            path = root / "embeddings.json"
            path.write_text(json.dumps(embedding), encoding="utf-8")
            relation_jobs = kr.prepare_relation_jobs(jobs, round1, path)
            channels = {channel for job in relation_jobs["jobs"] for item in job["candidates"] for channel in item["channels"]}
            self.assertIn("embedding-atom", channels)
            self.assertIn("embedding-concept", channels)
            embedding["round_1_concepts_sha256"] = "stale"
            embedding = kr.seal_artifact({key: value for key, value in embedding.items() if key != "artifact_sha256"})
            path.write_text(json.dumps(embedding), encoding="utf-8")
            with self.assertRaises(kr.RelationV2Error):
                kr.prepare_relation_jobs(jobs, round1, path)

    def test_external_model_and_embedding_calls_require_execute(self) -> None:
        with self.assertRaises(run_relation_model.RelationModelError):
            run_relation_model.run_packets(Path("x"), Path("y"), "concepts", "model", "key", False)
        with self.assertRaises(run_embeddings.EmbeddingError):
            run_embeddings.run_embeddings(Path("x"), Path("y"), Path("z"), "model", "key", False)

    def test_external_requests_use_explicit_model_and_structured_schema(self) -> None:
        packet = {"job_id": "j1", "packet_sha256": "digest"}
        decision = {"job_id": "j1", "packet_sha256": "digest", "concepts": [], "atom_concept_links": [], "atom_roles": []}
        seen: dict = {}
        def response_transport(request, timeout):
            seen.update(json.loads(request.data.decode("utf-8")))
            return json.dumps({"status": "completed", "output_text": json.dumps(decision)}).encode("utf-8")
        self.assertEqual(run_relation_model.request_packet(packet, "concepts", "explicit-model", "secret", 1, response_transport), decision)
        self.assertEqual(seen["model"], "explicit-model")
        self.assertFalse(seen["store"])
        self.assertEqual(seen["text"]["format"]["type"], "json_schema")
        embedding_seen: dict = {}
        def embedding_transport(request, timeout):
            embedding_seen.update(json.loads(request.data.decode("utf-8")))
            return json.dumps({"data": [{"index": 0, "embedding": [1.0, 0.0]}]}).encode("utf-8")
        self.assertEqual(run_embeddings.request_embeddings(["点"], "embedding-model", "secret", 1, embedding_transport), [[1.0, 0.0]])
        self.assertEqual(embedding_seen["model"], "embedding-model")

    def test_graph_audit_detects_cycle_redundancy_backward_and_components(self) -> None:
        atoms = {
            "a1": {"category": "knowledge", "source_range": [1, 1]},
            "a2": {"category": "knowledge", "source_range": [2, 2]},
            "a3": {"category": "knowledge", "source_range": [3, 3]},
            "a4": {"category": "knowledge", "source_range": [4, 4]},
        }
        concepts = [{"key": f"c{i}", "first_source_order": i} for i in range(1, 5)]
        links = [{"atom_key": f"a{i}", "concept_key": f"c{i}", "role": "introduces"} for i in range(1, 5)]
        relations = [
            {"key": "r12", "from_key": "c1", "to_key": "c2", "type": "develops", "tier": "backbone", "evidence_kind": "pedagogical-inference"},
            {"key": "r23", "from_key": "c2", "to_key": "c3", "type": "develops", "tier": "backbone", "evidence_kind": "pedagogical-inference"},
            {"key": "r13", "from_key": "c1", "to_key": "c3", "type": "prerequisite", "tier": "backbone", "evidence_kind": "pedagogical-inference"},
            {"key": "r31", "from_key": "c3", "to_key": "c1", "type": "develops", "tier": "backbone", "evidence_kind": "pedagogical-inference"},
        ]
        issues, wcc = kr.graph_issues({"concepts": concepts, "atom_concept_links": links, "concept_relations": relations, "relations": []}, atoms)
        codes = {item["code"] for item in issues}
        self.assertTrue({"concept-backbone-cycle", "concept-transitive-redundancy", "backward-learning-relation", "non-main-concept-component"}.issubset(codes))
        self.assertEqual(sorted(map(len, wcc)), [1, 3])

    def test_neo4j_export_is_deterministic_and_sync_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, graph = self.fixture(root)
            graph["concepts"] = [{"key": "c1", "preferred_label": "点", "aliases": [], "definition": "表示位置而没有大小的对象。", "kind": "concept", "first_source_order": 1}]
            graph["atom_concept_links"] = [{"key": "l1", "atom_key": "k1", "concept_key": "c1", "role": "introduces", "confidence": 0.99, "evidence_ranges": [[1, 1]]}]
            graph["concept_relations"] = []
            graph["relation_review"] = {"status": "passed", "graph_model": "atom-concept-dual-layer"}
            manifest_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
            first, second = root / "a", root / "b"
            export_neo4j.export_bundle(manifest_path, first)
            export_neo4j.export_bundle(manifest_path, second)
            for name in ("nodes.jsonl", "relationships.jsonl", "constraints.cypher", "import.cypher"):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            called = False
            def factory(uri: str, auth: tuple[str, str]):
                nonlocal called
                called = True
                raise AssertionError
            with self.assertRaises(sync_neo4j.Neo4jSyncError):
                sync_neo4j.sync_bundle(first / "graph-export.json", "bolt://test", "neo4j", "secret", "neo4j", False, driver_factory=factory)
            self.assertFalse(called)
            class Result(list):
                def consume(self):
                    return self
            class Session:
                def __init__(self):
                    self.queries = []
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def run(self, query, **parameters):
                    self.queries.append((query, parameters))
                    if "gds.wcc.stream" in query:
                        return Result([{"key": "c1", "componentId": 0}])
                    if "gds.leiden.stream" in query:
                        return Result([{"key": "c1", "communityId": 0}])
                    return Result()
            class Driver:
                def __init__(self): self.active = Session(); self.closed = False
                def verify_connectivity(self): return None
                def session(self, database): return self.active
                def close(self): self.closed = True
            driver = Driver()
            synced = sync_neo4j.sync_bundle(first / "graph-export.json", "bolt://test", "neo4j", "secret", "neo4j", True, run_gds=True, driver_factory=lambda uri, auth: driver)
            self.assertEqual(synced["analysis"]["status"], "wcc-and-leiden")
            self.assertTrue(driver.closed)

    def test_canvas_selective_concept_hubs_replace_grounded_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, graph = self.fixture(root)
            for node in graph["nodes"]:
                target = root / node["filename"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("内容\n", encoding="utf-8")
            graph["relation_review"] = {"status": "passed", "unresolved_count": 0, "mode": "llm-three-pass", "graph_model": "atom-concept-dual-layer", "featured_example_keys": ["w1"]}
            graph["concepts"] = [
                {"key": "c-point", "preferred_label": "点", "aliases": [], "definition": "表示位置而不计大小的几何对象。", "kind": "concept", "first_source_order": 1},
                {"key": "c-line", "preferred_label": "线", "aliases": [], "definition": "由点运动形成并表示路径的几何对象。", "kind": "concept", "first_source_order": 3},
            ]
            graph["atom_concept_links"] = [
                {"key": "l1", "atom_key": "k1", "concept_key": "c-point", "role": "introduces"},
                {"key": "l2", "atom_key": "s1", "concept_key": "c-point", "role": "triggered_by"},
                {"key": "l3", "atom_key": "s1", "concept_key": "c-line", "role": "motivates"},
                {"key": "l4", "atom_key": "k2", "concept_key": "c-line", "role": "introduces"},
                {"key": "l5", "atom_key": "w1", "concept_key": "c-line", "role": "applies"},
                {"key": "l6", "atom_key": "e1", "concept_key": "c-line", "role": "practices"},
            ]
            graph["concept_relations"] = [{"key": "cr1", "from_key": "c-point", "to_key": "c-line", "type": "develops", "tier": "backbone"}]
            graph["relations"] = [
                {"key": "r1", "from_key": "k1", "to_key": "s1", "type": "motivates", "tier": "backbone", "basis_keys": []},
                {"key": "r2", "from_key": "s1", "to_key": "k2", "type": "develops", "tier": "backbone", "basis_keys": ["cr1"]},
                {"key": "r3", "from_key": "k2", "to_key": "w1", "type": "illustrates", "tier": "supporting", "basis_keys": []},
                {"key": "r4", "from_key": "k2", "to_key": "e1", "type": "practices", "tier": "supporting", "basis_keys": []},
            ]
            manifest_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
            builder = build_canvas.CanvasBundleBuilder(graph, manifest_path, root, root / "Canvas")
            payloads, index = builder.build()
            chapter_path = next(path for path in payloads if path.parent.name == "chapters")
            canvas = payloads[chapter_path]
            ids = {node["id"] for node in canvas["nodes"]}
            self.assertIn(build_canvas.stable_id("concept", "c-point"), ids)
            self.assertIn(build_canvas.stable_id("concept", "c-line"), ids)
            projected_id = build_canvas.stable_id("edge", "chapter:relation:r2")
            self.assertNotIn(projected_id, {edge["id"] for edge in canvas["edges"]})
            concept_edge = next(edge for edge in canvas["edges"] if edge.get("label") == "主线 · 发展" and edge["fromNode"] == build_canvas.stable_id("concept", "c-point"))
            self.assertEqual((concept_edge["fromSide"], concept_edge["toSide"]), ("right", "left"))
            self.assertEqual(index["chapter_maps"][0]["counts"]["concept_hubs"], 2)
            incident = {str(endpoint) for edge in canvas["edges"] for endpoint in (edge["fromNode"], edge["toNode"])}
            self.assertTrue({build_canvas.stable_id("concept", "c-point"), build_canvas.stable_id("concept", "c-line")}.issubset(incident))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_mathmap import audit, full_paths
from bootstrap_registry import bootstrap
from link_to_mathmap import LinkPlan, archive_and_link_mathmap, discover_source_assets, render_kp_mount
from mathmap_registry import UNLINKED_QUESTION_TYPES_DIR, RegistryStore, sha256_bytes
from update_canvas_additive import update_canvas


class LinkerWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.vault = self.root / "vault"
        self.source = self.root / "book"
        for relative in (
            "mathmap/习题/questions",
            "mathmap/习题/answers",
            "mathmap/习题/题型整理",
            "mathmap/习题/题集",
            "mathmap/公式结论/公式合集",
            "mathmap/公式结论/公式整理",
            "mathmap/公式结论/独立公式",
            "mathmap/知识点",
        ):
            (self.vault / relative).mkdir(parents=True, exist_ok=True)
        self.source.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, root: Path, relative: str, content: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_nested_answers_are_never_classified_as_questions(self) -> None:
        self.write(self.source, "1.1_集合的概念/questions/Q00000001.md", "# 题目\n\n1+1=?")
        self.write(
            self.source,
            "1.1_集合的概念/questions/answers/Q00000001A1.md",
            "# 解析\n\n2",
        )
        assets = discover_source_assets(self.source, "测试书")
        by_path = {asset.relative: asset.node_type for asset in assets}
        self.assertEqual(by_path["1.1_集合的概念/questions/Q00000001.md"], "questions")
        self.assertEqual(
            by_path["1.1_集合的概念/questions/answers/Q00000001A1.md"],
            "answers",
        )

    def test_formula_extraction_is_virtual_during_discovery(self) -> None:
        self.write(
            self.source,
            "第一节 任意角与弧度制/讲义.md",
            "# 第一节 任意角与弧度制\n\n## 知识导学\n\n"
            "## 一. 任意角\n\n## 1. 角的相关概念\n角可以旋转形成。\n",
        )
        assets = discover_source_assets(self.source, "测试书")
        generated = [asset for asset in assets if asset.identity.startswith("generated-formula:")]
        self.assertEqual({asset.node_type for asset in generated}, {"独立公式", "公式整理", "公式合集"})
        self.assertFalse((self.vault / "mathmap/公式结论/独立公式/角的相关概念.md").exists())

    def test_bootstrap_is_read_only_until_write_flag(self) -> None:
        self.write(self.vault, "mathmap/习题/questions/Q00000001.md", "# 题目\n\n1+1=?")
        self.write(self.vault, "mathmap/知识点/集合的概念.md", "# 集合的概念\n\n# 题型\n")
        report = bootstrap(self.vault, write_registry=False)
        self.assertEqual(report["mode"], "read-only")
        self.assertFalse((self.vault / "question-qid-registry.json").exists())
        self.assertFalse((self.vault / ".mathmap-linker/provenance-manifest.json").exists())

        bootstrap(self.vault, write_registry=True)
        self.assertTrue((self.vault / "question-qid-registry.json").is_file())
        provenance = json.loads(
            (self.vault / ".mathmap-linker/provenance-manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("mathmap/知识点/集合的概念.md", provenance["files"])

    def test_dry_run_apply_and_rerun_are_idempotent(self) -> None:
        self.write(self.vault, "mathmap/知识点/集合的概念.md", "# 集合的概念\n\n# 题型\n")
        bootstrap(self.vault, write_registry=True)
        self.write(
            self.source,
            "1.1_集合的概念/questions/Q00000002.md",
            "# 题目\n\n1+1=?\n\n![[Q00000002A1]]\n",
        )
        self.write(
            self.source,
            "1.1_集合的概念/questions/answers/Q00000002A1.md",
            "# 解析\n\n答案为 2。\n",
        )
        self.write(
            self.source,
            "1.1_集合的概念/题型 1 集合判断.md",
            "# 题型 1 集合判断\n\n![[Q00000002]]\n",
        )

        dry = archive_and_link_mathmap(str(self.vault), str(self.source), "测试书")
        self.assertFalse(dry["applied"])
        self.assertGreaterEqual(dry["summary"]["create"], 3)
        self.assertFalse((self.vault / "mathmap/习题/questions/Q00000002.md").exists())
        self.assertFalse((self.vault / UNLINKED_QUESTION_TYPES_DIR).exists())

        applied = archive_and_link_mathmap(str(self.vault), str(self.source), "测试书", apply=True)
        self.assertTrue(applied["applied"])
        question = self.vault / "mathmap/习题/questions/Q00000002.md"
        answer = self.vault / "mathmap/习题/answers/Q00000002A1.md"
        tier2 = self.vault / "mathmap/习题/题型整理/题型 1 集合判断.md"
        self.assertTrue(question.is_file())
        self.assertTrue(answer.is_file())
        self.assertTrue(tier2.is_file())
        self.assertTrue((self.vault / UNLINKED_QUESTION_TYPES_DIR).is_dir())
        first_hashes = {path: sha256_bytes(path.read_bytes()) for path in (question, answer, tier2)}

        rerun = archive_and_link_mathmap(str(self.vault), str(self.source), "测试书")
        self.assertEqual(rerun["summary"]["conflicts"], 0)
        self.assertEqual(rerun["summary"]["create"], 0)
        second_hashes = {path: sha256_bytes(path.read_bytes()) for path in (question, answer, tier2)}
        self.assertEqual(first_hashes, second_hashes)

    def test_unmatched_question_type_routes_to_supported_unlinked_folder(self) -> None:
        bootstrap(self.vault, write_registry=True)
        tier2_source = (
            "第四节 未知映射/重点题型专练/"
            "题型 1 未知题型/题型 1 未知题型.md"
        )
        self.write(self.source, tier2_source, "# 题型 1 未知题型\n")
        self.write(
            self.source,
            "第四节 未知映射/重点题型专练/重点题型专练.md",
            f"# 重点题型专练\n\n![[{self.source.name}/{tier2_source}]]\n",
        )

        dry = archive_and_link_mathmap(str(self.vault), str(self.source), "测试书")
        unlinked_destination = f"{UNLINKED_QUESTION_TYPES_DIR}/题型 1 未知题型.md"
        changes = {item["destination"]: item for item in dry["changes"]}
        self.assertIn(unlinked_destination, changes)
        self.assertEqual(dry["summary"]["unlinked_question_types"], 1)
        self.assertEqual(dry["summary"]["create_directories"], 1)
        self.assertFalse((self.vault / UNLINKED_QUESTION_TYPES_DIR).exists())
        warning = next(
            item
            for item in dry["warnings"]
            if item["kind"] == "knowledge_point_review" and item["node_type"] == "题型整理"
        )
        self.assertTrue(warning["quarantined"])
        self.assertEqual(warning["unlinked_question_type_folder"], UNLINKED_QUESTION_TYPES_DIR)

        applied = archive_and_link_mathmap(str(self.vault), str(self.source), "测试书", apply=True)
        self.assertTrue(applied["applied"])
        self.assertTrue((self.vault / unlinked_destination).is_file())
        tier3 = self.vault / "mathmap/习题/题集/重点题型专练.md"
        self.assertIn(
            f"mathmap/习题/题型整理/未链接题型/题型 1 未知题型",
            tier3.read_text(encoding="utf-8"),
        )
        full_report = audit(self.vault, full_paths(self.vault))
        self.assertEqual(full_report["issue_count"], 0)

    def test_bootstrap_adopts_nested_unlinked_question_types(self) -> None:
        destination = f"{UNLINKED_QUESTION_TYPES_DIR}/遗留未链接题型.md"
        self.write(self.vault, destination, "# 遗留未链接题型\n")

        report = bootstrap(self.vault, write_registry=True)

        self.assertEqual(report["counts"]["题型整理"], 1)
        provenance = json.loads(
            (self.vault / ".mathmap-linker/provenance-manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn(destination, provenance["files"])
        self.assertIn(destination, set(full_paths(self.vault)))

    def test_manual_edit_becomes_conflict_instead_of_overwrite(self) -> None:
        destination = "mathmap/习题/题型整理/人工题型.md"
        path = self.write(self.vault, destination, "# 原始\n")
        store = RegistryStore(self.vault)
        store.adopt_file(destination, "legacy:test", "题型整理", sha256_bytes(path.read_bytes()), origin="legacy_bootstrap")
        store.save()
        path.write_text("# 用户手工修改\n", encoding="utf-8")

        plan = LinkPlan(self.vault, RegistryStore(self.vault), "测试书")
        changed = plan.propose(
            destination,
            b"# upstream changed\n",
            "题型整理",
            "book:test:file",
            "source-hash",
            "test",
        )
        self.assertFalse(changed)
        self.assertEqual(len(plan.conflicts), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "# 用户手工修改\n")

    def test_mount_insertion_stays_inside_target_heading(self) -> None:
        text = "# X\n\n# 题型\n## 来源：书A\n![[old]]\n\n# 公式与结论\n## 来源：书A\n![[formula]]\n"
        updated, changed = render_kp_mount(text, "题型整理", "new", "书A")
        self.assertTrue(changed)
        question_section = updated.split("# 公式与结论", 1)[0]
        self.assertIn("mathmap/习题/题型整理/new", question_section)
        self.assertNotIn("mathmap/习题/题型整理/new", updated.split("# 公式与结论", 1)[1])

    def test_canvas_update_is_additive_and_preserves_positions(self) -> None:
        canvas = {
            "nodes": [
                {"id": "existing", "type": "file", "file": "mathmap/知识点/A.md", "x": 10, "y": 20, "width": 400, "height": 240}
            ],
            "edges": [],
        }
        additions = {
            "nodes": [
                {"key": "mathmap/题型/B", "file": "mathmap/习题/题型整理/B.md", "parent_key": "mathmap/知识点/A"}
            ],
            "edges": [{"from_key": "mathmap/知识点/A", "to_key": "mathmap/题型/B", "label": "题型"}],
        }
        updated, sidecar, report = update_canvas(canvas, additions)
        self.assertEqual(updated["nodes"][0]["x"], 10)
        self.assertEqual(updated["nodes"][0]["y"], 20)
        self.assertEqual(report["moved_existing_nodes"], 0)
        self.assertEqual(len(report["added_nodes"]), 1)
        self.assertEqual(len(updated["edges"]), 1)


if __name__ == "__main__":
    unittest.main()

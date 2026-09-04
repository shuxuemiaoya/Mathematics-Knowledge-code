import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import refine_organizers
import semantic_atomization as semantic
import materialize_book
from validate_book_graph import sha256_file


class RefineOrganizerTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> tuple[Path, Path]:
        source = root / "source.md"
        source.write_text("\n".join(["# Book", "## Chapter", "## Section", "Introduction.", "## Observe and think", "What do you notice?", "Reusable conclusion.", "## Practice", "1. Solve this."]) + "\n", encoding="utf-8")
        manifest = root / "draft.json"
        graph = {
            "schema_version": 1,
            "source_markdown": str(source),
            "source_markdown_sha256": sha256_file(source),
            "nodes": [
                {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
                {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/01 Chapter/Chapter.md", "heading_ranges": [[2, 2]], "children": ["section"]},
                {"key": "section", "title": "Section", "layer": "organizer", "parent_key": "chapter", "organizer_level": 3, "filename": "组织层/Book/01 Chapter/01 Section/Section.md", "heading_ranges": [[3, 3]], "children": ["intro", "activity", "practice"]},
                {"key": "intro", "title": "Introduction", "layer": "atom", "parent_key": "section", "category": "knowledge", "filename": "原子层/知识点/intro.md", "source_range": [4, 4]},
                {"key": "activity", "title": "Observe and think", "layer": "organizer", "parent_key": "section", "organizer_level": 4, "filename": "组织层/Book/01 Chapter/01 Section/02 Observe/Observe.md", "heading_ranges": [[5, 5]], "children": ["activity-atom"]},
                {"key": "activity-atom", "title": "Question and conclusion", "layer": "atom", "parent_key": "activity", "category": "knowledge", "filename": "原子层/知识点/activity.md", "source_range": [6, 7]},
                {"key": "practice", "title": "Practice", "layer": "organizer", "parent_key": "section", "organizer_level": 4, "filename": "组织层/Book/01 Chapter/01 Section/03 Practice/Practice.md", "heading_ranges": [[8, 8]], "children": ["exercise"]},
                {"key": "exercise", "title": "Exercise", "layer": "atom", "parent_key": "practice", "category": "exercise", "filename": "原子层/习题/exercise.md", "source_range": [9, 9]},
            ],
            "source_order": ["intro", "activity-atom", "exercise"],
            "relations": [],
        }
        manifest.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        review = root / "organizer-review.json"
        payload = semantic.seal_artifact({
            "schema_version": 1,
            "kind": "organizer-review",
            "status": "passed",
            "base_manifest_sha256": sha256_file(manifest),
            "source_markdown_sha256": sha256_file(source),
            "reviewer": {"type": "codex-agent", "model": "current-agent"},
            "demote_organizer_keys": ["activity"],
            "content_runs": [{
                "owner_key": "topic", "create_organizer": True,
                "parent_key": "section", "title": "Reusable topic",
                "source_range": [4, 7],
                "reason": "The range is one source-supported reusable knowledge topic.",
            }],
            "renumber_parent_keys": ["section"],
        })
        review.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest, review

    def test_activity_heading_becomes_atom_content_under_topic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, review = self.make_fixture(Path(temporary))
            refined, report = refine_organizers.refine_manifest(manifest, review)
            self.assertEqual(report["counts"]["demoted_organizers"], 1)
            nodes = {node["key"]: node for node in refined["nodes"]}
            self.assertNotIn("activity", nodes)
            self.assertEqual(nodes["section"]["children"], ["topic", "practice"])
            topic_atoms = [nodes[key] for key in nodes["topic"]["children"]]
            self.assertEqual([atom["source_range"] for atom in topic_atoms], [[4, 4], [5, 7]])
            self.assertIn("01 Reusable topic", nodes["topic"]["filename"])
            self.assertIn("02 Practice", nodes["practice"]["filename"])
            final_atoms = []
            for atom in (node for node in refined["nodes"] if node.get("layer") == "atom"):
                final_atoms.append({
                    "atom_id": "final-" + atom["key"],
                    "owner_key": atom["parent_key"],
                    "source_range": atom["source_range"],
                    "category": atom["category"],
                    "title": atom["title"],
                })
            materialized, _ = materialize_book.prepare_nodes(refined, {"scope_root_keys": ["chapter"], "atoms": final_atoms})
            materialized_by_key = {node["key"]: node for node in materialized}
            self.assertTrue(materialized_by_key["topic"]["children"])
            rendered = materialize_book.render_atom_source(
                Path(temporary).joinpath("source.md").read_text(encoding="utf-8").splitlines(),
                [5, 7],
            )
            self.assertNotIn("## Observe and think", rendered)
            self.assertIn("What do you notice?", rendered)

    def test_stale_organizer_review_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, review = self.make_fixture(Path(temporary))
            payload = json.loads(review.read_text(encoding="utf-8"))
            payload["base_manifest_sha256"] = "0" * 64
            payload = semantic.seal_artifact({key: value for key, value in payload.items() if key != "artifact_sha256"})
            review.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(refine_organizers.OrganizerReviewError):
                refine_organizers.refine_manifest(manifest, review)


if __name__ == "__main__":
    unittest.main()

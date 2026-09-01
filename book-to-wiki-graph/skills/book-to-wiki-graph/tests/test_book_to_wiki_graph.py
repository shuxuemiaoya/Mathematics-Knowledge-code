from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from typing import Any


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import build_canvas
import init_book
import validate_book_graph


class BookToWikiGraphTests(unittest.TestCase):
    def materialize_graph(
        self,
        root: Path,
        source_lines: list[str],
        nodes: list[dict[str, Any]],
        relations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Path]:
        staging = root / "staging"
        book = root / "vault" / "book"
        staging.mkdir(parents=True)
        book.mkdir(parents=True)
        source = staging / "book.md"
        source.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
        profile = init_book.create_profile(source, staging, book)
        profile_path = staging / "book-profile.json"
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        atom_nodes = [node for node in nodes if node["layer"] == "atom"]
        source_order = [
            str(node["key"])
            for node in sorted(
                atom_nodes,
                key=lambda item: (
                    int(item["source_range"][0]),
                    int(item["source_range"][1]),
                    str(item["key"]),
                ),
            )
        ]
        manifest = {
            "schema_version": 1,
            "profile": str(profile_path.resolve()),
            "source_sha256": profile["source"]["sha256"],
            "source_markdown": str(source.resolve()),
            "source_markdown_sha256": validate_book_graph.sha256_file(source),
            "review": {
                "status": "passed",
                "reviewed_entire_book": True,
                "toc_hierarchy": "passed",
                "source_coverage": "passed",
                "atom_link_free": "passed",
            },
            "excluded_ranges": [],
            "nodes": nodes,
            "source_order": source_order,
            "relations": relations or [],
        }
        manifest_path = staging / "book-graph.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        by_key = {str(node["key"]): node for node in nodes}
        for node in nodes:
            path = book / str(node["filename"])
            path.parent.mkdir(parents=True, exist_ok=True)
            if node["layer"] == "atom":
                start, end = node["source_range"]
                path.write_text(
                    "\n".join(source_lines[start - 1 : end]) + "\n",
                    encoding="utf-8",
                )
                continue
            links: list[str] = []
            for child_key in node["children"]:
                child = by_key[str(child_key)]
                target = book / str(child["filename"])
                href = os.path.relpath(target, path.parent).replace("\\", "/")
                links.append(f"![{child['title']}]({href.replace(' ', '%20')})")
            path.write_text(
                f"# {node['title']}\n\n" + "\n\n".join(links) + "\n",
                encoding="utf-8",
            )
        return {
            "staging": staging,
            "book": book,
            "source": source,
            "profile": profile_path,
            "manifest": manifest_path,
        }

    def standard_graph(self, root: Path) -> dict[str, Path]:
        source_lines = [
            "# Book",
            "## Chapter A",
            "### Section A",
            "Opening scenario.",
            "Knowledge body.",
            "Worked example body.",
            "Exercise body.",
            "## Chapter B",
            "Second chapter knowledge.",
        ]
        nodes = [
            {
                "key": "book",
                "title": "Book",
                "layer": "organizer",
                "parent_key": None,
                "organizer_level": 1,
                "filename": "组织层/Book/Book.md",
                "heading_ranges": [[1, 1]],
                "children": ["chapter-a", "chapter-b"],
            },
            {
                "key": "chapter-a",
                "title": "Chapter A",
                "layer": "organizer",
                "parent_key": "book",
                "organizer_level": 2,
                "filename": "组织层/Book/Chapter A/Chapter A.md",
                "heading_ranges": [[2, 2]],
                "children": ["section-a"],
            },
            {
                "key": "section-a",
                "title": "Section A",
                "layer": "organizer",
                "parent_key": "chapter-a",
                "organizer_level": 3,
                "filename": "组织层/Book/Chapter A/Section A/Section A.md",
                "heading_ranges": [[3, 3]],
                "children": ["scenario", "knowledge", "example", "exercise"],
            },
            {
                "key": "scenario",
                "title": "Opening",
                "layer": "atom",
                "parent_key": "section-a",
                "category": "scenario",
                "filename": "原子层/情景引入/Opening.md",
                "source_range": [4, 4],
            },
            {
                "key": "knowledge",
                "title": "Knowledge",
                "layer": "atom",
                "parent_key": "section-a",
                "category": "knowledge",
                "filename": "原子层/知识点/Knowledge.md",
                "source_range": [5, 5],
            },
            {
                "key": "example",
                "title": "Example",
                "layer": "atom",
                "parent_key": "section-a",
                "category": "worked-example",
                "filename": "原子层/例题/Example.md",
                "source_range": [6, 6],
            },
            {
                "key": "exercise",
                "title": "Exercise",
                "layer": "atom",
                "parent_key": "section-a",
                "category": "exercise",
                "filename": "原子层/习题/Exercise.md",
                "source_range": [7, 7],
            },
            {
                "key": "chapter-b",
                "title": "Chapter B",
                "layer": "organizer",
                "parent_key": "book",
                "organizer_level": 2,
                "filename": "组织层/Book/Chapter B/Chapter B.md",
                "heading_ranges": [[8, 8]],
                "children": ["knowledge-b"],
            },
            {
                "key": "knowledge-b",
                "title": "Knowledge B",
                "layer": "atom",
                "parent_key": "chapter-b",
                "category": "knowledge",
                "filename": "原子层/知识点/Knowledge B.md",
                "source_range": [9, 9],
            },
        ]
        relations = [
            {
                "key": "scenario-introduces-knowledge",
                "from_key": "scenario",
                "to_key": "knowledge",
                "label": "introduces",
                "evidence": "Source line 4 explicitly introduces the knowledge on line 5.",
                "color": "5",
            }
        ]
        return self.materialize_graph(root, source_lines, nodes, relations)

    def load_index(self, output_dir: Path) -> dict[str, Any]:
        return json.loads((output_dir / "canvas-index.json").read_text(encoding="utf-8"))

    def load_canvas(self, output_dir: Path, relative: str) -> dict[str, Any]:
        return json.loads((output_dir / relative).read_text(encoding="utf-8"))

    def card_map(self, canvas: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(node["id"]): node
            for node in canvas["nodes"]
            if node.get("type") == "text"
        }

    def test_profile_freezes_source_and_fixed_atom_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text("# Source\n", encoding="utf-8")
            profile = init_book.create_profile(source, root / "staging", root / "book")
            self.assertEqual(profile["source"]["kind"], "markdown")
            self.assertEqual(
                set(profile["atom_categories"]),
                {"knowledge", "worked-example", "exercise", "scenario"},
            )

    def test_bundle_separates_overview_chapters_and_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            output_dir = items["book"] / "Canvas"
            report = build_canvas.build_canvas_bundle(
                items["manifest"], output_dir, items["book"]
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["canvases"], 4)
            index = self.load_index(output_dir)
            self.assertEqual([item["root_key"] for item in index["chapters"]], ["chapter-a", "chapter-b"])
            self.assertEqual(index["layout"]["sibling_order"], "source-top-to-bottom")

            overview = self.load_canvas(output_dir, index["overview"]["path"])
            overview_cards = self.card_map(overview)
            expected_organizers = {"book", "chapter-a", "section-a", "chapter-b"}
            self.assertEqual(
                set(overview_cards),
                {build_canvas.stable_id("card", key) for key in expected_organizers},
            )
            self.assertEqual(len([node for node in overview["nodes"] if node["type"] == "group"]), 2)
            relation_id = build_canvas.stable_id("edge", "relation:scenario-introduces-knowledge")
            self.assertNotIn(relation_id, {edge["id"] for edge in overview["edges"]})

            chapter_card = overview_cards[build_canvas.stable_id("card", "chapter-a")]
            href = urllib.parse.unquote(chapter_card["text"].split("](", 1)[1][:-1])
            self.assertEqual(
                (output_dir / href).resolve(),
                (output_dir / index["chapters"][0]["path"]).resolve(),
            )
            chapter = self.load_canvas(output_dir, index["chapters"][0]["path"])
            self.assertEqual(len(self.card_map(chapter)), 6)
            self.assertNotIn(relation_id, {edge["id"] for edge in chapter["edges"]})

            semantics = self.load_canvas(output_dir, index["semantics"]["path"])
            self.assertEqual(len(self.card_map(semantics)), 2)
            self.assertEqual({edge["id"] for edge in semantics["edges"]}, {relation_id})

            final = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertEqual(final["status"], "passed", final["errors"])

    def test_atom_order_labels_and_colors_follow_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter = self.load_canvas(output_dir, index["chapters"][0]["path"])
            cards = self.card_map(chapter)
            keys = ["scenario", "knowledge", "example", "exercise"]
            y_values = [cards[build_canvas.stable_id("card", key)]["y"] for key in keys]
            self.assertEqual(y_values, sorted(y_values))
            self.assertEqual(len(set(y_values)), len(y_values))
            expected = {
                "scenario": ("5", "情景引入 · "),
                "knowledge": ("2", "知识点 · "),
                "example": ("4", "例题 · "),
                "exercise": ("6", "习题 · "),
            }
            for key, (color, label) in expected.items():
                card = cards[build_canvas.stable_id("card", key)]
                self.assertEqual(card["color"], color)
                self.assertIn(label, card["text"])

    def test_arbitrary_depth_and_mixed_children_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_lines = [
                "# Book",
                "## Chapter",
                "Direct scenario.",
                "### Section",
                "#### Subsection",
                "Deep knowledge.",
            ]
            nodes = [
                {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
                {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/Chapter/Chapter.md", "heading_ranges": [[2, 2]], "children": ["lead", "section"]},
                {"key": "lead", "title": "Lead", "layer": "atom", "parent_key": "chapter", "category": "scenario", "filename": "原子层/情景引入/Lead.md", "source_range": [3, 3]},
                {"key": "section", "title": "Section", "layer": "organizer", "parent_key": "chapter", "organizer_level": 3, "filename": "组织层/Book/Chapter/Section/Section.md", "heading_ranges": [[4, 4]], "children": ["subsection"]},
                {"key": "subsection", "title": "Subsection", "layer": "organizer", "parent_key": "section", "organizer_level": 4, "filename": "组织层/Book/Chapter/Section/Subsection/Subsection.md", "heading_ranges": [[5, 5]], "children": ["deep"]},
                {"key": "deep", "title": "Deep", "layer": "atom", "parent_key": "subsection", "category": "knowledge", "filename": "原子层/知识点/Deep.md", "source_range": [6, 6]},
            ]
            items = self.materialize_graph(root, source_lines, nodes)
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter = self.load_canvas(output_dir, index["chapters"][0]["path"])
            cards = self.card_map(chapter)
            self.assertLess(
                cards[build_canvas.stable_id("card", "lead")]["y"],
                cards[build_canvas.stable_id("card", "section")]["y"],
            )
            self.assertGreater(
                cards[build_canvas.stable_id("card", "deep")]["x"],
                cards[build_canvas.stable_id("card", "subsection")]["x"],
            )
            report = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertIn("mixed-organizer-and-atom-children", {item["code"] for item in report["warnings"]})

    def test_hundreds_of_atoms_stay_in_one_vertical_source_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_lines = ["# Book", "## Chapter"]
            nodes: list[dict[str, Any]] = [
                {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
                {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/Chapter/Chapter.md", "heading_ranges": [[2, 2]], "children": []},
            ]
            categories = [
                ("knowledge", "知识点"),
                ("worked-example", "例题"),
                ("exercise", "习题"),
                ("scenario", "情景引入"),
            ]
            for index in range(250):
                key = f"atom-{index:03d}"
                category, directory = categories[index % len(categories)]
                source_lines.append(f"Atom body {index}.")
                nodes[1]["children"].append(key)
                nodes.append(
                    {
                        "key": key,
                        "title": f"Atom {index}",
                        "layer": "atom",
                        "parent_key": "chapter",
                        "category": category,
                        "filename": f"原子层/{directory}/Atom {index}.md",
                        "source_range": [index + 3, index + 3],
                    }
                )
            items = self.materialize_graph(root, source_lines, nodes)
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            self.assertIsNone(index["semantics"])
            chapter = self.load_canvas(output_dir, index["chapters"][0]["path"])
            cards = self.card_map(chapter)
            atom_cards = [cards[build_canvas.stable_id("card", f"atom-{index:03d}")] for index in range(250)]
            self.assertEqual(len({card["x"] for card in atom_cards}), 1)
            y_values = [card["y"] for card in atom_cards]
            self.assertEqual(y_values, sorted(y_values))
            self.assertEqual(len(set(y_values)), 250)
            report = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertEqual(report["status"], "passed", report["errors"])

    def test_manifest_child_order_must_match_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            manifest = json.loads(items["manifest"].read_text(encoding="utf-8"))
            section = next(node for node in manifest["nodes"] if node["key"] == "section-a")
            section["children"] = ["knowledge", "scenario", "example", "exercise"]
            items["manifest"].write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            section_note = items["book"] / str(section["filename"])
            by_key = {node["key"]: node for node in manifest["nodes"]}
            links = []
            for child_key in section["children"]:
                child = by_key[child_key]
                target = items["book"] / child["filename"]
                href = os.path.relpath(target, section_note.parent).replace("\\", "/").replace(" ", "%20")
                links.append(f"![{child['title']}]({href})")
            section_note.write_text("# Section A\n\n" + "\n\n".join(links) + "\n", encoding="utf-8")
            report = validate_book_graph.validate_graph(items["manifest"], items["book"])
            self.assertEqual(report["status"], "failed")
            self.assertIn("organizer-child-source-order", {item["code"] for item in report["errors"]})

    def test_unicode_special_and_duplicate_chapter_titles_are_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_lines = ["# 书", "## 集合/逻辑？", "甲。", "## 集合/逻辑？", "乙。"]
            nodes = [
                {"key": "book", "title": "书", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/书/书.md", "heading_ranges": [[1, 1]], "children": ["a", "b"]},
                {"key": "a", "title": "集合/逻辑？", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/书/A/A.md", "heading_ranges": [[2, 2]], "children": ["atom-a"]},
                {"key": "atom-a", "title": "甲", "layer": "atom", "parent_key": "a", "category": "knowledge", "filename": "原子层/知识点/甲.md", "source_range": [3, 3]},
                {"key": "b", "title": "集合/逻辑？", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/书/B/B.md", "heading_ranges": [[4, 4]], "children": ["atom-b"]},
                {"key": "atom-b", "title": "乙", "layer": "atom", "parent_key": "b", "category": "knowledge", "filename": "原子层/知识点/乙.md", "source_range": [5, 5]},
            ]
            items = self.materialize_graph(root, source_lines, nodes)
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            paths = [item["path"] for item in self.load_index(output_dir)["chapters"]]
            self.assertEqual(len(paths), len(set(paths)))
            self.assertTrue(all("/" not in Path(path).name and "?" not in path for path in paths))
            self.assertTrue(all((output_dir / path).is_file() for path in paths))

    def test_canvas_validator_rejects_visual_source_order_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter_path = output_dir / index["chapters"][0]["path"]
            chapter = json.loads(chapter_path.read_text(encoding="utf-8"))
            cards = self.card_map(chapter)
            first = cards[build_canvas.stable_id("card", "scenario")]
            second = cards[build_canvas.stable_id("card", "knowledge")]
            first["y"], second["y"] = second["y"], first["y"]
            chapter_path.write_text(
                json.dumps(chapter, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertEqual(report["status"], "failed")
            self.assertIn("canvas-sibling-order-invalid", {item["code"] for item in report["errors"]})

    def test_bundle_requires_explicit_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            with self.assertRaises(FileExistsError):
                build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            report = build_canvas.build_canvas_bundle(
                items["manifest"], output_dir, items["book"], overwrite=True
            )
            self.assertEqual(report["status"], "passed")

    def test_atom_outgoing_note_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            atom = items["book"] / "原子层" / "知识点" / "Knowledge.md"
            atom.write_text("[Another note](Another.md)\n", encoding="utf-8")
            report = validate_book_graph.validate_graph(items["manifest"], items["book"])
            self.assertEqual(report["status"], "failed")
            self.assertIn("atom-has-outgoing-link", {item["code"] for item in report["errors"]})


if __name__ == "__main__":
    unittest.main()

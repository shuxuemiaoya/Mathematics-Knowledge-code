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
from semantic_atomization import seal_artifact
import validate_book_graph


class BookToWikiGraphTests(unittest.TestCase):
    def materialize_graph(
        self,
        root: Path,
        source_lines: list[str],
        nodes: list[dict[str, Any]],
        relations: list[dict[str, Any]] | None = None,
        reviewed_relations: bool = True,
    ) -> dict[str, Path]:
        staging = root / "staging"
        book = root / "vault" / "book"
        staging.mkdir(parents=True)
        book.mkdir(parents=True)
        source = staging / "book.md"
        source.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
        profile = init_book.create_profile(source, staging, book)
        # These fixtures exercise schema-v1 backward compatibility.
        profile.pop("atomization", None)
        profile.pop("markdown_rendering", None)
        profile["canvas"] = {
            "enabled": True,
            "mode": "two-level-constellation",
            "theme": "adaptive",
            "overview_granularity": "chapter",
            "chapter_granularity": "atom",
        }
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
        if reviewed_relations:
            relation_final = seal_artifact(
                {
                    "schema_version": 1,
                    "kind": "relation-final",
                    "status": "passed",
                    "manifest": str(manifest_path),
                    "manifest_sha256": validate_book_graph.sha256_file(manifest_path),
                    "source_markdown_sha256": manifest["source_markdown_sha256"],
                    "relation_analysis": profile["relation_analysis"],
                    "concept_signatures": [
                        {"atom_key": "example", "role": "bridge", "teaches": ["A reusable mathematical method."], "assumes": ["Knowledge"]}
                    ] if any(node.get("key") == "example" for node in nodes) else [],
                    "reviewer": {"round_1": {"type": "fixture"}, "round_2": {"type": "fixture"}},
                    "bindings": {},
                    "unresolved_count": 0,
                    "relations": relations or [],
                }
            )
            relation_final_path = staging / "relation-final.json"
            relation_final_path.write_text(
                json.dumps(relation_final, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest["relation_review"] = {
                "status": "passed",
                "mode": "llm-two-pass",
                "final_artifact": {
                    "path": str(relation_final_path),
                    "sha256": relation_final["artifact_sha256"],
                },
                "bindings": {},
                "reviewer": relation_final["reviewer"],
                "featured_example_keys": ["example"] if any(node.get("key") == "example" for node in nodes) else [],
                "unresolved_count": 0,
            }
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
        def relation(key: str, left: str, right: str, relation_type: str, tier: str, ranges: tuple[int, int]) -> dict[str, Any]:
            return {
                "key": key,
                "from_key": left,
                "to_key": right,
                "type": relation_type,
                "tier": tier,
                "evidence_kind": "pedagogical-inference",
                "evidence_ranges": [
                    {"node_key": left, "source_range": [ranges[0], ranges[0]]},
                    {"node_key": right, "source_range": [ranges[1], ranges[1]]},
                ],
                "rationale": "Both endpoint texts establish this teaching progression.",
                "confidence": 0.98,
            }
        relations = [
            relation("scenario-motivates-knowledge", "scenario", "knowledge", "motivates", "backbone", (4, 5)),
            relation("knowledge-illustrates-example", "knowledge", "example", "illustrates", "supporting", (5, 6)),
            relation("knowledge-practices-exercise", "knowledge", "exercise", "practices", "supporting", (5, 7)),
            relation("knowledge-precedes-b", "knowledge", "knowledge-b", "prerequisite", "backbone", (5, 9)),
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
            self.assertEqual(profile["atomization"]["mode"], "llm-two-pass")
            self.assertEqual(profile["organization"]["activity_heading_policy"], "atom-content")
            self.assertEqual(profile["markdown_rendering"]["atom_heading_policy"], "omit")
            self.assertEqual(profile["markdown_rendering"]["leaf_organizer_policy"], "flat-note")
            self.assertEqual(profile["markdown_rendering"]["organizer_child_heading"], "relative-depth")
            self.assertEqual(
                profile["atomization"]["knowledge_granularity"],
                "complete-teaching-unit",
            )
            self.assertEqual(profile["relation_analysis"]["mode"], "llm-three-pass")
            self.assertEqual(profile["relation_analysis"]["graph_model"], "atom-concept-dual-layer")
            self.assertEqual(profile["relation_analysis"]["concept_merge_threshold"], 0.97)
            self.assertEqual(profile["atomization"]["teaching_role_audit"], "required-before-materialization")
            self.assertEqual(profile["canvas"]["mode"], "three-level-constellation")
            self.assertEqual(profile["canvas"]["section_granularity"], "atom-and-exercise-entry")
            self.assertEqual(profile["canvas"]["theme"], "adaptive")

    def test_three_level_canvas_reduces_chapter_noise_and_adds_section_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            profile = json.loads(items["profile"].read_text(encoding="utf-8"))
            profile["canvas"] = dict(init_book.DEFAULT_CANVAS)
            items["profile"].write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output_dir = items["book"] / "Canvas-v3"
            report = build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            self.assertEqual(report["canvases"], 5)
            self.assertEqual(report["section_maps"], 2)
            index = self.load_index(output_dir)
            self.assertEqual(index["schema_version"], 3)
            self.assertEqual(index["layout"]["zoom_levels"], ["book-chapters", "chapter-core", "section-detail"])
            chapter = self.load_canvas(output_dir, index["chapter_maps"][0]["path"])
            chapter_cards = self.card_map(chapter)
            self.assertNotIn(build_canvas.stable_id("exercise-entry", "section-a"), chapter_cards)
            self.assertFalse(any(str(edge.get("label", "")).startswith("练习") for edge in chapter["edges"]))
            section_entry = next(item for item in index["section_maps"] if item["chapter_key"] == "chapter-a")
            section = self.load_canvas(output_dir, section_entry["path"])
            self.assertIn(build_canvas.stable_id("exercise-entry", "section-a"), self.card_map(section))
            self.assertLessEqual(sum(str(edge.get("label", "")).startswith("练习") for edge in section["edges"]), 1)
            final = validate_book_graph.validate_graph(items["manifest"], items["book"], output_dir / "canvas-index.json")
            self.assertEqual(final["status"], "passed", final["errors"])

    def test_bundle_builds_two_level_atlas_and_chapter_maps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            output_dir = items["book"] / "Canvas"
            report = build_canvas.build_canvas_bundle(
                items["manifest"], output_dir, items["book"]
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["canvases"], 3)
            index = self.load_index(output_dir)
            self.assertEqual(index["schema_version"], 2)
            self.assertEqual([item["root_key"] for item in index["chapter_maps"]], ["chapter-a", "chapter-b"])
            self.assertEqual(index["layout"]["mode"], "two-level-constellation")

            overview = self.load_canvas(output_dir, index["atlas"]["path"])
            overview_cards = self.card_map(overview)
            self.assertEqual(
                set(overview_cards),
                {
                    build_canvas.stable_id("atlas", "book"),
                    build_canvas.stable_id("chapter", "chapter-a"),
                    build_canvas.stable_id("chapter", "chapter-b"),
                    build_canvas.stable_id("utility", "atlas-legend"),
                },
            )
            self.assertEqual(len([node for node in overview["nodes"] if node["type"] == "group"]), 0)
            self.assertTrue(any("先修 ×1" in edge.get("label", "") for edge in overview["edges"]))

            chapter_card = overview_cards[build_canvas.stable_id("chapter", "chapter-a")]
            href = urllib.parse.unquote(chapter_card["text"].split("](", 1)[1][:-1])
            self.assertEqual(
                (output_dir / href).resolve(),
                (output_dir / index["chapter_maps"][0]["path"]).resolve(),
            )
            chapter = self.load_canvas(output_dir, index["chapter_maps"][0]["path"])
            self.assertIn(build_canvas.stable_id("card", "knowledge"), self.card_map(chapter))
            self.assertIn(build_canvas.stable_id("external", "knowledge-b"), self.card_map(chapter))
            self.assertTrue(any(edge.get("label") == "主线 · 引发" for edge in chapter["edges"]))

            final = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertEqual(final["status"], "passed", final["errors"])

    def test_visible_atoms_featured_examples_and_exercise_organizers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter = self.load_canvas(output_dir, index["chapter_maps"][0]["path"])
            cards = self.card_map(chapter)
            keys = ["scenario", "knowledge", "example"]
            positions = {(cards[build_canvas.stable_id("card", key)]["x"], cards[build_canvas.stable_id("card", key)]["y"]) for key in keys}
            self.assertEqual(len(positions), len(keys))
            expected = {
                "scenario": ("5", "情景引入 · "),
                "knowledge": ("2", "知识点 · "),
                "example": ("4", "例题 · "),
            }
            for key, (color, label) in expected.items():
                card = cards[build_canvas.stable_id("card", key)]
                self.assertEqual(card["color"], color)
                self.assertIn(label, card["text"])
            self.assertNotIn(build_canvas.stable_id("card", "exercise"), cards)
            exercise_group = cards[build_canvas.stable_id("exercise-organizer", "section-a")]
            self.assertEqual(exercise_group["color"], "6")
            self.assertIn("练习星群 · Section A", exercise_group["text"])
            exercise_edge = next(edge for edge in chapter["edges"] if edge.get("label") == "练习 ×1")
            self.assertEqual((exercise_edge["fromSide"], exercise_edge["toSide"]), ("bottom", "top"))
            motivating = next(edge for edge in chapter["edges"] if edge.get("label") == "主线 · 引发")
            self.assertEqual((motivating["fromSide"], motivating["toSide"]), ("right", "top"))

    def test_multiple_knowledge_anchors_use_a_virtual_exercise_junction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_lines = ["# Book", "## Chapter", "### Section", "First knowledge.", "Second knowledge.", "Exercise body."]
            nodes = [
                {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
                {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/Chapter/Chapter.md", "heading_ranges": [[2, 2]], "children": ["section"]},
                {"key": "section", "title": "Section", "layer": "organizer", "parent_key": "chapter", "organizer_level": 3, "filename": "组织层/Book/Chapter/Section/Section.md", "heading_ranges": [[3, 3]], "children": ["k1", "k2", "exercise"]},
                {"key": "k1", "title": "First", "layer": "atom", "parent_key": "section", "category": "knowledge", "filename": "原子层/知识点/0001-K.md", "source_range": [4, 4]},
                {"key": "k2", "title": "Second", "layer": "atom", "parent_key": "section", "category": "knowledge", "filename": "原子层/知识点/0002-K.md", "source_range": [5, 5]},
                {"key": "exercise", "title": "Exercise", "layer": "atom", "parent_key": "section", "category": "exercise", "filename": "原子层/习题/0003-E.md", "source_range": [6, 6]},
            ]
            def relation(key: str, left: str, right: str, relation_type: str, tier: str, lines: tuple[int, int]) -> dict[str, Any]:
                return {
                    "key": key, "from_key": left, "to_key": right, "type": relation_type, "tier": tier,
                    "evidence_kind": "pedagogical-inference",
                    "evidence_ranges": [{"node_key": left, "source_range": [lines[0], lines[0]]}, {"node_key": right, "source_range": [lines[1], lines[1]]}],
                    "rationale": "Both source passages support this reviewed teaching connection.", "confidence": 0.98,
                }
            relations = [
                relation("r1", "k1", "k2", "develops", "backbone", (4, 5)),
                relation("r2", "k1", "exercise", "practices", "supporting", (4, 6)),
                relation("r3", "k2", "exercise", "practices", "supporting", (5, 6)),
            ]
            items = self.materialize_graph(root, source_lines, nodes, relations=relations)
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter = self.load_canvas(output_dir, index["chapter_maps"][0]["path"])
            cards = self.card_map(chapter)
            junction_id = build_canvas.stable_id("junction", "section")
            self.assertIn(junction_id, cards)
            self.assertNotIn("](", cards[junction_id]["text"])
            incoming = [edge for edge in chapter["edges"] if edge.get("toNode") == junction_id]
            self.assertEqual(len(incoming), 2)
            self.assertTrue(all((edge.get("fromSide"), edge.get("toSide")) == ("bottom", "top") for edge in incoming))
            report = validate_book_graph.validate_graph(items["manifest"], items["book"], output_dir / "canvas-index.json")
            self.assertEqual(report["status"], "passed", report["errors"])

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
            relations = [{
                "key": "lead-motivates-deep", "from_key": "lead", "to_key": "deep",
                "type": "motivates", "tier": "backbone", "evidence_kind": "pedagogical-inference",
                "evidence_ranges": [
                    {"node_key": "lead", "source_range": [3, 3]},
                    {"node_key": "deep", "source_range": [6, 6]},
                ],
                "rationale": "The opening scenario motivates the later reviewed knowledge unit.",
                "confidence": 0.98,
            }]
            items = self.materialize_graph(root, source_lines, nodes, relations=relations)
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter = self.load_canvas(output_dir, index["chapter_maps"][0]["path"])
            cards = self.card_map(chapter)
            self.assertIn(build_canvas.stable_id("card", "lead"), cards)
            self.assertIn(build_canvas.stable_id("card", "deep"), cards)
            self.assertIn(build_canvas.stable_id("landmark", "subsection"), cards)
            landmark_edge = next(
                edge for edge in chapter["edges"]
                if edge.get("fromNode") == build_canvas.stable_id("landmark", "subsection")
            )
            self.assertEqual(landmark_edge.get("toNode"), build_canvas.stable_id("card", "deep"))
            self.assertEqual(
                (landmark_edge.get("label"), landmark_edge.get("color"), landmark_edge.get("fromSide"), landmark_edge.get("toSide")),
                ("包含", build_canvas.SOURCE_ORDER_COLOR, "bottom", "top"),
            )
            self.assertEqual(len([node for node in chapter["nodes"] if node["type"] == "group"]), 2)
            report = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertIn("mixed-organizer-and-atom-children", {item["code"] for item in report["warnings"]})
            chapter["edges"] = [edge for edge in chapter["edges"] if edge.get("id") != landmark_edge["id"]]
            chapter_path = output_dir / index["chapter_maps"][0]["path"]
            chapter_path.write_text(json.dumps(chapter, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            isolated = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertIn("canvas-isolated-substantive-node", {item["code"] for item in isolated["errors"]})

    def test_hundreds_of_atoms_form_a_bounded_constellation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_lines = ["# Book", "## Chapter"]
            nodes: list[dict[str, Any]] = [
                {"key": "book", "title": "Book", "layer": "organizer", "parent_key": None, "organizer_level": 1, "filename": "组织层/Book/Book.md", "heading_ranges": [[1, 1]], "children": ["chapter"]},
                {"key": "chapter", "title": "Chapter", "layer": "organizer", "parent_key": "book", "organizer_level": 2, "filename": "组织层/Book/Chapter/Chapter.md", "heading_ranges": [[2, 2]], "children": []},
            ]
            for index in range(250):
                key = f"atom-{index:03d}"
                category, directory = "knowledge", "知识点"
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
            relations = [
                {
                    "key": f"chain-{index:03d}",
                    "from_key": f"atom-{index:03d}",
                    "to_key": f"atom-{index + 1:03d}",
                    "type": "develops", "tier": "backbone",
                    "evidence_kind": "pedagogical-inference",
                    "evidence_ranges": [
                        {"node_key": f"atom-{index:03d}", "source_range": [index + 3, index + 3]},
                        {"node_key": f"atom-{index + 1:03d}", "source_range": [index + 4, index + 4]},
                    ],
                    "rationale": "Each reviewed unit develops directly into the following teaching unit.",
                    "confidence": 0.98,
                }
                for index in range(249)
            ]
            items = self.materialize_graph(root, source_lines, nodes, relations=relations)
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter = self.load_canvas(output_dir, index["chapter_maps"][0]["path"])
            cards = self.card_map(chapter)
            atom_cards = [cards[build_canvas.stable_id("card", f"atom-{index:03d}")] for index in range(250)]
            self.assertGreater(len({card["x"] for card in atom_cards}), 20)
            self.assertGreater(len({card["y"] for card in atom_cards}), 20)
            self.assertGreaterEqual(index["chapter_maps"][0]["bounds"]["aspect_ratio"], 0.5)
            self.assertLessEqual(index["chapter_maps"][0]["bounds"]["aspect_ratio"], 2.0)
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
            paths = [item["path"] for item in self.load_index(output_dir)["chapter_maps"]]
            self.assertEqual(len(paths), len(set(paths)))
            self.assertTrue(all("/" not in Path(path).name and "?" not in path for path in paths))
            self.assertTrue(all((output_dir / path).is_file() for path in paths))

    def test_canvas_validator_rejects_overlapping_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.standard_graph(Path(temporary))
            output_dir = items["book"] / "Canvas"
            build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            index = self.load_index(output_dir)
            chapter_path = output_dir / index["chapter_maps"][0]["path"]
            chapter = json.loads(chapter_path.read_text(encoding="utf-8"))
            cards = self.card_map(chapter)
            first = cards[build_canvas.stable_id("card", "scenario")]
            second = cards[build_canvas.stable_id("card", "knowledge")]
            first["x"], first["y"] = second["x"], second["y"]
            chapter_path.write_text(
                json.dumps(chapter, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report = validate_book_graph.validate_graph(
                items["manifest"], items["book"], output_dir / "canvas-index.json"
            )
            self.assertEqual(report["status"], "failed")
            self.assertIn("canvas-card-overlap", {item["code"] for item in report["errors"]})

    def test_unreviewed_relations_only_build_navigation_atlas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            items = self.standard_graph(root)
            manifest = json.loads(items["manifest"].read_text(encoding="utf-8"))
            manifest.pop("relation_review")
            manifest["relations"] = []
            items["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output_dir = items["book"] / "Canvas-pending"
            report = build_canvas.build_canvas_bundle(items["manifest"], output_dir, items["book"])
            self.assertEqual(report["canvases"], 1)
            index = self.load_index(output_dir)
            self.assertEqual(index["relation_status"], "review_required")
            self.assertTrue(all(item["path"] is None for item in index["chapter_maps"]))

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

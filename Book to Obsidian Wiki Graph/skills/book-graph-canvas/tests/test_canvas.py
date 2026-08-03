from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = SKILL_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


canvas_tool = load_script("build_canvas")
reference_planner = load_script("plan_from_reference_canvas")
reference_finalizer = load_script("finalize_reference_canvas_review")
manifest_planner = load_script("plan_from_manifests")
style_comparator = load_script("compare_canvas_style")


class CanvasCompilerTests(unittest.TestCase):
    def test_style_comparator_passes_similar_canvas_and_blocks_flat_grid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference_path = root / "reference.canvas"
            similar_path = root / "similar.canvas"
            flat_path = root / "flat.canvas"
            groups = [
                {
                    "id": f"group-{index}",
                    "type": "group",
                    "label": f"层级 {index}",
                    "x": index * 100,
                    "y": index * 100,
                    "width": 1200 - index * 200,
                    "height": 1200 - index * 200,
                }
                for index in range(4)
            ]
            cards = [
                {
                    "id": f"card-{index}",
                    "type": "text",
                    "text": (
                        "说明卡" if index == 0 else f"[[主题-{index}]]"
                    ),
                    "x": 350 + (index % 2) * 220,
                    "y": 350 + index * 45,
                    "width": 180,
                    "height": 60 + (index % 3) * 60,
                    **({"color": "2"} if index < 7 else {}),
                }
                for index in range(10)
            ]
            edges = [
                {
                    "id": f"edge-{index}",
                    "fromNode": f"card-{index}",
                    "toNode": f"card-{index + 1}",
                    **({"color": "4"} if index < 7 else {}),
                }
                for index in range(9)
            ]
            reference = {"nodes": groups + cards, "edges": edges}
            reference_path.write_text(
                json.dumps(reference, ensure_ascii=False), encoding="utf-8"
            )
            similar = json.loads(json.dumps(reference, ensure_ascii=False))
            for node in similar["nodes"]:
                if node.get("type") == "text":
                    node["text"] = node["text"].replace(
                        "[[主题-", "[主题-"
                    ).replace("]]", "](主题.md)")
            similar_path.write_text(
                json.dumps(similar, ensure_ascii=False), encoding="utf-8"
            )
            flat_cards = json.loads(json.dumps(cards, ensure_ascii=False))
            for index, node in enumerate(flat_cards):
                node["x"] = 50 + index * 200
                node["y"] = 50
                node["height"] = 60
                node["color"] = "2"
                node["text"] = f"[主题 {index}](主题-{index}.md)"
            flat = {
                "nodes": [
                    {
                        "id": "only-group",
                        "type": "group",
                        "label": "全部",
                        "x": 0,
                        "y": 0,
                        "width": 2100,
                        "height": 180,
                    }
                ]
                + flat_cards,
                "edges": [
                    {
                        "id": f"flat-edge-{index}",
                        "fromNode": f"card-{index}",
                        "toNode": f"card-{index + 1}",
                        "label": "关联",
                    }
                    for index in range(9)
                ],
            }
            flat_path.write_text(
                json.dumps(flat, ensure_ascii=False), encoding="utf-8"
            )
            profile_path = root / "book-profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "source": {"sha256": "a" * 64},
                        "canvas": {
                            "style_reference": {
                                "path": str(reference_path.resolve()),
                                "sha256": style_comparator.sha256_file(
                                    reference_path
                                ),
                                "scope": "same-series-style",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            similar_report = style_comparator.compare_canvas_styles(
                profile_path, similar_path
            )
            flat_report = style_comparator.compare_canvas_styles(
                profile_path, flat_path
            )

            self.assertEqual(similar_report["status"], "passed")
            self.assertEqual(flat_report["status"], "style_review_required")
            codes = {
                item["code"]
                for item in flat_report["blocking_differences"]
            }
            self.assertIn("group-depth", codes)
            self.assertIn("group-density", codes)
            self.assertIn("edge-coloring", codes)
            self.assertIn("annotation-cards", codes)

    def test_manifest_planner_uses_reviewed_domains_and_definition_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            book = vault / "books" / "example"
            staging = root / "staging"
            (book / "知识点").mkdir(parents=True)
            (book / "概念").mkdir()
            staging.mkdir()
            (book / "example.md").write_text("# Example\n", encoding="utf-8")
            (book / "知识点" / "第一章.md").write_text("# 第一章\n", encoding="utf-8")
            (book / "知识点" / "主题.md").write_text("# 主题\n", encoding="utf-8")
            (book / "概念" / "对象.md").write_text("# 对象\n", encoding="utf-8")
            digest = "a" * 64
            profile_path = staging / "book-profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "source": {"sha256": digest},
                        "paths": {
                            "vault_root": str(vault),
                            "book_root": str(book),
                        },
                        "categories": [
                            {"role": "knowledge", "directory": "知识点"},
                            {"role": "concept", "directory": "概念"},
                        ],
                        "canvas": {
                            "node_colors": {
                                "super_core": "1",
                                "knowledge_or_concept": "2",
                            },
                            "edge_colors": {},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            split_path = staging / "split-manifest.json"
            split_path.write_text(
                json.dumps(
                    {
                        "source_sha256": digest,
                        "nodes": [
                            {
                                "key": "book-root",
                                "title": "Example",
                                "parent_key": None,
                                "category": "root",
                                "filename": "example.md",
                            },
                            {
                                "key": "chapter-1",
                                "title": "第一章",
                                "parent_key": "book-root",
                                "category": "knowledge",
                                "filename": "第一章.md",
                            },
                            {
                                "key": "topic-1",
                                "title": "主题",
                                "parent_key": "chapter-1",
                                "category": "knowledge",
                                "filename": "主题.md",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            concept_path = staging / "concept-manifest.json"
            concept_path.write_text(
                json.dumps(
                    {
                        "source_sha256": digest,
                        "concepts": [
                            {
                                "name": "对象",
                                "definition_source": "知识点/主题.md",
                                "definition_unit": "topic-1",
                                "target": "概念/对象.md",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            plan_path = staging / "canvas-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "domains": [
                            {
                                "key": "domain",
                                "label": "知识域",
                                "chapters": ["chapter-1"],
                            }
                        ],
                        "relations": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = manifest_planner.plan_manifest(
                profile_path, split_path, concept_path, plan_path
            )

            self.assertEqual(manifest["planning_basis"]["placed_split_notes"], 2)
            self.assertEqual(manifest["planning_basis"]["placed_concepts"], 1)
            self.assertEqual(
                sum(node["type"] == "group" for node in manifest["nodes"]), 2
            )
            self.assertTrue(
                any(edge.get("label") == "定义" for edge in manifest["edges"])
            )

    def test_reference_planner_converts_wikilinks_and_blocks_until_reviewed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            book = vault / "books" / "example"
            reference_root = root / "reference"
            staging = root / "staging"
            book.mkdir(parents=True)
            reference_root.mkdir()
            staging.mkdir()
            (book / "主题.md").write_text("# 主题\n", encoding="utf-8")
            reference_canvas = reference_root / "example.canvas"
            reference_canvas.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "group",
                                "type": "group",
                                "label": "主题域",
                                "x": 0,
                                "y": 0,
                                "width": 600,
                                "height": 500,
                            },
                            {
                                "id": "topic",
                                "type": "text",
                                "text": "[[books/example/主题|主题]]",
                                "x": 50,
                                "y": 50,
                                "width": 200,
                                "height": 60,
                            },
                            {
                                "id": "cluster",
                                "type": "group",
                                "label": "子主题",
                                "x": 20,
                                "y": 20,
                                "width": 260,
                                "height": 200,
                            },
                            {
                                "id": "external",
                                "type": "text",
                                "text": "[[outside/不存在|外部主题]]",
                                "x": 300,
                                "y": 50,
                                "width": 200,
                                "height": 60,
                            },
                        ],
                        "edges": [
                            {
                                "id": "kept-edge",
                                "fromNode": "group",
                                "toNode": "topic",
                            },
                            {
                                "id": "skipped-edge",
                                "fromNode": "topic",
                                "toNode": "external",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            profile_path = staging / "book-profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source": {"sha256": "a" * 64},
                        "paths": {
                            "vault_root": str(vault),
                            "book_root": str(book),
                        },
                        "links": {"encode_spaces": True},
                        "canvas": {
                            "enabled": True,
                            "node_colors": {},
                            "edge_colors": {},
                        },
                        "reference": {
                            "path": str(reference_root),
                            "scope": "same-book-content-and-style",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            custom_without_reference_review = {
                "version": 1,
                "profile": str(profile_path.resolve()),
                "source_sha256": "a" * 64,
                "nodes": [],
                "edges": [],
            }
            with self.assertRaisesRegex(
                canvas_tool.ManifestError,
                "requires reference_review",
            ):
                canvas_tool.load_profile(
                    profile_path.resolve(),
                    custom_without_reference_review,
                    vault.resolve(),
                )
            manifest_path = staging / "graph-manifest.json"

            report = reference_planner.plan(
                reference_canvas,
                profile_path,
                manifest_path,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "review_required")
            self.assertEqual(report["groups"], 2)
            self.assertEqual(report["skipped_nodes"], 1)
            self.assertEqual(report["skipped_edges"], 1)
            topic = next(
                node
                for node in manifest["nodes"]
                if node["type"] == "text"
            )
            self.assertEqual(
                topic["text"],
                "[主题](books/example/主题.md)",
            )
            with self.assertRaisesRegex(
                canvas_tool.ManifestError,
                "not approved",
            ):
                canvas_tool.compile_manifest(
                    manifest,
                    book / "example.canvas",
                    vault,
                )

            decisions_path = staging / "canvas-review-decisions.json"
            decisions_path.write_text(
                json.dumps(
                    {
                        "reference_sha256": manifest["reference_review"][
                            "reference_sha256"
                        ],
                        "skipped_nodes": [
                            {
                                "id": "external",
                                "disposition": "external-to-current-book",
                                "reason": (
                                    "The linked note is outside the approved "
                                    "current book corpus."
                                ),
                            }
                        ],
                        "skipped_edges": [
                            {
                                "id": "skipped-edge",
                                "disposition": "external-to-current-book",
                                "reason": (
                                    "The relation terminates at the reviewed "
                                    "external reference node."
                                ),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            reference_finalizer.finalize(manifest_path, decisions_path)
            approved = json.loads(manifest_path.read_text(encoding="utf-8"))

            canvas, summary = canvas_tool.compile_manifest(
                approved,
                book / "example.canvas",
                vault,
            )

            self.assertEqual(summary["groups"], 2)
            self.assertEqual(summary["edges"], 1)
            self.assertEqual(len(canvas["nodes"]), 3)

            flattened = json.loads(json.dumps(approved))
            nested_group = next(
                node
                for node in flattened["nodes"]
                if node["key"] == "reference-group-cluster"
            )
            nested_group["x"] = 700
            with self.assertRaisesRegex(
                canvas_tool.ManifestError,
                "flattened",
            ):
                canvas_tool.compile_manifest(
                    flattened,
                    book / "flattened.canvas",
                    vault,
                )

    def test_profile_palette_and_identity_drive_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            book = vault / "books" / "example"
            book.mkdir(parents=True)
            note = book / "topic.md"
            note.write_text("# Topic\n", encoding="utf-8")
            profile_path = root / "book-profile.json"
            profile = {
                "schema_version": 1,
                "source": {"sha256": "a" * 64},
                "paths": {"vault_root": str(vault)},
                "canvas": {
                    "enabled": True,
                    "node_colors": {"topic": "#123456"},
                    "edge_colors": {"relation": "#abcdef"},
                },
            }
            profile_path.write_text(
                json.dumps(profile), encoding="utf-8"
            )
            manifest = {
                "version": 1,
                "profile": str(profile_path.resolve()),
                "source_sha256": "a" * 64,
                "nodes": [
                    {
                        "key": "topic",
                        "type": "text",
                        "text": "[Topic](books/example/topic.md)",
                        "x": 0,
                        "y": 0,
                        "width": 200,
                        "height": 60,
                        "color": "#123456",
                    }
                ],
                "edges": [],
            }
            node_colors, edge_colors, resolved_vault = canvas_tool.load_profile(
                profile_path.resolve(), manifest, vault.resolve()
            )

            canvas, summary = canvas_tool.compile_manifest(
                manifest,
                book / "example.canvas",
                resolved_vault,
                node_colors=node_colors,
                edge_colors=edge_colors,
            )

            self.assertEqual(canvas["nodes"][0]["color"], "#123456")
            self.assertEqual(summary["nodes"], 1)

    def test_rejects_missing_canvas_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "version": 1,
                "nodes": [
                    {
                        "key": "missing",
                        "type": "text",
                        "text": "[Missing](missing.md)",
                        "x": 0,
                        "y": 0,
                        "width": 200,
                        "height": 60,
                    }
                ],
                "edges": [],
            }
            with self.assertRaises(canvas_tool.ManifestError):
                canvas_tool.compile_manifest(
                    manifest, root / "example.canvas", root
                )

    def test_rejects_residual_wikilink_in_canvas_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "version": 1,
                "nodes": [
                    {
                        "key": "legacy-link",
                        "type": "text",
                        "text": "[[books/example/topic|Topic]]",
                        "x": 0,
                        "y": 0,
                        "width": 200,
                        "height": 60,
                    }
                ],
                "edges": [],
            }

            with self.assertRaisesRegex(
                canvas_tool.ManifestError,
                "forbidden Wikilink",
            ):
                canvas_tool.compile_manifest(
                    manifest,
                    root / "example.canvas",
                    root,
                )


if __name__ == "__main__":
    unittest.main()

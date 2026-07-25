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


class CanvasCompilerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


def load_script(name: str):
    path = SKILL_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


profile_tool = load_script("make_book_profile")
style_discovery = load_script("discover_sibling_canvas_style")


class BookProfileTests(unittest.TestCase):
    def test_create_and_validate_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            book = vault / "books" / "example"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()

            profile = profile_tool.create_profile(
                source, vault, book, "Example"
            )

            self.assertEqual(profile_tool.profile_errors(profile), [])
            self.assertEqual(profile["links"]["asset_base"], "/books/example")
            self.assertEqual(profile["links"]["note_mode"], "vault-root")
            self.assertEqual(
                {item["role"] for item in profile["categories"]},
                {"knowledge", "concept", "exercise"},
            )
            self.assertEqual(
                profile["formatting"]["callout_body_mode"], "quoted-body"
            )
            self.assertEqual(
                profile["decomposition"]["non_toc_split_default"], "retain"
            )
            self.assertTrue(
                profile["decomposition"]["require_lesson_flow_manifest"]
            )
            self.assertEqual(
                profile["decomposition"][
                    "max_retained_teaching_block_nonblank_lines"
                ],
                40,
            )

    def test_textbook_can_enable_source_supported_auxiliary_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()
            profile = profile_tool.create_profile(
                source,
                vault,
                vault / "book",
                "Example",
                textbook_aux_roles=["reading", "method"],
            )
            self.assertEqual(profile_tool.profile_errors(profile), [])
            enabled = {
                item["role"]: item["directory"]
                for item in profile["categories"]
                if item.get("enabled", True)
            }
            self.assertEqual(enabled["reading"], "趣味阅读")
            self.assertEqual(enabled["method"], "思维或方法")

    def test_freezes_reference_corpus_and_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            reference = root / "reference"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()
            reference.mkdir()
            (reference / "样例.md").write_text(
                "# 样例\n\n> [!info] 情景引入\n> 正文。\n",
                encoding="utf-8",
            )
            profile = profile_tool.create_profile(
                source,
                vault,
                vault / "book",
                "Example",
                reference_corpus=reference,
                reference_scope="style-only",
            )
            self.assertEqual(profile_tool.profile_errors(profile), [])
            self.assertEqual(profile["reference"]["path"], str(reference.resolve()))
            self.assertEqual(profile["reference"]["scope"], "style-only")
            self.assertEqual(len(profile["reference"]["sha256"]), 64)

    def test_freezes_canvas_style_reference_and_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            staging = root / "staging"
            reference_canvas = root / "reference.canvas"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()
            staging.mkdir()
            reference_canvas.write_text(
                '{"nodes": [], "edges": []}\n', encoding="utf-8"
            )
            profile = profile_tool.create_profile(
                source,
                vault,
                vault / "book",
                "Example",
                staging_root=staging,
                canvas_style_reference=reference_canvas,
            )
            style_reference = profile["canvas"]["style_reference"]
            self.assertEqual(style_reference["scope"], "same-series-style")
            self.assertEqual(
                style_reference["path"], str(reference_canvas.resolve())
            )
            self.assertEqual(profile_tool.profile_errors(profile), [])

            profile_path = staging / "book-profile.json"
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False), encoding="utf-8"
            )
            reference_canvas.write_text(
                '{"nodes": [{"id": "changed"}], "edges": []}\n',
                encoding="utf-8",
            )
            errors = profile_tool.profile_location_errors(profile, profile_path)
            self.assertTrue(
                any("current reference canvas" in item for item in errors)
            )

    def test_discovers_nearest_same_series_sibling_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            books = Path(temporary) / "课本"
            target = books / "【人教版】高中选择性必修 第二册数学电子课本"
            first = books / "【人教版】高中选择性必修 第一册数学电子课本"
            third = books / "【人教版】高中选择性必修 第三册数学电子课本"
            wrong = books / "【人教版】高中必修 第一册数学电子课本"
            for directory in (target, first, third, wrong):
                directory.mkdir(parents=True)
                (directory / f"{directory.name}.canvas").write_text(
                    '{"nodes": [], "edges": []}\n', encoding="utf-8"
                )

            payload = style_discovery.discover(books, target)

            self.assertEqual(payload["status"], "selected")
            self.assertEqual(
                Path(payload["selected"]["path"]).parent,
                first.resolve(),
            )
            self.assertFalse(
                next(
                    item
                    for item in payload["candidates"]
                    if Path(item["path"]).parent == wrong.resolve()
                )["eligible"]
            )

    def test_textbook_rejects_unsupported_auxiliary_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()
            profile = profile_tool.create_profile(
                source, vault, vault / "book", "Example"
            )
            profile["categories"].append(
                {
                    "role": "reading",
                    "directory": "随便阅读",
                    "enabled": True,
                }
            )
            errors = profile_tool.profile_errors(profile)
            self.assertTrue(
                any("supported role/directory" in item for item in errors)
            )

    def test_rejects_duplicate_enabled_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()
            profile = profile_tool.create_profile(
                source, vault, vault / "book", "Example"
            )
            profile["categories"][1]["directory"] = profile["categories"][0][
                "directory"
            ]

            errors = profile_tool.profile_errors(
                json.loads(json.dumps(profile, ensure_ascii=False))
            )
            self.assertTrue(
                any("duplicate category directory" in item for item in errors)
            )

    def test_non_textbook_keeps_relative_note_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()
            profile = profile_tool.create_profile(
                source,
                vault,
                vault / "books" / "example",
                "Example",
                book_kind="monograph",
            )
            self.assertEqual(profile["links"]["note_mode"], "relative")

    def test_rejects_profile_relocated_outside_frozen_staging_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            vault = root / "vault"
            staging = root / "staging"
            moved = root / "moved"
            source.write_text("# Example\n", encoding="utf-8")
            vault.mkdir()
            staging.mkdir()
            moved.mkdir()
            profile = profile_tool.create_profile(
                source,
                vault,
                vault / "book",
                "Example",
                staging_root=staging,
            )
            moved_profile = moved / "book-profile.json"
            moved_profile.write_text(
                json.dumps(profile, ensure_ascii=False), encoding="utf-8"
            )
            errors = profile_tool.profile_location_errors(
                profile, moved_profile
            )
            self.assertTrue(any("moved or copied" in item for item in errors))


if __name__ == "__main__":
    unittest.main()

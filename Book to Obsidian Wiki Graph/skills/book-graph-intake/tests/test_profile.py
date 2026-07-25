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


if __name__ == "__main__":
    unittest.main()

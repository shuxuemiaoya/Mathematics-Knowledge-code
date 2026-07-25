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


audit_tool = load_script("audit_obsidian_graph")


class GraphAuditTests(unittest.TestCase):
    def make_profiled_book(
        self, root: Path
    ) -> tuple[Path, Path, Path, Path, Path, Path]:
        source = root / "source.md"
        source.write_text("# Source\n", encoding="utf-8")
        source_sha256 = audit_tool.sha256_file(source)
        vault = root / "vault"
        book = vault / "books" / "example"
        (book / "主题").mkdir(parents=True)
        (book / "术语").mkdir()
        (book / "主题" / "集合.md").write_text(
            "# 集合\n\n把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
            encoding="utf-8",
        )
        (book / "术语" / "集合.md").write_text(
            "把研究对象组成的总体叫做集合。\n",
            encoding="utf-8",
        )
        profile_path = root / "book-profile.json"
        profile = {
            "schema_version": 1,
            "book": {"title": "Example"},
            "source": {"path": str(source), "sha256": source_sha256},
            "paths": {
                "vault_root": str(vault.resolve()),
                "book_root": str(book.resolve()),
                "staging_root": str(root.resolve()),
            },
            "categories": [
                {
                    "role": "knowledge",
                    "directory": "主题",
                    "enabled": True,
                    "flat": False,
                },
                {
                    "role": "concept",
                    "directory": "术语",
                    "enabled": True,
                    "flat": True,
                },
            ],
            "links": {"markdown_only": True},
            "formatting": {"blank_before_top_level_callout": True},
            "canvas": {
                "enabled": False,
                "node_colors": {},
                "edge_colors": {},
            },
            "workspace": {"backup_policy": "none"},
        }
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False), encoding="utf-8"
        )
        coverage_path = root / "coverage-manifest.json"
        coverage_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": str(profile_path.resolve()),
                    "source_sha256": source_sha256,
                    "units": [
                        {
                            "source_key": "block-1",
                            "source_order": 1,
                            "status": "assigned",
                            "target": "主题/集合.md",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        concept_path = root / "concept-manifest.json"
        concept_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": str(profile_path.resolve()),
                    "source_sha256": source_sha256,
                    "concepts": [
                        {
                            "name": "集合",
                            "target": "术语/集合.md",
                            "linked_from": ["主题/集合.md"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return (
            source,
            vault,
            book,
            profile_path,
            coverage_path,
            concept_path,
        )

    def test_profile_mapped_concept_directory_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                expected_source_sha256=audit_tool.sha256_file(source),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertEqual(report["counts"]["concept_files"], 1)

    def test_rejects_wikilink_and_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n[[残留链接]]\n\n[missing](不存在.md)\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("residual-wikilinks", codes)
            self.assertIn("missing-markdown-link", codes)
            self.assertIn("orphan-concept", codes)

    def test_rejects_unstandardized_functional_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            items = self.make_profiled_book(Path(temporary))
            source, vault, book, profile, coverage, concepts = items
            (book / "主题" / "集合.md").write_text(
                "# 集合\n\n#### 思考\n\n问题。\n\n例 1 求解。\n\n解：答案。\n\n"
                "把研究对象组成的总体叫做[集合](../术语/集合.md)。\n",
                encoding="utf-8",
            )
            report = audit_tool.audit_book(
                book.resolve(),
                vault.resolve(),
                source=source.resolve(),
                profile_path=profile.resolve(),
                coverage_manifest=coverage.resolve(),
                concept_manifest=concepts.resolve(),
            )
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("unstandardized-functional-blocks", codes)
            self.assertEqual(
                report["counts"]["unstandardized_functional_blocks"], 2
            )


if __name__ == "__main__":
    unittest.main()

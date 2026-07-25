from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "book_pdf_to_markdown.py"
)
SPEC = importlib.util.spec_from_file_location("book_pdf_to_markdown", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AssetLinkTests(unittest.TestCase):
    def test_rewrites_redundant_parent_prefix(self) -> None:
        markdown = "![](测试/images/figure.jpg)"
        self.assertEqual(
            MODULE.rewrite_asset_links(markdown, "测试（图片整理版）"),
            "![](images/测试（图片整理版）/figure.jpg)",
        )

    def test_rewrite_is_idempotent(self) -> None:
        markdown = "![](images/测试（图片整理版）/figure.jpg)"
        once = MODULE.rewrite_asset_links(markdown, "测试（图片整理版）")
        twice = MODULE.rewrite_asset_links(once, "测试（图片整理版）")
        self.assertEqual(twice, once)

    def test_reports_missing_staged_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            unresolved = MODULE.unresolved_staged_asset_links(
                "![](images/测试（图片整理版）/missing.jpg)",
                "测试（图片整理版）",
                Path(temp_name),
            )
        self.assertEqual(unresolved, ["images/测试（图片整理版）/missing.jpg"])

    def test_accepts_existing_staged_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "figure.jpg").write_bytes(b"image")
            unresolved = MODULE.unresolved_staged_asset_links(
                "![](images/测试（图片整理版）/figure.jpg)",
                "测试（图片整理版）",
                root,
            )
        self.assertEqual(unresolved, [])

    def test_profile_sets_default_raw_markdown_in_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "book.pdf"
            source.write_bytes(b"pdf-placeholder")
            staging = root / "staging"
            profile_path = root / "book-profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source": {
                            "path": str(source),
                            "sha256": MODULE.sha256_file(source),
                        },
                        "paths": {"staging_root": str(staging)},
                    }
                ),
                encoding="utf-8",
            )
            resolved_source, target, resolved_profile = MODULE.resolve_paths(
                str(source), None, str(profile_path)
            )
        self.assertEqual(resolved_source, source.resolve())
        self.assertEqual(target, (staging / "book.raw.md").resolve())
        self.assertEqual(resolved_profile, profile_path.resolve())


if __name__ == "__main__":
    unittest.main()

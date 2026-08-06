#!/usr/bin/env python3
"""Unit tests for tag_book_metadata.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tag_book_metadata import (
    derive_metadata_for_file,
    format_frontmatter,
    infer_chapter,
    infer_difficulty,
    infer_duration,
    infer_grade,
    infer_importance,
    infer_node_type,
    infer_source,
    infer_tier,
    parse_frontmatter,
    process_book_metadata,
    validate_file_metadata,
)


class TestTagBookMetadata(unittest.TestCase):

    def test_parse_and_format_frontmatter(self):
        content = "---\n来源: 旧来源\n年级: 高一\n---\n\n# Header\nBody text"
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta["来源"], "旧来源")
        self.assertEqual(meta["年级"], "高一")
        self.assertIn("# Header", body)

        meta["节点类型"] = "知识点"
        formatted = format_frontmatter(meta, body)
        self.assertTrue(formatted.startswith("---\n"))
        self.assertIn("节点类型: 知识点", formatted)
        self.assertIn("# Header", formatted)

    def test_infer_functions(self):
        self.assertEqual(infer_grade("高中必修第一册", "2019人教A"), "高一")
        self.assertEqual(infer_grade("高中选择性必修第一册", "2019人教A"), "高二")

        profile = {"book": {"title": "数学必修第一册", "edition": "2019人教A"}}
        self.assertEqual(infer_source(profile), "2019人教A")

        book_root = Path("/tmp/vault/book")
        self.assertEqual(infer_node_type(book_root / "概念" / "集合.md", book_root), "概念")
        self.assertEqual(infer_node_type(book_root / "知识点" / "函数的单调性.md", book_root), "知识点")
        self.assertEqual(infer_node_type(book_root / "index.md", book_root), "目录")

        self.assertEqual(infer_chapter(book_root / "01-第一章_集合" / "note.md", book_root), "第一章 集合")
        self.assertEqual(infer_duration("概念", 50), "15分钟")
        self.assertEqual(infer_duration("知识点", 200), "45分钟")
        self.assertEqual(infer_difficulty("概念", "集合"), "简单")
        self.assertEqual(infer_difficulty("知识点", "导数的几何意义"), "难")

    def test_validate_file_metadata(self):
        valid_meta = {
            "来源": "2019 人教A 数学 必修一",
            "年级": "高一",
            "节点类型": "概念",
            "章节": "第一章 集合与常用逻辑用语",
            "时长": "15分钟",
            "难度": "简单",
            "重要程度": "理解",
            "推荐层级": "D",
        }
        self.assertEqual(validate_file_metadata(valid_meta), [])

        invalid_meta = dict(valid_meta)
        invalid_meta["时长"] = "99分钟"
        errors = validate_file_metadata(invalid_meta)
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid 时长", errors[0])

    def test_process_book_metadata_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            book_root = tmppath / "vault" / "BookRoot"
            staging_root = tmppath / "staging"
            staging_root.mkdir(parents=True, exist_ok=True)

            concept_dir = book_root / "01-第一章_集合" / "概念"
            concept_dir.mkdir(parents=True, exist_ok=True)
            note_file = concept_dir / "集合.md"
            note_file.write_text("# 集合\n\n集合的完整定义正文。", encoding="utf-8")

            profile_payload = {
                "schema_version": 1,
                "book": {"title": "高中必修第一册", "edition": "2019 人教A 数学 必修一"},
                "source": {"path": str(tmppath / "source.pdf"), "sha256": "a" * 64},
                "paths": {
                    "vault_root": str(tmppath / "vault"),
                    "book_root": str(book_root),
                    "staging_root": str(staging_root),
                },
                "categories": [
                    {"role": "knowledge", "directory": "知识点", "enabled": True},
                    {"role": "concept", "directory": "概念", "enabled": True},
                ],
            }
            profile_path = staging_root / "book-profile.json"
            profile_path.write_text(json.dumps(profile_payload, ensure_ascii=False), encoding="utf-8")

            report_path = staging_root / "metadata-report.json"
            report = process_book_metadata(book_root, profile_path, report_path)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["total_files"], 1)
            self.assertEqual(report["tagged_files"], 1)

            updated_content = note_file.read_text(encoding="utf-8")
            self.assertTrue(updated_content.startswith("---\n"))
            self.assertIn("节点类型: 概念", updated_content)
            self.assertIn("来源: 2019 人教A 数学 必修一", updated_content)
            self.assertIn("# 集合", updated_content)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from question_type_graph.answers import parse_answer_blocks
from question_type_graph.common import (
    ConfigurationError,
    validate_adapter_contract,
    write_json_atomic,
)
from question_type_graph.content import plan_content
from question_type_graph.hierarchy import plan_hierarchy
from question_type_graph.environment import resolve_env_file
from question_type_graph.inventory import build_inventory, contiguous_index_runs, inventory_markdown
from question_type_graph.mineru import PdfPart, build_payload, load_settings
from question_type_graph.profile import create_profile
from question_type_graph.provenance import map_markdown_lines
from question_type_graph.runtime import implementation_paths, input_fingerprint


class TestGeneralization(unittest.TestCase):
    def test_stage_fingerprint_can_bind_compiler_implementation(self) -> None:
        compiler_paths = implementation_paths("content", "answers", "common")

        self.assertTrue(all(path.is_file() for path in compiler_paths))
        self.assertNotEqual(
            input_fingerprint([], {"stage_contract": 1}),
            input_fingerprint(compiler_paths, {"stage_contract": 1}),
        )

    def test_env_discovery_is_independent_of_launch_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            profile = root / "staging" / "profile.json"
            profile.parent.mkdir()
            expected = root / ".env"
            expected.write_text("MINERU_API_KEY=test-key\n", encoding="utf-8")

            self.assertEqual(resolve_env_file(profile), expected.resolve())

    def test_inventory_reconstructs_interleaved_multi_column_index(self) -> None:
        candidates = contiguous_index_runs(
            [
                "1 First …… 1 3 Third …… 9 5 Fifth …… 17",
                "2 Second …… 5 4 Fourth …… 13 6 Sixth …… 21",
            ]
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["entry_count"], 6)
        self.assertEqual(candidates[0]["recommended_reading_order"], "column-major")
        self.assertEqual(
            [item["printed_ordinal"] for item in candidates[0]["entries"]],
            [1, 2, 3, 4, 5, 6],
        )
        self.assertEqual(candidates[0]["entries"][1]["source_line"], 2)

    def test_page_bbox_index_maps_raw_lines_with_part_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            markdown = Path(tmp_dir) / "raw.md"
            markdown.write_text(
                "<!-- source-part:1 pages:1-2 -->\n\n## Unit\n1. Exact question text\n",
                encoding="utf-8",
            )
            blocks = [
                {
                    "block_id": "questions:p2:b1",
                    "part": 1,
                    "source_page": 2,
                    "type": "text",
                    "bbox": [10, 20, 300, 80],
                    "text": "1. Exact question text",
                }
            ]

            line_map = map_markdown_lines(markdown, blocks)

            self.assertEqual(line_map["4"][0]["source_page"], 2)
            self.assertEqual(line_map["4"][0]["bbox"], [10, 20, 300, 80])

    def test_mineru_payload_is_forced_and_format_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            part = tmp_path / "part.pdf"
            part.write_bytes(b"pdf")
            payload = build_payload([PdfPart(part, 1, 1, 1, 1, "stable")], "ch")
            self.assertEqual(payload, {
                "files": [{"name": "part.pdf", "data_id": "stable", "is_ocr": True}],
                "model_version": "vlm",
                "language": "ch",
                "enable_formula": True,
                "enable_table": True,
            })

    def test_mineru_settings_accept_ch_and_zh_profile_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text("MINERU_API_KEY=test-key\n", encoding="utf-8")
            args = Namespace(
                env_file=str(env_file),
                base_url=None,
                language=None,
                poll_interval=1.0,
                max_polls=1,
                request_timeout=1.0,
            )
            for profile_language in ("ch", "zh", "zh-CN", "zh_CN"):
                with self.subTest(profile_language=profile_language):
                    settings = load_settings(args, {"language": profile_language})
                    self.assertEqual(settings.language, "ch")

    def test_numbering_patterns_are_adapter_controlled(self) -> None:
        cases = [
            (r"^(?P<number>\d+)[.]\s+", "12. Arabic", "12"),
            (r"^第(?P<number>[一二三四五六七八九十]+)题\s*", "第三题 Chinese", "三"),
            (r"^(?P<number>[①②③④⑤])\s*", "② Circled", "②"),
        ]
        for pattern, line, number in cases:
            with self.subTest(pattern=pattern, line=line):
                m = re.match(pattern, line)
                self.assertIsNotNone(m)
                self.assertEqual(m.group("number"), number)

    def test_inline_answer_boundaries_support_multiple_adapter_formats(self) -> None:
        cases = [
            (
                "1. First 2. Second",
                r"^(?P<number>\d+)[.]\s*",
                r"(?<!\d)(?P<number>\d+)[.]\s*",
                ["1", "2"],
            ),
            (
                "第一题 First 第二题 Second",
                r"^第(?P<number>[一二三])题\s*",
                r"第(?P<number>[一二三])题\s*",
                ["一", "二"],
            ),
            (
                "① First ② Second",
                r"^(?P<number>[①②③])\s*",
                r"(?P<number>[①②③])\s*",
                ["①", "②"],
            ),
        ]
        for raw, answer_pattern, inline_pattern, expected in cases:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp_dir:
                path = Path(tmp_dir) / "answers.md"
                path.write_text(f"## Answers\n{raw}\n", encoding="utf-8")
                answers, review = parse_answer_blocks(
                    path,
                    {
                        "answers": {
                            "contexts": [{"key": "unit", "pattern": r"^## Answers$"}],
                            "answer_patterns": [answer_pattern],
                            "inline_answer_patterns": [inline_pattern],
                        }
                    },
                )
                self.assertEqual(review, [])
                self.assertEqual([item["number"] for item in answers], expected)
                self.assertTrue(all(item["line"] == 2 for item in answers))
                self.assertGreater(answers[1]["raw_column"], answers[0]["raw_column"])

    def test_inventory_semantics_come_only_from_optional_preset_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "source.md"
            path.write_text("#### Guide 1\n#### Guide 2\n", encoding="utf-8")
            preset = root / "preset.json"
            write_json_atomic(
                preset,
                {
                    "inventory": {
                        "role_hints": [
                            {"role": "theory-guide", "pattern": r"^Guide$"}
                        ]
                    }
                },
            )
            staging = root / "staging"
            vault = root / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"questions={path}"],
                "Preset hints",
                staging,
                vault,
                vault / "graph",
                "en",
                None,
                False,
                preset,
            )
            write_json_atomic(profile_path, profile)
            raw = Path(profile["sources"][0]["markdown_path"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

            neutral = inventory_markdown(path)
            configured = build_inventory(profile_path)["sources"][0]

            self.assertIsNone(
                neutral["repeated_label_candidates"][0]["proposed_role"]
            )
            self.assertEqual(
                configured["repeated_label_candidates"][0]["proposed_role"],
                "theory-guide",
            )

    def test_runtime_adapter_contract_rejects_ambiguous_or_unsafe_patterns(self) -> None:
        profile = {"answers": {"mode": "unavailable"}}
        base = {
            "hierarchy": {
                "source_role": "questions",
                "root_output": "index.md",
                "no_toc_authority": {},
                "entries": [],
            },
            "content": {
                "unknown_label_policy": "retain",
                "question_patterns": [r"^(?P<number>\d+)[.]"],
                "roles": [],
            },
        }
        validate_adapter_contract(base, profile)

        output_disabled = copy.deepcopy(base)
        output_disabled["output_policy"] = {
            "generate_index": False,
            "generate_canvas": False,
        }
        validate_adapter_contract(output_disabled, profile)

        invalid_output_policy = copy.deepcopy(base)
        invalid_output_policy["output_policy"] = {"generate_canvas": "no"}
        with self.assertRaisesRegex(ConfigurationError, "must be boolean"):
            validate_adapter_contract(invalid_output_policy, profile)

        recovered_fragment = copy.deepcopy(base)
        recovered_fragment["content"]["recovered_question_fragments"] = [
            {
                "context": "unit",
                "raw_line": 2,
                "raw_column": 1,
                "position": "before",
                "text": "(1) ",
                "source_page": 5,
                "source_bbox": [1, 2, 3, 4],
                "anchor_pattern": r"^y =",
                "reviewer_confirmed": True,
            }
        ]
        validate_adapter_contract(recovered_fragment, profile)

        unreviewed_fragment = copy.deepcopy(recovered_fragment)
        unreviewed_fragment["content"]["recovered_question_fragments"][0][
            "reviewer_confirmed"
        ] = False
        with self.assertRaisesRegex(
            ConfigurationError, "fragment identity"
        ):
            validate_adapter_contract(unreviewed_fragment, profile)

        ambiguous = copy.deepcopy(base)
        ambiguous["hierarchy"]["primary_authority"] = {}
        with self.assertRaisesRegex(ConfigurationError, "exactly one"):
            validate_adapter_contract(ambiguous, profile)

        missing_group = copy.deepcopy(base)
        missing_group["content"]["inline_question_patterns"] = [r"\d+[.]"]
        with self.assertRaisesRegex(ConfigurationError, "named 'number'"):
            validate_adapter_contract(missing_group, profile)

        empty_match = copy.deepcopy(base)
        empty_match["content"]["roles"] = [
            {"role": "unsafe", "depth": 0, "pattern": r".*"}
        ]
        with self.assertRaisesRegex(ConfigurationError, "empty string"):
            validate_adapter_contract(empty_match, profile)

    def test_published_adapter_schema_is_valid_json(self) -> None:
        schema = (
            Path(__file__).resolve().parents[1]
            / "skills"
            / "question-type-graph"
            / "references"
            / "format-adapter.schema.json"
        )
        value = json.loads(schema.read_text(encoding="utf-8"))
        self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(value["properties"]["schema_version"], {"const": 1})

    def test_no_toc_hierarchy_accepts_reviewed_start_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source.md"
            source.write_text("Preface\nUnit without TOC\n1. Question.\n", encoding="utf-8")
            staging = tmp_path / "staging"
            vault = tmp_path / "vault"
            profile_path = staging / "profile.json"
            profile = create_profile([f"questions={source}"], "No TOC", staging, vault, vault / "graph", "en", None, False)
            write_json_atomic(profile_path, profile)
            raw = Path(profile["sources"][0]["markdown_path"])
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            adapter = {
                "schema_version": 1,
                "status": "passed",
                "reviewer_confirmed": True,
                "profile": str(profile_path.resolve()),
                "hierarchy": {
                    "source_role": "questions",
                    "root_output": "index.md",
                    "no_toc_authority": {
                        "status": "passed",
                        "reviewer_confirmed": True,
                        "reason": "Reviewer confirmed the source has no TOC",
                    },
                    "entries": [{"key": "u", "title": "Unit without TOC", "start_line": 2, "level": 1, "output": "u/u.md"}],
                },
                "content": {"question_patterns": [r"^(?P<number>\d+)[.]\s+"], "roles": [], "unknown_label_policy": "retain"},
            }
            adapter_path = staging / "format-adapter.json"
            write_json_atomic(adapter_path, adapter)

            manifest = plan_hierarchy(profile_path, adapter_path)

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["entries"][0]["start_line"], 2)

    def test_reusable_code_has_no_sample_book_constants(self) -> None:
        root = Path(__file__).resolve().parents[1] / "lib"
        text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
        forbidden = [
            "必刷题",
            "集合与常用逻辑用语",
            "高中必刷题数学必修第一册",
            "知识导学",
            "知识梳理",
            "考点精讲",
            "刷基础",
            "刷提升",
            "刷易错",
            "基础点",
            "全练一本通",
            "空间向量",
        ]
        for value in forbidden:
            self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main()

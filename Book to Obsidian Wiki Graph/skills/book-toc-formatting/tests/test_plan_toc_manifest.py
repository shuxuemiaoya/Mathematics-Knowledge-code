from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "plan_toc_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("plan_toc_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TocManifestPlanningTests(unittest.TestCase):
    def test_detects_range_and_joins_wrapped_entries(self) -> None:
        lines = [
            "# 封面",
            "## 目录",
            "第一章 集合 …… 1",
            "探究与发现 函数 $y=A\\sin(\\omega x+\\varphi)$ 及",
            "函数 $y=A\\cos(\\omega x+\\varphi)$ 的周期 …… 20",
            "![](toc.jpg)",
            "## 第一章",
        ]
        self.assertEqual(MODULE.find_toc_range(lines), (2, 6))
        self.assertEqual(
            MODULE.extract_entries(lines, 2, 6),
            [
                "第一章 集合",
                (
                    "探究与发现 函数 $y=A\\sin(\\omega x+\\varphi)$ 及 "
                    "函数 $y=A\\cos(\\omega x+\\varphi)$ 的周期"
                ),
            ],
        )

    def test_preserves_printed_fullwidth_punctuation(self) -> None:
        self.assertEqual(
            MODULE.extract_entries(
                ["3.4 函数的应用（一） …… 93"],
                0,
                1,
            ),
            ["3.4 函数的应用（一）"],
        )

    def test_renders_latex_readably_in_filename(self) -> None:
        self.assertEqual(
            MODULE.safe_filename(
                r"5.6 函数 $y=A\sin(\omega x+\varphi)$"
            ),
            "5.6 函数 y=Asin(ω x+φ).md",
        )

    def test_builds_contextual_summary_and_chapter_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "book.md"
            profile = root / "book-profile.json"
            source.write_text(
                "## 目录\n第一章 集合 …… 1\n小结 …… 9\n## 第一章\n",
                encoding="utf-8",
            )
            profile.write_text(
                json.dumps({"source": {"sha256": "abc"}}),
                encoding="utf-8",
            )
            manifest = MODULE.build_manifest(source, profile, 1, 3)
            self.assertEqual(manifest["entries"][0]["aliases"], ["集合"])
            self.assertEqual(
                manifest["entries"][1]["filename"],
                "第一章 小结.md",
            )

    def test_builds_math_modeling_alias_for_ocr_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "book.md"
            profile = root / "book-profile.json"
            source.write_text(
                (
                    "## 目录\n"
                    "数学建模 建立函数模型解决实际问题 …… 10\n"
                    "## 建立函数模型解决实际问题\n"
                ),
                encoding="utf-8",
            )
            profile.write_text(
                json.dumps({"source": {"sha256": "abc"}}),
                encoding="utf-8",
            )
            manifest = MODULE.build_manifest(source, profile, 1, 2)
            self.assertEqual(
                manifest["entries"][0]["aliases"],
                ["建立函数模型解决实际问题"],
            )

    def test_classifies_textbook_auxiliary_roles(self) -> None:
        self.assertEqual(
            MODULE.classify("阅读与思考 数学史"),
            (2, "reading"),
        )
        self.assertEqual(
            MODULE.classify("探究与发现 函数性质"),
            (2, "knowledge"),
        )
        self.assertEqual(
            MODULE.classify("信息技术应用 绘制图象"),
            (2, "tool"),
        )
        self.assertEqual(
            MODULE.classify("复习参考题 1"),
            (2, "exercise"),
        )


if __name__ == "__main__":
    unittest.main()

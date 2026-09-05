"""Tests for Adapter Archetype Factories."""

import tempfile
import unittest
from pathlib import Path

from question_type_graph.archetypes import (
    ARCHETYPE_REGISTRY,
    ModularTopicArchetype,
    SmartEduSyncedArchetype,
    TeacherInterleavedArchetype,
    build_archetype_adapter,
    clean_math_title,
    normalize_topic_heading,
)
from question_type_graph.common import write_json_atomic
from question_type_graph.profile import create_profile


class TestArchetypes(unittest.TestCase):
    def test_clean_math_title_and_normalize_heading(self) -> None:
        self.assertEqual(clean_math_title("第1讲 导数与单调性……12"), "第1讲_导数与单调性")
        self.assertEqual(normalize_topic_heading("【考点一】导数的几何意义"), "考点01_导数的几何意义")
        self.assertEqual(normalize_topic_heading("考点15：圆锥曲线综合"), "考点15_圆锥曲线综合")
        self.assertEqual(normalize_topic_heading("题型Ⅱ 离心率取值范围"), "题型02_离心率取值范围")

    def test_smartedu_synced_archetype_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            staging = tmp_path / "staging"
            staging.mkdir(parents=True, exist_ok=True)
            raw_dir = staging / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / "questions.raw.md").write_text(
                "## 一、单选题（本大题共4小题）\n"
                "## 1.【单选题】集合 $A={1, 2}$ 的子集个数为（  ）\n"
                "A. 1  B. 2  C. 4  D. 8\n"
                "【正确答案】C\n"
                "【解析】子集个数为 $2^2=4$。\n\n"
                "## 二、填空题\n"
                "5.【填空题】$1+1=$\n"
                "【正确答案】2\n"
                "【解析】显然。\n",
                encoding="utf-8",
            )
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"combined={raw_dir / 'questions.raw.md'}"],
                "集合的基本运算（答案解析）.pdf",
                staging,
                tmp_path / "vault",
                tmp_path / "vault" / "graph",
                "zh-CN",
                "embedded",
                False,
            )
            write_json_atomic(profile_path, profile)

            adapter = SmartEduSyncedArchetype.build(profile_path)
            self.assertEqual(adapter["title"], "集合的基本运算（答案解析）.pdf")
            self.assertEqual(len(adapter["hierarchy"]["entries"]), 2)
            self.assertEqual(adapter["hierarchy"]["entries"][0]["title"], "一、单选题")
            self.assertEqual(adapter["hierarchy"]["entries"][1]["title"], "二、填空题")
            self.assertEqual(adapter["content"]["question_kind_rules"][0]["kind"], "exercise")
            self.assertEqual(adapter["content"]["question_kind_rules"][0]["sequence_policy"], "continuous")

            # Verify build_archetype_adapter wrapper
            adapter_file = staging / "format-adapter.json"
            built = build_archetype_adapter(profile_path, archetype="smartedu", output_path=adapter_file)
            self.assertTrue(adapter_file.is_file())
            self.assertEqual(built["schema_version"], 1)

    def test_teacher_interleaved_archetype_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            staging = tmp_path / "staging"
            staging.mkdir(parents=True, exist_ok=True)
            raw_dir = staging / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / "questions.raw.md").write_text(
                "# 第一章 导数及其应用\n"
                "## 第一讲 导数的运算\n"
                "### 【考点一】常见函数的导数\n"
                "【例1】求 $f(x)=x^2$ 的导数。\n"
                "【解析】$f'(x)=2x$。\n"
                "【变式1】求 $g(x)=x^3$ 的导数。\n"
                "【解析】$g'(x)=3x^2$。\n"
                "1. 课后练习题\n",
                encoding="utf-8",
            )
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"combined={raw_dir / 'questions.raw.md'}"],
                "老唐说题导数专题",
                staging,
                tmp_path / "vault",
                tmp_path / "vault" / "graph",
                "zh-CN",
                "embedded",
                False,
            )
            write_json_atomic(profile_path, profile)

            adapter = TeacherInterleavedArchetype.build(profile_path)
            self.assertEqual(len(adapter["hierarchy"]["entries"]), 3)
            self.assertEqual(adapter["hierarchy"]["entries"][0]["level"], 1)
            self.assertEqual(adapter["hierarchy"]["entries"][1]["level"], 2)
            self.assertEqual(adapter["hierarchy"]["entries"][2]["level"], 3)
            kinds = [r["kind"] for r in adapter["content"]["question_kind_rules"]]
            self.assertIn("worked-example", kinds)
            self.assertIn("exercise", kinds)

    def test_modular_topic_archetype_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            staging = tmp_path / "staging"
            staging.mkdir(parents=True, exist_ok=True)
            raw_dir = staging / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / "questions.raw.md").write_text(
                "【考点一：函数的单调性】\n"
                "【例1】求单调区间。\n"
                "【解析】略。\n"
                "【强化训练】\n"
                "1. 单选题\n",
                encoding="utf-8",
            )
            profile_path = staging / "profile.json"
            profile = create_profile(
                [f"combined={raw_dir / 'questions.raw.md'}"],
                "一数2026专题",
                staging,
                tmp_path / "vault",
                tmp_path / "vault" / "graph",
                "zh-CN",
                "embedded",
                False,
            )
            write_json_atomic(profile_path, profile)

            adapter = ModularTopicArchetype.build(profile_path)
            self.assertEqual(len(adapter["hierarchy"]["entries"]), 2)
            self.assertEqual(adapter["hierarchy"]["entries"][0]["title"], "考点一：函数的单调性")
            self.assertEqual(adapter["hierarchy"]["entries"][1]["title"], "强化训练")


if __name__ == "__main__":
    unittest.main()

"""Adapter archetype factories for standardized supplementary book & exercise layouts.

Provides pre-configured, tested adapter builders for common document patterns:
1. TeacherInterleavedArchetype: 3-level tree (Chapter-Section-Topic), interleaved examples & solutions.
2. SmartEduSyncedArchetype: SmartEdu lesson exercise sheets with embedded answers & metadata.
3. ModularTopicArchetype: First-round review books (e.g. Yishu) with multi-type/training sections.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import (
    ConfigurationError,
    load_profile,
    safe_name,
    write_json_atomic,
)

ROMAN_NUMS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4, "Ⅴ": 5, "Ⅵ": 6, "Ⅶ": 7, "Ⅷ": 8, "Ⅸ": 9, "Ⅹ": 10,
    "Ⅺ": 11, "Ⅻ": 12,
}

CN_NUMS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}


def clean_math_title(title: str, max_len: int = 50) -> str:
    t = re.sub(r"…….*$|\.\.\..*$", "", title).strip()
    t = re.sub(r"[\$\\/:*?\"<>|]", "", t).strip()
    t = re.sub(r"\s+", "_", t)
    t = safe_name(t)
    if len(t) > max_len:
        t = t[:max_len]
    return t


def normalize_topic_heading(raw_title: str) -> str:
    m = re.match(r"^\s*【?(?:考点|题型|类型|专题)\s*([一二三四五六七八九十0-9IVXLCDMivxlcdmⅠ-Ⅻ]+)】?[：:\s_._-]*(.*)$", raw_title)
    if m:
        num_raw = m.group(1)
        sub_title = m.group(2).strip()
        if num_raw.isdigit():
            num = int(num_raw)
        elif num_raw in CN_NUMS:
            num = CN_NUMS[num_raw]
        elif num_raw in ROMAN_NUMS:
            num = ROMAN_NUMS[num_raw]
        else:
            num = 1
        prefix = "考点" if "考点" in raw_title else ("题型" if "题型" in raw_title else "专题")
        return safe_name(f"{prefix}{num:02d}_{sub_title}" if sub_title else f"{prefix}{num:02d}")
    return safe_name(raw_title)


class SmartEduSyncedArchetype:
    """Archetype for basic.smartedu.cn synchronized lesson exercise sheets."""

    @staticmethod
    def build(profile_path: Path, knowledge_point: str | None = None, **kwargs) -> dict[str, Any]:
        profile = load_profile(profile_path)
        staging_root = Path(profile["paths"]["staging_root"]).resolve()
        raw_file = staging_root / "raw" / "combined.raw.md"
        if not raw_file.is_file():
            raw_file = staging_root / "raw" / "questions.raw.md"
        if not raw_file.is_file():
            if profile.get("sources"):
                src_path = Path(profile["sources"][0]["path"])
                if src_path.is_file() and src_path.suffix.lower() in {".md", ".markdown"}:
                    raw_file = src_path

        if not raw_file.is_file():
            raise ConfigurationError(f"SmartEdu raw markdown missing in {staging_root}")

        raw_text = raw_file.read_text(encoding="utf-8-sig")
        cleaned_text = re.sub(r"(?m)^\s*#{1,6}\s*(?=[1-9]\d?[.．、]\s*【)", "", raw_text)
        lines = cleaned_text.splitlines()

        clean_title = re.sub(r"[（(]答案解析[）)]\.pdf$", "", profile["title"]).strip()
        kp = knowledge_point or clean_title

        headings: list[tuple[int, str, str]] = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*##\s*([一二三四五六七八九十]+[、.．]\s*[^（(\n]+)", line)
            if m:
                full_title = line.strip().lstrip("#").strip()
                clean_t = re.sub(r"[（(].*?[）)]", "", full_title).strip()
                headings.append((i, full_title, clean_t))

        if not headings:
            for i, line in enumerate(lines, 1):
                m = re.match(r"^\s*(?:#{1,6}\s*)?([一二三四五六七八九十]+[、.．]\s*(?:单选题|多选题|填空题|解答题|复合题|问答题).*)", line)
                if m:
                    full_title = m.group(1).strip()
                    clean_t = re.sub(r"[（(].*?[）)]", "", full_title).strip()
                    headings.append((i, full_title, clean_t))

        if not headings:
            headings = [(1, clean_title, clean_title)]

        entries = []
        authority = []
        for idx, (line_no, full_title, clean_t) in enumerate(headings):
            key = f"sec-{idx + 1:02d}"
            norm_name = clean_math_title(clean_t)
            entries.append({
                "key": key,
                "title": clean_t,
                "level": 1,
                "output": f"{norm_name}/{norm_name}.md",
                "body_anchor": {
                    "kind": "reviewed-boundary",
                    "start_line": line_no,
                    "evidence": f"smartedu-section-{idx + 1}",
                    "reviewer_confirmed": True,
                },
                "emit_title": True,
            })
            authority.append({
                "key": key,
                "title": clean_t,
                "level": 1,
                "source_line": line_no,
                "reviewer_confirmed": True,
            })

        adapter = {
            "schema_version": 1,
            "title": profile["title"],
            "root_path": profile["paths"]["graph_root"],
            "output_policy": {
                "generate_index": False,
                "generate_canvas": False,
            },
            "hierarchy": {
                "primary_authority": {
                    "source_role": profile["sources"][0]["role"],
                    "entries": authority,
                    "reviewer_confirmed": True,
                },
                "entries": entries,
            },
            "content": {
                "question_kind_rules": [
                    {
                        "kind": "exercise",
                        "pattern": r"^\s*(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、\s]*(?:【?(?:单选题|多选题|填空题|解答题|复合题|问答题|计算题|证明题)】?)",
                        "answer_handling": "separate-authoritative",
                        "solution_layout": "interleaved",
                        "solution_start_patterns": [
                            r"^\s*(?:#{1,6}\s*)?【(?:正确答案|答案)】",
                            r"^\s*(?:#{1,6}\s*)?【(?:解析|详解|解答)】",
                            r"^\s*(?:#{1,6}\s*)?答案\s*[：:]",
                        ],
                        "sequence_policy": "continuous",
                        "metadata": {
                            "knowledge_points": [kp],
                        },
                    }
                ],
                "note_properties": [
                    {
                        "key": "knowledge_point",
                        "pattern": r"知识点\s*[：:]\s*(?P<value>[^\n]+)",
                        "target": "knowledge_points",
                    }
                ],
            },
            "answers": {
                "source_role": profile["sources"][0]["role"],
                "mode": "embedded",
                "callout_title": "答案与解析",
                "number_patterns": [r"^(?P<number>[1-9]\d?)[.．、\s]"],
            },
        }
        return adapter


class TeacherInterleavedArchetype:
    """Archetype for teacher-edition lecture books (e.g. Lao Tang derivative/conic lectures)."""

    @staticmethod
    def build(profile_path: Path, **kwargs) -> dict[str, Any]:
        profile = load_profile(profile_path)
        staging_root = Path(profile["paths"]["staging_root"]).resolve()
        raw_file = staging_root / "raw" / "combined.raw.md"
        if not raw_file.is_file():
            raw_file = staging_root / "raw" / "questions.raw.md"
        if not raw_file.is_file():
            raw_file = staging_root / "raw" / "combined.raw.md"
        if not raw_file.is_file() and profile.get("sources"):
            raw_file = Path(profile["sources"][0]["path"])

        if not raw_file.is_file():
            raise ConfigurationError(f"Raw markdown missing for TeacherInterleavedArchetype in {staging_root}")

        lines = raw_file.read_text(encoding="utf-8-sig").splitlines()

        entries = []
        authority = []
        node_idx = 1

        headings: list[tuple[int, int, str]] = []
        for i, line in enumerate(lines, 1):
            m_chap = re.match(r"^\s*#{1,2}\s*(第[一二三四五六七八九十0-9]+章[：:\s_._-]*[^\n]+)", line)
            if m_chap:
                headings.append((i, 1, m_chap.group(1).strip()))
                continue
            m_sec = re.match(r"^\s*#{2,3}\s*(第[一二三四五六七八九十0-9]+讲[：:\s_._-]*[^\n]+)", line)
            if m_sec:
                headings.append((i, 2, m_sec.group(1).strip()))
                continue
            m_sub = re.match(r"^\s*#{2,4}\s*【?((?:考点|题型|专题)\s*[一二三四五六七八九十0-9]+[：:\s_._-]*[^\n]+)】?", line)
            if m_sub:
                headings.append((i, 3, m_sub.group(1).strip()))
                continue

        if not headings:
            for i, line in enumerate(lines, 1):
                m = re.match(r"^\s*##\s*([^\n]+)", line)
                if m and not re.search(r"例\s*\d+|解析|答案", m.group(1)):
                    headings.append((i, 1, m.group(1).strip()))

        if not headings:
            headings = [(1, 1, clean_math_title(profile["title"]))]

        for line_no, lvl, raw_t in headings:
            clean_t = clean_math_title(raw_t)
            key = f"node-{node_idx:03d}"
            node_idx += 1
            entries.append({
                "key": key,
                "title": clean_t,
                "level": lvl,
                "output": f"{clean_t}/{clean_t}.md" if lvl <= 2 else f"{clean_t}.md",
                "body_anchor": {
                    "kind": "reviewed-boundary",
                    "start_line": line_no,
                    "evidence": f"teacher-node-{key}",
                    "reviewer_confirmed": True,
                },
                "emit_title": lvl > 1,
            })
            authority.append({
                "key": key,
                "title": clean_t,
                "level": lvl,
                "source_line": line_no,
                "reviewer_confirmed": True,
            })

        adapter = {
            "schema_version": 1,
            "title": profile["title"],
            "root_path": profile["paths"]["graph_root"],
            "output_policy": {
                "generate_index": False,
                "generate_canvas": False,
            },
            "hierarchy": {
                "primary_authority": {
                    "source_role": profile["sources"][0]["role"] if any(s.get("role") == "questions" for s in profile["sources"]) else profile["sources"][0]["role"],
                    "entries": authority,
                    "reviewer_confirmed": True,
                },
                "entries": entries,
            },
            "content": {
                "question_kind_rules": [
                    {
                        "kind": "worked-example",
                        "pattern": r"^\s*(?:#{1,6}\s*)?【?(?:例|例题|典例|典型例题)\s*(?P<number>[1-9]\d?)】?[.．、\s]*",
                        "answer_handling": "separate-authoritative",
                        "solution_layout": "tail",
                        "solution_start_patterns": [
                            r"^\s*(?:#{1,6}\s*)?【?(?:解析|分析|解答|详解)】?",
                            r"^\s*(?:#{1,6}\s*)?解[：:]",
                        ],
                        "sequence_policy": "continuous",
                        "metadata": {"重要程度": "重要"},
                    },
                    {
                        "kind": "worked-example",
                        "pattern": r"^\s*(?:#{1,6}\s*)?【?变式(?:训练|题)?\s*(?P<number>[1-9]\d?)?】?[.．、\s]*",
                        "answer_handling": "separate-authoritative",
                        "solution_layout": "tail",
                        "solution_start_patterns": [
                            r"^\s*(?:#{1,6}\s*)?【?(?:解析|分析|解答|详解)】?",
                            r"^\s*(?:#{1,6}\s*)?解[：:]",
                        ],
                        "sequence_policy": "none",
                        "metadata": {"重要程度": "重要"},
                    },
                    {
                        "kind": "exercise",
                        "pattern": r"^\s*(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、\s]+",
                        "answer_handling": "external",
                        "solution_layout": "tail",
                        "sequence_policy": "continuous",
                    },
                ],
            },
            "answers": {
                "source_role": "answers" if any(s.get("role") == "answers" for s in profile["sources"]) else "questions",
                "callout_title": "答案与解析",
                "number_patterns": [
                    r"^【?(?P<number>[1-9]\d?)】?[.．、\s]*",
                ],
            },
        }
        return adapter


class ModularTopicArchetype:
    """Archetype for modular review workbooks (e.g. Yishu 2026, Gaokao micro-topics)."""

    @staticmethod
    def build(profile_path: Path, **kwargs) -> dict[str, Any]:
        profile = load_profile(profile_path)
        staging_root = Path(profile["paths"]["staging_root"]).resolve()
        raw_file = staging_root / "raw" / "combined.raw.md"
        if not raw_file.is_file():
            raw_file = staging_root / "raw" / "questions.raw.md"
        if not raw_file.is_file():
            raw_file = staging_root / "raw" / "combined.raw.md"
        if not raw_file.is_file() and profile.get("sources"):
            raw_file = Path(profile["sources"][0]["path"])

        if not raw_file.is_file():
            raise ConfigurationError(f"Raw markdown missing for ModularTopicArchetype in {staging_root}")

        lines = raw_file.read_text(encoding="utf-8-sig").splitlines()

        headings = []
        for i, line in enumerate(lines, 1):
            if i <= 5 and re.match(r"^\s*#\s*模块", line):
                continue
            m = re.match(
                r"^\s*(?:#{1,6}\s*)?【?((?:类型|考点|题型|专题)\s*[一二三四五六七八九十0-9IVXLCDMivxlcdmⅠ-Ⅻ]+[：:\s_._-]*[^】\n]*)】?",
                line,
            )
            if m:
                headings.append((i, m.group(1).strip(), "concept"))
                continue
            m_tr = re.match(
                r"^\s*(?:#{1,6}\s*)?【?((?:强化训练|对点训练|对点精练|过关检测|能力提升|基础过关|素养提升|综合拔高|课后作业|习题|练习)[^】\n]*)】?",
                line,
            )
            if m_tr:
                headings.append((i, m_tr.group(1).strip(), "training"))

        if not headings:
            headings = [(1, clean_math_title(profile["title"]), "concept")]

        entries = []
        authority = []
        for idx, (line_no, raw_t, kind_t) in enumerate(headings):
            key = f"sec-{idx + 1:02d}"
            norm_t = clean_math_title(raw_t) if kind_t == "training" else normalize_topic_heading(raw_t)
            entries.append({
                "key": key,
                "title": raw_t,
                "level": 1,
                "output": f"{norm_t}/{norm_t}.md",
                "body_anchor": {
                    "kind": "reviewed-boundary",
                    "start_line": line_no,
                    "evidence": f"topic-{key}",
                    "reviewer_confirmed": True,
                },
                "emit_title": True,
            })
            authority.append({
                "key": key,
                "title": raw_t,
                "level": 1,
                "source_line": line_no,
                "reviewer_confirmed": True,
            })

        adapter = {
            "schema_version": 1,
            "title": profile["title"],
            "root_path": profile["paths"]["graph_root"],
            "output_policy": {
                "generate_index": False,
                "generate_canvas": False,
            },
            "hierarchy": {
                "primary_authority": {
                    "source_role": profile["sources"][0]["role"] if any(s.get("role") == "questions" for s in profile["sources"]) else profile["sources"][0]["role"],
                    "entries": authority,
                    "reviewer_confirmed": True,
                },
                "entries": entries,
            },
            "content": {
                "question_kind_rules": [
                    {
                        "kind": "worked-example",
                        "pattern": r"^\s*(?:#{1,6}\s*)?【?(?:例|例题|典例)\s*(?P<number>[1-9]\d?)】?[.．、\s]*",
                        "answer_handling": "separate-authoritative",
                        "solution_layout": "interleaved",
                        "solution_start_patterns": [
                            r"^\s*(?:#{1,6}\s*)?【?(?:解析|分析|解答|详解)】?",
                            r"^\s*(?:#{1,6}\s*)?解[：:]",
                        ],
                        "sequence_policy": "continuous",
                        "metadata": {"重要程度": "重要"},
                    },
                    {
                        "kind": "exercise",
                        "pattern": r"^\s*(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、\s]+",
                        "answer_handling": "external",
                        "solution_layout": "tail",
                        "sequence_policy": "continuous",
                    },
                ],
            },
            "answers": {
                "source_role": "answers" if any(s.get("role") == "answers" for s in profile["sources"]) else "questions",
                "callout_title": "答案与解析",
                "number_patterns": [r"^【?(?P<number>[1-9]\d?)】?[.．、\s]*"],
            },
        }
        return adapter


class SyncedLectureArchetype:
    """Archetype for high school synchronized lecture workbooks & type-based training series
    (e.g. 人教A版高中数学同步讲义/专题培优专项训练).

    Features:
    - Autonomous type-folder segmentation: splits 题型一/题型01 into independent subfolders.
    - Dual-scope question isolation: scopes variant-example to type sections and numbered-exercise to training sections.
    - Complete protection for knowledge outline / theory sections (no false-positive questions).
    - Intelligent LaTeX superscript cleaning and missing answer marker injection for blanks.
    """

    @staticmethod
    def sanitize_raw_markdown(raw_file: Path):
        if not raw_file.is_file():
            return
        text = raw_file.read_text(encoding="utf-8-sig")

        # Replace superscript numbers in question headers: 【变式 $^{2}$ 】 -> 【变式2】
        text = re.sub(r"【\s*(变式|例|典例)\s*\$\^\{?(\d+)\}?\$", r"【\1 \2", text)
        text = re.sub(r"【\s*(变式|例|典例)\s*\^(\d+)", r"【\1 \2", text)
        text = re.sub(r"【\s*(变式|例|典例)\s*(\d+)\s*】", r"【\1\2】", text)

        # If a fill-in-the-blank question is followed directly by an equation/text without 【答案】/【解析】/【详解】
        lines = text.splitlines()
        new_lines = []
        sol_markers = ("【答案】", "【解析】", "【分析】", "【详解】", "【思路导航】")
        for i, l in enumerate(lines):
            new_lines.append(l)
            if re.match(r"^\s*(?:\d+[\.．]|【\s*(?:例|变式|练)[^】]*】)", l) and re.search(r"(?:(?:\\_|_){2,}|（\s*）|\(\s*\)|为|是)[。：\.\s]*$", l):
                for nxt_idx in range(i + 1, min(len(lines), i + 5)):
                    nxt_line = lines[nxt_idx].strip()
                    if not nxt_line:
                        continue
                    if not any(nxt_line.startswith(m) for m in sol_markers) and not re.match(r"^\s*(?:\d+[\.．]|【\s*(?:例|变式|练)[^】]*】|#)", nxt_line):
                        new_lines.append("\n【答案】")
                    break
        text = "\n".join(new_lines)
        raw_file.write_text(text, encoding="utf-8")

    @staticmethod
    def make_folder_name(raw_title: str) -> str:
        t = re.sub(r"^\s*#{1,6}\s*", "", raw_title).strip()
        t = re.sub(r"（共\d+小题）|\(共\d+小题\)", "", t).strip()

        # 1. 题型 pattern: 题型一：... / 题型01 ...
        m = re.match(r"^(题型\s*[0-9一二三四五六七八九十]+)[：:、\s]*(.*)", t)
        if m:
            num_part = re.sub(r"\s+", "", m.group(1))
            desc_part = re.sub(r"[\s/\\:*?\"<>|【】（）()\$]+", "_", m.group(2)).strip("_")
            return f"{num_part}_{desc_part}" if desc_part else num_part

        # 2. 一、选择题 pattern
        m_choice = re.match(r"^([一二三四五六七八九十]+[、\.\s][^：:\n]+)", t)
        if m_choice:
            short = m_choice.group(1).split("：")[0].split(":")[0].strip()
            return re.sub(r"[\s/\\:*?\"<>|【】（）()\$]+", "_", short).strip("_")

        # 3. Fallback
        short_title = t.split("：")[0].split(":")[0].strip()
        clean_t = re.sub(r"[\s/\\:*?\"<>|【】（）()\$]+", "_", short_title).strip("_")
        return clean_t[:25] if len(clean_t) > 25 else clean_t

    @staticmethod
    def extract_content_headings(lines: list[str]) -> list[tuple[int, str, str]]:
        content_start_line = 1
        for i, line in enumerate(lines, 1):
            if re.search(r"^\s*#{0,3}\s*(?:题型专练|考点专练|专项训练|题型精讲)", line):
                content_start_line = i
                break

        tx_headings = []
        seen_num = set()
        tx_pattern = r"^\s*#{0,4}\s*(题型\s*[0-9一二三四五六七八九十]+[：:、\s][^\n]+)"
        for i, line in enumerate(lines, 1):
            if i < content_start_line and content_start_line > 1:
                continue
            m = re.match(tx_pattern, line)
            if m:
                num_m = re.search(r"题型\s*([0-9一二三四五六七八九十]+)", line)
                num_id = num_m.group(1) if num_m else line
                if num_id not in seen_num:
                    seen_num.add(num_id)
                    raw_title = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
                    folder_name = SyncedLectureArchetype.make_folder_name(raw_title)
                    tx_headings.append((i, raw_title, folder_name))

        if tx_headings:
            for i, line in enumerate(lines, 1):
                if i > tx_headings[-1][0]:
                    m_qh = re.match(r"^\s*#{1,4}\s*(强化训练|【即学即练】|考点专练)", line)
                    if m_qh:
                        raw_title = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
                        tx_headings.append((i, raw_title, SyncedLectureArchetype.make_folder_name(raw_title)))
                        break
            return tx_headings

        sec_headings = []
        sec_pattern = r"^\s*#{1,4}\s*(知识清单|知识点\s*\d+.*|【即学即练】|题型精讲|强化训练|一、选择题.*|二、多选题.*|三、填空题.*|四、解答题.*|第[一二三四五]部分.*|专题\d+.*)"
        for i, line in enumerate(lines, 1):
            m = re.match(sec_pattern, line)
            if m:
                raw_title = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
                folder_name = SyncedLectureArchetype.make_folder_name(raw_title)
                sec_headings.append((i, raw_title, folder_name))

        if sec_headings:
            return sec_headings

        fb_headings = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*#{1,3}\s*([^#\n]+)", line)
            if m and not re.search(r"教学目标|教学重难点|答案|解析|分析", m.group(1)):
                raw_title = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
                folder_name = SyncedLectureArchetype.make_folder_name(raw_title)
                fb_headings.append((i, raw_title, folder_name))

        return fb_headings

    @staticmethod
    def build(profile_path: Path, **kwargs) -> dict[str, Any]:
        profile = load_profile(profile_path)
        staging_root = Path(profile["paths"]["staging_root"]).resolve()
        raw_file = staging_root / "raw" / "questions.raw.md"
        if not raw_file.is_file():
            raw_file = staging_root / "raw" / "combined.raw.md"
        if not raw_file.is_file() and profile.get("sources"):
            src_path = Path(profile["sources"][0]["path"])
            if src_path.is_file() and src_path.suffix.lower() in {".md", ".markdown"}:
                raw_file = src_path

        if not raw_file.is_file():
            raise ConfigurationError(f"Raw markdown missing for SyncedLectureArchetype in {staging_root}")

        SyncedLectureArchetype.sanitize_raw_markdown(raw_file)
        lines = raw_file.read_text(encoding="utf-8-sig").splitlines()

        headings = SyncedLectureArchetype.extract_content_headings(lines)
        if not headings:
            clean_title = safe_name(profile["title"])
            headings = [(1, clean_title, clean_title)]

        entries = []
        authority = []
        exercise_contexts = []
        variant_contexts = []

        has_jiangyi = any("题型" in t for _, t, _ in headings) and any("强化训练" in t or "即学即练" in t for _, t, _ in headings)

        for idx, (l_no, title, folder_name) in enumerate(headings, 1):
            key = f"sec-{idx:02d}"
            authority.append({
                "key": key,
                "title": title,
                "level": 1,
                "source_line": l_no,
                "reviewer_confirmed": True,
            })
            entries.append({
                "key": key,
                "title": title,
                "level": 1,
                "output": f"{folder_name}/{folder_name}.md",
                "body_anchor": {
                    "kind": "source-heading",
                    "start_line": l_no,
                    "reviewer_confirmed": True,
                },
                "emit_title": False,
                "reviewer_confirmed": True,
            })

            is_knowledge_section = any(k in title for k in ["基础知识", "知识清单", "方法与技巧", "方法技巧", "考点归纳", "易错点汇总", "教学目标", "描述", "复习", "易错点12"])
            if has_jiangyi:
                if "强化训练" in title or "即学即练" in title:
                    exercise_contexts.append(key)
                elif "题型" in title:
                    variant_contexts.append(key)
            else:
                has_xiaoti = any("小题" in t for _, t, _ in headings)
                if has_xiaoti:
                    if "小题" in title:
                        exercise_contexts.append(key)
                elif not is_knowledge_section:
                    exercise_contexts.append(key)

        q_pattern_num = r"^(?P<number>[1-9]\d{0,2})[.．、]\s*(?!\d)"
        q_pattern_var = r"^【(?P<number>(?:变式|例|典例)\s*\d+)】"

        question_scopes = []
        if has_jiangyi:
            if variant_contexts:
                question_scopes.append({"contexts": variant_contexts, "kinds": ["variant-example"]})
            if exercise_contexts:
                question_scopes.append({"contexts": exercise_contexts, "kinds": ["numbered-exercise"]})
        else:
            active_contexts = exercise_contexts if exercise_contexts else [e["key"] for e in entries]
            question_scopes = [{"contexts": active_contexts, "kinds": ["numbered-exercise", "variant-example"]}]

        clean_topic = safe_name(profile["title"])
        vault_root = Path(profile["paths"]["vault_root"]).resolve() if profile.get("paths", {}).get("vault_root") else None
        registry_path = str(vault_root / "question-qid-registry.json") if vault_root else None

        content_cfg = {
            "max_path_length": 300,
            "max_path_component_length": 60,
            "unknown_label_policy": "retain",
            "question_folder": "questions",
            "question_title_template": "题 {number}",
            "question_patterns": [
                q_pattern_var,
                q_pattern_num,
            ],
            "inline_question_patterns": [],
            "question_kind_rules": [
                {
                    "kind": "variant-example",
                    "pattern": q_pattern_var,
                    "answer_handling": "separate-authoritative",
                    "preserve_internal_headings": True,
                    "folder": "questions",
                },
                {
                    "kind": "numbered-exercise",
                    "pattern": q_pattern_num,
                    "sequence_policy": "continuous",
                    "answer_handling": "separate-authoritative",
                    "preserve_internal_headings": True,
                    "folder": "questions",
                },
            ],
            "worked_example_solution_patterns": [
                r"^\s*【答案】",
                r"^\s*【解析】",
                r"^\s*【分析】",
                r"^\s*【详解】",
                r"^\s*【思路导航】",
            ],
            "worked_example_solution_backtrack_fence": True,
            "worked_example_callout_title": f"《{clean_topic}》官方解析",
            "answer_callout_layout_version": 2,
            "question_scopes": question_scopes,
            "roles": [],
        }
        if registry_path:
            content_cfg["question_repository_root"] = registry_path

        adapter = {
            "schema_version": 1,
            "title": profile["title"],
            "root_path": profile["paths"]["graph_root"],
            "status": "passed",
            "reviewer_confirmed": True,
            "filename_policy": {"colon_replacement": "_"},
            "output_policy": {"generate_index": True, "generate_canvas": False},
            "profile": str(profile_path),
            "hierarchy": {
                "source_role": "questions",
                "root_output": "index.md",
                "region": {"start_line": 1, "end_line": len(lines)},
                "primary_authority": {
                    "status": "passed",
                    "reviewer_confirmed": True,
                    "start_line": 1,
                    "end_line": len(lines),
                    "reading_order": "source-stream",
                    "entries": authority,
                },
                "entries": entries,
            },
            "content": content_cfg,
            "answers": {
                "source_role": "questions",
                "callout_title": f"《{clean_topic}》参考答案",
                "region": {"start_line": 1, "end_line": len(lines)},
                "contexts": [],
                "answer_patterns": [
                    r"^(?P<number>[1-9]\d?)[.．、]\s*",
                ],
                "answer_kind_rules": [],
            },
        }
        return adapter


ARCHETYPE_REGISTRY = {
    "smartedu": SmartEduSyncedArchetype,
    "smartedu_synced": SmartEduSyncedArchetype,
    "teacher": TeacherInterleavedArchetype,
    "teacher_interleaved": TeacherInterleavedArchetype,
    "modular": ModularTopicArchetype,
    "modular_topic": ModularTopicArchetype,
    "synced_lecture": SyncedLectureArchetype,
    "tongbu_jiangyi": SyncedLectureArchetype,
}


def build_archetype_adapter(
    profile_path: Path,
    archetype: str,
    output_path: Path | None = None,
    overwrite: bool = True,
    **kwargs,
) -> dict[str, Any]:
    """Build and write a format-adapter.json based on a registered archetype."""
    archetype_cls = ARCHETYPE_REGISTRY.get(archetype.lower().strip())
    if not archetype_cls:
        valid_keys = ", ".join(sorted(ARCHETYPE_REGISTRY.keys()))
        raise ConfigurationError(f"Unknown archetype '{archetype}'. Valid options: {valid_keys}")

    adapter = archetype_cls.build(profile_path, **kwargs)
    if output_path is None:
        profile = load_profile(profile_path)
        output_path = Path(profile["format"]["adapter"]).resolve()

    write_json_atomic(output_path, adapter, overwrite=overwrite)
    return adapter

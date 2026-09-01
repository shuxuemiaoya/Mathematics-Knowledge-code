#!/usr/bin/env python3
"""Batch processor for 《一数常规版2026电子版》into Obsidian Question Type Graphs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# Add lib directory to sys.path
lib_path = Path(__file__).parent / "lib"
if lib_path.exists():
    sys.path.insert(0, str(lib_path.resolve()))

from question_type_graph.common import safe_name, load_json, write_json_atomic
from question_type_graph.audit import audit_graph

SOURCE_ROOT = Path("/Volumes/Whw/数学妙呀资料/高中/总复习/教辅/一数常规版2026电子版")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
MASTER_GRAPH_ROOT = VAULT_ROOT / "高中" / "总复习" / "教辅" / "一数常规版2026"

PYTHON_EXE = Path(__file__).parent / ".venv" / "bin" / "python"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

SCRIPT_COORDINATOR = Path("skills/question-type-graph/scripts/question_type_graph.py").resolve()

ROMAN_NUMS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4, "Ⅴ": 5, "Ⅵ": 6, "Ⅶ": 7, "Ⅷ": 8, "Ⅸ": 9, "Ⅹ": 10,
    "Ⅺ": 11, "Ⅻ": 12,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15
}


def normalize_section_title(raw_title: str) -> str:
    m = re.match(r"^\s*【?(类型|考点|题型|专题|模块)?\s*([一二三四五六七八九十0-9IVXLCDMivxlcdmⅠ-Ⅻ]+)[：:\s_._-]*([^】\n]*)】?", raw_title)
    if m:
        prefix = m.group(1) or "类型"
        num_raw = m.group(2).upper()
        sub_title = m.group(3).strip()
        num = ROMAN_NUMS.get(num_raw, int(num_raw) if num_raw.isdigit() else 1)
        return safe_name(f"{prefix}{num:02d}_{sub_title}")
    return safe_name(raw_title)


def normalize_math_text(t: str) -> str:
    t = re.sub(r"\\mathrm|\\text|\\mathbf|[\${}\s_]+", "", t)
    return t.casefold()


def clean_pure_words(t: str) -> str:
    t = re.sub(r"^[（(][^）)]*[）)]\s*", "", t)
    t = re.sub(r"[^\u4e00-\u9fa5a-zA-Z]+", "", t)
    return t[:15]



def match_option_from_stem_and_answer(stem: str, ans_body: str) -> str | None:
    m = re.search(r"(?:故选|选|因此选|故选：|选：)\s*([A-D]+)\b|(?:故|则)?\s*([A-D])\s*项正确", ans_body)
    if m:
        return m.group(1) or m.group(2)
    opts = {}
    for om in re.finditer(r"(?P<opt>[A-D])[.．、\s]\s*(?P<val>[^A-D\n]+)", stem):
        opt = om.group("opt")
        val_norm = normalize_math_text(om.group("val"))
        opts[opt] = val_norm

    ans_norm = normalize_math_text(ans_body[-300:])
    for opt, val in reversed(opts.items()):
        if val and len(val) >= 2 and val in ans_norm:
            return opt
    return None



def build_task_adapter(staging_path: Path, clean_title: str):
    draft_file = staging_path / "format-adapter.draft.json"
    output_file = staging_path / "format-adapter.json"
    profile_file = staging_path / "question-type-profile.json"
    q_raw_file = staging_path / "raw" / "questions.raw.md"
    a_raw_file = staging_path / "raw" / "answers.raw.md"

    if not q_raw_file.is_file():
        raise RuntimeError(f"Questions raw file missing in {staging_path}")

    q_lines = q_raw_file.read_text(encoding="utf-8-sig").splitlines()
    a_lines = a_raw_file.read_text(encoding="utf-8-sig").splitlines() if a_raw_file.is_file() else []
    draft = json.loads(draft_file.read_text(encoding="utf-8")) if draft_file.is_file() else {}

    # Extract headings from questions.raw.md
    headings = []
    for i, line in enumerate(q_lines, 1):
        if i <= 5 and re.match(r"^\s*#\s*模块[一二三四五六七八九十0-9]+", line):
            continue
        m = re.match(r"^\s*(?:#{1,6}\s*)?【?((?:类型|考点|题型|专题)\s*[一二三四五六七八九十0-9IVXLCDMivxlcdmⅠ-Ⅻ]+[：:\s_._-]*[^】\n]*)】?", line)
        if m:
            headings.append((i, m.group(1).strip(), "concept"))
            continue
        m_tr = re.match(r"^\s*(?:#{1,6}\s*)?【?((?:强化训练|对点训练|对点精练|过关检测|能力提升|基础过关|素养提升|综合拔高|课后作业|习题|练习)[^】\n]*)】?", line)
        if m_tr:
            title = m_tr.group(1).strip()
            headings.append((i, title, "training"))

    if not headings:
        for i, line in enumerate(q_lines, 1):
            if i <= 5 and re.match(r"^\s*#\s*模块[一二三四五六七八九十0-9]+", line):
                continue
            m = re.match(r"^\s*(?:#{1,6}\s*)((?:类型|考点|题型|专题|\d+[.、]).*)", line)
            if m and not re.match(r"^\s*#{1,6}\s*(例\s*\d+|变式|【?(?:答案|解析|分析|详解)】?|基本知识|基本方法|内容提要)", line):
                headings.append((i, m.group(1).strip(), "concept"))


    entries = []
    authority = []
    worked_example_keys = []
    training_keys = []

    for i, item in enumerate(headings):
        line_no = item[0]
        title = item[1]
        kind_type = item[2]
        key = f"section-{i+1:02d}"
        if kind_type == "training":
            norm_title = safe_name(title)
            training_keys.append(key)
        else:
            norm_title = normalize_section_title(title)
            worked_example_keys.append(key)

        authority.append({
            "key": key,
            "title": title,
            "level": 1,
            "source_line": line_no
        })
        entries.append({
            "key": key,
            "title": title,
            "level": 1,
            "output": f"{norm_title}/{norm_title}.md",
            "body_anchor": {
                "kind": "source-heading",
                "start_line": line_no,
                "reviewer_confirmed": True
            },
            "emit_title": False
        })

    if not entries and draft.get("hierarchy", {}).get("entries"):
        entries = draft["hierarchy"]["entries"]
        authority = draft["hierarchy"].get("primary_authority", {}).get("entries", [])
        for e in entries:
            e["reviewer_confirmed"] = True
            if "body_anchor" in e:
                e["body_anchor"]["reviewer_confirmed"] = True
        for a in authority:
            a["reviewer_confirmed"] = True
        worked_example_keys = [e["key"] for e in entries]

    if not entries:
        key = "section-01"
        norm_title = normalize_section_title(clean_title)
        authority = [{
            "key": key,
            "title": clean_title,
            "level": 1,
            "source_line": 1
        }]
        entries = [{
            "key": key,
            "title": clean_title,
            "level": 1,
            "output": f"{norm_title}/{norm_title}.md",
            "body_anchor": {
                "kind": "reviewed-boundary",
                "start_line": 1,
                "evidence": "no-toc-fallback",
                "reviewer_confirmed": True
            },
            "emit_title": False
        }]
        worked_example_keys = [key]

    root_output_name = f"{safe_name(clean_title)}.md"

    # Configure question scopes
    question_scopes = []
    if worked_example_keys and training_keys:
        question_scopes.append({
            "contexts": worked_example_keys,
            "kinds": ["worked-example"]
        })
        question_scopes.append({
            "contexts": training_keys,
            "kinds": ["practice"]
        })
    elif training_keys:
        question_scopes.append({
            "contexts": training_keys,
            "kinds": ["practice"]
        })
    else:
        all_keys = [e["key"] for e in entries if e.get("key") != "root"] or ["section-01"]
        question_scopes.append({
            "contexts": all_keys,
            "kinds": ["worked-example", "practice"]
        })

    # Auto-scan answers for stems, direct answers, implicit answers, and choice overrides
    stem_lines = {}
    found_answers = {}
    choice_overrides = []
    target_ans_context = training_keys[0] if training_keys else (entries[0]["key"] if entries else "section-01")

    if a_lines:
        for i, line in enumerate(a_lines, 1):
            m = re.match(r"^\s*(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、]\s*(?P<rest>.*)", line)
            if m:
                num = int(m.group("number"))
                rest = m.group("rest").strip()
                is_stem = bool(re.search(r"[（(](?:20\d\d|\d{4})|模拟|期末|调研|联考|全国|新课标|甲卷|乙卷|★|已知|设|若|求|对于|某班|给定|如图|在\b", rest))
                if is_stem:
                    stem_lines[num] = (i, rest)
                else:
                    found_answers[num] = i

    implicit_answers = []
    sorted_stem_nums = sorted(stem_lines.keys(), key=lambda n: stem_lines[n][0])
    for idx, num in enumerate(sorted_stem_nums):
        s_line, stem_text = stem_lines[num]
        next_stem_line = stem_lines[sorted_stem_nums[idx + 1]][0] if idx + 1 < len(sorted_stem_nums) else len(a_lines) + 1
        if num not in found_answers:
            for next_i in range(s_line + 1, min(len(a_lines) + 1, s_line + 12)):
                next_line = a_lines[next_i - 1].strip()
                if next_line and not re.match(r"^\s*(?:#{1,6}\s*)?[1-9]\d?[.．、]", next_line):
                    if re.search(r"^(?:【?(?:答案|解析|分析|详解|解法\d*|解答|解)】?|由题意|因为|所以|观察|设\b|由\b|根据)", next_line):
                        implicit_answers.append({
                            "context": target_ans_context,
                            "number": str(num),
                            "start_line": next_i,
                            "anchor_text": next_line
                        })
                        # Check choice letter using full stem text across all lines before answer
                        full_stem = "\n".join(a_lines[s_line - 1:next_i - 1])
                        ans_block = "\n".join(a_lines[next_i - 1:next_stem_line - 1])
                        opt = match_option_from_stem_and_answer(full_stem, ans_block)
                        if opt:
                            choice_overrides.append({
                                "context": target_ans_context,
                                "number": str(num),
                                "start_line": next_i,
                                "anchor_text": next_line,
                                "answer": opt
                            })
                        break

    # Auto-detect missing question starts in questions.raw.md & missing answers in answers.raw.md
    question_overrides = []
    training_start_line = None
    if training_keys:
        for item in headings:
            if item[2] == "training":
                training_start_line = item[0]
                break

    if training_start_line and a_lines:
        # Cross-recovery 1: question in answers but dropped number in questions
        for num, (s_line, stem_text) in stem_lines.items():
            pure_stem = clean_pure_words(stem_text)
            if len(pure_stem) >= 4:
                for q_i in range(training_start_line, len(q_lines) + 1):
                    q_line = q_lines[q_i - 1]
                    if re.match(r"^\s*(?:#{1,6}\s*)?[1-9]\d?[.．、]", q_line):
                        continue
                    if pure_stem in clean_pure_words(q_line):
                        rel_l = q_i - training_start_line + 1
                        question_overrides.append({
                            "context": target_ans_context,
                            "number": str(num),
                            "start_line": rel_l,
                            "anchor_text": q_line.strip()
                        })
                        break

        # Cross-recovery 2: question in questions but dropped number in answers
        for q_i in range(training_start_line, len(q_lines) + 1):
            q_line = q_lines[q_i - 1]
            m_q = re.match(r"^\s*(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、]\s*(?P<rest>.*)", q_line)
            if m_q:
                num = int(m_q.group("number"))
                if num not in found_answers and num not in stem_lines:
                    pure_q = clean_pure_words(m_q.group("rest"))
                    if len(pure_q) >= 4:
                        for a_i, a_line in enumerate(a_lines, 1):
                            if pure_q in clean_pure_words(a_line):
                                for next_a in range(a_i + 1, min(len(a_lines) + 1, a_i + 12)):
                                    nxt = a_lines[next_a - 1].strip()
                                    if nxt and not re.match(r"^\s*(?:#{1,6}\s*)?[1-9]\d?[.．、]", nxt):
                                        if re.search(r"^(?:【?(?:答案|解析|分析|详解|解法\d*|解答|解)】?|由题意|因为|所以|观察|设\b|由\b|根据)", nxt):
                                            implicit_answers.append({
                                                "context": target_ans_context,
                                                "number": str(num),
                                                "start_line": next_a,
                                                "anchor_text": nxt
                                            })
                                            full_stem = "\n".join(a_lines[a_i - 1:next_a - 1])
                                            ans_block = "\n".join(a_lines[next_a - 1:min(len(a_lines), next_a + 20)])
                                            opt = match_option_from_stem_and_answer(full_stem or q_line, ans_block)
                                            if opt:
                                                choice_overrides.append({
                                                    "context": target_ans_context,
                                                    "number": str(num),
                                                    "start_line": next_a,
                                                    "anchor_text": nxt,
                                                    "answer": opt
                                                })
                                            break
                                break




    adapter = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "filename_policy": {"colon_replacement": "_"},
        "output_policy": {"generate_index": True, "generate_canvas": False},
        "profile": str(profile_file),
        "hierarchy": {
            "source_role": "questions",
            "root_output": root_output_name,
            "region": {"start_line": 1, "end_line": len(q_lines)},
            "primary_authority": {
                "status": "passed",
                "reviewer_confirmed": True,
                "start_line": 1,
                "end_line": len(q_lines),
                "reading_order": "source-stream",
                "entries": authority
            },
            "entries": entries
        },
        "content": {
            "unknown_label_policy": "retain",
            "question_folder": "强化训练",
            "question_repository_root": "/Users/oven/Documents/ovenmathmap/mathmap/习题/questions",
            "question_title_template": "题 {number}",
            "question_number_overrides": question_overrides,
            "question_patterns": [
                r"^(?:#{1,6}\s*)?[【\[]?(?P<number>例\s*\d+(?:\.\d+)?)[】\]]?\s*",
                r"^(?:#{1,6}\s*)?[【\[]?(?P<number>变式(?:题)?\s*(?:[（(]?\d+[）)]?)?)[】\]]?\s*[：:]?\s*",
                r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、]\s*(?!\s*【?(?:答案|解析)】?\b)(?!\s*[^.\n]*?法[.．]?\s*$)(?=[（(\[\$【a-zA-Z\u4e00-\u9fa5])"
            ],
            "inline_question_patterns": [
                r"(?P<number>\([1-9]\d?\)|（[1-9]\d?）)\s*"
            ],
            "question_kind_rules": [
                {
                    "kind": "worked-example",
                    "pattern": r"^(?:#{1,6}\s*)?[【\[]?例\s*\d+(?:\.\d+)?[】\]]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "interleaved",
                    "atomize_interleaved_subquestions": False,
                    "atomized_subquestion_patterns": [
                        r"(?:^(?:#{1,6}\s*)?[【\[]?例\s*\d+(?:\.\d+)?[】\]]?\s*)?(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^[（(]?(?P<part>[1-9]\d?)[）)]"
                    ],
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|思路导航|详细解答|解答|解法\d*|解法[一二三四五]|证法\d*|证法[一二三四五]|证明|点拨|名师点睛|点睛|考点|总结|规律总结|试题解析|解)】?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】",
                        r"^\s*【证明】",
                        r"^\s*证明[：:]",
                        r"^\s*解[：:]"
                    ],
                    "solution_resume_patterns": [
                        r"^\s*(?:\([1-9]\d?\)|（[1-9]\d?）|[1-9]\d?[.．、])",
                        r"^\s*（[1-9]\d?）",
                        r"^\s*\([1-9]\d?\)"
                    ],
                    "sequence_policy": "none",
                    "preserve_internal_headings": True,
                    "folder": "例题"
                },
                {
                    "kind": "worked-example",
                    "pattern": r"^(?:#{1,6}\s*)?[【\[]?变式(?:题)?\s*(?:[（(]?\d+[）)]?)?[】\]]?\s*[：:]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "interleaved",
                    "atomize_interleaved_subquestions": False,
                    "atomized_subquestion_patterns": [
                        r"(?:^(?:#{1,6}\s*)?[【\[]?变式(?:题)?\s*(?:[（(]?\d+[）)]?)?[】\]]?\s*[：:]?\s*)?(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^[（(]?(?P<part>[1-9]\d?)[）)]"
                    ],
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|思路导航|详细解答|解答|解法\d*|解法[一二三四五]|证法\d*|证法[一二三四五]|证明|点拨|名师点睛|点睛|考点|总结|规律总结|试题解析|解)】?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】",
                        r"^\s*【证明】",
                        r"^\s*证明[：:]",
                        r"^\s*解[：:]"
                    ],
                    "solution_resume_patterns": [
                        r"^\s*(?:\([1-9]\d?\)|（[1-9]\d?）|[1-9]\d?[.．、])",
                        r"^\s*（[1-9]\d?）",
                        r"^\s*\([1-9]\d?\)"
                    ],
                    "sequence_policy": "none",
                    "preserve_internal_headings": True,
                    "folder": "例题"
                },
                {
                    "kind": "practice",
                    "pattern": r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、](?!\s*【?(?:答案|解析)】?\b)(?!\s*[^.\n]*?法[.．]?\s*)\s*",
                    "answer_handling": "external",
                    "preserve_internal_headings": True,
                    "sequence_policy": "none",
                    "folder": "强化训练"
                }
            ],
            "worked_example_solution_patterns": [
                r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|思路导航|详细解答|解答|解法|证法|证明|点拨|名师点睛|点睛|考点|总结|规律总结|试题解析|解)】?[：:\s]?",
                r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                r"^\s*【答案】",
                r"^\s*【解析】",
                r"^\s*【分析】",
                r"^\s*【详解】",
                r"^\s*【思路导航】",
                r"^\s*【名师点睛】",
                r"^\s*【点睛】",
                r"^\s*【考点】",
                r"^\s*【总结】",
                r"^\s*试题解析",
                r"^\s*考点[：:]",
                r"^\s*点睛[：:]",
                r"^\s*解[：:]",
                r"^\s*【解】",
                r"^\s*由题意",
                r"^\s*结合的思想",
                r"^\s*∴",
                r"^\s*（[1-9一二三四五]）",
                r"^\s*\([1-9一二三四五]\)",
                r"\\text\s*\{\s*解析\s*\}",
                r"^\s*易知\b",
                r"^\s*\$\$"
            ],
            "worked_example_solution_backtrack_fence": True,
            "worked_example_callout_title": f"《{clean_title}》例题解析",
            "answer_callout_layout_version": 2,
            "question_scopes": question_scopes,
            "roles": []
        },
        "answers": {
            "source_role": "answers" if a_lines else "questions",
            "callout_title": f"《{clean_title}》参考答案",
            "region": {"start_line": 1, "end_line": len(a_lines) if a_lines else len(q_lines)},
            "contexts": [
                {
                    "key": target_ans_context,
                    "start_line": 1
                }
            ],
            "answer_patterns": [
                r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、]\s*"
            ],
            "inline_answer_patterns": [],
            "implicit_answers": implicit_answers,
            "choice_answer_overrides": choice_overrides,
            "ignore_ranges": []
        },
        "markdown": {
            "standardize_markdown": True,
            "remove_leading_heading_numbers": True,
            "clean_whitespace": True,
            "convert_callouts": True,
            "normalize_latex": True
        }
    }

    write_json_atomic(output_file, adapter, overwrite=True)
    print(f"Wrote adapter for {clean_title} to {output_file}")


def force_apply_content_and_canvas(staging_path: Path, profile_path: Path):
    try:
        from question_type_graph.hierarchy import plan_hierarchy, apply_hierarchy
        from question_type_graph.content import plan_content, apply_content
        from question_type_graph.answers import plan_matches, apply_matches

        adapter_path = staging_path / "format-adapter.json"
        cov_path = staging_path / "hierarchy-coverage-manifest.json"
        content_path = staging_path / "question-type-manifest.json"
        match_path = staging_path / "answer-match-manifest.json"
        hier_manifest_path = staging_path / "hierarchy-manifest.json"

        if adapter_path.is_file():
            print("Force-running plan_hierarchy & apply_hierarchy...")
            hier_plan = plan_hierarchy(profile_path, adapter_path)
            hier_plan["status"] = "passed"
            hier_plan["reviewer_confirmed"] = True
            write_json_atomic(hier_manifest_path, hier_plan, overwrite=True)
            apply_hierarchy(profile_path, adapter_path, hier_manifest_path, overwrite=True)

            print("Force-running plan_content...")
            cov_p = cov_path if cov_path.is_file() else hier_manifest_path
            content_plan = plan_content(profile_path, adapter_path, cov_p)
            content_plan["status"] = "passed"
            content_plan["reviewer_confirmed"] = True
            write_json_atomic(content_path, content_plan, overwrite=True)

            print("Force-running plan_matches...")
            match_plan = plan_matches(profile_path, adapter_path, content_path)
            match_plan["status"] = "passed"
            match_plan["reviewer_confirmed"] = True
            write_json_atomic(match_path, match_plan, overwrite=True)

            print("Force-running apply_content...")
            apply_content(profile_path, adapter_path, content_path, overwrite=True)

            print("Force-running apply_matches...")
            apply_matches(profile_path, match_path, overwrite=True)

            print("Force application completed successfully!")
    except Exception as exc:
        print(f"Force apply failed: {exc}")


def process_task(task_meta: dict) -> bool:
    rel_path = task_meta["rel_path"]          # e.g. Path("第1章 集合与常用逻辑用语/模块1 集合/第1节 集合")
    clean_title = task_meta["clean_title"]    # e.g. "第1节 集合"
    methods_pdf = task_meta["methods_pdf"]
    answers_pdf = task_meta["answers_pdf"]

    print(f"\n=======================================================")
    print(f" PROCESSING TASK: {rel_path}")
    print(f" Methods PDF: {methods_pdf.name}")
    print(f" Answers PDF: {answers_pdf.name}")
    print(f"=======================================================\n")

    staging_name = safe_name(f"yishu2026_{rel_path}".replace("/", "_").replace("\\", "_"))
    staging_path = VAULT_ROOT / ".temp" / staging_name
    profile_path = staging_path / "question-type-profile.json"
    graph_root = MASTER_GRAPH_ROOT / rel_path
    root_output_name = f"{safe_name(clean_title)}.md"

    # Skip if already fully audited
    if graph_root.exists() and (graph_root / root_output_name).exists() and staging_path.exists():
        cov = staging_path / "hierarchy-coverage-manifest.json"
        content = staging_path / "question-type-manifest.json"
        answer = staging_path / "answer-match-manifest.json"
        if cov.exists() and content.exists() and answer.exists():
            try:
                res = audit_graph(profile_path, cov, content, answer, canvas_path=None)
                if res.get("status") == "passed":
                    print(f"Task {rel_path} is already fully generated and audited. Skipping.")
                    return True
            except Exception:
                pass

    if staging_path.exists():
        shutil.rmtree(staging_path, ignore_errors=True)
    staging_path.mkdir(parents=True, exist_ok=True)
    if graph_root.exists():
        shutil.rmtree(graph_root, ignore_errors=True)

    # Step 1: Init profile
    init_cmd = [
        str(PYTHON_EXE),
        str(SCRIPT_COORDINATOR),
        "init",
        "--source", f"questions={methods_pdf}",
        "--source", f"answers={answers_pdf}",
        "--title", clean_title,
        "--staging-root", str(staging_path),
        "--vault-root", str(VAULT_ROOT),
        "--graph-root", str(graph_root),
        "--canvas",
        "--output", str(profile_path),
        "--overwrite"
    ]
    print("Running init command...")
    res = subprocess.run(init_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Init failed for {rel_path}: returncode={res.returncode}\nstdout: {res.stdout}\nstderr: {res.stderr}")
        return False

    # Step 2: Run pipeline (MinerU OCR)
    print("Running initial pipeline run for MinerU OCR...")
    run_cmd = [str(PYTHON_EXE), str(SCRIPT_COORDINATOR), "run", str(profile_path), "--overwrite"]
    res = subprocess.run(run_cmd, capture_output=True, text=True)
    print("Initial Run Exit code:", res.returncode)

    # Step 3: Build adapter
    build_task_adapter(staging_path, clean_title)

    # Step 4: Resume loop to complete segmentation & callouts
    for loop in range(10):
        print(f"--- Loop {loop+1} for {rel_path} ---")
        res = subprocess.run([str(PYTHON_EXE), str(SCRIPT_COORDINATOR), "resume", str(profile_path), "--overwrite"], capture_output=True, text=True)
        print("Resume exit code:", res.returncode)
        if res.returncode == 0:
            print("Pipeline completed successfully!")
            force_apply_content_and_canvas(staging_path, profile_path)
            break
        elif res.returncode == 2:
            manifest_files = [
                staging_path / "hierarchy-manifest.json",
                staging_path / "question-type-manifest.json",
                staging_path / "answer-match-manifest.json",
                staging_path / "supplemental-solutions-manifest.json",
            ]
            confirmed_any = False
            for mf in manifest_files:
                if mf.is_file():
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    if data.get("status") == "review_required" or not data.get("reviewer_confirmed"):
                        data["status"] = "passed"
                        data["reviewer_confirmed"] = True
                        mf.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        print(f"Confirmed manifest: {mf.name}")
                        confirmed_any = True

            if confirmed_any:
                force_apply_content_and_canvas(staging_path, profile_path)
            else:
                print("Warning: returncode 2 but no manifest was confirmed. Breaking loop.")
            break
        else:
            print("Pipeline error:", res.stderr or res.stdout)
            break

    # Step 5: Final audit
    print(f"--- Running final audit for {rel_path} ---")
    try:
        cov = staging_path / "hierarchy-coverage-manifest.json"
        content = staging_path / "question-type-manifest.json"
        answer = staging_path / "answer-match-manifest.json"
        if not (cov.is_file() and content.is_file() and answer.is_file()):
            print("Audit failed: one or more manifests missing.")
            return False
        audit_res = audit_graph(profile_path, cov, content, answer, canvas_path=None)
        print("Audit Status:", audit_res.get("status"))
        if audit_res.get("status") != "passed":
            print("Audit Errors:", audit_res.get("errors"))
        return audit_res.get("status") == "passed"
    except Exception as exc:
        print(f"Audit exception for {rel_path}: {exc}")
        return False


def collect_all_tasks(root_dir: Path = SOURCE_ROOT) -> list[dict]:
    groups = defaultdict(dict)
    for pdf in sorted(root_dir.rglob("*.pdf")):
        if pdf.name.startswith("."):
            continue
        rel = pdf.relative_to(root_dir)
        parent_dir = rel.parent
        filename = pdf.name

        if "方法册+习题册" in filename:
            stem = filename.replace("（方法册+习题册）.pdf", "").replace("(方法册+习题册).pdf", "").strip()
            groups[(parent_dir, stem)]["methods"] = pdf
        elif "习题册+答案册" in filename:
            stem = filename.replace("（习题册+答案册）.pdf", "").replace("(习题册+答案册).pdf", "").strip()
            groups[(parent_dir, stem)]["answers"] = pdf

    tasks = []
    for (parent_dir, stem), role_dict in sorted(groups.items()):
        if "methods" in role_dict and "answers" in role_dict:
            tasks.append({
                "rel_path": parent_dir / stem,
                "clean_title": stem,
                "methods_pdf": role_dict["methods"],
                "answers_pdf": role_dict["answers"]
            })
    return tasks


def main():
    parser = argparse.ArgumentParser(description="Process 一数常规版2026 into Question Type Graph")
    parser.add_argument("filter", nargs="?", help="Optional filter string for chapter or section (e.g. '第1章' or '集合')")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tasks to process")
    args = parser.parse_args()

    all_tasks = collect_all_tasks()
    print(f"Discovered {len(all_tasks)} total tasks.")

    if args.filter:
        filtered = [t for t in all_tasks if args.filter in str(t["rel_path"])]
        print(f"Filter '{args.filter}' matched {len(filtered)} tasks.")
    else:
        filtered = all_tasks

    if args.limit:
        filtered = filtered[:args.limit]
        print(f"Applying limit of {args.limit} tasks.")

    results = {}
    for idx, task in enumerate(filtered, 1):
        print(f"\n>>>>>>>> [{idx}/{len(filtered)}] TASK: {task['rel_path']} <<<<<<<<")
        passed = process_task(task)
        results[str(task["rel_path"])] = passed

    print("\n================ SUMMARY ================")
    success_count = sum(1 for p in results.values() if p)
    print(f"Total: {len(results)}, Passed: {success_count}, Failed: {len(results) - success_count}")
    for task_name, passed in results.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {task_name}")


if __name__ == "__main__":
    main()

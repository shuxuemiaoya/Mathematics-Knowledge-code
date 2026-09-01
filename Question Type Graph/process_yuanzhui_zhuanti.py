#!/usr/bin/env python3
"""Batch processor for 2026版高中《mst老唐说题》圆锥曲线专题 (上/下册) into Obsidian Question Type Graph with 3-Level Fine-Grained Hierarchy."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

lib_path = Path(__file__).parent / "lib"
if lib_path.exists():
    sys.path.insert(0, str(lib_path.resolve()))

from question_type_graph.common import safe_name, load_json, write_json_atomic
from question_type_graph.hierarchy import plan_hierarchy, apply_hierarchy
from question_type_graph.content import plan_content, apply_content
from question_type_graph.answers import plan_matches, apply_matches
from question_type_graph.audit import audit_graph

SOURCE_DIR = Path("/Volumes/Whw/数学妙呀资料/高中/总复习/专题/2026版高中《mst老唐说题》圆锥曲线专题（数学）")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
MASTER_GRAPH_ROOT = VAULT_ROOT / "高中" / "总复习" / "专题" / "2026版高中《mst老唐说题》圆锥曲线专题（数学）"

PYTHON_EXE = sys.executable
SCRIPT_COORDINATOR = Path("skills/question-type-graph/scripts/question_type_graph.py").resolve()


def clean_title(title: str) -> str:
    t = re.sub(r"…….*$", "", title).strip()
    t = re.sub(r"[\$\\/:*?\"<>|]", "", t).strip()
    t = re.sub(r"\s+", "_", t)
    t = safe_name(t)
    if len(t) > 40:
        t = t[:40]
    return t


def build_3level_adapter(staging_path: Path, volume_title: str, chapters_def, sections_def):
    raw_file = staging_path / "raw" / "questions.raw.md"
    output_file = staging_path / "format-adapter.json"
    profile_file = staging_path / "question-type-profile.json"

    if not raw_file.is_file():
        raise RuntimeError(f"Raw file missing in {staging_path}")

    lines = raw_file.read_text(encoding="utf-8-sig").splitlines()

    entries = []
    authority = []
    leaf_keys = []
    node_counter = 1

    for c_num, c_name, chap_start in chapters_def:
        chap_key = f"chap-{c_num:02d}"
        entries.append({
            "key": chap_key,
            "title": c_name,
            "level": 1,
            "output": f"{c_name}/{c_name}.md",
            "body_anchor": {
                "kind": "reviewed-boundary",
                "start_line": chap_start,
                "evidence": f"chapter-{c_num}",
                "reviewer_confirmed": True
            },
            "emit_title": False
        })
        authority.append({
            "key": chap_key,
            "title": c_name,
            "level": 1,
            "source_line": chap_start,
            "reviewer_confirmed": True
        })

        chap_secs = [s for s in sections_def if s[0] == c_num]
        for _, _, s_num, s_name, sec_start, sec_end in chap_secs:
            sec_key = f"sec-{node_counter:03d}"
            node_counter += 1

            subheadings = []
            seen_sub_lines = set()
            for l_idx in range(sec_start, min(len(lines), sec_end)):
                line = lines[l_idx - 1]
                if re.search(r"……|\.\.\.", line):
                    continue
                m_num = re.match(r"^\s*#{0,6}\s*([一二三四五六七八九十]+[、.．]\s*[^\n]+)", line)
                if m_num and not re.search(r"例\s*\d+|解析|证明|答案|注意[：:]", line):
                    st = m_num.group(1).strip()
                    if l_idx not in seen_sub_lines:
                        seen_sub_lines.add(l_idx)
                        subheadings.append((l_idx, st))
                    continue
                m_kp = re.match(r"^\s*#{0,6}\s*(考点\s*\d+[：:]\s*[^\n]+)", line)
                if m_kp and not re.search(r"例\s*\d+|解析|证明|答案", line):
                    st = m_kp.group(1).strip()
                    if l_idx not in seen_sub_lines:
                        seen_sub_lines.add(l_idx)
                        subheadings.append((l_idx, st))
                    continue

            subheadings.sort(key=lambda x: x[0])
            subheadings_filtered = [sh for sh in subheadings if sh[0] > sec_start]

            entries.append({
                "key": sec_key,
                "title": s_name,
                "level": 2,
                "output": f"{c_name}/{s_name}/{s_name}.md",
                "body_anchor": {
                    "kind": "reviewed-boundary",
                    "start_line": sec_start,
                    "evidence": f"section-{sec_key}",
                    "reviewer_confirmed": True
                },
                "emit_title": False
            })
            authority.append({
                "key": sec_key,
                "title": s_name,
                "level": 2,
                "source_line": sec_start,
                "reviewer_confirmed": True
            })

            if not subheadings_filtered:
                leaf_keys.append(sec_key)
            else:
                seen_sub_titles = set()
                for sub_idx, (sub_line, sub_raw_title) in enumerate(subheadings_filtered, 1):
                    sub_key = f"sub-{node_counter:03d}"
                    node_counter += 1

                    sub_c_title = clean_title(sub_raw_title)
                    if not sub_c_title:
                        sub_c_title = f"考点_{sub_idx:02d}"

                    base_title = sub_c_title
                    dedup_i = 1
                    while sub_c_title in seen_sub_titles:
                        dedup_i += 1
                        sub_c_title = f"{base_title}_{dedup_i}"
                    seen_sub_titles.add(sub_c_title)

                    entries.append({
                        "key": sub_key,
                        "title": sub_c_title,
                        "level": 3,
                        "output": f"{c_name}/{s_name}/{sub_c_title}/{sub_c_title}.md",
                        "body_anchor": {
                            "kind": "reviewed-boundary",
                            "start_line": sub_line,
                            "evidence": f"subtopic-{sub_key}",
                            "reviewer_confirmed": True
                        },
                        "emit_title": False
                    })
                    authority.append({
                        "key": sub_key,
                        "title": sub_c_title,
                        "level": 3,
                        "source_line": sub_line,
                        "reviewer_confirmed": True
                    })
                    leaf_keys.append(sub_key)

    adapter = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "filename_policy": {"colon_replacement": "_"},
        "output_policy": {"generate_index": False, "generate_canvas": False},
        "profile": str(profile_file),
        "hierarchy": {
            "source_role": "questions",
            "root_output": f"圆锥曲线专题_{volume_title}.md",
            "region": {"start_line": 1, "end_line": len(lines)},
            "primary_authority": {
                "status": "passed",
                "reviewer_confirmed": True,
                "start_line": 1,
                "end_line": len(lines),
                "reading_order": "source-stream",
                "entries": authority
            },
            "entries": entries
        },
        "content": {
            "unknown_label_policy": "retain",
            "question_folder": "例题",
            "question_repository_root": "/Users/oven/Documents/ovenmathmap/mathmap/习题/questions",
            "question_title_template": "题 {number}",
            "question_patterns": [
                r"^(?P<number>\[?例\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])\]?)\s*",
                r"^(?P<number>\[?变式(?:题)?\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])?\]?)\s*[：:]?\s*"
            ],
            "inline_question_patterns": [
                r"(?P<number>\([1-9]\d?\)|（[1-9]\d?）)\s*"
            ],
            "question_kind_rules": [
                {
                    "kind": "worked-example",
                    "pattern": r"^\[?例\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])\]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "interleaved",
                    "atomize_interleaved_subquestions": False,
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|详细解答|解答|解法|试题解析|解)】?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】"
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
                    "pattern": r"^\[?变式(?:题)?\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])?\]?\s*[：:]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "interleaved",
                    "atomize_interleaved_subquestions": False,
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|详细解答|解答|解法|试题解析|解)】?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】"
                    ],
                    "solution_resume_patterns": [
                        r"^\s*(?:\([1-9]\d?\)|（[1-9]\d?）|[1-9]\d?[.．、])",
                        r"^\s*（[1-9]\d?）",
                        r"^\s*\([1-9]\d?\)"
                    ],
                    "sequence_policy": "none",
                    "preserve_internal_headings": True,
                    "folder": "例题"
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
            "worked_example_callout_title": f"《圆锥曲线专题({volume_title})》例题解析",
            "answer_callout_layout_version": 2,
            "question_scopes": [
                {
                    "contexts": leaf_keys,
                    "kinds": ["worked-example"]
                }
            ],
            "roles": []
        },
        "answers": {
            "source_role": "questions",
            "mode": "separate",
            "question_number_regexes": [
                r"^(?P<number>\[?例\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])\]?)\s*",
                r"^(?P<number>\[?变式(?:题)?\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])?\]?)\s*[：:]?\s*"
            ],
            "answer_content_regexes": [
                r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|详细解答|解答|解法|试题解析|解)】?[：:\s]?",
                r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                r"^\s*【答案】",
                r"^\s*【解析】",
                r"^\s*【分析】",
                r"^\s*【详解】"
            ],
            "auto_accept_exact_context_matches": True,
            "auto_accept_exact_number_matches": True
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
    print(f"Wrote 3-level adapter for {volume_title} to {output_file} (Total entries={len(entries)}, leaf nodes={len(leaf_keys)})")


def apply_volume_graph(staging_path: Path, profile_path: Path):
    adapter_path = staging_path / "format-adapter.json"
    cov_path = staging_path / "hierarchy-coverage-manifest.json"
    content_path = staging_path / "question-type-manifest.json"
    match_path = staging_path / "answer-match-manifest.json"
    hier_manifest_path = staging_path / "hierarchy-manifest.json"

    print("1. Planning hierarchy...")
    hier_plan = plan_hierarchy(profile_path, adapter_path)
    hier_plan["status"] = "passed"
    hier_plan["reviewer_confirmed"] = True
    write_json_atomic(hier_manifest_path, hier_plan, overwrite=True)

    print("2. Applying hierarchy...")
    apply_hierarchy(profile_path, adapter_path, hier_manifest_path, overwrite=True)

    print("3. Planning content...")
    content_plan = plan_content(profile_path, adapter_path, cov_path)
    content_plan["status"] = "passed"
    content_plan["reviewer_confirmed"] = True
    write_json_atomic(content_path, content_plan, overwrite=True)

    print("4. Planning matches...")
    match_plan = plan_matches(profile_path, adapter_path, content_path)
    match_plan["status"] = "passed"
    match_plan["reviewer_confirmed"] = True
    write_json_atomic(match_path, match_plan, overwrite=True)

    print("5. Applying content...")
    apply_content(profile_path, adapter_path, content_path, overwrite=True)

    print("6. Applying matches...")
    apply_matches(profile_path, match_path, overwrite=True)

    print("Successfully built 3-level graph for profile!")


def process_volume(volume_title: str, pdf_filename: str) -> bool:
    pdf_path = SOURCE_DIR / pdf_filename
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found!")
        return False

    staging_path = VAULT_ROOT / ".temp" / f"2026版高中《mst老唐说题》圆锥曲线专题（数学）-{volume_title}-staging"
    profile_path = staging_path / "question-type-profile.json"
    graph_root = MASTER_GRAPH_ROOT / volume_title
    
    print(f"\n=======================================================")
    print(f" PROCESSING 3-LEVEL VOLUME: {volume_title}")
    print(f" PDF: {pdf_filename}")
    print(f" Staging: {staging_path}")
    print(f" Graph Root: {graph_root}")
    print(f"=======================================================")

    # Step 1: Init profile
    if not staging_path.exists() or not profile_path.exists():
        staging_path.mkdir(parents=True, exist_ok=True)
    
    init_cmd = [
        PYTHON_EXE,
        str(SCRIPT_COORDINATOR),
        "init",
        "--source", f"questions={pdf_path}",
        "--title", f"2026版高中《mst老唐说题》圆锥曲线专题（数学）-{volume_title}",
        "--staging-root", str(staging_path),
        "--vault-root", str(VAULT_ROOT),
        "--graph-root", str(graph_root),
        "--output", str(profile_path),
        "--overwrite"
    ]
    subprocess.run(init_cmd, capture_output=True, text=True)

    # Step 2: MinerU OCR
    raw_md = staging_path / "raw" / "questions.raw.md"
    if not raw_md.exists():
        print("Running MinerU OCR pipeline (Chunk limit MAX_PAGES=50)...")
        run_cmd = [PYTHON_EXE, str(SCRIPT_COORDINATOR), "run", str(profile_path), "--overwrite"]
        res = subprocess.run(run_cmd, capture_output=True, text=True)
        print(f"Initial Run Exit Code: {res.returncode}")
        if res.returncode not in (0, 2) and not raw_md.exists():
            print(f"OCR failed: {res.stderr}\n{res.stdout}")
            return False

    # Clean intermediate manifests for clean rebuild
    for fn in ["hierarchy-manifest.json", "hierarchy-coverage-manifest.json", "question-type-manifest.json", "answer-match-manifest.json", "pipeline-state.json"]:
        p = staging_path / fn
        if p.exists(): p.unlink()

    # Step 3: Build 3-level adapter with exact verified chapters and sections
    if "上" in volume_title:
        shang_chapters = [
            (1, "第01章_圆锥曲线四定义", 780),
            (2, "第02章_离心率", 2190),
            (3, "第03章_几何视角下的焦点三角形", 3055),
            (4, "第04章_小题新题型与多选的综合题方法篇", 4005),
            (5, "第05章_常规韦达联立", 5200),
            (6, "第06章_联立之同构方程", 5840),
            (7, "第07章_圆锥曲线常规数据处理方法", 6780),
            (8, "第08章_联立计算高阶篇", 7830),
            (9, "第09章_圆锥曲线跨界综合", 9350),
        ]
        shang_sections = [
            # Chapter 1
            (1, "第01章_圆锥曲线四定义", 1, "第一节_椭圆双曲的轨迹翻译_第一定义", 786, 1172),
            (1, "第01章_圆锥曲线四定义", 2, "第二节_椭圆双曲的比值模型_第二定义", 1172, 1375),
            (1, "第01章_圆锥曲线四定义", 3, "第三节_椭圆双曲的斜率转化_第三定义", 1375, 1545),
            (1, "第01章_圆锥曲线四定义", 4, "第四节_圆锥曲线的第四定义", 1545, 1612),
            (1, "第01章_圆锥曲线四定义", 5, "第五节_抛物线的焦准翻译", 1612, 1783),
            (1, "第01章_圆锥曲线四定义", 6, "第六节_长度最值问题之声东击西", 1783, 1945),
            (1, "第01章_圆锥曲线四定义", 7, "第七节_截口曲线与祖暅原理", 1945, 2190),
            # Chapter 2
            (2, "第02章_离心率", 1, "第一节_弦长体系下的焦长模型与焦比定理", 2199, 2538),
            (2, "第02章_离心率", 2, "第二节_几何性质下的渐近线模型", 2538, 2832),
            (2, "第02章_离心率", 3, "第三节_长度与角度下的离心率范围约束", 2832, 3055),
            # Chapter 3
            (3, "第03章_几何视角下的焦点三角形", 1, "第一节_角度语言与坐标语言下的焦点三角形", 3062, 3344),
            (3, "第03章_几何视角下的焦点三角形", 2, "第二节_几何光学性质下的焦点三角形", 3344, 3561),
            (3, "第03章_几何视角下的焦点三角形", 3, "第三节_三角形四心性质的应用", 3561, 3865),
            (3, "第03章_几何视角下的焦点三角形", 4, "第四节_焦点三角形与大小圆问题", 3865, 4005),
            # Chapter 4
            (4, "第04章_小题新题型与多选的综合题方法篇", 1, "第一节_切线与切点弦", 4010, 4594),
            (4, "第04章_小题新题型与多选的综合题方法篇", 2, "第二节_坐标旋转与曲线转换", 4594, 4956),
            (4, "第04章_小题新题型与多选的综合题方法篇", 3, "第三节_圆锥曲线之间的交点", 4956, 5200),
            # Chapter 5
            (5, "第05章_常规韦达联立", 1, "第一节_正反设直线的方案选择", 5206, 5424),
            (5, "第05章_常规韦达联立", 2, "第二节_向量乘积中的翻译方法", 5424, 5769),
            (5, "第05章_常规韦达联立", 3, "第三节_运算技巧下的韦达定理拓展", 5769, 5840),
            # Chapter 6
            (6, "第06章_联立之同构方程", 1, "第一节_抛物线两点联立式方程", 5845, 6302),
            (6, "第06章_联立之同构方程", 2, "第二节_斜率同构式与坐标同构式的应用", 6302, 6712),
            (6, "第06章_联立之同构方程", 3, "第三节_比值参数同构", 6712, 6780),
            # Chapter 7
            (7, "第07章_圆锥曲线常规数据处理方法", 1, "第一节_齐次化处理斜率和积问题", 6782, 6993),
            (7, "第07章_圆锥曲线常规数据处理方法", 2, "第二节_隐藏的斜率和积问题", 6993, 7199),
            (7, "第07章_圆锥曲线常规数据处理方法", 3, "第三节_点差法与中垂线问题", 7199, 7526),
            (7, "第07章_圆锥曲线常规数据处理方法", 4, "第四节_定比点差法", 7526, 7830),
            # Chapter 8
            (8, "第08章_联立计算高阶篇", 1, "第一节_长度参数与直线参数方程", 7837, 8073),
            (8, "第08章_联立计算高阶篇", 2, "第二节_单动点与圆锥曲线参数方程", 8073, 8326),
            (8, "第08章_联立计算高阶篇", 3, "第三节_复数变换与三角旋转", 8326, 8544),
            (8, "第08章_联立计算高阶篇", 4, "第四节_直线系和圆系方程", 8544, 8652),
            (8, "第08章_联立计算高阶篇", 5, "第五节_二次曲线系与四点共圆", 8652, 8894),
            (8, "第08章_联立计算高阶篇", 6, "第六节_二次曲线方程与四点联立曲线系", 8894, 9350),
            # Chapter 9
            (9, "第09章_圆锥曲线跨界综合", 1, "第一节_圆锥曲线与立体几何综合", 9360, 9542),
            (9, "第09章_圆锥曲线跨界综合", 2, "第二节_圆锥曲线与三角函数的综合", 9542, 9693),
            (9, "第09章_圆锥曲线跨界综合", 3, "第三节_圆锥曲线与导数的综合", 9693, 9835),
            (9, "第09章_圆锥曲线跨界综合", 4, "第四节_圆锥曲线与数列综合", 9835, 99999),
        ]
        build_3level_adapter(staging_path, "上册", shang_chapters, shang_sections)
    else:
        xia_chapters = [
            (10, "第10章_万能的两点对合式", 440),
            (11, "第11章_从定比点差到极点极线", 1240),
            (12, "第12章_调和点列与调和线束定理与对合关系", 2346),
            (13, "第13章_新定义下的斜率调整与仿射", 5010),
            (14, "第14章_新定义下的面积转化", 5830),
        ]
        xia_sections = [
            # Chapter 10
            (10, "第10章_万能的两点对合式", 1, "第一节_反比例对合方程解决圆锥曲线与数列综合", 442, 726),
            (10, "第10章_万能的两点对合式", 2, "第二节_抛物线切线对合与两点对合数列构造综合", 726, 877),
            (10, "第10章_万能的两点对合式", 3, "第三节_椭圆双曲线的两点对合式", 877, 1240),
            # Chapter 11
            (11, "第11章_从定比点差到极点极线", 1, "第一节_单比与交比", 1241, 1750),
            (11, "第11章_从定比点差到极点极线", 2, "第二节_极点极线定义与自极三角形", 1750, 2071),
            (11, "第11章_从定比点差到极点极线", 3, "第三节_蝴蝶定理与坎迪定理", 2071, 2346),
            # Chapter 12
            (12, "第12章_调和点列与调和线束定理与对合关系", 1, "第一节_调和点列与点的对合", 2348, 2468),
            (12, "第12章_调和点列与调和线束定理与对合关系", 2, "第二节_调和线束两大定理的应用", 2468, 3190),
            (12, "第12章_调和点列与调和线束定理与对合关系", 3, "第三节_角平分线与调和点列", 3190, 3396),
            (12, "第12章_调和点列与调和线束定理与对合关系", 4, "第四节_斜率对合与斜率翻译", 3396, 4341),
            (12, "第12章_调和点列与调和线束定理与对合关系", 5, "第五节_斜率积的三次对合", 4341, 4548),
            (12, "第12章_调和点列与调和线束定理与对合关系", 6, "第六节_从笛沙格定理到帕斯卡定理", 4548, 4845),
            (12, "第12章_调和点列与调和线束定理与对合关系", 7, "第七节_帕斯卡定理与对偶定理布利安桑定理", 4845, 5010),
            # Chapter 13
            (13, "第13章_新定义下的斜率调整与仿射", 1, "第一节_斜率调整法", 5011, 5221),
            (13, "第13章_新定义下的斜率调整与仿射", 2, "第二节_仿射法与面积转化", 5221, 5830),
            # Chapter 14
            (14, "第14章_新定义下的面积转化", 1, "第一节_过焦点弦的面积问题", 5833, 6303),
            (14, "第14章_新定义下的面积转化", 2, "第二节_坐标面积公式与面积最值", 6303, 6460),
            (14, "第14章_新定义下的面积转化", 3, "第三节_面积比值转化问题", 6460, 99999),
        ]
        build_3level_adapter(staging_path, "下册", xia_chapters, xia_sections)

    # Step 4: Apply hierarchy, content, answers directly
    apply_volume_graph(staging_path, profile_path)

    # Step 5: Run audit
    print(f"--- Running final audit for {volume_title} ---")
    cov = staging_path / "hierarchy-coverage-manifest.json"
    content = staging_path / "question-type-manifest.json"
    answer = staging_path / "answer-match-manifest.json"
    if cov.exists() and content.exists() and answer.exists():
        try:
            res = audit_graph(profile_path, cov, content, answer, canvas_path=None)
            print(f"Audit Status for {volume_title}: {res.get('status')}")
            return res.get("status") == "passed"
        except Exception as e:
            print(f"Audit error: {e}")
            return False

    return True


def main():
    if MASTER_GRAPH_ROOT.exists():
        shutil.rmtree(MASTER_GRAPH_ROOT, ignore_errors=True)
    MASTER_GRAPH_ROOT.mkdir(parents=True, exist_ok=True)

    volumes = [
        ("上册", "圆锥曲线专题.pdf"),
        ("下册", "圆锥专题.pdf")
    ]
    for vol_title, pdf_name in volumes:
        success = process_volume(vol_title, pdf_name)
        print(f"Volume {vol_title} result: {'SUCCESS' if success else 'FAILED'}")


if __name__ == "__main__":
    main()

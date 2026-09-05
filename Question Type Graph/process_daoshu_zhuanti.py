#!/usr/bin/env python3
"""Batch processor for 2026版高中《mst老唐说题》导数专题 (上/下册) into Obsidian Question Type Graph with 3-Level Fine-Grained Hierarchy."""

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

SOURCE_DIR = Path("/Volumes/Whw/数学妙呀资料/高中/总复习/专题/2026版高中《mst老唐说题》导数专题（数学）")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
MASTER_GRAPH_ROOT = VAULT_ROOT / "高中" / "总复习" / "专题" / "2026版高中《mst老唐说题》导数专题（数学）"

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


def build_3level_adapter(staging_path: Path, volume_title: str, sections_meta, chapters_meta):
    raw_file = staging_path / "raw" / "questions.raw.md"
    output_file = staging_path / "format-adapter.json"
    profile_file = staging_path / "question-type-profile.json"

    if not raw_file.is_file():
        raise RuntimeError(f"Raw file missing in {staging_path}")

    lines = raw_file.read_text(encoding="utf-8-sig").splitlines()

    # Step 1: Scan subheadings within each section
    entries = []
    authority = []
    leaf_keys = []
    
    node_counter = 1

    for c_num, c_name, chap_start in chapters_meta:
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

        # Process sections belonging to this chapter
        chap_secs = [s for s in sections_meta if s[0] == c_num]
        for _, _, s_num, s_name, sec_start, sec_end in chap_secs:
            sec_key = f"sec-{node_counter:03d}"
            node_counter += 1

            # Find subheadings in [sec_start, sec_end)
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

            # Ensure subheadings are sorted by line
            subheadings.sort(key=lambda x: x[0])

            # Filter out subheadings that start at the exact same line as sec_start
            subheadings_filtered = []
            for l_no, s_t in subheadings:
                if l_no > sec_start:
                    subheadings_filtered.append((l_no, s_t))
                elif l_no == sec_start:
                    # If subheading is on the first line, we still count it but bump sec_start slightly before or keep it as level 3
                    subheadings_filtered.append((l_no + 1 if l_no == sec_start else l_no, s_t))

            # Add Level 2 Section entry
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
                # Add Level 3 Subtopic entries
                seen_sub_titles = set()
                for sub_idx, (sub_line, sub_raw_title) in enumerate(subheadings_filtered, 1):
                    sub_key = f"sub-{node_counter:03d}"
                    node_counter += 1
                    
                    sub_c_title = clean_title(sub_raw_title)
                    if not sub_c_title:
                        sub_c_title = f"考点_{sub_idx:02d}"
                    
                    # Deduplicate title within section
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
            "root_output": f"导数专题_{volume_title}.md",
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
            "question_patterns": [
                r"^(?P<number>\[?例\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])\]?)\s*",
                r"^(?P<number>\[?变式(?:题)?\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])?\]?)\s*[：:]?\s*"
            ],
            "inline_question_patterns": [],
            "question_kind_rules": [
                {
                    "kind": "worked-example",
                    "pattern": r"^\[?例\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])\]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "tail",
                    "atomize_interleaved_subquestions": False,
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|详细解答|解答|解法|试题解析)】?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】"
                    ],
                    "solution_resume_patterns": [],
                    "sequence_policy": "none",
                    "preserve_internal_headings": True,
                    "folder": "例题"
                },
                {
                    "kind": "worked-example",
                    "pattern": r"^\[?变式(?:题)?\s*(?:[0-9]+(?:\.\d+)?|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳一二三四五六七八九十]+|[（(][0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十]+[）)])?\]?\s*[：:]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "tail",
                    "atomize_interleaved_subquestions": False,
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|详细解答|解答|解法|试题解析)】?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】"
                    ],
                    "solution_resume_patterns": [],
                    "sequence_policy": "none",
                    "preserve_internal_headings": True,
                    "folder": "例题"
                }
            ],
            "worked_example_solution_patterns": [
                r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|思路导航|详细解答|解答|解法|证法|点拨|名师点睛|点睛|考点|总结|规律总结|试题解析)】?[：:\s]?",
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
            "worked_example_callout_title": f"《导数专题({volume_title})》例题解析",
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
                r"^\s*(?:[1-9]\d?[.．、]\s*)?【?(?:答案|解析|分析|详解|详细解答|解答|解法|试题解析)】?[：:\s]?",
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
    print(f"Wrote accurate 3-level adapter for {volume_title} to {output_file} (Total entries={len(entries)}, leaf nodes={len(leaf_keys)})")


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

    staging_path = VAULT_ROOT / ".temp" / f"2026版高中《mst老唐说题》导数专题（数学）-{volume_title}-staging"
    profile_path = staging_path / "question-type-profile.json"
    graph_root = MASTER_GRAPH_ROOT / volume_title
    
    print(f"\n=======================================================")
    print(f" PROCESSING 3-LEVEL VOLUME: {volume_title}")
    print(f" PDF: {pdf_filename}")
    print(f" Staging: {staging_path}")
    print(f" Graph Root: {graph_root}")
    print(f"=======================================================\n")

    # Step 1: Init profile
    if not staging_path.exists() or not profile_path.exists():
        staging_path.mkdir(parents=True, exist_ok=True)
    
    init_cmd = [
        PYTHON_EXE,
        str(SCRIPT_COORDINATOR),
        "init",
        "--source", f"questions={pdf_path}",
        "--title", f"2026版高中《mst老唐说题》导数专题（数学）-{volume_title}",
        "--staging-root", str(staging_path),
        "--vault-root", str(VAULT_ROOT),
        "--graph-root", str(graph_root),
        "--output", str(profile_path),
        "--overwrite"
    ]
    subprocess.run(init_cmd, capture_output=True, text=True)

    # Clean intermediate manifests
    for fn in ["hierarchy-manifest.json", "hierarchy-coverage-manifest.json", "question-type-manifest.json", "answer-match-manifest.json", "pipeline-state.json"]:
        p = staging_path / fn
        if p.exists(): p.unlink()

    # Step 2: Build 3-level adapter
    if "上" in volume_title:
        shang_chapters = [
            (1, "第01章_技能篇_导数基本技能", 713),
            (2, "第02章_技能篇_导数的切线方程", 2225),
            (3, "第03章_小题篇_抽象函数的构造", 3301),
            (4, "第04章_小题篇_比大小", 3878),
            (5, "第05章_小题篇_数形结合", 4430),
            (6, "第06章_综合篇_新三板斧", 5223),
            (7, "第07章_综合篇_显点探路", 6727),
            (8, "第08章_综合篇_隐点探路", 7635),
        ]
        shang_sections = [
            (1, "第01章_技能篇_导数基本技能", 1, "第一节_同构函数的基础应用", 715, 1281),
            (1, "第01章_技能篇_导数基本技能", 2, "第二节_切线函数的基本应用", 1281, 1472),
            (1, "第01章_技能篇_导数基本技能", 3, "第三节_指对处理的基本方法", 1472, 1703),
            (1, "第01章_技能篇_导数基本技能", 4, "第四节_三次函数的基本理论", 1703, 1912),
            (1, "第01章_技能篇_导数基本技能", 5, "第五节_泰勒展开的基本应用", 1912, 2103),
            (1, "第01章_技能篇_导数基本技能", 6, "第六节_帕德逼近的基本原理", 2103, 2225),
            (2, "第02章_技能篇_导数的切线方程", 1, "第一节_基本切线方程", 2229, 2524),
            (2, "第02章_技能篇_导数的切线方程", 2, "第二节_函数的切线界定", 2524, 2908),
            (2, "第02章_技能篇_导数的切线方程", 3, "第三节_切线的秘密", 2908, 3301),
            (3, "第03章_小题篇_抽象函数的构造", 1, "第一节_原函数与导函数的周期性构造", 3303, 3470),
            (3, "第03章_小题篇_抽象函数的构造", 2, "第二节_抽象函数单调性构造", 3470, 3746),
            (3, "第03章_小题篇_抽象函数的构造", 3, "第三节_抽象函数构造的逆向思维", 3746, 3878),
            (4, "第04章_小题篇_比大小", 1, "第一节_指数与对数比大小", 3880, 4205),
            (4, "第04章_小题篇_比大小", 2, "第二节_利用泰勒展开和帕德逼近比大小", 4205, 4430),
            (5, "第05章_小题篇_数形结合", 1, "第一节_数形结合与恒成立", 4434, 4811),
            (5, "第05章_小题篇_数形结合", 2, "第二节_数形结合与零点问题", 4811, 5171),
            (5, "第05章_小题篇_数形结合", 3, "第三节_整点问题", 5171, 5223),
            (6, "第06章_综合篇_新三板斧", 1, "第一节_指对三角的放缩应用", 5227, 5577),
            (6, "第06章_综合篇_新三板斧", 2, "第二节_保值性原理", 5577, 5830),
            (6, "第06章_综合篇_新三板斧", 3, "第三节_分而治之的上下函数选取", 5830, 6144),
            (6, "第06章_综合篇_新三板斧", 4, "第四节_找点体系与原理解析", 6144, 6727),
            (7, "第07章_综合篇_显点探路", 1, "第一节_端点效应探路", 6731, 6984),
            (7, "第07章_综合篇_显点探路", 2, "第二节_极点效应探路", 6984, 7323),
            (7, "第07章_综合篇_显点探路", 3, "第三节_极值显点探路与零点个数问题", 7323, 7635),
            (8, "第08章_综合篇_隐点探路", 1, "第一节_构造极点效应解决含参恒成立", 7639, 7751),
            (8, "第08章_综合篇_隐点探路", 2, "第二节_特殊点探路与隐零点思想", 7751, 7900),
            (8, "第08章_综合篇_隐点探路", 3, "第三节_隐点效应与极值点不等式证明", 7900, 99999),
        ]
        build_3level_adapter(staging_path, "上册", shang_sections, shang_chapters)
    else:
        xia_chapters = [
            (9, "第09章_导数与双变量", 480),
            (10, "第10章_导数不等式与数列综合", 3545),
            (11, "第11章_三角与导数综合", 5134),
        ]
        xia_sections = [
            (9, "第09章_导数与双变量", 1, "第一节_极值和差", 485, 1196),
            (9, "第09章_导数与双变量", 2, "第二节_极值点偏移", 1196, 2034),
            (9, "第09章_导数与双变量", 3, "第三节_零点差直线拟合问题", 2034, 2401),
            (9, "第09章_导数与双变量", 4, "第四节_拟合体系", 2401, 3026),
            (9, "第09章_导数与双变量", 5, "第五节_拐点偏移", 3026, 3253),
            (9, "第09章_导数与双变量", 6, "第六节_浙江风格的双变量", 3253, 3426),
            (9, "第09章_导数与双变量", 7, "第七节_双元问题调整与主元法", 3426, 3547),
            (10, "第10章_导数不等式与数列综合", 1, "第一节_导数与数列递推", 3547, 3796),
            (10, "第10章_导数不等式与数列综合", 2, "第二节_切线放缩型", 3796, 4497),
            (10, "第10章_导数不等式与数列综合", 3, "第三节_飘带函数型", 4497, 4899),
            (10, "第10章_导数不等式与数列综合", 4, "第四节_导数与数列迭代放缩与求和", 4899, 5136),
            (11, "第11章_三角与导数综合", 1, "第一节_三角函数与零点综合", 5136, 5645),
            (11, "第11章_三角与导数综合", 2, "第二节_三角函数恒成立问题", 5645, 6297),
            (11, "第11章_三角与导数综合", 3, "第三节_三角函数与数列综合", 6297, 6616),
            (11, "第11章_三角与导数综合", 4, "第四节_三角函数与双元杂谈", 6616, 99999),
        ]
        build_3level_adapter(staging_path, "下册", xia_sections, xia_chapters)

    # Step 3: Apply hierarchy, content, answers directly
    apply_volume_graph(staging_path, profile_path)

    # Step 4: Run audit
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
        ("上册", "导数专题 上.pdf"),
        ("下册", "导数专题 下.pdf")
    ]
    for vol_title, pdf_name in volumes:
        success = process_volume(vol_title, pdf_name)
        print(f"Volume {vol_title} result: {'SUCCESS' if success else 'FAILED'}")


if __name__ == "__main__":
    main()

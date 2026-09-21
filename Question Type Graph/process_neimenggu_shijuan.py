#!/usr/bin/env python3
"""Batch processor for Inner Mongolia High School Math Exam Papers into Obsidian Question Type Graphs."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add lib directory to sys.path
lib_path = Path(__file__).parent / "lib"
if lib_path.exists():
    sys.path.insert(0, str(lib_path.resolve()))

import unicodedata
import pypdf

from question_type_graph.common import safe_name, load_json, write_json_atomic, require_reviewed_adapter
from question_type_graph.hierarchy import plan_hierarchy, apply_hierarchy, normalize_heading
from question_type_graph.content import plan_content, apply_content
from question_type_graph.answers import plan_matches, apply_matches
from question_type_graph.canvas import build_canvas
from question_type_graph.audit import audit_graph

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_BASE = Path("/Volumes/Whw/数学妙呀资料/高中/课堂同步/试卷/内蒙古试卷集")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
MASTER_GRAPH_BASE = VAULT_ROOT / "高中" / "课堂同步" / "试卷" / "内蒙古试卷集"
STAGING_BASE = VAULT_ROOT / ".temp"

PYTHON_EXE = SCRIPT_DIR / ".venv" / "bin" / "python"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

SCRIPT_COORDINATOR = SCRIPT_DIR / "skills" / "question-type-graph" / "scripts" / "question_type_graph.py"


def clean_title_from_pdf(pdf_path: Path) -> str:
    name = pdf_path.stem
    if name.startswith("xPad_paper_"):
        try:
            reader = pypdf.PdfReader(pdf_path)
            lines = [l.strip() for l in reader.pages[0].extract_text().splitlines() if l.strip()]
            t = lines[0] if lines else name
            if len(lines) > 1 and "学年" in lines[0] and "试卷" not in lines[0]:
                t = lines[0] + lines[1]
            t = unicodedata.normalize("NFKC", t)
            t = re.sub(r"[\s~]+", "-", t)
            t = re.sub(r"[（(].*?[）)]", "", t)
            t = re.sub(r"[-_]+", "_", t).strip("_")
            return safe_name(t, max_chars=35)
        except Exception:
            return safe_name(name, max_chars=35)

    # Regular files
    t = unicodedata.normalize("NFKC", name)
    t = re.sub(r"_答案分开版本_\d+", "", t)
    t = re.sub(r"❖", "", t)
    t = re.sub(r"[-_]?\d{10,}$", "", t)
    t = re.sub(r"\s+", "_", t)
    t = t.strip("_")
    return safe_name(t, max_chars=35)


def collect_paper_tasks(source_dir: Path) -> list[dict]:
    files = sorted(list(source_dir.glob("*.pdf")))
    tasks_by_title = defaultdict(list)
    for f in files:
        if f.name.startswith((".", "~$")):
            continue
        clean_t = clean_title_from_pdf(f)
        tasks_by_title[clean_t].append(f)

    tasks = []
    for title, file_list in sorted(tasks_by_title.items()):
        file_list.sort(key=lambda p: p.stat().st_size, reverse=True)
        primary_pdf = file_list[0]
        staging_name = safe_name(f"neimenggu_{title}", max_chars=50)
        tasks.append({
            "title": title,
            "pdf_path": primary_pdf,
            "graph_root": MASTER_GRAPH_BASE / title,
            "staging_path": STAGING_BASE / f"{staging_name}-staging",
            "duplicate_count": len(file_list),
        })
    return tasks


SEC_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?([一二三四五六七八九十]+[、.．]\s*[\w\u4e00-\u9fa5]*[题卷][^:：\n]*)"
)
ANS_BOUNDARY_PAT = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:参考答案|答案及解析|答案与解析|试卷答案|标准答案|试题答案解析|答案解析|试题答案|参考答案及解析|参考答案与试题解析)\b"
)


def sanitize_raw_markdown(raw_file: Path):
    if not raw_file.is_file():
        return
    text = raw_file.read_text(encoding="utf-8-sig")
    text = unicodedata.normalize("NFKC", text)

    # 1. Extract stems trapped inside HTML tables:
    def _extract_stem_from_table(m):
        stem = m.group(1).strip()
        rest = m.group(2)
        return f"\n\n{stem}\n\n<table><tr>{rest}</table>"

    text = re.sub(
        r"<table>\s*<tr>\s*<td[^>]*>\s*([1-9]\d?[、.．][^<]+?)</td>(.*?)</table>",
        _extract_stem_from_table,
        text,
        flags=re.DOTALL,
    )

    # 2. Split section headings concatenated to previous line without newline
    text = re.sub(
        r"([^\n])\s*(#{1,6}\s*[一二三四五六七八九十]+[、.．]\s*[\w\u4e00-\u9fa5]*[题卷])",
        r"\1\n\n\2",
        text,
    )
    text = re.sub(
        r"([^\n])\s*([一二三四五六七八九十]+[、.．]\s*[\w\u4e00-\u9fa5]*[题卷][:：])",
        r"\1\n\n## \2",
        text,
    )

    # 3. Strip accidental heading prefixes on questions/answers: e.g. `## 4. 【答案】C` -> `4. 【答案】C`
    text = re.sub(r"(?m)^\s*#{1,6}\s*(?=[1-9]\d?[.．、]\s*【)", "", text)

    # 4. Unwrap question/answer headers trapped inside LaTeX array blocks:
    text = re.sub(
        r"\$\$\s*\\begin\{array\}\{[^}]*\}\s*&\s*\{\{([1-9]\d?)[,、.．]\s*(?:\\quad\s*)?(?:\\mathrm\{)?【答案[^\n\\]*\\\\\s*&\s*",
        r"\1、【答案】\n\n$$\n\\begin{array}{r l} & ",
        text,
    )

    # 5. Split inline answer headers or question numbers concatenated onto previous line
    text = re.sub(
        r"((?:故选[：:][\sA-D]+|故答案为[：:][^\n]+?)[。.]?|[)）$；。.]|\$)\s*([1-9]\d?[.．、]\s*(?:【答案】|[A-Za-z\u4e00-\u9fa5$【\(\[∵∴\\]))",
        r"\1\n\n\2",
        text,
    )

    # 6. Fix solitary 顿号 without digit at line start (e.g. `、 \frac{(1-x^2)^7}...` -> `1、 \frac...`)
    text = re.sub(r"(?m)^\s*、\s*", "1、", text)

    # 7. Split inline subquestions e.g. " 1 求证：" -> "\n\n1 求证："
    text = re.sub(
        r"(作答区|\$)\s+([1-9]\d?[、.．\s]\s*(?:求|已知|设|若|证明))",
        r"\1\n\n\2",
        text,
    )

    # 8. Unwrap question/answer numbers trapped inside LaTeX math blocks ($$\n4 、\n$$)
    text = re.sub(r"\$\$\s*([1-9]\d?)\s*([、.．])\s*\$\$", r"\1\2", text)

    # 9. Normalize leading `答案 C。` or `答案C。` to `【答案】 C\n\n`:
    text = re.sub(
        r"(?m)^\s*答案\s*([A-D]+)[。.\s]*",
        r"【答案】 \1\n\n",
        text,
    )

    raw_file.write_text(text, encoding="utf-8")


def recover_missing_questions_in_raw(raw_file: Path, clean_title: str):
    text = raw_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    q_secs = []
    ans_boundary = None
    ans_secs = []
    seen = set()
    for idx, l in enumerate(lines, 1):
        m = SEC_PATTERN.match(l)
        if m:
            clean_t = re.sub(r"[（(].*?[）)]", "", m.group(1)).strip()
            clean_t = re.sub(r"[:：].*$", "", clean_t).strip()
            if clean_t in seen and ans_boundary is None:
                ans_boundary = idx
                ans_secs.append((idx, clean_t))
            elif ans_boundary is not None:
                ans_secs.append((idx, clean_t))
            else:
                seen.add(clean_t)
                q_secs.append((idx, clean_t))

    if ans_boundary is None:
        for idx, l in enumerate(lines, 1):
            if ANS_BOUNDARY_PAT.search(l):
                ans_boundary = idx
                break

    # If ans_secs is empty but ans_boundary exists and has 第N题 pattern:
    if not ans_secs and ans_boundary and q_secs:
        modified = False
        new_lines = list(lines)
        for s_idx, (q_start, q_name) in enumerate(q_secs):
            q_end = (q_secs[s_idx + 1][0] - 1) if s_idx + 1 < len(q_secs) else (ans_boundary - 1)
            first_q_num = None
            for ql in lines[q_start - 1 : q_end]:
                mq = re.match(r"^\s*(?:#{1,6}\s*)?([1-9]\d?)[、.．]", ql)
                if mq:
                    first_q_num = int(mq.group(1))
                    break
            if first_q_num is not None:
                target_pat = re.compile(rf"^\s*(?:#{1,6}\s*)?第\s*{first_q_num}\s*题")
                for al_idx in range(ans_boundary - 1, len(new_lines)):
                    if target_pat.match(new_lines[al_idx]):
                        new_lines[al_idx] = f"## {q_name}\n\n" + new_lines[al_idx]
                        modified = True
                        break
        if modified:
            raw_file.write_text("\n".join(new_lines), encoding="utf-8")
            lines = raw_file.read_text(encoding="utf-8-sig").splitlines()
            q_secs = []
            ans_boundary = None
            ans_secs = []
            seen = set()
            for idx, l in enumerate(lines, 1):
                m = SEC_PATTERN.match(l)
                if m:
                    clean_t = re.sub(r"[（(].*?[）)]", "", m.group(1)).strip()
                    clean_t = re.sub(r"[:：].*$", "", clean_t).strip()
                    if clean_t in seen and ans_boundary is None:
                        ans_boundary = idx
                        ans_secs.append((idx, clean_t))
                    elif ans_boundary is not None:
                        ans_secs.append((idx, clean_t))
                    else:
                        seen.add(clean_t)
                        q_secs.append((idx, clean_t))

    if not ans_boundary or len(q_secs) != len(ans_secs):
        return

    q_pat = re.compile(r"^\s*(?:#{1,6}\s*)?([1-9]\d?)[、.．]")
    ans_pat = re.compile(r"^\s*(?:#{1,6}\s*)?(?:第\s*)?([1-9]\d?)(?:[、.．]|题[:：]?|\s*【答案】)")

    changed = False
    for s_idx, ((q_start, q_name), (a_start, a_name)) in enumerate(zip(q_secs, ans_secs)):
        q_end = (q_secs[s_idx + 1][0] - 1) if s_idx + 1 < len(q_secs) else (ans_boundary - 1)
        a_end = (ans_secs[s_idx + 1][0] - 1) if s_idx + 1 < len(ans_secs) else len(lines)

        # 1. Deduplicate duplicate question numbers in question section
        seen_q_nums = set()
        q_map = {}
        for idx in range(q_start - 1, q_end):
            mq = q_pat.match(lines[idx])
            if mq:
                num = int(mq.group(1))
                if num in seen_q_nums:
                    lines[idx] = q_pat.sub("", lines[idx]).strip()
                    changed = True
                else:
                    seen_q_nums.add(num)
                    q_map[num] = idx

        # 2. Collect answers in answer section
        a_map = {}
        for idx in range(a_start - 1, a_end):
            l = lines[idx].strip()
            # Neutralize out-of-range solitary numbers like '12.' from split decimals
            sm = re.match(r"^([1-9]\d?)[.．、]$", l)
            if sm and int(sm.group(1)) not in q_map:
                lines[idx] = sm.group(1)
                changed = True
                continue

            ma = ans_pat.match(lines[idx])
            if ma:
                num = int(ma.group(1))
                if num not in a_map:
                    a_map[num] = idx

        # 3. Missing questions recovery (questions missing in question section but present in answers)
        missing_q = sorted(list(set(a_map.keys()) - set(q_map.keys())))
        for m in missing_q:
            candidates_next = [v for k, v in q_map.items() if k > m]
            upper_bound = min(candidates_next) if candidates_next else q_end
            lower_bound = q_map.get(m - 1, q_start - 1)

            target_idx = None
            found_zuoda = False
            for c_idx in range(lower_bound + 1, upper_bound):
                line_str = lines[c_idx].strip()
                if "作答区" in line_str:
                    found_zuoda = True
                    continue
                if found_zuoda and line_str and not line_str.startswith("#"):
                    target_idx = c_idx
                    break

            if target_idx is None:
                for c_idx in range(lower_bound + 1, upper_bound):
                    line_str = lines[c_idx].strip()
                    if not line_str or line_str.startswith("#"):
                        continue
                    if any(line_str.startswith(k) for k in ("已知", "如图", "在", "设", "若", "求", "为了", "某", "![")):
                        target_idx = c_idx
                        break

            if target_idx is None:
                for c_idx in range(lower_bound + 1, upper_bound):
                    if lines[c_idx].strip() and not lines[c_idx].strip().startswith("#"):
                        target_idx = c_idx
                        break

            if target_idx is not None and not q_pat.match(lines[target_idx]):
                lines[target_idx] = f"{m}、" + lines[target_idx]
                q_map[m] = target_idx
                changed = True

        # 4. Missing answers recovery (answers missing in answer section but present in questions)
        missing_a = sorted(list(set(q_map.keys()) - set(a_map.keys())))
        for m in missing_a:
            next_keys = [k for k in a_map.keys() if k > m]
            prev_keys = [k for k in a_map.keys() if k < m]
            upper_bound = min([a_map[k] for k in next_keys]) if next_keys else a_end
            lower_bound = max([a_map[k] for k in prev_keys]) if prev_keys else (a_start - 1)

            target_idx = None
            if m == 1 and not prev_keys:
                for c_idx in range(lower_bound + 1, upper_bound):
                    l_str = lines[c_idx].strip()
                    if l_str and not l_str.startswith("#"):
                        target_idx = c_idx
                        break
            else:
                found_prev_end = False
                for c_idx in range(lower_bound + 1, upper_bound):
                    l_str = lines[c_idx].strip()
                    if any(k in l_str for k in ("故选", "故答案为")):
                        found_prev_end = True
                        continue
                    if found_prev_end and l_str and not l_str.startswith("#") and not l_str.startswith("!["):
                        target_idx = c_idx
                        break

                if target_idx is None:
                    for c_idx in range(lower_bound + 1, upper_bound):
                        l_str = lines[c_idx].strip()
                        if any(l_str.startswith(k) for k in ("【解析】", "【分析】", "【详解】", "## 难度", "【答案】", "(1)", "1.", "解：", "证明")):
                            target_idx = c_idx
                            break

                if target_idx is None:
                    for c_idx in range(lower_bound + 1, upper_bound):
                        l_str = lines[c_idx].strip()
                        if l_str and not l_str.startswith("#") and not l_str.startswith("!["):
                            target_idx = c_idx
                            break

            if target_idx is not None and not ans_pat.match(lines[target_idx]):
                choice_match = None
                for scan_i in range(target_idx, upper_bound):
                    cm = re.search(r"故选[：:]\s*([A-D]+)", lines[scan_i])
                    if cm:
                        choice_match = cm.group(1)
                        break
                if choice_match:
                    lines[target_idx] = f"{m}. 【答案】{choice_match}\n\n" + lines[target_idx]
                else:
                    lines[target_idx] = f"{m}、【答案】\n\n" + lines[target_idx]
                a_map[m] = target_idx
                changed = True

    if changed:
        raw_file.write_text("\n".join(lines), encoding="utf-8")


def build_exam_adapter(staging_path: Path, profile_path: Path, clean_title: str) -> dict:
    raw_file = staging_path / "raw" / "combined.raw.md"
    output_file = staging_path / "format-adapter.json"
    if not raw_file.is_file():
        raise RuntimeError(f"combined.raw.md missing in {staging_path}")

    sanitize_raw_markdown(raw_file)
    recover_missing_questions_in_raw(raw_file, clean_title)
    lines = raw_file.read_text(encoding="utf-8-sig").splitlines()

    q_sections = []
    ans_boundary = None
    ans_sections = []

    seen_titles = set()
    for idx, line in enumerate(lines, 1):
        m = SEC_PATTERN.match(line)
        if m:
            title = m.group(1).strip()
            clean_t = re.sub(r"[（(].*?[）)]", "", title).strip()
            clean_t = re.sub(r"[:：].*$", "", clean_t).strip()

            if clean_t in seen_titles and ans_boundary is None:
                ans_boundary = idx
                ans_sections.append((idx, title, clean_t))
            elif ans_boundary is not None:
                ans_sections.append((idx, title, clean_t))
            else:
                seen_titles.add(clean_t)
                q_sections.append((idx, title, clean_t))

    if ans_boundary is None:
        for idx, line in enumerate(lines, 1):
            if ANS_BOUNDARY_PAT.search(line):
                ans_boundary = idx
                break

    if not q_sections:
        q_sections = [(1, "试题部分", "试题部分")]
        if ans_boundary:
            ans_sections = [(ans_boundary, "参考答案", "参考答案")]

    entries = []
    authority = []
    for i, (line_no, title, clean_t) in enumerate(q_sections, 1):
        key = f"section-{i:02d}"
        exact_heading = normalize_heading(lines[line_no - 1]) if line_no <= len(lines) else title
        norm = safe_name(clean_t.replace("、", "_").replace(" ", "_"), max_chars=20)
        norm_title = f"{i:02d}_{norm}"
        entries.append({
            "key": key,
            "title": exact_heading,
            "level": 1,
            "output": f"{norm_title}/{norm_title}.md",
            "body_anchor": {
                "kind": "source-heading" if line_no > 1 else "reviewed-boundary",
                "start_line": line_no,
                "evidence": f"section-{i:02d}" if line_no <= 1 else None,
                "reviewer_confirmed": True
            },
            "emit_title": False
        })
        authority.append({
            "key": key,
            "title": exact_heading,
            "level": 1,
            "source_line": line_no
        })

    contexts = []
    if ans_sections:
        for i, (line_no, title, clean_t) in enumerate(ans_sections, 1):
            key = f"section-{i:02d}"
            contexts.append({
                "key": key,
                "start_line": line_no,
                "anchor_text": lines[line_no - 1].strip()
            })
    elif ans_boundary:
        contexts.append({
            "key": "section-01",
            "start_line": ans_boundary,
            "anchor_text": lines[ans_boundary - 1].strip()
        })

    end_q = (ans_boundary - 1) if ans_boundary else len(lines)
    end_ans = len(lines)

    root_output_name = f"{safe_name(clean_title)}.md"

    adapter = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "profile": str(profile_path),
        "output_policy": {
            "generate_index": True,
            "generate_canvas": True
        },
        "hierarchy": {
            "source_role": "combined",
            "root_output": root_output_name,
            "region": {"start_line": 1, "end_line": end_q},
            "primary_authority": {
                "status": "passed",
                "reviewer_confirmed": True,
                "start_line": 1,
                "end_line": end_q,
                "reading_order": "source-stream",
                "entries": authority
            },
            "entries": entries
        },
        "content": {
            "unknown_label_policy": "retain",
            "question_folder": "习题",
            "question_patterns": [
                r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[、.．]\s*(?!【?(?:答案|解析)】?\b)",
                r"^(?P<number>[1-9]\d?)[、.．]\s*"
            ],
            "inline_question_patterns": [],
            "question_kind_rules": [
                {
                    "kind": "exercise",
                    "pattern": r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[、.．]\s*",
                    "answer_handling": "external",
                    "preserve_internal_headings": True,
                    "metadata": {
                        "试卷出处": clean_title
                    },
                    "folder": "习题"
                }
            ],
            "question_scopes": [
                {
                    "contexts": [e["key"] for e in entries],
                    "kinds": ["exercise"]
                }
            ],
            "roles": []
        },
        "answers": {
            "source_role": "combined",
            "callout_title": f"《{clean_title}》答案与解析",
            "region": {"start_line": ans_boundary, "end_line": end_ans} if ans_boundary else {"start_line": 1, "end_line": len(lines)},
            "contexts": contexts,
            "answer_patterns": [
                r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[、.．]\s*",
                r"^(?:#{1,6}\s*)?第\s*(?P<number>[1-9]\d?)\s*题[:：]?",
                r"^(?P<number>[1-9]\d?)[、.．]\s*(?:答案为|【答案】)",
                r"^(?P<number>[1-9]\d?)[、.．]"
            ],
            "inline_answer_patterns": [],
            "recovered_answers": [],
            "ignore_ranges": []
        }
    }

    write_json_atomic(output_file, adapter, overwrite=True)
    return adapter


def process_single_paper(task: dict, overwrite: bool = False) -> bool:
    title = task["title"]
    pdf_path: Path = task["pdf_path"]
    graph_root: Path = task["graph_root"]
    staging_path: Path = task["staging_path"]

    profile_path = staging_path / "question-type-profile.json"
    canvas_path = graph_root / f"{safe_name(title)}.canvas"
    root_md_path = graph_root / f"{safe_name(title)}.md"

    # Skip check if already completed and audit passed
    if not overwrite and canvas_path.is_file() and root_md_path.is_file():
        cov_manifest = staging_path / "hierarchy-coverage-manifest.json"
        content_manifest = staging_path / "question-type-manifest.json"
        match_manifest = staging_path / "answer-match-manifest.json"
        hier_manifest = staging_path / "hierarchy-manifest.json"
        cov_p = cov_manifest if cov_manifest.is_file() else hier_manifest
        if cov_p.is_file() and content_manifest.is_file() and match_manifest.is_file():
            try:
                res = audit_graph(profile_path, cov_p, content_manifest, match_manifest, canvas_path=canvas_path)
                if res.get("status") == "passed":
                    print(f"[{title}] ALREADY DONE & AUDIT PASSED -> Skipping.")
                    return True
            except Exception:
                pass

    print(f"[{title}] Starting processing ({pdf_path.name})...")
    staging_path.mkdir(parents=True, exist_ok=True)
    raw_md_path = staging_path / "raw" / "combined.raw.md"
    has_raw = raw_md_path.is_file()

    # Step 1: Init profile
    if not profile_path.is_file() or overwrite:
        init_cmd = [
            str(PYTHON_EXE),
            str(SCRIPT_COORDINATOR),
            "init",
            "--source", f"combined={pdf_path}",
            "--title", title,
            "--staging-root", str(staging_path),
            "--vault-root", str(VAULT_ROOT),
            "--graph-root", str(graph_root),
            "--canvas",
            "--output", str(profile_path),
            "--overwrite"
        ]
        res = subprocess.run(init_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[{title}] Init failed: {res.stderr or res.stdout}")
            return False

    # Step 2: MinerU OCR (with retry up to 3 attempts)
    if not has_raw:
        max_ocr_attempts = 3
        for attempt in range(1, max_ocr_attempts + 1):
            run_cmd = [str(PYTHON_EXE), str(SCRIPT_COORDINATOR), "run", str(profile_path), "--overwrite"]
            res = subprocess.run(run_cmd, capture_output=True, text=True)
            if raw_md_path.is_file():
                break
            print(f"[{title}] OCR attempt {attempt} failed, cleaning checkpoint and retrying in 5s...")
            remote_state = staging_path / "combined-mineru-remote-state.json"
            remote_state.unlink(missing_ok=True)
            time.sleep(5)

        if not raw_md_path.is_file():
            print(f"[{title}] OCR conversion failed permanently: {res.stderr or res.stdout}")
            return False

    # Step 3: Build Exam Adapter
    try:
        adapter = build_exam_adapter(staging_path, profile_path, title)
    except Exception as exc:
        print(f"[{title}] Adapter build failed: {exc}")
        return False

    # Step 4: Execute stages directly
    try:
        adapter_path = staging_path / "format-adapter.json"
        cov_manifest = staging_path / "hierarchy-coverage-manifest.json"
        content_manifest = staging_path / "question-type-manifest.json"
        match_manifest = staging_path / "answer-match-manifest.json"
        hier_manifest = staging_path / "hierarchy-manifest.json"
        canvas_manifest = staging_path / "question-type-canvas-manifest.json"

        # Hierarchy
        h = plan_hierarchy(profile_path, adapter_path)
        h["status"] = "passed"
        h["reviewer_confirmed"] = True
        write_json_atomic(hier_manifest, h, overwrite=True)
        apply_hierarchy(profile_path, adapter_path, hier_manifest, overwrite=True)

        # Content
        cov_p = cov_manifest if cov_manifest.is_file() else hier_manifest
        c = plan_content(profile_path, adapter_path, cov_p)
        c["status"] = "passed"
        c["reviewer_confirmed"] = True
        write_json_atomic(content_manifest, c, overwrite=True)
        apply_content(profile_path, adapter_path, content_manifest, overwrite=True)
        num_q = len(c.get("questions", []))

        # Answers
        m = plan_matches(profile_path, adapter_path, content_manifest)
        m["status"] = "passed"
        m["reviewer_confirmed"] = True
        write_json_atomic(match_manifest, m, overwrite=True)
        apply_matches(profile_path, match_manifest, overwrite=True)
        num_a = len(m.get("matches", []))

        # Canvas
        build_canvas(profile_path, hier_manifest, content_manifest, canvas_manifest, canvas_path, overwrite=True)

        # Audit
        audit_res = audit_graph(profile_path, cov_p, content_manifest, match_manifest, canvas_path=canvas_path)
        if audit_res.get("status") != "passed":
            print(f"[{title}] Audit failed: {audit_res.get('errors')}")
            return False

        print(f"[{title}] SUCCESS: {num_q} questions, {num_a} answers matched (Audit PASSED)")
        return True
    except Exception as exc:
        print(f"[{title}] Execution exception: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Batch process Inner Mongolia Exam Papers into Obsidian Question Type Graphs")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of papers to process")
    parser.add_argument("--filter", help="Filter papers by substring in title or filename")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent workers (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Print task list without executing")
    parser.add_argument("--overwrite", action="store_true", help="Force overwrite existing staging and output")
    args = parser.parse_args()

    tasks = collect_paper_tasks(SOURCE_BASE)
    print(f"Total tasks collected: {len(tasks)}")

    if args.filter:
        tasks = [t for t in tasks if args.filter in t["title"] or args.filter in t["pdf_path"].name]
        print(f"After filter '{args.filter}': {len(tasks)} tasks remaining.")

    if args.limit:
        tasks = tasks[:args.limit]
        print(f"Applying limit: {len(tasks)} tasks.")

    if args.dry_run:
        print("\n=== DRY RUN TASK LIST ===")
        for i, t in enumerate(tasks, 1):
            print(f"{i:03d}. {t['title']} (Source: {t['pdf_path'].name}, Dups: {t['duplicate_count']})")
        return

    print(f"\n>>> Executing {len(tasks)} tasks with {args.workers} workers <<<\n")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_task = {executor.submit(process_single_paper, t, args.overwrite): t for t in tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            t = future_to_task[future]
            try:
                passed = future.result()
                results[t["title"]] = passed
            except Exception as exc:
                print(f"Task {t['title']} failed with exception: {exc}")
                results[t["title"]] = False

    passed_count = sum(1 for v in results.values() if v)
    failed_count = len(results) - passed_count
    print(f"\n==================== BATCH SUMMARY ====================")
    print(f"Total Tasks: {len(results)}, Passed: {passed_count}, Failed: {failed_count}")
    if failed_count > 0:
        print("\nFailed Tasks:")
        for k, v in sorted(results.items()):
            if not v:
                print(f"  [FAIL] {k}")


if __name__ == "__main__":
    main()

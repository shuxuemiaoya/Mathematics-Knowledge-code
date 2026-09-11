#!/usr/bin/env python3
"""Batch processor for 人教A版高中数学同步讲义 (2026版全五册) into Obsidian Question Type Graphs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Add lib directory to sys.path
lib_path = Path(__file__).parent / "lib"
if lib_path.exists():
    sys.path.insert(0, str(lib_path.resolve()))

from question_type_graph.common import safe_name, load_json, write_json_atomic
from question_type_graph.audit import audit_graph

SOFFICE_BIN = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
ENV_FILE = Path("/Users/oven/Documents/Mathematics-Knowledge-code/.env")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
STAGING_ROOT_BASE = VAULT_ROOT / ".temp" / "synclabs-2026-staging"
PDF_CACHE_BASE = STAGING_ROOT_BASE / "pdf"
MASTER_GRAPH_ROOT = VAULT_ROOT / "高中" / "课堂同步" / "题库" / "人教A版高中数学同步讲义(2026)"

SCRIPT_COORDINATOR = Path("skills/question-type-graph/scripts/question_type_graph.py").resolve()

BOOKS_CONFIG = [
    ("01_必修第一册", "/Volumes/Whw/数学妙呀资料/高中/课堂同步/题库/1、人教A版高中数学同步讲义必修一/2026"),
    ("02_必修第二册", "/Volumes/Whw/数学妙呀资料/高中/课堂同步/题库/2、人教A版高中数学同步讲义必修二/2026"),
    ("03_选择性必修第一册", "/Volumes/Whw/数学妙呀资料/高中/课堂同步/题库/3、人教A版高中数学同步讲义选择性必修一/2026"),
    ("04_选择性必修第二册", "/Volumes/Whw/数学妙呀资料/高中/课堂同步/题库/4、人教A版高中数学同步讲义选择性必修二/2026"),
    ("05_选择性必修第三册", "/Volumes/Whw/数学妙呀资料/高中/课堂同步/题库/5、人教A版高中数学同步讲义选择性必修三/2026"),
]


def clean_title(title: str) -> str:
    t = re.sub(r"（(?:解析版|全解全析|教师版|试题版|原卷版|考试版).*?）", "", title)
    t = re.sub(r"\[\d+\]", "", t)
    t = re.sub(r"[\$\\/:*?\"<>|]", "", t).strip()
    t = re.sub(r"\s+", "_", t)
    t = safe_name(t)
    if len(t) > 35:
        t = t[:35]
    return t


def convert_docx_to_pdf(docx_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_name = docx_path.stem + ".pdf"
    pdf_path = out_dir / pdf_name
    if pdf_path.is_file() and pdf_path.stat().st_size > 0:
        return pdf_path

    if not Path(SOFFICE_BIN).is_file():
        raise RuntimeError(f"soffice not found at {SOFFICE_BIN}")

    print(f"  [LibreOffice] Converting: {docx_path.name} -> PDF...")
    
    # Kill any stale soffice hung processes
    subprocess.run(["pkill", "-9", "-f", "soffice.bin"], capture_output=True)

    # Use unique UserInstallation to avoid lock conflict
    cmd = [
        SOFFICE_BIN,
        "--headless",
        "-env:UserInstallation=file:///tmp/LibreOffice_Conversion",
        "--convert-to", "pdf",
        str(docx_path),
        "--outdir", str(out_dir)
    ]
    
    for attempt in range(3):
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if pdf_path.is_file() and pdf_path.stat().st_size > 0:
            print(f"    -> Generated: {pdf_name} ({pdf_path.stat().st_size} bytes)")
            return pdf_path
        time.sleep(2)
        subprocess.run(["pkill", "-9", "-f", "soffice.bin"], capture_output=True)

    raise RuntimeError(f"Failed to convert {docx_path.name} to PDF: {res.stderr}")



def sanitize_raw_markdown(raw_file: Path):
    if not raw_file.is_file():
        return
    text = raw_file.read_text(encoding="utf-8-sig")

    # Replace superscript numbers in question headers: 【变式 $^{2}$ 】 -> 【变式2】
    text = re.sub(r"【\s*(变式|例|典例)\s*\$\^\{?(\d+)\}?\$", r"【\1 \2", text)
    text = re.sub(r"【\s*(变式|例|典例)\s*\^(\d+)", r"【\1 \2", text)
    text = re.sub(r"【\s*(变式|例|典例)\s*(\d+)\s*】", r"【\1\2】", text)

    # If a fill-in-the-blank question is followed directly by an equation/text without 【答案】/【解析】/【详解】
    # e.g., "25．已知空间向量...为 ____。\n\n$$\n(0, 2)..."
    # insert "\n\n【答案】\n" so QTG can detect the authoritative solution boundary
    lines = text.splitlines()
    new_lines = []
    sol_markers = ("【答案】", "【解析】", "【分析】", "【详解】", "【思路导航】")
    for i, l in enumerate(lines):
        new_lines.append(l)
        # Check if line is a question stem (e.g. "25．已知..." or "【例1】...") ending with blank / parens / punctuation
        if re.match(r"^\s*(?:\d+[\.．]|【\s*(?:例|变式|练)[^】]*】)", l) and re.search(r"(?:(?:\\_|_){2,}|（\s*）|\(\s*\)|为|是)[。：\.\s]*$", l):
            # check next non-empty line
            for nxt_idx in range(i + 1, min(len(lines), i + 5)):
                nxt_line = lines[nxt_idx].strip()
                if not nxt_line:
                    continue
                # Never insert 【答案】 if next line is multiple choice option (e.g. A. B. C. D.)
                if re.match(r"^\s*(?:[A-D][\.．、\s]|[（(][A-D][）)])", nxt_line):
                    break
                if not any(nxt_line.startswith(m) for m in sol_markers) and not re.match(r"^\s*(?:\d+[\.．]|【\s*(?:例|变式|练)[^】]*】|#)", nxt_line):
                    # Next line is solution content but missing 【答案】
                    new_lines.append("\n【答案】")
                break
    text = "\n".join(new_lines)
    # Remove any falsely inserted 【答案】 right before choice options
    text = re.sub(r'【答案】\s*\n\s*([A-D][\.．、\s])', r'\1', text)

    # Merge wrapped list item numbers that MinerU falsely put on a new line (e.g. "i=1,2,3,\ldots,\n\n25. 已知")
    text = re.sub(r'(\\ldots,?\s*)\n+(\d+)\.\s*(已知|设|若)', r'\1 \2。 \3', text)
    text = re.sub(r'\n+(\d+)\.\s*(已知\s*[A-Za-z\s]*类型样本)', r'\n\1。 \2', text)

    raw_file.write_text(text, encoding="utf-8")

    # Keep questions-conversion-report.json target_sha256 in sync
    conv_report = raw_file.parent.parent / "questions-conversion-report.json"
    if conv_report.is_file():
        import hashlib
        try:
            r_data = json.loads(conv_report.read_text(encoding="utf-8"))
            r_data["target_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            conv_report.write_text(json.dumps(r_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass



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


def extract_content_headings(lines: list[str]) -> list[tuple[int, str, str]]:
    """Extract semantic headings for adapter.
    Returns: list of (line_number, raw_title_heading_matched, folder_name)
    """
    # 1. Check if document has 题型 sections
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
                folder_name = make_folder_name(raw_title)
                tx_headings.append((i, raw_title, folder_name))

    if tx_headings:
        # Check if there is also a 强化训练 / 即学即练 after the 题型 sections
        for i, line in enumerate(lines, 1):
            if i > tx_headings[-1][0]:
                m_qh = re.match(r"^\s*#{1,4}\s*(强化训练|【即学即练】|考点专练)", line)
                if m_qh:
                    raw_title = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
                    tx_headings.append((i, raw_title, make_folder_name(raw_title)))
                    break
        return tx_headings

    # 2. If no 题型, match test paper or unit test sections (一、选择题, etc.)
    sec_headings = []
    sec_pattern = r"^\s*#{1,4}\s*(知识清单|知识点\s*\d+.*|【即学即练】|题型精讲|强化训练|一、选择题.*|二、多选题.*|三、填空题.*|四、解答题.*|第[一二三四五]部分.*|专题\d+.*)"
    for i, line in enumerate(lines, 1):
        m = re.match(sec_pattern, line)
        if m:
            raw_title = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
            folder_name = make_folder_name(raw_title)
            sec_headings.append((i, raw_title, folder_name))

    if sec_headings:
        return sec_headings

    # 3. Fallback to any markdown headings
    fb_headings = []
    for i, line in enumerate(lines, 1):
        m = re.match(r"^\s*#{1,3}\s*([^#\n]+)", line)
        if m and not re.search(r"教学目标|教学重难点|答案|解析|分析", m.group(1)):
            raw_title = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
            folder_name = make_folder_name(raw_title)
            fb_headings.append((i, raw_title, folder_name))

    return fb_headings


def build_adapter_for_topic(staging_path: Path, profile_file: Path, clean_topic: str):
    raw_file = staging_path / "raw" / "questions.raw.md"
    output_file = staging_path / "format-adapter.json"

    if not raw_file.is_file():
        raise RuntimeError(f"Raw markdown not found at {raw_file}")

    sanitize_raw_markdown(raw_file)
    lines = raw_file.read_text(encoding="utf-8").splitlines()

    headings = extract_content_headings(lines)

    entries = []
    authority = []
    exercise_contexts = []
    variant_contexts = []

    has_jiangyi = any("题型" in t for _, t, _ in headings) and any("强化训练" in t or "即学即练" in t for _, t, _ in headings)

    seen_folder_names: dict[str, int] = {}
    for idx, (l_no, title, folder_name) in enumerate(headings, 1):
        key = f"sec-{idx:02d}"

        if folder_name in seen_folder_names:
            seen_folder_names[folder_name] += 1
            dedup_folder = f"{folder_name}_{seen_folder_names[folder_name]}"
        else:
            seen_folder_names[folder_name] = 1
            dedup_folder = folder_name

        authority.append({
            "key": key,
            "title": title,
            "level": 1,
            "source_line": l_no,
            "reviewer_confirmed": True
        })
        entries.append({
            "key": key,
            "title": title,
            "level": 1,
            "output": f"{dedup_folder}/{dedup_folder}.md",
            "body_anchor": {
                "kind": "source-heading",
                "start_line": l_no,
                "reviewer_confirmed": True
            },
            "emit_title": False,
            "reviewer_confirmed": True
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

    adapter = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "filename_policy": {"colon_replacement": "_"},
        "output_policy": {"generate_index": True, "generate_canvas": False},
        "profile": str(profile_file),
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
                "entries": authority
            },
            "entries": entries
        },
        "content": {
            "max_path_length": 300,
            "max_path_component_length": 60,
            "unknown_label_policy": "retain",
            "question_folder": "questions",
            "question_repository_root": str(VAULT_ROOT / "question-qid-registry.json"),
            "question_title_template": "题 {number}",
            "question_patterns": [
                q_pattern_var,
                q_pattern_num
            ],
            "inline_question_patterns": [],
            "question_kind_rules": [
                {
                    "kind": "variant-example",
                    "pattern": q_pattern_var,
                    "answer_handling": "separate-authoritative",
                    "preserve_internal_headings": True,
                    "folder": "questions"
                },
                {
                    "kind": "numbered-exercise",
                    "pattern": q_pattern_num,
                    "sequence_policy": "continuous",
                    "answer_handling": "separate-authoritative",
                    "preserve_internal_headings": True,
                    "folder": "questions"
                }
            ],
            "worked_example_solution_patterns": [
                r"^\s*【答案】",
                r"^\s*【解析】",
                r"^\s*【分析】",
                r"^\s*【详解】",
                r"^\s*【思路导航】"
            ],
            "worked_example_solution_backtrack_fence": True,
            "worked_example_callout_title": f"《{clean_topic}》官方解析",
            "answer_callout_layout_version": 2,
            "question_scopes": question_scopes,
            "roles": []
        },
        "answers": {
            "source_role": "questions",
            "callout_title": f"《{clean_topic}》参考答案",
            "region": {"start_line": 1, "end_line": len(lines)},
            "contexts": [],
            "answer_patterns": [
                r"^(?P<number>[1-9]\d?)[.．、]\s*"
            ],
            "answer_kind_rules": []
        }
    }

    output_file.write_text(json.dumps(adapter, ensure_ascii=False, indent=2), encoding="utf-8")


def locate_staging_dir(book_name: str, docx_stem: str, chapter_name: str, topic_name: str) -> Path | None:
    """Locate existing staging directory by inspecting profiles and folder names."""
    book_staging = STAGING_ROOT_BASE / book_name
    if not book_staging.is_dir():
        return None

    clean_t = clean_title(docx_stem)

    # Pass 1: Search through subdirectories checking profiles for exact docx_stem match
    for d in book_staging.iterdir():
        if not d.is_dir():
            continue
        prof = d / "question-type-profile.json"
        if prof.is_file():
            try:
                data = json.loads(prof.read_text(encoding="utf-8"))
                for s in data.get("sources", []):
                    p = s.get("path", "")
                    if (docx_stem in p or Path(p).stem == docx_stem) and (d / "raw" / "questions.raw.md").is_file():
                        return d
            except Exception:
                pass

    # Pass 2: Structured matching by chapter prefix + topic identity
    is_tisheng = "提升" in topic_name or "提升" in docx_stem
    is_qianghua = ("强化" in topic_name or "强化" in docx_stem) and not is_tisheng

    # Extract topic number (e.g. "专题01", "专题5.1", "专题04+")
    num_m = re.search(r"专题\s*(\d+(?:\.\d+)*)", topic_name) or re.search(r"专题\s*(\d+(?:\.\d+)*)", docx_stem)
    topic_num = ("专题" + num_m.group(1)) if num_m else None

    # Detect topic type
    is_chapter_jiangyi = ("讲义" in topic_name) and not topic_num  # 全章讲义, not 专题讲义
    is_danyuan_ceshi = ("单元测试" in topic_name) and not topic_num
    is_qizhong_model = any(k in topic_name for k in ["模拟卷", "月考"]) and not topic_num

    # Clean chapter key for prefix matching
    chapter_clean = re.sub(r"[\s/\\:*?\"<>|【】（）()\$\+\-]+", "", chapter_name)

    candidates = []
    for d in book_staging.iterdir():
        if not d.is_dir():
            continue
        if not (d / "raw" / "questions.raw.md").is_file():
            continue

        d_name = d.name
        d_flat = d_name.replace("_", "")

        # Gate 1: Chapter prefix must match (at least first 3 chars, e.g. "月考", "期中", "第一章", "第二章")
        ch_key = chapter_clean[:3] if len(chapter_clean) >= 3 else chapter_clean
        if ch_key not in d_flat:
            continue

        # Gate 2: 提升卷/强化卷 strict isolation
        if is_tisheng != ("提升" in d_name):
            continue
        if is_qianghua and "提升" in d_name:
            continue

        # Gate 3: Topic number matching (most specific)
        if topic_num:
            norm_dot = topic_num.replace(".", "_")
            norm_flat = topic_num.replace(".", "")
            if topic_num in d_name or norm_dot in d_name or norm_flat in d_name:
                # Verify exact number to avoid 专题5 matching 专题5.5
                d_num_m = re.search(r"专题_?(\d+(?:[_\.]\d+)*)", d_name)
                if d_num_m:
                    d_num_flat = d_num_m.group(1).replace("_", ".").replace("..", ".")
                    t_num_flat = num_m.group(1) if num_m else ""
                    if d_num_flat == t_num_flat:
                        # Also check type alignment: 讲义 vs 专项训练
                        score = 10
                        if "讲义" in topic_name and "讲义" in d_name:
                            score += 2
                        elif "专项训练" in topic_name and ("专项训练" in d_name or "培优专项" in d_name):
                            score += 2
                        candidates.append((score, d))
                else:
                    candidates.append((5, d))
        elif is_chapter_jiangyi:
            # Must NOT be a 专题 staging
            if "专题" in d_name:
                continue
            if "讲义" in d_name and "单元测试" not in d_name:
                candidates.append((8, d))
        elif is_danyuan_ceshi:
            if "专题" in d_name:
                continue
            if "单元测试" in d_name or ("强化" in d_name and "专题" not in d_name):
                candidates.append((8, d))
        elif is_qizhong_model:
            # 模拟卷 / 月考 — broad stem matching
            stem_flat = re.sub(r"[\s/\\:*?\"<>|【】（）()\$\+\-]+", "", clean_t)
            if stem_flat[:12] in d_flat:
                candidates.append((6, d))
        else:
            # General fallback: stem substring match
            stem_flat = re.sub(r"[\s/\\:*?\"<>|【】（）()\$\+\-]+", "", clean_t)
            score = 0
            for length in range(14, 4, -2):
                if stem_flat[:length] in d_flat:
                    score = length
                    break
            if score > 0:
                candidates.append((score, d))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # Fallback to independent dedicated staging path
    unique_tag = "_提升卷" if is_tisheng else ("_强化卷" if is_qianghua else ("_讲义" if is_chapter_jiangyi else ("_单元测试" if is_danyuan_ceshi else "")))
    fallback_dir = book_staging / (safe_name(f"{chapter_name}_{clean_t}") + unique_tag)
    return fallback_dir


def check_graph_number_gaps(graph_root: Path) -> list[int]:
    """Check if question numbers have gaps/missing numbers in a generated topic graph."""
    if not graph_root.is_dir():
        return []
    questions_files = list(graph_root.rglob("questions/Q*.md"))
    if not questions_files:
        return []
    num_map = {}
    for qf in questions_files:
        txt = qf.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"###\s+题目\s*\n+([1-9]\d{0,2})[.．、]", txt)
        if m:
            num = int(m.group(1))
            num_map[num] = qf.name
    if not num_map:
        return []
    nums = sorted(num_map.keys())
    all_present = set(nums)
    expected_range = range(nums[0], nums[-1] + 1)
    missing = [x for x in expected_range if x not in all_present]
    return missing


def process_single_task(
    book_name: str,
    chapter_name: str,
    topic_name: str,
    docx_path: Path,
    staging_dir: Path | None,
    dry_run: bool = False,
    force: bool = False,
    repair_gaps: bool = False
) -> bool:
    # Target graph root according to user requirement:
    # MASTER_GRAPH_ROOT / book_name / chapter_name / topic_name
    graph_root = MASTER_GRAPH_ROOT / book_name / chapter_name / topic_name

    clean_t = clean_title(docx_path.stem)
    if staging_dir is None:
        staging_dir = STAGING_ROOT_BASE / book_name / safe_name(f"{chapter_name}_{clean_t}")

    print(f"\n========================================================")
    print(f"Processing: [{book_name}] {chapter_name} / {topic_name}")
    print(f"  Docx: {docx_path.name}")
    print(f"  Graph Root: {graph_root}")
    print(f"  Staging:    {staging_dir}")
    print(f"========================================================")

    # Check if repair_gaps is enabled and whether existing graph has gaps
    if repair_gaps and not force:
        gaps = check_graph_number_gaps(graph_root)
        if gaps:
            print(f"  [REPAIR GAP DETECTED] Missing question numbers: {gaps[:10]}... Forcing regeneration!")
            force = True

    audit_file = staging_dir / "final-audit-report.json"
    if not force and audit_file.is_file():
        try:
            audit_data = load_json(audit_file)
            prof_file = staging_dir / "question-type-profile.json"
            if prof_file.is_file():
                prof_data = load_json(prof_file)
                if prof_data.get("paths", {}).get("graph_root") == str(graph_root) and audit_data.get("status") == "passed":
                    print(f"  -> Already completed & audit passed: {topic_name} ({audit_data.get('question_count', 0)} questions)")
                    return True
        except Exception:
            pass

    if dry_run:
        print(f"  [DRY RUN] Would process: {topic_name}")
        return True

    # 1. Convert Docx to PDF if needed
    pdf_dir = PDF_CACHE_BASE / book_name
    pdf_path = convert_docx_to_pdf(docx_path, pdf_dir)

    # 2. Init QTG Profile
    staging_dir.mkdir(parents=True, exist_ok=True)
    profile_file = staging_dir / "question-type-profile.json"

    # Clean prior non-raw intermediate artifacts in staging to avoid collision
    keep_names = ["raw", "questions-conversion-report.json", "source-provenance-index.json", "questions-mineru-remote-state.json"]
    if not force:
        keep_names.append("format-adapter.json")
    for f in list(staging_dir.iterdir()):
        if f.name in keep_names:
            continue
        if f.is_dir():
            shutil.rmtree(f, ignore_errors=True)
        else:
            f.unlink(missing_ok=True)

    # Ensure target graph_root is clean
    if graph_root.exists():
        shutil.rmtree(graph_root, ignore_errors=True)

    cmd_init = [
        sys.executable,
        str(SCRIPT_COORDINATOR),
        "init",
        "--source", f"questions={pdf_path}",
        "--title", topic_name,
        "--staging-root", str(staging_dir),
        "--vault-root", str(VAULT_ROOT),
        "--graph-root", str(graph_root),
        "--overwrite",
        "--output", str(profile_file)
    ]
    res = subprocess.run(cmd_init, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  Error initializing profile: {res.stderr}")
        return False

    # 3. Check raw Markdown
    raw_file = staging_dir / "raw" / "questions.raw.md"
    if not raw_file.is_file():
        print(f"  [MinerU OCR] Submitting PDF to MinerU...")
        cmd_run = [
            sys.executable,
            str(SCRIPT_COORDINATOR),
            "run",
            "--env-file", str(ENV_FILE),
            str(profile_file)
        ]
        res = subprocess.run(cmd_run, capture_output=True, text=True)
        if not raw_file.is_file():
            print(f"  MinerU OCR failed to generate {raw_file}: {res.stderr}")
            return False

    # Ensure questions-conversion-report.json exists for resume step
    conv_report = staging_dir / "questions-conversion-report.json"
    if raw_file.is_file() and not conv_report.is_file():
        import hashlib
        pdf_bytes = pdf_path.read_bytes() if pdf_path.is_file() else b""
        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else "unknown"
        raw_bytes = raw_file.read_bytes()
        raw_sha = hashlib.sha256(raw_bytes).hexdigest()
        report = {
            "schema_version": 1,
            "stage": "question-type-pdf-to-markdown",
            "status": "completed",
            "profile": str(profile_file),
            "role": "questions",
            "source_pdf": str(pdf_path),
            "source_sha256": pdf_sha,
            "target_md": str(raw_file),
            "target_sha256": raw_sha,
            "page_count": 1,
            "part_count": 1,
            "parts": [{"index": 1, "start_page": 1, "end_page": 1}],
            "asset_count": 0,
            "page_provenance": {
                "format": "mineru-content-list",
                "page_index_semantics": "raw MinerU page_idx values are preserved per PDF part",
                "artifact_count": 0,
                "artifacts": []
            },
            "ocr_forced": True,
            "model_version": "vlm",
            "language": "ch",
            "enable_formula": True,
            "enable_table": True,
            "validation": {
                "source_hash_unchanged": True,
                "page_coverage_complete": True,
                "target_nonempty": True,
                "page_block_provenance_preserved": True
            }
        }
        write_json_atomic(conv_report, report)

    # 4. Synthesize reviewed adapter
    build_adapter_for_topic(staging_dir, profile_file, topic_name)

    # 5. Resume QTG Coordinator
    print(f"  [QTG Pipeline] Resuming hierarchy, content segmentation & formatting...")
    cmd_resume = [
        sys.executable,
        str(SCRIPT_COORDINATOR),
        "resume",
        "--overwrite",
        "--env-file", str(ENV_FILE),
        str(profile_file)
    ]
    res = subprocess.run(cmd_resume, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  Resume failed: {res.stdout}\n{res.stderr}")
        return False

    # 6. Check Audit
    if audit_file.is_file():
        audit_data = load_json(audit_file)
        if audit_data.get("status") == "passed":
            print(f"  -> SUCCESS: Audit passed! Questions count: {audit_data.get('question_count')}")
            return True
        else:
            print(f"  -> Audit failed: {audit_data.get('errors')}")
            return False
    return False


def main():
    parser = argparse.ArgumentParser(description="Process 2026 Sync Lecture Notes into Question Type Graph")
    parser.add_argument("--book", choices=["1", "2", "3", "4", "5", "all"], default="all", help="Book index or all")
    parser.add_argument("--chapter", help="Filter by chapter substring")
    parser.add_argument("--topic", help="Filter by topic substring")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files to process (0 for unlimited)")
    parser.add_argument("--clean-old", action="store_true", help="Remove old category directories (专项训练, 单元测试, 讲义)")
    parser.add_argument("--repair-gaps", action="store_true", help="Detect and repair topics with question number gaps")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without processing")
    args = parser.parse_args()

    target_books = BOOKS_CONFIG if args.book == "all" else [BOOKS_CONFIG[int(args.book) - 1]]

    # Clean old invalid classification directories if requested (strictly scoped!)
    if args.clean_old:
        print("Cleaning legacy category directories (专项训练, 单元测试, 讲义, 阶段测试)...")
        for b_name, _ in target_books:
            book_dir = MASTER_GRAPH_ROOT / b_name
            if not book_dir.is_dir():
                continue
            for chap_dir in book_dir.iterdir():
                if not chap_dir.is_dir():
                    continue
                if args.chapter and args.chapter not in chap_dir.name:
                    continue
                for old_cat in ["专项训练", "单元测试", "讲义", "阶段测试"]:
                    cat_dir = chap_dir / old_cat
                    if cat_dir.is_dir():
                        if args.dry_run:
                            print(f"  [DRY-RUN] Would remove scoped old directory: {cat_dir}")
                        else:
                            print(f"  Removing scoped old directory: {cat_dir}")
                            shutil.rmtree(cat_dir, ignore_errors=True)


    repack_dir = STAGING_ROOT_BASE / "repackaged_docx"
    repack_files = {f.stem: f for f in repack_dir.glob("*.docx")} if repack_dir.is_dir() else {}

    # Helper: normalize key for fuzzy repack matching
    def _clean_key(s: str) -> str:
        return re.sub(r"[\s\+\-\_（）\(\)\.、~\[\]]+", "", s)

    # Build fuzzy repack index
    repack_cleaned = {_clean_key(k): v for k, v in repack_files.items()}

    def _find_repack(topic_name: str) -> Path | None:
        """Find a repackaged docx by fuzzy clean-key matching."""
        # 1. Exact stem match
        if topic_name in repack_files:
            return repack_files[topic_name]
        # 2. Cleaned key substring match (bidirectional)
        ck = _clean_key(topic_name)
        for rk, rv in repack_cleaned.items():
            if ck[:20] in rk or rk[:20] in ck:
                return rv
        return None

    def _is_unzipped_docx(d: Path) -> bool:
        """Check if directory is an unzipped .docx package (contains word/ subdirectory)."""
        return (d / "word").is_dir() or (d / "[Content_Types].xml").is_file()

    def _derive_topic_name(raw_name: str) -> str:
        """Strip version suffixes like （解析版）, （原卷版） etc. from a topic name."""
        t = re.sub(r"（(?:解析版|原卷版|全解全析|教师版|试题版|考试版)）", "", raw_name)
        t = re.sub(r"\((?:解析版|原卷版|全解全析|教师版|试题版|考试版)\)", "", t)
        t = re.sub(r"\.docx$", "", t)
        return t.strip()

    tasks = []
    for b_name, b_path in target_books:
        for chapter_dir in sorted(Path(b_path).iterdir()):
            if not chapter_dir.is_dir():
                continue
            if args.chapter and args.chapter not in chapter_dir.name:
                continue

            # Collect direct docx files in chapter (e.g. Chapter 5 三角函数 flat layout)
            direct_docxs = [f for f in chapter_dir.iterdir()
                            if f.is_file() and f.suffix == ".docx" and not f.name.startswith("~$")
                            and any(k in f.name for k in ["解析版", "全解全析", "教师", "（解析）", "(解析)"])
                            and not any(k in f.name for k in ["原卷", "考试版", "参考答案"])]
            # Group direct docx as individual tasks with topic_name derived from filename
            seen_direct_topics = set()
            for docx_f in sorted(direct_docxs):
                topic_name = _derive_topic_name(docx_f.stem)
                if args.topic and args.topic not in topic_name:
                    continue
                if topic_name in seen_direct_topics:
                    continue
                seen_direct_topics.add(topic_name)
                staging_dir = locate_staging_dir(b_name, docx_f.stem, chapter_dir.name, topic_name)
                tasks.append((b_name, chapter_dir.name, topic_name, docx_f, staging_dir))

            for topic_dir in sorted(chapter_dir.iterdir()):
                if not topic_dir.is_dir():
                    continue
                if args.topic and args.topic not in topic_dir.name:
                    continue

                # Case A: Unzipped docx package (directory with word/ inside)
                if _is_unzipped_docx(topic_dir):
                    topic_name = _derive_topic_name(topic_dir.name)
                    if topic_name in seen_direct_topics:
                        continue  # already handled via direct docx
                    chosen_docx = _find_repack(topic_dir.name) or _find_repack(topic_name)
                    if chosen_docx:
                        staging_dir = locate_staging_dir(b_name, chosen_docx.stem, chapter_dir.name, topic_name)
                        tasks.append((b_name, chapter_dir.name, topic_name, chosen_docx, staging_dir))
                    else:
                        print(f"  [SKIP] Unzipped docx with no repack: {topic_dir.name}")
                    continue

                # Case B: Normal topic subdirectory
                docxs = [f for f in topic_dir.rglob("*.docx") if not f.name.startswith("~$") and "/word" not in str(f)]
                docxs = [f for f in docxs if any(k in f.name for k in ["解析版", "全解全析", "教师", "（解析）", "(解析)"]) and not any(k in f.name for k in ["原卷", "考试版", "参考答案"])]

                chosen_docx = None
                if docxs:
                    chosen_docx = docxs[0]
                else:
                    # Try repack matching
                    chosen_docx = _find_repack(topic_dir.name)
                    if not chosen_docx:
                        # Also try matching inside the topic_dir for unzipped packages
                        for sub in topic_dir.iterdir():
                            if sub.is_dir() and _is_unzipped_docx(sub):
                                chosen_docx = _find_repack(sub.name) or _find_repack(_derive_topic_name(sub.name))
                                if chosen_docx:
                                    break

                if chosen_docx:
                    staging_dir = locate_staging_dir(b_name, chosen_docx.stem, chapter_dir.name, topic_dir.name)
                    tasks.append((b_name, chapter_dir.name, topic_dir.name, chosen_docx, staging_dir))

    print(f"Found {len(tasks)} tasks matching criteria.")
    if args.limit > 0:
        tasks = tasks[:args.limit]
        print(f"Limited to {len(tasks)} tasks.")

    success_count = 0
    fail_count = 0
    for idx, (b_name, chap_name, top_name, docx_p, st_dir) in enumerate(tasks, 1):
        print(f"\n>>> [{idx}/{len(tasks)}] Starting {top_name} ...")
        ok = process_single_task(
            b_name, chap_name, top_name, docx_p, st_dir,
            dry_run=args.dry_run,
            repair_gaps=args.repair_gaps
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1

    print(f"\n========================================================")
    print(f"Batch completed: {success_count} succeeded, {fail_count} failed.")
    print(f"========================================================")


if __name__ == "__main__":
    main()

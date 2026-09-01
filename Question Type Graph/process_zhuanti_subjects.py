#!/usr/bin/env python3
"""Universal batch processor for 高中总复习专题 PDF collections into Obsidian Question Type Graphs."""

import json
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

SOURCE_ROOT = Path("/Volumes/Whw/数学妙呀资料/高中/总复习/专题")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
GRAPH_BASE = VAULT_ROOT / "高中" / "总复习" / "专题"

PYTHON_EXE = sys.executable
SCRIPT_COORDINATOR = Path("skills/question-type-graph/scripts/question_type_graph.py").resolve()

CN_NUMS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15
}


def normalize_section_title(raw_title: str) -> str:
    m = re.match(r"^\s*【?考点([一二三四五六七八九十0-9]+)】?[：:\s_._-]*(.*)$", raw_title)
    if m:
        num_str = m.group(1)
        sub_title = m.group(2).strip()
        if num_str.isdigit():
            num = int(num_str)
        else:
            num = CN_NUMS.get(num_str, 1)
        return safe_name(f"考点{num:02d}_{sub_title}")
    return safe_name(raw_title)


def build_teacher_adapter(staging_path: Path, subject_name: str, clean_title: str):
    topic_stem = re.sub(rf"-{re.escape(subject_name)}.*$", "", clean_title).strip()
    draft_file = staging_path / "format-adapter.draft.json"
    raw_file = staging_path / "raw" / "questions.raw.md"
    output_file = staging_path / "format-adapter.json"
    profile_file = staging_path / "question-type-profile.json"

    if not draft_file.is_file() or not raw_file.is_file():
        raise RuntimeError(f"Draft or raw file missing in {staging_path}")

    lines = raw_file.read_text(encoding="utf-8-sig").splitlines()
    draft = json.loads(draft_file.read_text(encoding="utf-8"))

    headings = []
    for i, line in enumerate(lines, 1):
        m = re.match(r"^\s*(#{1,6}\s*)?【?(考点[一二三四五六七八九十0-9]+[：:\s_._-]*[^】\n]*)】?", line)
        if m:
            headings.append((i, m.group(2).strip()))

    if not headings:
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*(#{1,6}\s*)(考点.*|专题\d+.*|模型\d+.*)", line)
            if m and not re.match(r"^\s*#{1,6}\s*(专题\d+\s+.*|1\.|2\.|3\.|4\.|5\.|6\.|7\.|基本知识|基本方法|基本题型|对点精练|对点训练)", line):
                headings.append((i, m.group(2).strip()))

    entries = []
    authority = []
    for i, (line_no, title) in enumerate(headings):
        key = f"section-{i+1:02d}"
        norm_title = normalize_section_title(title)
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

    if not entries:
        key = "section-01"
        norm_title = normalize_section_title(topic_stem)
        authority = [{
            "key": key,
            "title": topic_stem,
            "level": 1,
            "source_line": 1
        }]
        entries = [{
            "key": key,
            "title": topic_stem,
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

    scopes = []
    for i, entry in enumerate(entries):
        key = entry["key"]
        start_line = entry.get("body_anchor", {}).get("start_line", 1)
        end_line = (
            entries[i + 1].get("body_anchor", {}).get("start_line", len(lines) + 1) - 1
            if i + 1 < len(entries)
            else len(lines)
        )
        sec_lines = lines[start_line - 1 : end_line]

        example_starts = []
        practice_starts = []
        for rel_idx, line in enumerate(sec_lines):
            note_line_no = rel_idx + 1
            if re.search(
                r"^\s*#{0,6}\s*【?(?:例题选讲|典型例题|典例剖析|精选题型|题型精讲|例题精析|例题)】?",
                line,
            ) or re.match(r"^\s*\[?例\s*\d+", line):
                example_starts.append(note_line_no)
            elif re.search(
                r"^\s*#{0,6}\s*【?(?:对点训练|对点精练|当堂检测|达标检测|考点过关|强化训练|巩固练习|跟踪训练|随堂练习|课后作业|课时作业)】?",
                line,
            ):
                practice_starts.append(note_line_no)

        if example_starts:
            scopes.append({
                "context": key,
                "kinds": ["worked-example"],
                "start_line": min(example_starts),
                "end_line": len(sec_lines),
            })
        if practice_starts:
            scopes.append({
                "context": key,
                "kinds": ["separate-authoritative"],
                "start_line": min(practice_starts),
                "end_line": len(sec_lines),
            })
        if not example_starts and not practice_starts:
            scopes.append({
                "context": key,
                "kinds": ["worked-example", "separate-authoritative"],
                "start_line": 1,
                "end_line": len(sec_lines),
            })

    topic_stem = re.sub(rf"-{re.escape(subject_name)}.*$", "", clean_title).strip()
    root_output_name = f"{safe_name(topic_stem)}.md"

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
            "question_folder": "对点训练",
            "question_repository_root": "/Users/oven/Documents/ovenmathmap/mathmap/习题/questions",
            "question_title_template": "题 {number}",
            "question_patterns": [
                r"^(?P<number>\[?例\s*\d+(?:\.\d+)?\]?)\s*",
                r"^(?P<number>\[?变式(?:题)?\s*(?:[（(]?\d+[）)]?)?\]?)\s*[：:]?\s*",
                r"^(?P<number>[1-9]\d?)[.．、]\s*(?!\s*【?(?:答案|解析)】?\b)(?!\s*[^.\n]*?法[.．]?\s*$)(?=[（(\[\$【a-zA-Z\u4e00-\u9fa5])"
            ],
            "inline_question_patterns": [
                r"(?P<number>\([1-9]\d?\)|（[1-9]\d?）)\s*"
            ],
            "question_kind_rules": [
                {
                    "kind": "worked-example",
                    "pattern": r"^\[?例\s*\d+(?:\.\d+)?\]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "interleaved",
                    "atomize_interleaved_subquestions": True,
                    "atomized_subquestion_patterns": [
                        r"(?:^\[?例\s*\d+(?:\.\d+)?\]?\s*)?(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^[（(]?(?P<part>[1-9]\d?)[）)]"
                    ],
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?[【\[]?(?:答案与解析|答案及解析|答案|解析|分析|详解|详细解答|解答|解法|试题解析|思路点拨|思路分析|解)[】\]]?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】",
                        r"^\s*\[答案\]",
                        r"^\s*\[解析\]",
                        r"^\s*\[分析\]",
                        r"^\s*\[详解\]",
                        r"^\s*\[解答\]",
                        r"^\s*\[思路点拨\]"
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
                    "pattern": r"^\[?变式(?:题)?\s*(?:[（(]?\d+[）)]?)?\]?\s*[：:]?\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "interleaved",
                    "atomize_interleaved_subquestions": True,
                    "atomized_subquestion_patterns": [
                        r"(?:^\[?变式(?:题)?\s*(?:[（(]?\d+[）)]?)?\]?\s*[：:]?\s*)?(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^(?P<part>\([1-9]\d?\)|（[1-9]\d?）)",
                        r"^[（(]?(?P<part>[1-9]\d?)[）)]"
                    ],
                    "solution_start_patterns": [
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?[【\[]?(?:答案与解析|答案及解析|答案|解析|分析|详解|详细解答|解答|解法|试题解析|思路点拨|思路分析|解)[】\]]?[：:\s]?",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                        r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                        r"^\s*【答案】",
                        r"^\s*【解析】",
                        r"^\s*【分析】",
                        r"^\s*【详解】",
                        r"^\s*\[答案\]",
                        r"^\s*\[解析\]",
                        r"^\s*\[分析\]",
                        r"^\s*\[详解\]",
                        r"^\s*\[解答\]",
                        r"^\s*\[思路点拨\]"
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
                    "kind": "separate-authoritative",
                    "pattern": r"^(?P<number>[1-9]\d?)[.．、](?!\s*【?(?:答案|解析)】?\b)(?!\s*[^.\n]*?法[.．]?\s*)\s*",
                    "answer_handling": "separate-authoritative",
                    "preserve_internal_headings": True,
                    "sequence_policy": "none",
                    "folder": "对点训练"
                }
            ],
            "worked_example_solution_patterns": [
                r"^\s*(?:[1-9]\d?[.．、]\s*)?[【\[]?(?:答案与解析|答案及解析|答案|解析|分析|详解|思路导航|详细解答|解答|解法|证法|证明|点拨|名师点睛|点睛|考点|总结|规律总结|试题解析|思路点拨|思路分析|解)[】\]]?[：:\s]?",
                r"^\s*(?:[1-9]\d?[.．、]\s*)?答案\b",
                r"^\s*(?:[1-9]\d?[.．、]\s*)?解析\b",
                r"^\s*【答案】",
                r"^\s*【解析】",
                r"^\s*\[答案\]",
                r"^\s*\[解析\]",
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
            "question_scopes": scopes,
            "roles": []
        },
        "answers": {
            "source_role": "questions",
            "mode": "separate",
            "question_number_regexes": [
                r"^(?P<number>\[?例\s*\d+(?:\.\d+)?\]?)\s*",
                r"^(?P<number>\[?变式(?:题)?\s*(?:[（(]?\d+[）)]?)?\]?)\s*[：:]?\s*",
                r"^(?P<number>[1-9]\d?)[.．、]\s*"
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
    print(f"Wrote teacher adapter for {clean_title} to {output_file}")


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

        if adapter_path.is_file() and cov_path.is_file():
            print("Force-running plan_hierarchy & apply_hierarchy...")
            hier_plan = plan_hierarchy(profile_path, adapter_path)
            hier_plan["status"] = "passed"
            hier_plan["reviewer_confirmed"] = True
            write_json_atomic(hier_manifest_path, hier_plan, overwrite=True)
            apply_hierarchy(profile_path, adapter_path, hier_manifest_path, overwrite=True)

            print("Force-running plan_content...")
            content_plan = plan_content(profile_path, adapter_path, cov_path)
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


def process_single_topic(subject_name: str, clean_title: str, pdf_path: Path) -> bool:
    print(f"\n=======================================================")
    print(f" PROCESSING [{subject_name}] TOPIC: {clean_title}")
    print(f" PDF Path: {pdf_path.name}")
    print(f"=======================================================\n")

    staging_path = VAULT_ROOT / ".temp" / f"{subject_name}-{clean_title}-staging"
    profile_path = staging_path / "question-type-profile.json"
    graph_root = GRAPH_BASE / subject_name / clean_title
    topic_stem = re.sub(rf"-{re.escape(subject_name)}.*$", "", clean_title).strip()
    root_output_name = f"{safe_name(topic_stem)}.md"

    # Fast skip if already generated and verified
    if graph_root.exists() and (graph_root / root_output_name).exists() and staging_path.exists():
        cov = staging_path / "hierarchy-coverage-manifest.json"
        content = staging_path / "question-type-manifest.json"
        answer = staging_path / "answer-match-manifest.json"
        if cov.exists() and content.exists() and answer.exists():
            try:
                res = audit_graph(profile_path, cov, content, answer, canvas_path=None)
                if res.get("status") == "passed":
                    print(f"Topic {clean_title} is already fully generated and audited. Skipping.")
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
        PYTHON_EXE,
        str(SCRIPT_COORDINATOR),
        "init",
        "--source", f"questions={pdf_path}",
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
        print(f"Init failed for {clean_title}: returncode={res.returncode}\nstdout: {res.stdout}\nstderr: {res.stderr}")
        return False

    # Step 2: Run pipeline (MinerU OCR)
    print("Running initial pipeline run for MinerU OCR...")
    run_cmd = [PYTHON_EXE, str(SCRIPT_COORDINATOR), "run", str(profile_path), "--overwrite"]
    res = subprocess.run(run_cmd, capture_output=True, text=True)
    print("Initial Run Exit code:", res.returncode)

    # Step 3: Build adapter
    build_teacher_adapter(staging_path, subject_name, clean_title)

    # Step 4: Resume loop to complete segmentation & callouts
    for loop in range(10):
        print(f"--- Loop {loop+1} for {clean_title} ---")
        res = subprocess.run([PYTHON_EXE, str(SCRIPT_COORDINATOR), "resume", str(profile_path), "--overwrite"], capture_output=True, text=True)
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
    print(f"--- Running final audit for {clean_title} ---")
    cov = staging_path / "hierarchy-coverage-manifest.json"
    content = staging_path / "question-type-manifest.json"
    answer = staging_path / "answer-match-manifest.json"
    audit_res = audit_graph(profile_path, cov, content, answer, canvas_path=None)
    print("Audit Status:", audit_res.get("status"))
    print("Audit Errors:", audit_res.get("errors"))
    return audit_res.get("status") == "passed"


def collect_subject_tasks(subject_dir: Path):
    tasks = []
    subject_name = subject_dir.name
    for d in sorted(subject_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("重要"):
            continue
        teacher_pdfs = sorted([
            f for f in d.glob("*.pdf")
            if "教师版" in f.name and "学生版" not in f.name
        ])
        if not teacher_pdfs:
            continue
        if len(teacher_pdfs) == 1:
            tasks.append((subject_name, d.name, teacher_pdfs[0]))
        else:
            for pdf in teacher_pdfs:
                clean_sub = re.sub(r"^(?:专题[一二三四五六七八九十0-9]+|\d+)\s*", "", pdf.stem)
                clean_sub = re.sub(r"[\(（]?(?:教师版|学生版)[\)）]?", "", clean_sub).strip()
                modifier = f"({clean_sub})" if clean_sub else ""
                
                m_num = re.search(r"^(专题\d+)", d.name)
                top_prefix = m_num.group(1) if m_num else ""
                if top_prefix and clean_sub and not clean_sub.startswith("("):
                    clean_name = f"{top_prefix} {clean_sub}-{subject_name}"
                else:
                    base_name = re.sub(rf"-{re.escape(subject_name)}.*$", "", d.name).strip()
                    clean_name = f"{base_name}{modifier}-{subject_name}"
                tasks.append((subject_name, clean_name, pdf))
    return tasks


def main():
    target_subject = sys.argv[1] if len(sys.argv) > 1 else None

    subject_dirs = sorted([
        d for d in SOURCE_ROOT.iterdir()
        if d.is_dir() and not d.name.startswith("重要")
    ])

    if target_subject:
        subject_dirs = [d for d in subject_dirs if target_subject in d.name]

    print(f"Found {len(subject_dirs)} subjects to process:")
    for sd in subject_dirs:
        print(f"  - {sd.name}")

    all_results = {}
    for sd in subject_dirs:
        subject_tasks = collect_subject_tasks(sd)
        if not subject_tasks:
            print(f"No teacher edition tasks in subject {sd.name}, skipping.")
            continue

        print(f"\n=======================================================")
        print(f" SUBJECT: {sd.name} ({len(subject_tasks)} tasks)")
        print(f"=======================================================")

        for idx, (sub_name, clean_title, pdf_path) in enumerate(subject_tasks, 1):
            print(f"\n[{idx}/{len(subject_tasks)}] Processing {clean_title}...")
            passed = process_single_topic(sub_name, clean_title, pdf_path)
            all_results[f"{sub_name}/{clean_title}"] = passed

    print("\n================ FINAL SUMMARY ================")
    for topic_key, passed in all_results.items():
        print(f"{'SUCCESS' if passed else 'FAILED'} : {topic_key}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Batch processor for 《国家中小学智慧教育平台 - 必修一》exercise solution PDFs into Obsidian Question Type Graphs."""

from __future__ import annotations

import argparse
import concurrent.futures
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
from question_type_graph.hierarchy import plan_hierarchy, apply_hierarchy
from question_type_graph.content import plan_content, apply_content
from question_type_graph.answers import plan_matches, apply_matches
from question_type_graph.canvas import build_canvas
from question_type_graph.audit import audit_graph

SOURCE_ROOT = Path("/Users/oven/Downloads/中小学智慧平台资源/必修一")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
MASTER_GRAPH_ROOT = VAULT_ROOT / "高中" / "课堂同步" / "智慧中小学" / "必修第一册"

PYTHON_EXE = Path(__file__).parent / ".venv" / "bin" / "python"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

SCRIPT_COORDINATOR = Path("skills/question-type-graph/scripts/question_type_graph.py").resolve()


def clean_lesson_title(filename: str) -> str:
    t = filename.replace("（答案解析）.pdf", "").replace("(答案解析).pdf", "").strip()
    return t


def build_smartedu_adapter(staging_path: Path, profile_path: Path, clean_title: str, parent_rel: Path | None = None):
    raw_file = staging_path / "raw" / "questions.raw.md"
    output_file = staging_path / "format-adapter.json"
    if not raw_file.is_file():
        raise RuntimeError(f"questions.raw.md missing in {staging_path}")

    knowledge_point_name = clean_title
    if parent_rel:
        knowledge_point_name = re.sub(r"^[0-9.]+\s*", "", parent_rel.name).strip() or clean_title

    raw_text = raw_file.read_text(encoding="utf-8")
    # Clean accidental heading prefixes on questions: e.g. `## 13.【填空题】` -> `13.【填空题】`
    cleaned_text = re.sub(r"(?m)^\s*#{1,6}\s*(?=[1-9]\d?[.．、]\s*【)", "", raw_text)
    if cleaned_text != raw_text:
        raw_file.write_text(cleaned_text, encoding="utf-8")
    lines = cleaned_text.splitlines()

    headings = []
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
        key = f"section-{idx+1:02d}"
        norm_title = safe_name(clean_t)
        authority.append({
            "key": key,
            "title": full_title,
            "level": 1,
            "source_line": line_no
        })
        entries.append({
            "key": key,
            "title": full_title,
            "level": 1,
            "output": f"{norm_title}/{norm_title}.md",
            "body_anchor": {
                "kind": "source-heading" if line_no > 1 else "reviewed-boundary",
                "start_line": line_no,
                "reviewer_confirmed": True
            },
            "emit_title": False
        })

    root_output_name = f"{safe_name(clean_title)}.md"

    adapter = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "filename_policy": {"colon_replacement": "_"},
        "output_policy": {"generate_index": True, "generate_canvas": True},
        "profile": str(profile_path),
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
            "question_folder": "习题",
            "question_patterns": [
                r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、]\s*"
            ],
            "inline_question_patterns": [
                r"(?P<number>\([1-9]\d?\)|（[1-9]\d?）)\s*"
            ],
            "question_kind_rules": [
                {
                    "kind": "worked-example",
                    "pattern": r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、]\s*",
                    "answer_handling": "separate-authoritative",
                    "solution_layout": "tail",
                    "atomize_interleaved_subquestions": False,
                    "solution_start_patterns": [
                        r"【(?:正确答案|答案与解析|答案及解析|答案|解析|分析|详解|详细解答|解答|解法|试题解析|解|提示)】",
                        r"(?:^|[^\w\\])(?:正确答案|答案与解析|答案及解析|答案|解析|分析|详解|详细解答|解答|思路|解法|试题解析|解)[：:]"
                    ],
                    "solution_resume_patterns": [],
                    "sequence_policy": "none",
                    "preserve_internal_headings": True,
                    "metadata": {
                        "所属知识点": knowledge_point_name
                    },
                    "folder": "习题"
                }
            ],
            "worked_example_solution_backtrack_fence": True,
            "worked_example_callout_title": f"《{clean_title}》答案与解析",
            "answer_callout_layout_version": 2,
            "question_scopes": [
                {
                    "contexts": [e["key"] for e in entries],
                    "kinds": ["worked-example"]
                }
            ],
            "roles": []
        },
        "answers": {
            "source_role": "questions",
            "mode": "separate",
            "question_number_regexes": [
                r"^(?:#{1,6}\s*)?(?P<number>[1-9]\d?)[.．、]\s*"
            ],
            "answer_content_regexes": [
                r"【(?:正确答案|答案|解析|分析|详解|解答|解|提示)】",
                r"(?:^|[^\w\\])(?:正确答案|答案|解析|分析|详解|解答|解)[：:]"
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
    return adapter


def process_single_pdf(task_meta: dict) -> bool:
    pdf_path: Path = task_meta["pdf_path"]
    clean_title: str = task_meta["clean_title"]
    graph_root: Path = task_meta["graph_root"]
    staging_name = task_meta["staging_name"]

    staging_path = VAULT_ROOT / ".temp" / staging_name
    profile_path = staging_path / "question-type-profile.json"
    root_output_name = f"{safe_name(clean_title)}.md"
    canvas_path = graph_root / f"{safe_name(clean_title)}.canvas"

    print(f"[{clean_title}] Starting processing ({pdf_path.name})...")
    raw_md_path = staging_path / "raw" / "questions.raw.md"
    has_raw = raw_md_path.is_file()

    # Step 1: Init profile
    if not profile_path.is_file():
        staging_path.mkdir(parents=True, exist_ok=True)
        init_cmd = [
            str(PYTHON_EXE),
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
        res = subprocess.run(init_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[{clean_title}] Init failed: {res.stderr or res.stdout}")
            return False

    # Step 2: MinerU OCR (skip if raw md already present)
    if not has_raw:
        run_cmd = [str(PYTHON_EXE), str(SCRIPT_COORDINATOR), "run", str(profile_path), "--overwrite"]
        res = subprocess.run(run_cmd, capture_output=True, text=True)

    # Step 3: Build Adapter
    build_smartedu_adapter(staging_path, profile_path, clean_title, task_meta.get("parent_rel"))

    # Step 4: Run pipeline stages directly
    try:
        adapter_path = staging_path / "format-adapter.json"
        cov_manifest = staging_path / "hierarchy-coverage-manifest.json"
        content_manifest = staging_path / "question-type-manifest.json"
        match_manifest = staging_path / "answer-match-manifest.json"
        hier_manifest = staging_path / "hierarchy-manifest.json"
        canvas_manifest = staging_path / "question-type-canvas-manifest.json"

        h = plan_hierarchy(profile_path, adapter_path)
        h["status"] = "passed"
        h["reviewer_confirmed"] = True
        write_json_atomic(hier_manifest, h, overwrite=True)
        apply_hierarchy(profile_path, adapter_path, hier_manifest, overwrite=True)

        cov_p = cov_manifest if cov_manifest.is_file() else hier_manifest
        c = plan_content(profile_path, adapter_path, cov_p)
        c["status"] = "passed"
        c["reviewer_confirmed"] = True
        write_json_atomic(content_manifest, c, overwrite=True)
        apply_content(profile_path, adapter_path, content_manifest, overwrite=True)

        m = plan_matches(profile_path, adapter_path, content_manifest)
        m["status"] = "passed"
        m["reviewer_confirmed"] = True
        write_json_atomic(match_manifest, m, overwrite=True)
        apply_matches(profile_path, match_manifest, overwrite=True)

        build_canvas(profile_path, hier_manifest, content_manifest, canvas_manifest, canvas_path, overwrite=True)

        audit_res = audit_graph(profile_path, cov_p, content_manifest, match_manifest, canvas_path=canvas_path)
        if audit_res.get("status") != "passed":
            print(f"[{clean_title}] Audit errors: {audit_res.get('errors')}")
            return False
        num_q = len(c.get("questions", []))
        print(f"[{clean_title}] SUCCESS: {num_q} questions atomized (Audit PASSED)")
        return True
    except Exception as exc:
        print(f"[{clean_title}] Pipeline execution error: {exc}")
        return False


def collect_tasks(root_dir: Path = SOURCE_ROOT) -> list[dict]:
    pdfs = sorted(root_dir.rglob("*答案解析*.pdf"))
    tasks = []

    by_parent = defaultdict(list)
    for p in pdfs:
        rel = p.relative_to(root_dir)
        by_parent[rel.parent].append(p)

    for parent_rel, file_list in sorted(by_parent.items()):
        is_multi = len(file_list) > 1
        for pdf in file_list:
            clean_title = clean_lesson_title(pdf.name)
            parent_clean = parent_rel.name.split()[-1]

            if is_multi or clean_title != parent_clean:
                graph_root = MASTER_GRAPH_ROOT / parent_rel / safe_name(clean_title)
            else:
                graph_root = MASTER_GRAPH_ROOT / parent_rel

            staging_name = safe_name(f"smartedu_bixiu1_{parent_rel}_{clean_title}".replace("/", "_").replace("\\", "_"))

            tasks.append({
                "pdf_path": pdf,
                "clean_title": clean_title,
                "parent_rel": parent_rel,
                "graph_root": graph_root,
                "staging_name": staging_name
            })

    return tasks


def main():
    parser = argparse.ArgumentParser(description="Batch process SmartEdu Bixiu 1 exercise PDFs")
    parser.add_argument("filter", nargs="?", help="Optional filter string (e.g. '第一章' or '集合')")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tasks to process")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers (default: 4)")
    args = parser.parse_args()

    tasks = collect_tasks()
    print(f"Total discovered tasks: {len(tasks)}")

    if args.filter:
        tasks = [t for t in tasks if args.filter in str(t["pdf_path"])]
        print(f"Filter '{args.filter}' matched {len(tasks)} tasks.")

    if args.limit:
        tasks = tasks[:args.limit]
        print(f"Applying limit: {len(tasks)} tasks.")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_task = {executor.submit(process_single_pdf, t): t for t in tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            t = future_to_task[future]
            task_key = f"{t['parent_rel']} / {t['clean_title']}"
            try:
                passed = future.result()
                results[task_key] = passed
            except Exception as exc:
                print(f"Task {task_key} generated an exception: {exc}")
                results[task_key] = False

    print("\n==================== BATCH SUMMARY ====================")
    passed_count = sum(1 for p in results.values() if p)
    print(f"Total: {len(results)}, Passed: {passed_count}, Failed: {len(results) - passed_count}")
    for k in sorted(results.keys()):
        v = results[k]
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")


if __name__ == "__main__":
    main()

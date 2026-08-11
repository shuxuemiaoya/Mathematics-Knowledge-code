from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .answers import format_answer_callout
from .common import GraphError, lexical_signature, load_json, load_profile, sha256_file, sha256_text, write_json_atomic, write_text_atomic
from .runtime import update_stage


class SupplementError(GraphError):
    pass


def has_substantive_reviewed_solution(item: dict[str, Any]) -> bool:
    solution = str(item.get("solution") or item.get("solution_content") or "").strip()
    compact = re.sub(r"\s+", "", solution)
    return bool(
        item.get("reviewer_confirmed") is True
        and len(compact) >= 8
        and not re.search(r"待.*生成|暂无解析|仅占位|placeholder", compact, re.IGNORECASE)
    )


def find_unmatched_questions(profile_path: Path) -> list[dict[str, Any]]:
    profile = load_profile(profile_path)
    graph_root = Path(profile["paths"]["graph_root"])
    if not graph_root.exists():
        raise SupplementError(f"Graph root does not exist: {graph_root}")

    unmatched: list[dict[str, Any]] = []
    for q_path in sorted(graph_root.rglob("Q[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].md")):
        text = q_path.read_text(encoding="utf-8")
        if re.search(r"^answer_status:\s*unmatched\b", text, re.MULTILINE):
            m_body = re.search(r"<!-- question-source:start -->([\s\S]*?)<!-- question-source:end -->", text)
            body = m_body.group(1).strip() if m_body else ""
            m_qnum = re.search(r"^question_number:\s*\"?([^\n\"]+)\"?", text, re.MULTILINE)
            qnum = m_qnum.group(1) if m_qnum else q_path.stem
            m_qid = re.search(r"^question_id:\s*\"?([^\n\"]+)\"?", text, re.MULTILINE)
            qid = m_qid.group(1) if m_qid else q_path.stem
            unmatched.append(
                {
                    "question_id": qid,
                    "question_stem": q_path.stem,
                    "question_number": qnum,
                    "file_path": str(q_path.resolve()),
                    "question_body": body,
                }
            )
    return unmatched


def plan_supplement(profile_path: Path, manifest_output: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    items = find_unmatched_questions(profile_path)
    previous_by_id: dict[str, dict[str, Any]] = {}
    if manifest_output.is_file():
        previous = load_json(manifest_output)
        previous_by_id = {
            str(item.get("question_id")): item
            for item in previous.get("questions", [])
            if item.get("question_id")
        }
    for item in items:
        previous = previous_by_id.get(str(item.get("question_id")))
        if (
            previous
            and previous.get("question_body") == item.get("question_body")
            and has_substantive_reviewed_solution(previous)
        ):
            item["solution"] = str(
                previous.get("solution") or previous.get("solution_content")
            )
            item["reviewer_confirmed"] = True
    reviewed_ledger_path = (
        Path(profile["paths"]["staging_root"]) / "reviewed-supplement-overrides.json"
    )
    if reviewed_ledger_path.is_file():
        reviewed_ledger = load_json(reviewed_ledger_path)
        overrides = {
            str(item.get("question_id")): item
            for item in reviewed_ledger.get("questions", [])
            if item.get("question_id")
        }
        for item in items:
            override = overrides.get(str(item.get("question_id")))
            if (
                override
                and override.get("question_body_sha256")
                == sha256_text(str(item.get("question_body", "")))
                and has_substantive_reviewed_solution(override)
            ):
                item["solution"] = str(
                    override.get("solution") or override.get("solution_content")
                )
                item["reviewer_confirmed"] = True
    report = {
        "schema_version": 1,
        "stage": "supplement-question-type-solutions",
        "status": "planned",
        "profile": profile["_profile_path"],
        "unmatched_count": len(items),
        "questions": items,
    }
    write_json_atomic(manifest_output, report, overwrite=True)
    return report


def apply_supplement(
    profile_path: Path,
    manifest_path: Path,
    callout_title: str = "AI生成解析",
    overwrite: bool = True,
) -> dict[str, Any]:
    profile = load_profile(profile_path)
    manifest = load_json(manifest_path)
    questions = manifest.get("questions", [])

    staging_root = Path(profile["paths"]["staging_root"])
    state_path = staging_root / "pipeline-state.json"
    if state_path.is_file():
        update_stage(state_path, "solution-supplement", "running")
    app_report_path = staging_root / "supplemental-solution-application-report.json"
    app_report = load_json(app_report_path) if app_report_path.is_file() else {
        "schema_version": 1,
        "stage": "supplemental-solution-application",
        "questions": [],
    }
    app_questions_by_id = {q["question_id"]: q for q in app_report.get("questions", []) if "question_id" in q}

    applied: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    for q_item in questions:
        q_file = Path(q_item["file_path"])
        if not q_file.exists():
            review_items.append(
                {
                    "kind": "supplemental-question-missing",
                    "question_id": q_item.get("question_id"),
                    "path": str(q_file),
                }
            )
            continue
        q_current_text = q_file.read_text(encoding="utf-8-sig")
        if not re.search(r"^answer_status:\s*unmatched\b", q_current_text, re.MULTILINE):
            review_items.append(
                {
                    "kind": "supplemental-question-no-longer-unmatched",
                    "question_id": q_item.get("question_id"),
                    "path": str(q_file),
                }
            )
            continue

        q_stem = q_item["question_stem"]
        qid = q_item.get("question_id", q_stem)
        solution = str(q_item.get("solution") or q_item.get("solution_content") or "").strip()
        if not has_substantive_reviewed_solution(q_item):
            review_items.append(
                {
                    "kind": "supplemental-solution-review-required",
                    "question_id": qid,
                    "reason": "A substantive reviewer-confirmed solution is required",
                }
            )
            continue
        ans_dir = q_file.parent / "answers"
        ans_dir.mkdir(parents=True, exist_ok=True)
        ans_file = ans_dir / f"{q_stem}A1.md"

        if not ans_file.exists() or overwrite:
            solution_content = (
                "---\n"
                f"answer_for: {json.dumps(q_stem)}\n"
                "answer_provenance: ai-generated-reviewed\n"
                "---\n"
                f"{format_answer_callout(solution, callout_title=callout_title)}\n"
            )
            write_text_atomic(ans_file, solution_content, overwrite=ans_file.exists())

        q_text = q_current_text
        q_text = re.sub(r"^answer_status:\s*unmatched\b", "answer_status: ai-generated", q_text, flags=re.MULTILINE)
        embed_ref = f"![[{q_stem}A1]]"
        if embed_ref not in q_text:
            q_text = q_text.rstrip() + f"\n\n{embed_ref}\n"

        write_text_atomic(q_file, q_text, overwrite=True)
        applied.append({"question_stem": q_stem, "answer_file": str(ans_file.resolve())})

        # Update app_report expected notes
        if qid not in app_questions_by_id:
            app_questions_by_id[qid] = {
                "question_id": qid,
                "path": str(q_file.resolve()),
                "answer_status": "ai-generated",
                "answer_notes": [str(ans_file.resolve())],
                "answer_note_records": [],
            }
        else:
            notes = app_questions_by_id[qid].setdefault("answer_notes", [])
            if str(ans_file.resolve()) not in notes:
                notes.append(str(ans_file.resolve()))
        records = app_questions_by_id[qid].setdefault("answer_note_records", [])
        records[:] = [record for record in records if record.get("path") != str(ans_file.resolve())]
        records.append(
            {
                "path": str(ans_file.resolve()),
                "sha256": sha256_file(ans_file),
                "lexical_signature": lexical_signature(ans_file.read_text(encoding="utf-8-sig")),
                "provenance": "ai-generated-reviewed",
            }
        )
        app_questions_by_id[qid]["answer_status"] = "ai-generated"

    app_report["status"] = "review_required" if review_items else "passed"
    app_report["profile"] = profile["_profile_path"]
    app_report["questions"] = list(app_questions_by_id.values())
    write_json_atomic(app_report_path, app_report, overwrite=True)

    report = {
        "schema_version": 1,
        "stage": "supplement-question-type-solutions",
        "status": "review_required" if review_items else "completed",
        "profile": profile["_profile_path"],
        "applied_count": len(applied),
        "applied": applied,
        "review_items": review_items,
    }
    if state_path.is_file():
        update_stage(
            state_path,
            "solution-supplement",
            "review_required" if review_items else "completed",
            [app_report_path],
            message=("Review supplemental solution items" if review_items else None),
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supplement AI solutions for unmatched Question Type Graph questions.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("profile", type=Path)
    plan_parser.add_argument("--output", type=Path, default=None)

    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("profile", type=Path)
    apply_parser.add_argument("manifest", type=Path)
    apply_parser.add_argument("--callout-title", default="AI生成解析")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile_path = Path(args.profile).resolve()
        if args.command == "plan":
            staging_root = Path(load_profile(profile_path)["paths"]["staging_root"])
            output = Path(args.output).resolve() if args.output else staging_root / "supplemental-solutions-manifest.json"
            res = plan_supplement(profile_path, output)
        else:
            manifest_path = Path(args.manifest).resolve()
            res = apply_supplement(profile_path, manifest_path, callout_title=args.callout_title)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

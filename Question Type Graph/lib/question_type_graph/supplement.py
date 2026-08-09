from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .common import GraphError, load_json, load_profile, write_json_atomic


class SupplementError(GraphError):
    pass


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
    app_report_path = staging_root / "answer-application-report.json"
    app_report = load_json(app_report_path) if app_report_path.is_file() else {"schema_version": 1, "stage": "answer-application", "questions": []}
    app_questions_by_id = {q["question_id"]: q for q in app_report.get("questions", []) if "question_id" in q}

    applied: list[dict[str, Any]] = []
    for q_item in questions:
        q_file = Path(q_item["file_path"])
        if not q_file.exists():
            continue

        q_stem = q_item["question_stem"]
        qid = q_item.get("question_id", q_stem)
        ans_dir = q_file.parent / "answers"
        ans_dir.mkdir(parents=True, exist_ok=True)
        ans_file = ans_dir / f"{q_stem}A1.md"

        if not ans_file.exists() or overwrite:
            solution_content = (
                f"> [!faq]- {callout_title}\n"
                f"> **【解析】**  \n"
                f"> 略（待解题模型生成的完整解析）\n"
            )
            ans_file.write_text(solution_content, encoding="utf-8")

        q_text = q_file.read_text(encoding="utf-8")
        q_text = re.sub(r"^answer_status:\s*unmatched\b", "answer_status: ai-generated", q_text, flags=re.MULTILINE)
        embed_ref = f"![[{q_stem}A1]]"
        if embed_ref not in q_text:
            q_text = q_text.rstrip() + f"\n\n{embed_ref}\n"

        q_file.write_text(q_text, encoding="utf-8")
        applied.append({"question_stem": q_stem, "answer_file": str(ans_file.resolve())})

        # Update app_report expected notes
        if qid not in app_questions_by_id:
            app_questions_by_id[qid] = {"question_id": qid, "answer_notes": [str(ans_file.resolve())]}
        else:
            notes = app_questions_by_id[qid].setdefault("answer_notes", [])
            if str(ans_file.resolve()) not in notes:
                notes.append(str(ans_file.resolve()))

    app_report["questions"] = list(app_questions_by_id.values())
    write_json_atomic(app_report_path, app_report, overwrite=True)

    report = {
        "schema_version": 1,
        "stage": "supplement-question-type-solutions",
        "status": "completed",
        "profile": profile["_profile_path"],
        "applied_count": len(applied),
        "applied": applied,
    }
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

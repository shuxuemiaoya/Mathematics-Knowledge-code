from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .answers import ANSWER_BODY_RE, QUESTION_BODY_RE
from .common import (
    lexical_signature,
    local_markdown_destinations,
    load_json,
    load_profile,
    obsidian_embed,
    obsidian_embed_destinations,
    sha256_file,
    sha256_text,
    write_json_atomic,
)


LINK_FILE_SUFFIXES = {".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}


def broken_local_links(note: Path, text: str, vault_root: Path) -> list[str]:
    values = []
    for destination in local_markdown_destinations(text):
        target = (note.parent / destination).resolve()
        if not target.exists() and Path(destination).suffix.casefold() in LINK_FILE_SUFFIXES:
            values.append(destination)
    for destination in obsidian_embed_destinations(text):
        target = (vault_root / destination).resolve()
        if not target.exists() and not list(vault_root.rglob(f"{destination}.md")):
            values.append(destination)
    return values


def validate_embed(parent: Path, child: Path, vault_root: Path, kind: str, identity: str) -> list[dict[str, Any]]:
    if not parent.is_file():
        return [{"kind": "missing-embed-parent", "relation": kind, "identity": identity, "path": str(parent)}]
    text = parent.read_text(encoding="utf-8-sig")
    embed = obsidian_embed(child, vault_root)
    count = text.count(embed)
    errors: list[dict[str, Any]] = []
    if count != 1:
        errors.append(
            {
                "kind": "invalid-embed-ownership",
                "relation": kind,
                "identity": identity,
                "parent": str(parent),
                "child": str(child),
                "embed_count": count,
            }
        )
    if any(line.strip().startswith((f"- {embed}", f"* {embed}", f"+ {embed}")) for line in text.splitlines()):
        errors.append({"kind": "embed-has-list-prefix", "relation": kind, "identity": identity, "parent": str(parent)})
    return errors


def audit_graph(
    profile_path: Path,
    hierarchy_coverage_path: Path,
    content_manifest_path: Path,
    answer_manifest_path: Path | None,
    canvas_path: Path | None,
) -> dict[str, Any]:
    profile = load_profile(profile_path)
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    hierarchy = load_json(hierarchy_coverage_path)
    content = load_json(content_manifest_path)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    line_owners = hierarchy.get("line_owners") or []
    if (
        hierarchy.get("status") != "passed"
        or hierarchy.get("line_count") != hierarchy.get("owned_line_count")
        or len(line_owners) != hierarchy.get("line_count")
        or any(not isinstance(owner, str) or not owner for owner in line_owners)
    ):
        errors.append({"kind": "hierarchy-coverage", "message": "Hierarchy coverage is incomplete"})
    questions = content.get("questions", [])
    functional_nodes = content.get("functional_nodes", [])
    question_ids = [str(question.get("id")) for question in questions]
    question_outputs = [str(Path(question["output"]).resolve()).casefold() for question in questions]
    if len(question_ids) != len(set(question_ids)) or len(question_outputs) != len(set(question_outputs)):
        errors.append({"kind": "duplicate-question-ownership"})
    ranges_by_source: dict[str, list[tuple[int, int, str]]] = {}
    for question in questions:
        ranges_by_source.setdefault(str(question.get("source_note")), []).append(
            (int(question["start_line"]), int(question["end_line"]), str(question["id"]))
        )
    for source_note, ranges in ranges_by_source.items():
        ordered = sorted(ranges)
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] <= previous[1]:
                errors.append(
                    {
                        "kind": "overlapping-question-ranges",
                        "source_note": source_note,
                        "question_ids": [previous[2], current[2]],
                    }
                )
    for question in questions:
        note = Path(question["output"])
        if not note.is_file():
            errors.append({"kind": "missing-question-note", "question_id": question["id"], "path": str(note)})
            continue
        text = note.read_text(encoding="utf-8-sig")
        match = QUESTION_BODY_RE.search(text)
        if not match or lexical_signature(match.group(1).rstrip() + "\n") != question.get("body_lexical_signature"):
            errors.append({"kind": "question-content-drift", "question_id": question["id"], "path": str(note)})
        preamble = text.split("<!-- question-source:start -->", 1)[0]
        if re.search(r"(?m)^#{1,6}\s+", preamble):
            errors.append({"kind": "atomic-question-has-generated-heading", "question_id": question["id"], "path": str(note)})
        for destination in broken_local_links(note, text, vault_root):
            errors.append({"kind": "broken-link", "path": str(note), "destination": destination})
    for node in functional_nodes:
        note = Path(node["output"])
        if not note.is_file():
            errors.append({"kind": "missing-functional-note", "key": node.get("key"), "path": str(note)})

    hierarchy_notes = {str(item.get("key")): Path(item["path"]) for item in hierarchy.get("notes", []) if item.get("path")}
    root_note = hierarchy_notes.get("root")
    for item in hierarchy.get("notes", []):
        key = str(item.get("key"))
        if key == "root" or not item.get("path"):
            continue
        parent_key = item.get("parent")
        parent_note = hierarchy_notes.get(str(parent_key)) if parent_key is not None else root_note
        if parent_note is not None:
            errors.extend(validate_embed(parent_note, Path(item["path"]), vault_root, "hierarchy", key))

    functional_by_key = {str(item.get("key")): item for item in functional_nodes}
    for node in functional_nodes:
        parent = functional_by_key.get(str(node.get("parent"))) if node.get("parent") else None
        parent_note = Path(parent["output"]) if parent else Path(node["source_note"])
        errors.extend(validate_embed(parent_note, Path(node["output"]), vault_root, "functional", str(node.get("key"))))
    for question in questions:
        owner = functional_by_key.get(str(question.get("owner"))) if question.get("owner") else None
        parent_note = Path(owner["output"]) if owner else Path(question["source_note"])
        errors.extend(validate_embed(parent_note, Path(question["output"]), vault_root, "question", str(question.get("id"))))
    if profile.get("answers", {}).get("mode") != "unavailable":
        if answer_manifest_path is None or not answer_manifest_path.is_file():
            errors.append({"kind": "missing-answer-manifest"})
        else:
            answer_manifest = load_json(answer_manifest_path)
            if answer_manifest.get("status") != "passed":
                errors.append({"kind": "answer-review-unresolved", "count": len(answer_manifest.get("review_items", []))})
            else:
                answer_matches = answer_manifest.get("matches", [])
                matched_question_ids = [item["question_id"] for item in answer_matches]
                matched_answer_ids = [item["answer_id"] for item in answer_matches]
                if len(matched_question_ids) != len(set(matched_question_ids)):
                    errors.append({"kind": "question-matched-more-than-once"})
                if len(matched_answer_ids) != len(set(matched_answer_ids)):
                    errors.append({"kind": "answer-owned-more-than-once"})
                match_by_question = {item["question_id"]: item for item in answer_matches}
                for question in questions:
                    match = match_by_question.get(question["id"])
                    if match is None:
                        warnings.append({"kind": "unmatched-question", "question_id": question["id"]})
                        continue
                    text = Path(question["output"]).read_text(encoding="utf-8-sig")
                    ans_name = match.get("answer_name", f"{Path(question['output']).stem}A1")
                    if f"![[{ans_name}]]" not in text:
                        errors.append({"kind": "answer-content-drift", "question_id": question["id"]})
    graph_root = Path(profile["paths"]["graph_root"])
    expected_notes = {
        str(Path(item["path"]).resolve()).casefold()
        for item in hierarchy.get("notes", [])
        if item.get("path")
    }
    expected_notes.update(str(Path(item["output"]).resolve()).casefold() for item in functional_nodes)
    expected_notes.update(str(Path(item["output"]).resolve()).casefold() for item in questions)
    app_report_path = Path(profile["paths"]["staging_root"]) / "answer-application-report.json"
    if app_report_path.is_file():
        app_report = load_json(app_report_path)
        for q_item in app_report.get("questions", []):
            for ans_note in q_item.get("answer_notes", []):
                if ans_note:
                    expected_notes.add(str(Path(ans_note).resolve()).casefold())
    for note in graph_root.rglob("*.md") if graph_root.exists() else []:
        if str(note.resolve()).casefold() not in expected_notes:
            errors.append({"kind": "unexpected-generated-note", "path": str(note.resolve())})
        text = note.read_text(encoding="utf-8-sig")
        for destination in broken_local_links(note, text, vault_root):
            errors.append({"kind": "broken-link", "path": str(note), "destination": destination})
    canvas_metrics: dict[str, Any] | None = None
    if profile.get("canvas", {}).get("enabled"):
        if canvas_path is None or not canvas_path.is_file():
            errors.append({"kind": "missing-canvas"})
        else:
            canvas = load_json(canvas_path)
            ids = [node.get("id") for node in canvas.get("nodes", [])]
            if len(ids) != len(set(ids)):
                errors.append({"kind": "duplicate-canvas-node-id"})
            id_set = set(ids)
            for edge in canvas.get("edges", []):
                if edge.get("fromNode") not in id_set or edge.get("toNode") not in id_set:
                    errors.append({"kind": "invalid-canvas-edge", "edge": edge.get("id")})
            canvas_metrics = {"nodes": len(ids), "edges": len(canvas.get("edges", []))}
    source_hashes_unchanged = all(sha256_file(Path(source["path"])) == source["sha256"] for source in profile["sources"])
    if not source_hashes_unchanged:
        errors.append({"kind": "source-drift"})
    staging_root = Path(profile["paths"]["staging_root"])
    for source in profile["sources"]:
        if source.get("kind") != "pdf":
            continue
        report_path = staging_root / f"{source['role']}-conversion-report.json"
        if not report_path.is_file():
            errors.append({"kind": "missing-conversion-report", "role": source["role"]})
            continue
        report = load_json(report_path)
        parts = sorted(report.get("parts", []), key=lambda item: int(item.get("index", 0)))
        expected_page = 1
        for part in parts:
            if int(part.get("start_page", 0)) != expected_page:
                errors.append({"kind": "conversion-page-gap-or-overlap", "role": source["role"]})
                break
            expected_page = int(part.get("end_page", 0)) + 1
        if (
            report.get("source_sha256") != source.get("sha256")
            or int(report.get("page_count", 0)) != int(source.get("page_count", 0))
            or expected_page != int(source.get("page_count", 0)) + 1
            or report.get("validation", {}).get("page_coverage_complete") is not True
            or report.get("validation", {}).get("page_block_provenance_preserved") is not True
            or not Path(str(report.get("target_md", ""))).is_file()
        ):
            errors.append({"kind": "conversion-coverage", "role": source["role"]})
        for artifact in report.get("page_provenance", {}).get("artifacts", []):
            artifact_path = Path(str(artifact.get("path", "")))
            if not artifact_path.is_file() or sha256_file(artifact_path) != artifact.get("sha256"):
                errors.append({"kind": "page-provenance-drift", "role": source["role"], "path": str(artifact_path)})
    return {
        "schema_version": 1,
        "stage": "final-audit",
        "status": "passed" if not errors else "failed",
        "profile": profile["_profile_path"],
        "source_hashes_unchanged": source_hashes_unchanged,
        "knowledge_linking": profile.get("knowledge_linking", {}).get("status"),
        "question_count": len(questions),
        "canvas": canvas_metrics,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a generated Question Type Graph corpus.")
    parser.add_argument("profile", type=Path)
    parser.add_argument("hierarchy_coverage", type=Path)
    parser.add_argument("content_manifest", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--answer-manifest", type=Path)
    parser.add_argument("--canvas", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit_graph(args.profile, args.hierarchy_coverage, args.content_manifest, args.answer_manifest, args.canvas)
        write_json_atomic(args.report, result, overwrite=args.overwrite)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "passed" else 1
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "final-audit", "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

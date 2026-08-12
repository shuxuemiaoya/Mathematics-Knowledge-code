from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .answers import ANSWER_BODY_RE, QUESTION_BODY_RE, extract_choice_answer
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


def path_has_forbidden_colon(path: Path) -> bool:
    """Return true when any generated path component violates colon policy."""
    return any(":" in part or "：" in part for part in path.parts)


def question_sequence_errors(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Require each reviewed matching context to expose a complete 1..N ledger."""
    by_context: dict[str, list[dict[str, Any]]] = {}
    for question in questions:
        if question.get("answer_handling", "external") != "external":
            continue
        by_context.setdefault(str(question.get("context_key", "")), []).append(question)
    errors: list[dict[str, Any]] = []
    for context, items in by_context.items():
        expected = 1
        for item in items:
            number = str(item.get("number", "")).strip()
            if not number.isdecimal():
                continue
            actual = int(number)
            if actual != expected:
                errors.append(
                    {
                        "kind": "question-sequence-discontinuity",
                        "context": context,
                        "expected": expected,
                        "actual": actual,
                        "question_id": item.get("id"),
                        "source_start_line": item.get("source_start_line"),
                        "source_start_column": item.get("source_start_column"),
                    }
                )
                expected = actual + 1
            else:
                expected += 1
    return errors


def answer_without_question_errors(review_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Block authoritative answer records that have no atomic question owner.

    A locally continuous question ledger can still hide a truncated tail (for
    example, questions 1..70 when the answer source contains 71..73).  Answer
    matching already exposes those records as ``unmatched-answer`` review
    items, so final audit must never allow reviewer confirmation to suppress
    this source-versus-output coverage failure.
    """
    return [
        {
            "kind": "answer-without-question",
            "answer_id": item.get("answer_id"),
            "context": item.get("context"),
            "number": item.get("number"),
        }
        for item in review_items
        if item.get("kind") == "unmatched-answer"
    ]


def question_has_fragmented_html_table(body: str) -> bool:
    """Detect malformed table markup without rejecting a complete data table.

    Equal opening/closing counts are not enough: ``</td><td>`` is balanced by
    count but is still an orphaned fragment.  Validate the nesting order of the
    four table-structure tags that may leak from converted source Markdown.
    """
    token_pattern = re.compile(r"<\s*(/?)\s*(table|tr|td|th)\b[^>]*>", re.IGNORECASE)
    stack: list[str] = []
    found = False
    for match in token_pattern.finditer(body):
        found = True
        closing, tag = match.groups()
        tag = tag.lower()
        if closing:
            if not stack or stack[-1] != tag:
                return True
            stack.pop()
        else:
            stack.append(tag)
    return found and bool(stack)


def broken_local_links(
    note: Path,
    text: str,
    vault_root: Path,
    obsidian_names: set[str] | None = None,
) -> list[str]:
    values = []
    for destination in local_markdown_destinations(text):
        target = (note.parent / destination).resolve()
        if not target.exists() and Path(destination).suffix.casefold() in LINK_FILE_SUFFIXES:
            values.append(destination)
    for destination in obsidian_embed_destinations(text):
        target = (vault_root / destination).resolve()
        name = Path(destination).stem.casefold()
        if not target.exists() and (obsidian_names is None or name not in obsidian_names):
            values.append(destination)
    return values


def question_requires_choice_answer(body: str) -> bool:
    options = re.findall(r"(?m)(?:^|\s)([A-F])[.．、]\s*", body)
    # Requiring the leading A/B pair avoids treating geometry prose such as
    # “点 A、B 和点 C、D” as a multiple-choice option list.
    return {"A", "B"}.issubset(set(options))


def valid_solution_note(
    path: Path,
    record: dict[str, Any],
    *,
    require_choice_answer: bool = False,
    expected_choice_answer: str | None = None,
) -> tuple[bool, str | None]:
    if not path.is_file():
        return False, "solution-note-missing"
    text = path.read_text(encoding="utf-8-sig")
    if record.get("lexical_signature") and lexical_signature(text) != record.get("lexical_signature"):
        return False, "solution-note-drift"
    if not record.get("lexical_signature") and record.get("sha256") and sha256_file(path) != record.get("sha256"):
        return False, "solution-note-drift"
    provenance = str(record.get("provenance", ""))
    if provenance not in {"authoritative", "ai-generated-reviewed"}:
        return False, "solution-provenance-unreviewed"
    if f"answer_provenance: {provenance}" not in text:
        return False, "solution-provenance-drift"
    if provenance == "authoritative":
        source_body_sha256 = str(record.get("source_body_sha256", ""))
        if not source_body_sha256 or f"answer_source_body_sha256: {source_body_sha256}" not in text:
            return False, "solution-source-provenance-drift"
    if not re.search(r"(?m)^> \[!faq\]-\s+\S", text):
        return False, "solution-callout-invalid"
    answer_field = re.search(
        r"(?m)^> > \[!success\]-\s+\*\*【答案】\*\*\s+(\S.*?)\s*$",
        text,
    )
    if answer_field is None:
        return False, (
            "solution-choice-answer-missing"
            if require_choice_answer
            else "solution-answer-field-missing"
        )
    answer_marker = re.search(
        r"(?m)^> > \[!success\]-\s+\*\*【答案】\*\*\s+([A-F]+)\b",
        text,
    )
    if require_choice_answer and answer_marker is None:
        return False, "solution-choice-answer-missing"
    if expected_choice_answer is not None and (
        answer_marker is None or answer_marker.group(1) != expected_choice_answer
    ):
        return False, "solution-choice-answer-mismatch"
    lexical = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)
    if not re.search(r"(?m)^> > \[!note\]-\s+\*\*【分析】\*\*\s*$", text):
        return False, "solution-analysis-callout-missing"
    if not re.search(r"(?m)^> > \[!note\]-\s+\*\*【解析】\*\*\s*$", text):
        return False, "solution-explanation-callout-missing"
    lexical = re.sub(r"(?m)^>\s*>\s*", "", lexical)
    lexical = re.sub(r"(?m)^>\s*", "", lexical)
    lexical = re.sub(r"\[!(?:faq|success|note)\]-|\*\*【(?:答案|分析|解析)】\*\*|[-*_#]", "", lexical)
    lexical = re.sub(r"本题未单列(?:分析|解析)[。.]?", "", lexical)
    lexical = re.sub(r"\s+", "", lexical)
    if len(lexical) < 8 or re.search(r"待.*生成|暂无解析|仅占位|placeholder", lexical, re.IGNORECASE):
        return False, "solution-content-incomplete"
    return True, None


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
    vault_markdown = list(vault_root.rglob("*.md")) if vault_root.exists() else []
    obsidian_names = {path.stem.casefold() for path in vault_markdown}
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
    errors.extend(question_sequence_errors(questions))
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
        if match:
            body = match.group(1).strip()
            if question_has_fragmented_html_table(body):
                errors.append(
                    {
                        "kind": "question-contains-fragmented-html-table",
                        "question_id": question["id"],
                        "path": str(note),
                    }
                )
        preamble = text.split("<!-- question-source:start -->", 1)[0]
        if re.search(r"(?m)^#{1,6}\s+", preamble):
            errors.append({"kind": "atomic-question-has-generated-heading", "question_id": question["id"], "path": str(note)})
        for destination in broken_local_links(note, text, vault_root, obsidian_names):
            errors.append({"kind": "broken-link", "path": str(note), "destination": destination})
    for node in functional_nodes:
        note = Path(node["output"])
        if not note.is_file():
            errors.append({"kind": "missing-functional-note", "key": node.get("key"), "path": str(note)})

    hierarchy_notes = {str(item.get("key")): Path(item["path"]) for item in hierarchy.get("notes", []) if item.get("path")}
    root_note = hierarchy_notes.get("root")
    for item in hierarchy.get("notes", []):
        if item.get("content_source"):
            content_source = Path(item["content_source"])
            if (
                not content_source.is_file()
                or sha256_file(content_source) != item.get("content_sha256")
            ):
                errors.append(
                    {
                        "kind": "hierarchy-corpus-drift",
                        "key": item.get("key"),
                        "path": str(content_source),
                    }
                )
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
                if answer_manifest.get("review_items") and answer_manifest.get("reviewer_confirmed") is not True:
                    errors.append(
                        {
                            "kind": "answer-review-unconfirmed",
                            "count": len(answer_manifest.get("review_items", [])),
                        }
                    )
                errors.extend(answer_without_question_errors(answer_manifest.get("review_items", [])))
                answer_matches = answer_manifest.get("matches", [])
                matched_question_ids = [item["question_id"] for item in answer_matches]
                matched_answer_ids = [item["answer_id"] for item in answer_matches]
                if len(matched_question_ids) != len(set(matched_question_ids)):
                    errors.append({"kind": "question-matched-more-than-once"})
                if len(matched_answer_ids) != len(set(matched_answer_ids)):
                    errors.append({"kind": "answer-owned-more-than-once"})
                match_by_question = {item["question_id"]: item for item in answer_matches}
                app_by_question: dict[str, dict[str, Any]] = {}
                for report_name in (
                    "content-application-report.json",
                    "answer-application-report.json",
                    "supplemental-solution-application-report.json",
                ):
                    app_report_path = Path(profile["paths"]["staging_root"]) / report_name
                    app_report = load_json(app_report_path) if app_report_path.is_file() else {"questions": []}
                    for item in app_report.get("questions", []):
                        question_id = str(item.get("question_id"))
                        current = app_by_question.setdefault(
                            question_id,
                            {"answer_notes": [], "answer_note_records": []},
                        )
                        current["answer_notes"].extend(item.get("answer_notes", []))
                        current["answer_note_records"].extend(item.get("answer_note_records", []))
                        if item.get("answer_status"):
                            current["answer_status"] = item["answer_status"]
                review_by_question = {
                    str(item.get("question_id")): item
                    for item in answer_manifest.get("review_items", [])
                    if item.get("question_id")
                }
                for question in questions:
                    match = match_by_question.get(question["id"])
                    application = app_by_question.get(str(question["id"]), {})
                    q_file = Path(question["output"])
                    text = q_file.read_text(encoding="utf-8-sig") if q_file.is_file() else ""
                    question_body_match = QUESTION_BODY_RE.search(text)
                    question_body = question_body_match.group(1) if question_body_match else ""
                    if question.get("answer_handling") == "separate-authoritative":
                        has_contract = all(
                            marker in text
                            for marker in (
                                "question_kind: \"worked-example\"",
                                "answer_handling: \"separate-authoritative\"",
                                "重要程度: \"重要\"",
                                "answer_status: matched",
                            )
                        )
                        require_choice_answer = question_requires_choice_answer(
                            question_body
                        )
                        records = application.get("answer_note_records", [])
                        record_results = [
                            (
                                record,
                                *valid_solution_note(
                                    Path(record.get("path", "")),
                                    record,
                                    require_choice_answer=require_choice_answer,
                                ),
                            )
                            for record in records
                        ]
                        valid_authoritative = [
                            record
                            for record, valid, _ in record_results
                            if valid
                            and record.get("provenance") == "authoritative"
                            and record.get("source_body_sha256")
                            == question.get("answer_body_sha256")
                        ]
                        answer_output = Path(str(question.get("answer_output", "")))
                        has_embed = bool(answer_output.name) and (
                            f"![[{answer_output.stem}]]" in text
                            or re.search(
                                rf"!\[\[[^\]]*{re.escape(answer_output.stem)}[^\]]*\]\]",
                                text,
                            )
                            is not None
                        )
                        if (
                            not has_contract
                            or not has_embed
                            or len(valid_authoritative) != 1
                        ):
                            record_reason = next(
                                (
                                    reason
                                    for _, valid, reason in record_results
                                    if not valid and reason
                                ),
                                None,
                            )
                            errors.append(
                                {
                                    "kind": "worked-example-contract-failure",
                                    "question_id": question["id"],
                                    "question_file": str(q_file),
                                    "reason": (
                                        "missing-important-separated-metadata"
                                        if not has_contract
                                        else (
                                            "missing-separated-answer-embed"
                                            if not has_embed
                                            else record_reason
                                            or "invalid-separated-authoritative-answer"
                                        )
                                    ),
                                }
                            )
                        continue
                    require_choice_answer = question_requires_choice_answer(question_body)
                    expected_choice_answer = (
                        extract_choice_answer(str(match.get("answer_body", "")))
                        if match is not None and require_choice_answer
                        else None
                    )
                    has_embed = bool(re.search(r"!\[\[Q\d+A\d+[^\]]*\]\]", text))
                    is_unmatched = "answer_status: unmatched" in text
                    records = application.get("answer_note_records", [])
                    record_results: list[tuple[dict[str, Any], bool, str | None]] = []
                    for record in records:
                        valid, reason = valid_solution_note(
                            Path(record.get("path", "")),
                            record,
                            require_choice_answer=require_choice_answer,
                            expected_choice_answer=expected_choice_answer,
                        )
                        record_results.append((record, valid, reason))
                    record_errors: list[str | None] = []
                    if match is not None:
                        authoritative_results = [
                            item
                            for item in record_results
                            if item[0].get("provenance") == "authoritative"
                        ]
                        supplemental_results = [
                            item
                            for item in record_results
                            if item[0].get("provenance") == "ai-generated-reviewed"
                        ]
                        has_valid_supplement = any(valid for _, valid, _ in supplemental_results)
                        for record, valid, reason in record_results:
                            provenance = record.get("provenance")
                            compensable_result_only = bool(
                                provenance == "authoritative"
                                and reason == "solution-content-incomplete"
                                and has_valid_supplement
                            )
                            if not valid and not compensable_result_only:
                                record_errors.append(reason)
                            if provenance not in {"authoritative", "ai-generated-reviewed"}:
                                record_errors.append("solution-provenance-unreviewed")
                        authoritative_source_matches = bool(authoritative_results) and all(
                            record.get("source_body_sha256") == match.get("answer_body_sha256")
                            for record, _, _ in authoritative_results
                        )
                        if not authoritative_source_matches:
                            record_errors.append("solution-source-provenance-drift")
                        has_substantive_solution = any(
                            valid for _, valid, _ in authoritative_results
                        ) or has_valid_supplement
                        has_valid_solution = bool(records) and not record_errors and has_substantive_solution
                    else:
                        for record, valid, reason in record_results:
                            if not valid:
                                record_errors.append(reason)
                            if record.get("provenance") != "ai-generated-reviewed":
                                record_errors.append("solution-provenance-unreviewed")
                        has_valid_solution = bool(records) and not record_errors
                    if not has_embed or is_unmatched or not has_valid_solution:
                        review_item = review_by_question.get(str(question["id"]), {})
                        reason = (
                            record_errors[0]
                            if record_errors
                            else review_item.get("root_cause")
                            or ("missing-answer-key" if match is None else "unembedded-solution")
                        )
                        errors.append(
                            {
                                "kind": "question-lacking-explanation",
                                "question_id": question["id"],
                                "question_file": str(q_file),
                                "reason": reason,
                            }
                        )
                    if match is not None and has_valid_solution:
                        ans_name = match.get("answer_name", f"{q_file.stem}A1")
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
    for report_name in (
        "content-application-report.json",
        "answer-application-report.json",
        "supplemental-solution-application-report.json",
    ):
        app_report_path = Path(profile["paths"]["staging_root"]) / report_name
        if app_report_path.is_file():
            app_report = load_json(app_report_path)
            for q_item in app_report.get("questions", []):
                for ans_note in q_item.get("answer_notes", []):
                    if ans_note:
                        expected_notes.add(str(Path(ans_note).resolve()).casefold())
    for generated_path in graph_root.rglob("*") if graph_root.exists() else []:
        if path_has_forbidden_colon(generated_path.relative_to(graph_root)):
            errors.append(
                {
                    "kind": "generated-filename-forbidden-colon",
                    "path": str(generated_path.resolve()),
                }
            )
    for note in graph_root.rglob("*.md") if graph_root.exists() else []:
        if str(note.resolve()).casefold() not in expected_notes:
            errors.append({"kind": "unexpected-generated-note", "path": str(note.resolve())})
        text = note.read_text(encoding="utf-8-sig")
        for destination in broken_local_links(note, text, vault_root, obsidian_names):
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

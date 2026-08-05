from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .common import (
    bounded_output_path,
    ConfigurationError,
    load_json,
    load_profile,
    lexical_signature,
    obsidian_embed,
    rebase_local_links,
    require_reviewed_adapter,
    safe_name,
    sha256_file,
    sha256_text,
    write_json_atomic,
    write_text_atomic,
)


GENERATED_LINK_RE = re.compile(
    r"^(?:\s*!\[\[[^\]]+\]\]\s*|\s*-\s+\[[^\]]+\]\([^)]+\)\s*)$"
)
SOURCE_PART_RE = re.compile(r"<!--\s*source-part:(?P<part>\d+)\s+pages:(?P<start>\d+)-(?P<end>\d+)\s*-->")


def visible_label(line: str) -> str:
    return re.sub(r"^\s*#{1,6}\s+", "", line).strip()


def compile_role_rules(adapter: dict[str, Any]) -> list[dict[str, Any]]:
    rules = adapter.get("content", {}).get("roles") or []
    compiled: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        role = str(rule.get("role", "")).strip()
        pattern = str(rule.get("pattern", ""))
        if not role or not pattern:
            raise ConfigurationError(f"Content role rule {index} is incomplete")
        compiled.append({**rule, "role": role, "depth": int(rule.get("depth", 0)), "_compiled": re.compile(pattern)})
    return compiled


def compile_question_patterns(adapter: dict[str, Any]) -> list[re.Pattern[str]]:
    patterns = adapter.get("content", {}).get("question_patterns") or []
    if not patterns:
        raise ConfigurationError("Adapter content.question_patterns is required")
    compiled = [re.compile(str(pattern)) for pattern in patterns]
    for pattern in compiled:
        if "number" not in pattern.groupindex:
            raise ConfigurationError("Every question pattern requires a named 'number' group")
    return compiled


def match_role(line: str, rules: list[dict[str, Any]]) -> tuple[dict[str, Any], re.Match[str]] | None:
    title = visible_label(line)
    for rule in rules:
        match = rule["_compiled"].fullmatch(title)
        if match:
            return rule, match
    return None


def match_question(line: str, patterns: list[re.Pattern[str]]) -> re.Match[str] | None:
    for pattern in patterns:
        match = pattern.match(line)
        if match:
            return match
    return None


def plan_note(
    note_entry: dict[str, Any],
    rules: list[dict[str, Any]],
    question_patterns: list[re.Pattern[str]],
    adapter: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    path = Path(note_entry["path"])
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    source_parts = [
        {
            "line": index,
            "part": int(match.group("part")),
            "start_page": int(match.group("start")),
            "end_page": int(match.group("end")),
        }
        for index, line in enumerate(lines, 1)
        if (match := SOURCE_PART_RE.search(line))
    ]
    labels: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    role_occurrences: dict[str, int] = {}
    embed_barriers = {
        index
        for index, line in enumerate(lines, 1)
        if GENERATED_LINK_RE.match(line)
    }
    for index, line in enumerate(lines, 1):
        if GENERATED_LINK_RE.match(line):
            continue
        if match_question(line, question_patterns):
            continue
        if (
            adapter.get("content", {}).get("skip_source_heading", True)
            and re.match(r"^\s*#{1,6}\s+\S", line)
            and visible_label(line) == str(note_entry.get("title", "")).strip()
        ):
            continue
        matched = match_role(line, rules)
        if matched:
            rule, match = matched
            title = match.groupdict().get("title") or visible_label(line)
            role_occurrences[rule["role"]] = role_occurrences.get(rule["role"], 0) + 1
            occurrence = role_occurrences[rule["role"]]
            answer_context = None
            if rule.get("answer_context") is True or rule.get("answer_context_template"):
                template = str(
                    rule.get("answer_context_template", "{note_key}:{role}:{occurrence}")
                )
                answer_context = template.format(
                    note_key=note_entry["key"],
                    role=rule["role"],
                    occurrence=occurrence,
                    title=str(title).strip(),
                )
            labels.append(
                {
                    "key": f"{note_entry['key']}:block:{len(labels) + 1}",
                    "role": rule["role"],
                    "depth": rule["depth"],
                    "title": str(title).strip(),
                    "start_line": index,
                    "source_note_key": note_entry["key"],
                    "source_note": str(path),
                    "occurrence": occurrence,
                    "answer_context": answer_context,
                }
            )
        elif re.match(r"^\s*#{1,6}\s+\S", line) and adapter.get("content", {}).get("unknown_label_policy", "review") == "review":
            unknown.append({"kind": "unknown-label", "source_note": str(path), "line": index, "text": visible_label(line)})

    for index, label in enumerate(labels):
        end = len(lines)
        for following in labels[index + 1:]:
            if following["depth"] <= label["depth"]:
                end = following["start_line"] - 1
                break
        barrier = min((line for line in embed_barriers if label["start_line"] < line <= end), default=None)
        if barrier is not None:
            end = barrier - 1
        label["end_line"] = end
        parent = None
        for previous in reversed(labels[:index]):
            if previous["depth"] < label["depth"] and previous["end_line"] >= label["start_line"]:
                parent = previous["key"]
                break
        label["parent"] = parent

    graph_root = Path(adapter["_graph_root"])
    question_folder = str(adapter.get("content", {}).get("question_folder", "questions"))
    path_by_label: dict[str, Path] = {}
    component_limit = int(adapter.get("content", {}).get("max_path_component_length", 80))
    path_limit = int(adapter.get("content", {}).get("max_path_length", 220))
    if component_limit < 12 or component_limit > 120:
        raise ConfigurationError("content.max_path_component_length must be between 12 and 120")
    functional_folder_template = str(adapter.get("content", {}).get("functional_folder_template", "{title}"))
    functional_file_template = str(adapter.get("content", {}).get("functional_file_template", "{title}.md"))
    for ordinal, label in enumerate(labels, 1):
        parent_path = path.parent
        if label["parent"]:
            parent_path = path_by_label[label["parent"]].parent
        values = {"ordinal": ordinal, "title": label["title"], "role": label["role"]}
        folder_name = functional_folder_template.format(**values)
        file_name = functional_file_template.format(**values)
        folder = parent_path / safe_name(folder_name, label["role"])[:component_limit]
        output = folder / safe_name(file_name, f"{label['role']}.md")[:component_limit]
        if output.suffix.casefold() != ".md":
            output = output.with_suffix(".md")
        output = bounded_output_path(graph_root, output, path_limit, label["key"])
        relative = output.relative_to(graph_root.resolve())
        label["output"] = str(output.resolve())
        label["output_relative"] = relative.as_posix()
        path_by_label[label["key"]] = output.resolve()

    questions: list[dict[str, Any]] = []
    starts: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines, 1):
        match = match_question(line, question_patterns)
        if match:
            number = str(match.group("number")).strip()
            if (
                not adapter.get("content", {}).get("allow_zero_question_number", False)
                and number.isdecimal()
                and int(number) == 0
            ):
                unknown.append(
                    {
                        "kind": "invalid-question-number",
                        "source_note": str(path),
                        "line": index,
                        "number": number,
                        "text": line,
                    }
                )
                continue
            starts.append((index, match))
    label_start_lines = {label["start_line"] for label in labels}
    question_file_template = str(adapter.get("content", {}).get("question_file_template", "{title}.md"))
    for position, (start, match) in enumerate(starts):
        end = starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)
        boundary = min((value for value in label_start_lines if start < value <= end), default=None)
        if boundary:
            end = boundary - 1
        embed_boundary = min((value for value in embed_barriers if start < value <= end), default=None)
        if embed_boundary is not None:
            end = embed_boundary - 1
        owner = None
        for label in labels:
            if label["start_line"] < start <= label["end_line"]:
                if owner is None or label["depth"] >= owner["depth"]:
                    owner = label
        number = str(match.group("number")).strip()
        evidence = {
            key: str(value).strip()
            for key, value in match.groupdict().items()
            if key != "number" and value is not None and str(value).strip()
        }
        context_key = str(
            owner.get("answer_context")
            if owner and owner.get("answer_context")
            else note_entry.get("answer_context", note_entry["key"])
        )
        base = Path(owner["output"]).parent if owner else path.parent
        title = str(adapter.get("content", {}).get("question_title_template", "Question {number}")).format(number=number)
        file_name = question_file_template.format(number=number, title=title, ordinal=position + 1, source_line=start)
        output = base / safe_name(question_folder, "questions")[:component_limit] / safe_name(file_name, f"{number}.md")[:component_limit]
        if output.suffix.casefold() != ".md":
            output = output.with_suffix(".md")
        output = bounded_output_path(
            graph_root,
            output,
            path_limit,
            f"{note_entry['key']}:question:{number}:{start}",
        )
        body = "\n".join(lines[start - 1:end]).rstrip() + "\n"
        source_part = next((item for item in reversed(source_parts) if item["line"] <= start), None)
        questions.append(
            {
                "id": f"{note_entry['key']}:question:{number}:{start}",
                "number": number,
                "evidence": evidence,
                "title": title,
                "source_note_key": note_entry["key"],
                "source_note": str(path),
                "context_key": context_key,
                "owner": owner["key"] if owner else None,
                "start_line": start,
                "end_line": end,
                "output": str(output.resolve()),
                "body_sha256": sha256_text(body),
                "body_lexical_signature": lexical_signature(body),
                "source_part": source_part,
            }
        )
    return labels, questions, unknown


def plan_content(profile_path: Path, adapter_path: Path, hierarchy_coverage_path: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    adapter = require_reviewed_adapter(profile, adapter_path)
    coverage = load_json(hierarchy_coverage_path)
    if coverage.get("status") != "passed":
        raise ConfigurationError("Hierarchy coverage must pass before content planning")
    adapter["_graph_root"] = profile["paths"]["graph_root"]
    rules = compile_role_rules(adapter)
    patterns = compile_question_patterns(adapter)
    labels: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    hierarchy_adapter = adapter.get("hierarchy", {}).get("entries") or []
    context_by_key = {str(item.get("key")): item.get("answer_context", item.get("key")) for item in hierarchy_adapter}
    for note in coverage.get("notes", []):
        if note.get("key") == "root" or note.get("structural_only") is True:
            continue
        note = {**note, "answer_context": context_by_key.get(str(note.get("key")), note.get("key"))}
        note_labels, note_questions, note_review = plan_note(note, rules, patterns, adapter)
        labels.extend(note_labels)
        questions.extend(note_questions)
        review.extend(note_review)
    ids = [question["id"] for question in questions]
    outputs = [question["output"].casefold() for question in questions]
    functional_outputs = [node["output"].casefold() for node in labels]
    all_outputs = outputs + functional_outputs
    if len(ids) != len(set(ids)) or len(all_outputs) != len(set(all_outputs)):
        raise ConfigurationError("Question identities or output paths collide")
    return {
        "schema_version": 1,
        "stage": "content-segmentation",
        "status": "review_required" if review else "passed",
        "profile": profile["_profile_path"],
        "adapter": str(adapter_path.resolve()),
        "hierarchy_coverage": str(hierarchy_coverage_path.resolve()),
        "functional_nodes": labels,
        "questions": questions,
        "review_items": review,
    }


def render_question(question: dict[str, Any], body: str, answer_mode: str = "separate") -> str:
    frontmatter = [
        "---",
        f"question_id: {json.dumps(question['id'], ensure_ascii=False)}",
        f"question_number: {json.dumps(question['number'], ensure_ascii=False)}",
        f"context_key: {json.dumps(question['context_key'], ensure_ascii=False)}",
        f"question_source: {json.dumps(question['source_note'], ensure_ascii=False)}",
        f"question_body_sha256: {question['body_sha256']}",
        f"answer_status: {'unavailable' if answer_mode == 'unavailable' else 'unmatched'}",
        "---",
        "<!-- question-source:start -->",
        body.rstrip(),
        "<!-- question-source:end -->",
        "",
    ]
    source_part = question.get("source_part")
    if source_part:
        page_range = f"{source_part['start_page']}-{source_part['end_page']}"
        frontmatter[6:6] = [
            f"source_pdf_part: {source_part['part']}",
            f"source_page_range: {json.dumps(page_range)}",
        ]
    return "\n".join(frontmatter)


def apply_content(profile_path: Path, adapter_path: Path, manifest_path: Path, overwrite: bool) -> dict[str, Any]:
    profile = load_profile(profile_path)
    require_reviewed_adapter(profile, adapter_path)
    manifest = load_json(manifest_path)
    if manifest.get("status") != "passed":
        raise ConfigurationError("Content manifest must pass before application")
    functional = manifest.get("functional_nodes", [])
    questions = manifest.get("questions", [])
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    by_source: dict[str, dict[str, Any]] = {}
    for node in functional:
        by_source.setdefault(node["source_note"], {"nodes": [], "questions": []})["nodes"].append(node)
    for question in questions:
        by_source.setdefault(question["source_note"], {"nodes": [], "questions": []})["questions"].append(question)

    report_path = Path(profile["paths"]["staging_root"]) / "content-application-report.json"
    previous_generated: set[str] = set()
    if overwrite and report_path.is_file():
        previous = load_json(report_path)
        previous_generated.update(str(item["path"]) for item in previous.get("generated_outputs", []))
        previous_generated.update(str(item["path"]) for item in previous.get("questions", []))
    written_questions: list[dict[str, Any]] = []
    generated_outputs: list[dict[str, Any]] = []
    for source_name, values in by_source.items():
        source = Path(source_name)
        lines = source.read_text(encoding="utf-8-sig").splitlines()
        nodes = values["nodes"]
        note_by_key = {node["key"]: Path(node["output"]) for node in nodes}
        direct_questions: dict[str | None, list[dict[str, Any]]] = {}
        for question in values["questions"]:
            direct_questions.setdefault(question.get("owner"), []).append(question)
            body = "\n".join(lines[question["start_line"] - 1:question["end_line"]]).rstrip() + "\n"
            if sha256_text(body) != question["body_sha256"]:
                raise ConfigurationError(f"Question source changed before apply: {question['id']}")
            output = Path(question["output"])
            rendered_question = rebase_local_links(
                render_question(question, body, str(profile.get("answers", {}).get("mode", "separate"))),
                source,
                output,
            )
            write_text_atomic(output, rendered_question, overwrite=overwrite)
            written_questions.append({"id": question["id"], "path": str(output), "sha256": sha256_file(output)})

        for node in sorted(nodes, key=lambda item: item["depth"], reverse=True):
            output = Path(node["output"])
            child_nodes = [item for item in nodes if item.get("parent") == node["key"]]
            replacements: dict[int, tuple[int, str]] = {}
            for child in child_nodes:
                replacements[child["start_line"]] = (
                    child["end_line"],
                    obsidian_embed(Path(child["output"]), vault_root),
                )
            for question in direct_questions.get(node["key"], []):
                replacements[question["start_line"]] = (
                    question["end_line"],
                    obsidian_embed(Path(question["output"]), vault_root),
                )
            rendered: list[str] = []
            line = node["start_line"]
            while line <= node["end_line"]:
                replacement = replacements.get(line)
                if replacement:
                    rendered.append(replacement[1])
                    line = replacement[0] + 1
                else:
                    rendered.append(lines[line - 1])
                    line += 1
            node_text = rebase_local_links("\n".join(rendered).rstrip() + "\n", source, output)
            write_text_atomic(output, node_text, overwrite=overwrite)
            generated_outputs.append({"kind": "functional", "path": str(output), "sha256": sha256_file(output)})

        top_nodes = [node for node in nodes if node.get("parent") is None]
        replacements: dict[int, tuple[int, str]] = {}
        for node in top_nodes:
            replacements[node["start_line"]] = (
                node["end_line"],
                obsidian_embed(Path(node["output"]), vault_root),
            )
        for question in direct_questions.get(None, []):
            replacements[question["start_line"]] = (
                question["end_line"],
                obsidian_embed(Path(question["output"]), vault_root),
            )
        rendered = []
        line = 1
        while line <= len(lines):
            replacement = replacements.get(line)
            if replacement:
                rendered.append(replacement[1])
                line = replacement[0] + 1
            else:
                rendered.append(lines[line - 1])
                line += 1
        write_text_atomic(source, "\n".join(rendered).rstrip() + "\n", overwrite=True)

    generated_outputs.extend({"kind": "question", **item} for item in written_questions)
    current_generated = {str(item["path"]) for item in generated_outputs}
    graph_root = Path(profile["paths"]["graph_root"]).resolve()
    removed_stale: list[str] = []
    for stale_name in sorted(previous_generated - current_generated):
        stale = Path(stale_name).resolve()
        try:
            stale.relative_to(graph_root)
        except ValueError as exc:
            raise ConfigurationError(f"Refusing to prune output outside graph root: {stale}") from exc
        if stale.is_file():
            stale.unlink()
            removed_stale.append(str(stale))

    result = {
        "schema_version": 1,
        "stage": "content-application",
        "status": "passed",
        "profile": profile["_profile_path"],
        "manifest": str(manifest_path.resolve()),
        "functional_node_count": len(functional),
        "question_count": len(questions),
        "questions": written_questions,
        "generated_outputs": generated_outputs,
        "removed_stale_outputs": removed_stale,
    }
    write_json_atomic(report_path, result, overwrite=overwrite)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or apply profile-driven functional and atomic-question segmentation.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("profile", type=Path)
    plan.add_argument("adapter", type=Path)
    plan.add_argument("hierarchy_coverage", type=Path)
    plan.add_argument("output", type=Path)
    plan.add_argument("--overwrite", action="store_true")
    apply = sub.add_parser("apply")
    apply.add_argument("profile", type=Path)
    apply.add_argument("adapter", type=Path)
    apply.add_argument("manifest", type=Path)
    apply.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = plan_content(args.profile, args.adapter, args.hierarchy_coverage)
            write_json_atomic(args.output, result, overwrite=args.overwrite)
        else:
            result = apply_content(args.profile, args.adapter, args.manifest, args.overwrite)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "content-segmentation", "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

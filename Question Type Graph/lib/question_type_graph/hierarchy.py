from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .common import (
    adapter_output_policy,
    ConfigurationError,
    load_json,
    load_profile,
    obsidian_embed,
    prune_empty_directories,
    rebase_local_links,
    require_reviewed_adapter,
    resolve_inside,
    safe_name,
    sha256_file,
    sha256_text,
    write_json_atomic,
    write_text_atomic,
)


def normalize_generated_output(value: str) -> str:
    """Normalize every generated hierarchy path component to vault policy."""
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ConfigurationError(f"Hierarchy output must be a safe relative path: {value}")
    return Path(*(safe_name(part) for part in path.parts)).as_posix()


def normalize_heading(line: str) -> str:
    return re.sub(r"^\s*#{1,6}\s+", "", line).strip()


def equivalent_boundary_title(line: str, title: str) -> bool:
    def normalized(value: str) -> str:
        value = normalize_heading(value)
        value = re.sub(r"^[【\[]|[】\]]$", "", value).strip()
        return re.sub(r"\s+", " ", value)

    return normalized(line) == normalized(title)


def source_for_role(profile: dict[str, Any], role: str) -> dict[str, Any]:
    values = [source for source in profile["sources"] if source.get("role") == role]
    if len(values) != 1:
        raise ConfigurationError(f"Hierarchy source role must resolve once: {role}")
    return values[0]


def reviewed_hierarchy_entries(
    hierarchy: dict[str, Any], lines: list[str], start_limit: int, end_limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bind executable entries to a reviewed primary ledger or an explicit no-TOC decision."""
    configured = hierarchy.get("entries") or []
    authority = hierarchy.get("primary_authority")
    if not authority:
        no_toc = hierarchy.get("no_toc_authority")
        if not isinstance(no_toc, dict):
            return configured, [
                {
                    "kind": "missing-hierarchy-authority",
                    "message": "Provide primary_authority or an explicit reviewed no_toc_authority decision",
                }
            ]
        if (
            no_toc.get("status") != "passed"
            or no_toc.get("reviewer_confirmed") is not True
            or not str(no_toc.get("reason", "")).strip()
        ):
            raise ConfigurationError("no_toc_authority must be reviewed, passed, and include a reason")
        return configured, []
    if authority.get("status") != "passed" or authority.get("reviewer_confirmed") is not True:
        raise ConfigurationError("Primary hierarchy authority must be reviewed and passed")
    expected = authority.get("entries") or []
    if not isinstance(expected, list) or not expected:
        raise ConfigurationError("Primary hierarchy authority requires a complete entries ledger")
    authority_start = int(authority.get("start_line", start_limit))
    authority_end = int(authority.get("end_line", end_limit))
    if authority_start < 1 or authority_end > len(lines) or authority_start > authority_end:
        raise ConfigurationError("Primary hierarchy authority range is outside the source Markdown")

    review: list[dict[str, Any]] = []
    expected_by_key: dict[str, dict[str, Any]] = {}
    for item in expected:
        key = str(item.get("key", "")).strip()
        title = str(item.get("title", "")).strip()
        level = int(item.get("level", 0))
        source_line = int(item.get("source_line", 0))
        source_end_line = int(item.get("source_end_line", source_line))
        if (
            not key
            or key in expected_by_key
            or not title
            or level < 1
            or level > 6
            or source_line < authority_start
            or source_end_line > authority_end
            or source_line > source_end_line
        ):
            raise ConfigurationError(f"Invalid primary authority entry: {item}")
        expected_by_key[key] = {**item, "key": key, "title": title, "level": level}

    configured_by_key = {str(item.get("key", "")).strip(): item for item in configured}
    if len(configured_by_key) != len(configured):
        raise ConfigurationError("Hierarchy entries contain duplicate or empty keys")
    for key, item in expected_by_key.items():
        configured_item = configured_by_key.get(key)
        if configured_item is None:
            review.append({"kind": "missing-primary-authority-entry", "key": key, "title": item["title"]})
            continue
        if configured_item.get("title") not in (None, item["title"]):
            review.append({"kind": "primary-title-mismatch", "key": key, "expected": item["title"]})
        if configured_item.get("level") not in (None, item["level"]):
            review.append({"kind": "primary-level-mismatch", "key": key, "expected": item["level"]})
    for key, item in configured_by_key.items():
        if key not in expected_by_key and item.get("supplemental") is not True:
            review.append({"kind": "unregistered-hierarchy-entry", "key": key})

    configured_authority_order = [
        str(item.get("key")) for item in configured if str(item.get("key")) in expected_by_key
    ]
    expected_order = list(expected_by_key)
    if configured_authority_order != [key for key in expected_order if key in configured_by_key]:
        review.append({"kind": "primary-authority-order-mismatch"})

    merged: list[dict[str, Any]] = []
    for item in configured:
        key = str(item.get("key", "")).strip()
        authority_item = expected_by_key.get(key)
        if authority_item:
            merged.append(
                {
                    **item,
                    "title": authority_item["title"],
                    "level": authority_item["level"],
                    "toc_source_line": authority_item["source_line"],
                    "toc_source_end_line": authority_item.get("source_end_line", authority_item["source_line"]),
                }
            )
        else:
            merged.append(item)
    return merged, review


PRINTED_TOC_LEADER_RE = re.compile(r"(?:…{2,}|\.{4,})\s*\d+")
LECTURE_TITLE_RE = re.compile(r"^第\s*(\d+)\s*讲(?:\s|$)")
NUMBERED_SUBSECTION_RE = re.compile(r"^(\d+)\.(\d+)(?:\s|$)")


def reviewed_printed_toc_coverage(
    hierarchy: dict[str, Any], lines: list[str], first_body_line: int
) -> list[dict[str, Any]]:
    """Reject a reviewed ledger that silently covers only part of a printed TOC.

    Coverage is counted per leader-delimited entry, not merely per raw line.
    Multi-column OCR commonly joins two or more printed TOC records onto one
    Markdown line; registering only one of them must not make the row pass.
    """
    authority = hierarchy.get("primary_authority")
    if not isinstance(authority, dict):
        return []
    registered_spans: list[tuple[int, int]] = []
    for item in authority.get("entries") or []:
        start = int(item.get("source_line", 0))
        end = int(item.get("source_end_line", start))
        registered_spans.append((start, end))

    excluded_spans: list[tuple[int, int]] = []
    for item in authority.get("excluded_entries") or []:
        start = int(item.get("source_line", 0))
        end = int(item.get("source_end_line", start))
        if (
            start < 1
            or end < start
            or end >= first_body_line
            or item.get("reviewer_confirmed") is not True
            or not str(item.get("title", "")).strip()
            or not str(item.get("reason", "")).strip()
        ):
            raise ConfigurationError(f"Invalid excluded printed TOC entry: {item}")
        excluded_spans.append((start, end))

    review: list[dict[str, Any]] = []
    for line_number in range(1, min(first_body_line, len(lines) + 1)):
        text = lines[line_number - 1].strip()
        observed_count = len(PRINTED_TOC_LEADER_RE.findall(text))
        if observed_count == 0:
            continue
        registered_count = sum(
            start <= line_number <= end for start, end in registered_spans
        )
        excluded_count = sum(
            start <= line_number <= end for start, end in excluded_spans
        )
        covered_count = registered_count + excluded_count
        if covered_count < observed_count:
            review.append(
                {
                    "kind": "unregistered-printed-toc-entry",
                    "line": line_number,
                    "text": text,
                    "observed_entry_count": observed_count,
                    "registered_entry_count": covered_count,
                    "missing_entry_count": observed_count - covered_count,
                }
            )
    return review


def leaf_question_ownership_review(
    hierarchy: dict[str, Any], entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Require every question-bearing node to be a hierarchy leaf when opted in."""
    if hierarchy.get("question_ownership_policy", "non-structural") != "leaf-only":
        return []
    parent_keys = {
        str(entry.get("parent"))
        for entry in entries
        if entry.get("parent") is not None
    }
    return [
        {
            "kind": "structural-parent-not-marked",
            "key": entry.get("key"),
            "title": entry.get("title"),
        }
        for entry in entries
        if str(entry.get("key")) in parent_keys
        and entry.get("structural_only") is not True
    ]


def conventional_numbering_structure_review(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cross-check conventional 第N讲 / N.M / 思考题 hierarchy semantics."""
    if not any(LECTURE_TITLE_RE.match(str(entry.get("title", "")).strip()) for entry in entries):
        return []
    lectures: dict[str, dict[str, Any]] = {}
    review: list[dict[str, Any]] = []
    for entry in entries:
        title = str(entry.get("title", "")).strip()
        lecture_match = LECTURE_TITLE_RE.match(title)
        if lecture_match:
            lectures[lecture_match.group(1)] = entry
            continue
        subsection_match = NUMBERED_SUBSECTION_RE.match(title)
        if subsection_match:
            lecture = lectures.get(subsection_match.group(1))
            if lecture is None:
                review.append(
                    {
                        "kind": "orphan-numbered-subsection",
                        "key": entry.get("key"),
                        "title": title,
                    }
                )
            elif (
                int(entry.get("level", 0)) <= int(lecture.get("level", 0))
                or entry.get("parent") != lecture.get("key")
            ):
                review.append(
                    {
                        "kind": "numbered-subsection-parent-mismatch",
                        "key": entry.get("key"),
                        "title": title,
                        "expected_parent": lecture.get("key"),
                    }
                )
            continue
        if re.fullmatch(r"思考题\s*", title):
            lecture = next(reversed(list(lectures.values())), None)
            if lecture is not None and (
                int(entry.get("level", 0)) <= int(lecture.get("level", 0))
                or entry.get("parent") != lecture.get("key")
            ):
                review.append(
                    {
                        "kind": "thought-exercises-parent-mismatch",
                        "key": entry.get("key"),
                        "expected_parent": lecture.get("key"),
                    }
                )
    return review


def find_entry_line(lines: list[str], entry: dict[str, Any], minimum: int, maximum: int) -> int | None:
    anchor = entry.get("body_anchor")
    if isinstance(anchor, dict):
        value = int(anchor.get("start_line", 0))
        kind = str(anchor.get("kind", "")).strip()
        if anchor.get("reviewer_confirmed") is not True or kind not in {"source-heading", "reviewed-boundary"}:
            raise ConfigurationError(f"Hierarchy body anchor is not reviewed: {entry.get('key')}")
        if kind == "reviewed-boundary" and not str(anchor.get("evidence", "")).strip():
            raise ConfigurationError(f"Reviewed hierarchy boundary lacks evidence: {entry.get('key')}")
        if kind == "source-heading" and minimum <= value <= maximum:
            titles = [str(entry.get("title", "")), *[str(item) for item in entry.get("aliases", [])]]
            if normalize_heading(lines[value - 1]) not in {item.strip() for item in titles if item.strip()}:
                raise ConfigurationError(f"Source-heading anchor does not match its title: {entry.get('key')}")
        return value if minimum <= value <= maximum else None
    if isinstance(entry.get("start_line"), int):
        value = int(entry["start_line"])
        return value if minimum <= value <= maximum else None
    titles = [str(entry.get("title", "")), *[str(value) for value in entry.get("aliases", [])]]
    titles = [value.strip() for value in titles if value.strip()]
    pattern = entry.get("match_pattern")
    compiled = re.compile(str(pattern)) if pattern else None
    for index in range(max(1, minimum), min(maximum, len(lines)) + 1):
        title = normalize_heading(lines[index - 1])
        if title in titles or (compiled and compiled.fullmatch(title)):
            return index
    return None


def plan_hierarchy(profile_path: Path, adapter_path: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    adapter = require_reviewed_adapter(profile, adapter_path)
    output_policy = adapter_output_policy(adapter)
    hierarchy = adapter.get("hierarchy") or {}
    role = str(hierarchy.get("source_role") or ("combined" if profile["answers"]["mode"] == "embedded" else "questions"))
    source = source_for_role(profile, role)
    markdown = Path(source["markdown_path"]).resolve()
    if not markdown.is_file():
        raise ConfigurationError(f"Converted hierarchy Markdown is missing: {markdown}")
    lines = markdown.read_text(encoding="utf-8-sig").splitlines()
    region = hierarchy.get("region") or {}
    start_limit = int(region.get("start_line", 1))
    end_limit = int(region.get("end_line", len(lines)))
    if start_limit < 1 or end_limit > len(lines) or start_limit > end_limit:
        raise ConfigurationError("Hierarchy region is outside the source Markdown")
    configured, authority_review = reviewed_hierarchy_entries(hierarchy, lines, start_limit, end_limit)
    if not isinstance(configured, list) or not configured:
        return {
            "schema_version": 1,
            "stage": "hierarchy-segmentation",
            "status": "review_required",
            "profile": profile["_profile_path"],
            "adapter": str(adapter_path.resolve()),
            "source_role": role,
            "source_markdown": str(markdown),
            "source_markdown_sha256": sha256_file(markdown),
            "entries": [],
            "review_items": [{"kind": "hierarchy", "message": "No reviewed hierarchy entries are configured"}],
        }
    entries: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = list(authority_review)
    minimum = start_limit
    keys: set[str] = set()
    outputs: set[str] = set()
    for raw in configured:
        key = str(raw.get("key", "")).strip()
        title = str(raw.get("title", "")).strip()
        level = int(raw.get("level", 0))
        output = str(raw.get("output", "")).strip()
        if not key or key in keys or not title or level < 1 or level > 6 or not output.endswith(".md"):
            raise ConfigurationError(f"Invalid or duplicate hierarchy entry: {raw}")
        output = normalize_generated_output(output)
        if output.casefold() in outputs:
            raise ConfigurationError(f"Hierarchy outputs collide after filename normalization: {output}")
        outputs.add(output.casefold())
        line = find_entry_line(lines, raw, minimum, end_limit)
        if line is None:
            review_items.append({"kind": "unmatched-hierarchy-entry", "key": key, "title": title})
            continue
        keys.add(key)
        entries.append(
            {
                "key": key,
                "title": title,
                "role": raw.get("role", "hierarchy"),
                "level": level,
                "start_line": line,
                "output": output,
                "answer_context": raw.get("answer_context", key),
                "structural_only": raw.get("structural_only") is True,
                "emit_title": raw.get("emit_title") is True,
                "supplemental": raw.get("supplemental") is True,
                "toc_source_line": raw.get("toc_source_line"),
                "toc_source_end_line": raw.get("toc_source_end_line"),
            }
        )
        minimum = line if raw.get("structural_only") is True else line + 1
    for index, entry in enumerate(entries):
        end = end_limit
        for following in entries[index + 1:]:
            if following["level"] <= entry["level"]:
                end = following["start_line"] - 1
                break
        entry["end_line"] = end
        parent = None
        for previous in reversed(entries[:index]):
            if previous["level"] < entry["level"]:
                parent = previous["key"]
                break
        entry["parent"] = parent
    if entries:
        review_items.extend(
            reviewed_printed_toc_coverage(
                hierarchy,
                lines,
                min(int(entry["start_line"]) for entry in entries),
            )
        )
        review_items.extend(conventional_numbering_structure_review(entries))
        review_items.extend(leaf_question_ownership_review(hierarchy, entries))
    return {
        "schema_version": 1,
        "stage": "hierarchy-segmentation",
        "status": "review_required" if review_items else "passed",
        "profile": profile["_profile_path"],
        "adapter": str(adapter_path.resolve()),
        "source_role": role,
        "source_markdown": str(markdown),
        "source_markdown_sha256": sha256_file(markdown),
        "line_count": len(lines),
        "root_output": normalize_generated_output(str(hierarchy.get("root_output", "index.md"))),
        "generate_index": output_policy["generate_index"],
        "navigation_embed_mode": "direct-children",
        "question_ownership_policy": hierarchy.get(
            "question_ownership_policy", "non-structural"
        ),
        "entries": entries,
        "review_items": review_items,
    }


def direct_children(entries: list[dict[str, Any]], key: str | None) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry.get("parent") == key]


def apply_hierarchy(profile_path: Path, adapter_path: Path, manifest_path: Path, overwrite: bool) -> dict[str, Any]:
    profile = load_profile(profile_path)
    adapter = require_reviewed_adapter(profile, adapter_path)
    output_policy = adapter_output_policy(adapter)
    manifest = load_json(manifest_path)
    if manifest.get("status") != "passed":
        raise ConfigurationError("Hierarchy manifest must pass before application")
    markdown = Path(manifest["source_markdown"])
    if sha256_file(markdown) != manifest.get("source_markdown_sha256"):
        raise ConfigurationError("Hierarchy source Markdown changed after planning")
    lines = markdown.read_text(encoding="utf-8-sig").splitlines()
    graph_root = Path(profile["paths"]["graph_root"]).resolve()
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    coverage_path = Path(profile["paths"]["staging_root"]) / "hierarchy-coverage-manifest.json"
    previous_notes: set[str] = set()
    if overwrite and coverage_path.is_file():
        previous_coverage = load_json(coverage_path)
        previous_notes.update(
            str(Path(item["path"]).resolve())
            for item in previous_coverage.get("notes", [])
            if item.get("path")
        )
    if graph_root.exists() and any(graph_root.iterdir()) and not overwrite:
        raise ConfigurationError("Graph root is non-empty; explicit --overwrite required")
    raw_asset_root = markdown.parent / "images"
    graph_asset_root = graph_root / "images"
    if raw_asset_root.is_dir():
        shutil.copytree(raw_asset_root, graph_asset_root, dirs_exist_ok=overwrite)
    relocations = [(raw_asset_root, graph_asset_root)] if raw_asset_root.is_dir() else []
    entries = manifest["entries"]
    output_by_key = {entry["key"]: resolve_inside(graph_root, entry["output"]) for entry in entries}
    line_owners = ["root"] * len(lines)

    for entry in entries:
        for number in range(entry["start_line"], entry["end_line"] + 1):
            line_owners[number - 1] = entry["key"]
    for entry in sorted(entries, key=lambda item: item["level"]):
        for child in direct_children(entries, entry["key"]):
            for number in range(child["start_line"], child["end_line"] + 1):
                line_owners[number - 1] = child["key"]

    written: list[dict[str, Any]] = []
    corpus_root = Path(profile["paths"]["staging_root"]) / "hierarchy-corpus"
    for entry in sorted(entries, key=lambda item: item["level"], reverse=True):
        note = output_by_key[entry["key"]]
        children = sorted(direct_children(entries, entry["key"]), key=lambda item: item["start_line"])
        child_by_start = {child["start_line"]: child for child in children}
        output_lines: list[str] = []
        output_source_lines: list[int | None] = []
        if entry.get("emit_title"):
            output_lines.extend([f"{'#' * min(int(entry['level']), 6)} {entry['title']}", ""])
            output_source_lines.extend([None, None])
        line = entry["start_line"]
        while line <= entry["end_line"]:
            child = child_by_start.get(line)
            if child:
                output_lines.append(obsidian_embed(output_by_key[child["key"]], vault_root))
                output_source_lines.append(None)
                line = child["end_line"] + 1
            else:
                if (
                    entry.get("emit_title")
                    and line == entry["start_line"]
                    and (
                        re.match(r"^\s*#{1,6}\s+\S", lines[line - 1])
                        or equivalent_boundary_title(lines[line - 1], entry["title"])
                    )
                ):
                    line += 1
                    while line <= entry["end_line"] and not lines[line - 1].strip():
                        line += 1
                    continue
                output_lines.append(lines[line - 1])
                output_source_lines.append(line)
                line += 1
        text = "\n".join(output_lines).rstrip() + "\n"
        output_source_lines = output_source_lines[: len(text.splitlines())]
        text = rebase_local_links(text, markdown, note, relocations)
        content_source = corpus_root / f"{sha256_text(entry['key'])[:16]}.md"
        write_text_atomic(content_source, text, overwrite=True)
        write_text_atomic(note, text, overwrite=overwrite)
        written.append(
            {
                "key": entry["key"],
                "title": entry["title"],
                "role": entry.get("role", "hierarchy"),
                "level": entry["level"],
                "parent": entry.get("parent"),
                "structural_only": entry.get("structural_only") is True,
                "supplemental": entry.get("supplemental") is True,
                "answer_context": entry.get("answer_context", entry["key"]),
                "path": str(note),
                "sha256": sha256_file(note),
                "content_source": str(content_source.resolve()),
                "content_sha256": sha256_file(content_source),
                "source_line_map": output_source_lines,
            }
        )

    generate_index = (
        manifest.get("generate_index", output_policy["generate_index"]) is True
    )
    if generate_index:
        root_note = resolve_inside(graph_root, manifest["root_output"])
        top = sorted(direct_children(entries, None), key=lambda item: item["start_line"])
        top_by_start = {item["start_line"]: item for item in top}
        root_lines: list[str] = []
        root_source_lines: list[int | None] = []
        line = 1
        while line <= len(lines):
            child = top_by_start.get(line)
            if child:
                root_lines.append(obsidian_embed(output_by_key[child["key"]], vault_root))
                root_source_lines.append(None)
                line = child["end_line"] + 1
            else:
                root_lines.append(lines[line - 1])
                root_source_lines.append(line)
                line += 1
        root_text = rebase_local_links(
            "\n".join(root_lines).rstrip() + "\n",
            markdown,
            root_note,
            relocations,
        )
        root_source_lines = root_source_lines[: len(root_text.splitlines())]
        write_text_atomic(root_note, root_text, overwrite=overwrite)
        written.append(
            {
                "key": "root",
                "path": str(root_note),
                "sha256": sha256_file(root_note),
                "source_line_map": root_source_lines,
            }
        )
    current_notes = {str(Path(item["path"]).resolve()) for item in written if item.get("path")}
    removed_stale: list[str] = []
    for stale_name in sorted(previous_notes - current_notes):
        stale = Path(stale_name).resolve()
        try:
            stale.relative_to(graph_root)
        except ValueError as exc:
            raise ConfigurationError(f"Refusing to prune hierarchy output outside graph root: {stale}") from exc
        if stale.is_file():
            stale.unlink()
            removed_stale.append(str(stale))
    removed_empty_directories = prune_empty_directories(graph_root)
    coverage = {
        "schema_version": 1,
        "stage": "hierarchy-coverage",
        "status": "passed",
        "profile": profile["_profile_path"],
        "source_role": manifest.get("source_role"),
        "source_markdown": str(markdown),
        "source_markdown_sha256": manifest["source_markdown_sha256"],
        "line_count": len(lines),
        "owned_line_count": len(line_owners),
        "line_owners": line_owners,
        "generate_index": generate_index,
        "notes": written,
        "removed_stale_outputs": removed_stale,
        "removed_empty_directories": removed_empty_directories,
    }
    write_json_atomic(coverage_path, coverage, overwrite=overwrite)
    return coverage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or apply reviewed supplementary-book hierarchy segmentation.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("profile", type=Path)
    plan.add_argument("adapter", type=Path)
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
            result = plan_hierarchy(args.profile, args.adapter)
            write_json_atomic(args.output, result, overwrite=args.overwrite)
        else:
            result = apply_hierarchy(args.profile, args.adapter, args.manifest, args.overwrite)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "hierarchy-segmentation", "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

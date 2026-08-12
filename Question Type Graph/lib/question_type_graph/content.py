from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
from typing import Any

from .common import (
    bounded_output_path,
    compile_number_patterns,
    ConfigurationError,
    load_json,
    load_profile,
    lexical_signature,
    obsidian_embed,
    prune_empty_directories,
    rebase_local_links,
    require_reviewed_adapter,
    safe_name,
    sha256_file,
    sha256_text,
    write_json_atomic,
    write_text_atomic,
)
from .spans import split_virtual_lines


GENERATED_LINK_RE = re.compile(
    r"^(?:\s*!\[\[[^\]]+\]\]\s*|\s*-\s+\[[^\]]+\]\([^)]+\)\s*)$"
)
SOURCE_PART_RE = re.compile(r"<!--\s*source-part:(?P<part>\d+)\s+pages:(?P<start>\d+)-(?P<end>\d+)\s*-->")
HTML_TABLE_LINE_RE = re.compile(r"^\s*<table\b[^>]*>.*?</table>\s*$", re.IGNORECASE | re.DOTALL)
HTML_ROW_RE = re.compile(r"<tr\b[^>]*>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
HTML_CELL_RE = re.compile(
    r"<t[dh]\b(?P<attrs>[^>]*)>(?P<body>.*?)</t[dh]>",
    re.IGNORECASE | re.DOTALL,
)
HTML_ROWSPAN_RE = re.compile(r"\browspan\s*=\s*[\"']?(?P<value>\d+)", re.IGNORECASE)
HTML_COLSPAN_RE = re.compile(r"\bcolspan\s*=\s*[\"']?(?P<value>\d+)", re.IGNORECASE)


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
    return compile_number_patterns(
        adapter.get("content", {}).get("question_patterns"),
        "content.question_patterns",
    )


def compile_inline_question_patterns(
    adapter: dict[str, Any], question_patterns: list[re.Pattern[str]]
) -> list[re.Pattern[str]]:
    content = adapter.get("content", {})
    if "inline_question_patterns" not in content:
        return question_patterns
    return compile_number_patterns(
        content.get("inline_question_patterns"),
        "content.inline_question_patterns",
        required=False,
    )


def match_role(line: str, rules: list[dict[str, Any]]) -> tuple[dict[str, Any], re.Match[str]] | None:
    title = visible_label(line)
    for rule in rules:
        if rule.get("heading_only") is True and not re.match(r"^\s*#{1,6}\s+\S", line):
            continue
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


def question_in_reviewed_scope(
    note_key: str,
    raw_line: int,
    owner: dict[str, Any] | None,
    labels: list[dict[str, Any]],
    adapter: dict[str, Any],
) -> bool:
    """Restrict numeric detection to reviewer-selected functional sections."""
    scopes = adapter.get("content", {}).get("question_scopes")
    if scopes is None:
        return True
    by_key = {str(item["key"]): item for item in labels}
    owner_roles: set[str] = set()
    current = owner
    while current:
        owner_roles.add(str(current.get("role", "")))
        current = by_key.get(str(current.get("parent"))) if current.get("parent") else None
    for scope in scopes:
        contexts = scope.get("contexts")
        if contexts is None and scope.get("context") is not None:
            contexts = [scope.get("context")]
        if contexts is not None and note_key not in {str(value) for value in contexts}:
            continue
        if scope.get("start_line") is not None and raw_line < int(scope["start_line"]):
            continue
        if scope.get("end_line") is not None and raw_line > int(scope["end_line"]):
            continue
        roles = {str(value) for value in scope.get("roles", [])}
        if roles and not roles.intersection(owner_roles):
            continue
        return True
    return False


def detach_configured_role_roots(
    labels: list[dict[str, Any]], adapter: dict[str, Any]
) -> None:
    """Detach exercise blocks from a non-exercise ancestor when OCR omits a band label."""
    rules = adapter.get("content", {}).get("detached_role_folders") or []
    if not isinstance(rules, list):
        raise ConfigurationError("content.detached_role_folders must be a list")
    by_key = {str(label["key"]): label for label in labels}
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ConfigurationError(
                f"content.detached_role_folders[{index}] must be an object"
            )
        ancestor_role = str(rule.get("from_ancestor_role", "")).strip()
        folder = str(rule.get("folder", "")).strip()
        roles = {
            str(role).strip()
            for role in (rule.get("roles") or [])
            if str(role).strip()
        }
        if not ancestor_role or not folder or not roles:
            raise ConfigurationError(
                f"content.detached_role_folders[{index}] requires "
                "from_ancestor_role, folder, and non-empty roles"
            )
        for label_index, label in enumerate(labels):
            if label.get("role") not in roles or not label.get("parent"):
                continue
            ancestor = by_key.get(str(label.get("parent")))
            while ancestor and ancestor.get("role") != ancestor_role:
                ancestor = by_key.get(str(ancestor.get("parent"))) if ancestor.get("parent") else None
            if ancestor is None:
                continue
            ancestor["end_line"] = min(
                int(ancestor["end_line"]), int(label["start_line"]) - 1
            )
            label["parent"] = None
            label["detached_root_folder"] = folder
            # Same-depth source headings can be subdivisions of the detached
            # exercise root (for example numbered models beneath a question
            # type).  Depth alone originally leaves them on the theory
            # ancestor, so claim the contiguous run until the next exercise
            # root or shallower structural boundary.
            for following in labels[label_index + 1:]:
                if int(following["depth"]) < int(label["depth"]):
                    break
                if (
                    following.get("role") in roles
                    and int(following["depth"]) <= int(label["depth"])
                ):
                    break
                if (
                    following.get("role") == ancestor_role
                    and int(following["depth"]) <= int(ancestor["depth"])
                ):
                    break
                if following.get("parent") == ancestor.get("key"):
                    following["parent"] = label["key"]
                    label["end_line"] = max(
                        int(label["end_line"]), int(following["end_line"])
                    )


def _split_table_cell_boundaries(
    text: str,
    *,
    raw_line: int,
    raw_column: int,
    table_row: int,
    table_column: int,
    patterns: list[re.Pattern[str]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Split one HTML table cell at adapter-defined questions and roles."""
    starts = {
        match.start()
        for pattern in patterns
        for match in pattern.finditer(text)
        if match.groupdict().get("number") is not None
    }
    # Role syntax remains adapter-owned. Testing suffixes recovers a label
    # appended after a question or image without embedding publisher terms.
    seen_role_kinds: set[str] = set()
    for start in range(len(text)):
        matched_role = match_role(text[start:].strip(), rules)
        if matched_role and matched_role[0]["role"] not in seen_role_kinds:
            starts.add(start)
            seen_role_kinds.add(str(matched_role[0]["role"]))
    starts = sorted(starts)
    if not starts:
        stripped = text.strip()
        if not stripped:
            return []
        offset = text.index(stripped)
        return [
            {
                "text": stripped,
                "raw_line": raw_line,
                "raw_column": raw_column + offset,
                "subline": 0,
                "table_row": table_row,
                "table_column": table_column,
            }
        ]
    if starts[0] > 0 and text[: starts[0]].strip():
        starts.insert(0, 0)
    elif starts[0] > 0:
        starts[0] = 0
    result: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        raw_segment = text[start:end]
        segment = raw_segment.strip()
        if not segment:
            continue
        leading = len(raw_segment) - len(raw_segment.lstrip())
        result.append(
            {
                "text": segment,
                "raw_line": raw_line,
                "raw_column": raw_column + start + leading,
                "subline": 0,
                "table_row": table_row,
                "table_column": table_column,
            }
        )
    return result


def _flatten_question_html_table(
    text: str,
    *,
    raw_line: int,
    patterns: list[re.Pattern[str]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Flatten a multi-column exercise table into semantic reading order."""
    if not HTML_TABLE_LINE_RE.fullmatch(text):
        return None
    streams: dict[int, list[dict[str, Any]]] = {}
    active_rowspans: dict[int, int] = {}
    for row_number, row_match in enumerate(HTML_ROW_RE.finditer(text), 1):
        row_body = row_match.group("body")
        column = 0
        for cell_match in HTML_CELL_RE.finditer(row_body):
            while active_rowspans.get(column, 0) > 0:
                column += 1
            attrs = cell_match.group("attrs")
            rowspan_match = HTML_ROWSPAN_RE.search(attrs)
            colspan_match = HTML_COLSPAN_RE.search(attrs)
            rowspan = int(rowspan_match.group("value")) if rowspan_match else 1
            colspan = int(colspan_match.group("value")) if colspan_match else 1
            cell_column = column
            cell_raw_column = (
                row_match.start("body") + cell_match.start("body") + 1
            )
            streams.setdefault(cell_column, []).extend(
                _split_table_cell_boundaries(
                    cell_match.group("body"),
                    raw_line=raw_line,
                    raw_column=cell_raw_column,
                    table_row=row_number,
                    table_column=cell_column,
                    patterns=patterns,
                    rules=rules,
                )
            )
            if rowspan > 1:
                for occupied_column in range(cell_column, cell_column + colspan):
                    active_rowspans[occupied_column] = max(
                        active_rowspans.get(occupied_column, 0), rowspan
                    )
            column += colspan
        active_rowspans = {
            occupied_column: remaining - 1
            for occupied_column, remaining in active_rowspans.items()
            if remaining - 1 > 0
        }

    if not any(
        match_question(item["text"], patterns)
        for stream in streams.values()
        for item in stream
    ):
        return None

    def is_boundary(item: dict[str, Any]) -> bool:
        return bool(
            match_question(item["text"], patterns)
            or match_role(item["text"], rules)
        )

    def next_question_number(stream: list[dict[str, Any]], cursor: int) -> int:
        for item in stream[cursor:]:
            match = match_question(item["text"], patterns)
            if match and str(match.group("number")).strip().isdecimal():
                return int(str(match.group("number")).strip())
        return 10**18

    cursors = {column: 0 for column in streams}
    ordered: list[dict[str, Any]] = []
    while any(cursors[column] < len(streams[column]) for column in streams):
        available = [
            column
            for column in streams
            if cursors[column] < len(streams[column])
        ]
        selected = min(
            available,
            key=lambda column: (
                next_question_number(streams[column], cursors[column]),
                column,
            ),
        )
        stream = streams[selected]
        cursor = cursors[selected]
        # One unit is optional preamble + one role/question + continuation.
        # Thus an image remains with its question, while a new role is a hard
        # boundary whose priority comes from the next question in its column.
        while cursor < len(stream) and not is_boundary(stream[cursor]):
            ordered.append(stream[cursor])
            cursor += 1
        if cursor < len(stream):
            ordered.append(stream[cursor])
            cursor += 1
        while cursor < len(stream) and not is_boundary(stream[cursor]):
            ordered.append(stream[cursor])
            cursor += 1
        cursors[selected] = cursor

    for subline, item in enumerate(ordered):
        item["subline"] = subline
    return ordered


def split_inline_question_headers(
    raw_lines: list[str],
    patterns: list[re.Pattern[str]],
    rules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rules = rules or []
    virtual: list[dict[str, Any]] = []
    for raw_line, text in enumerate(raw_lines, 1):
        table_items = _flatten_question_html_table(
            text,
            raw_line=raw_line,
            patterns=patterns,
            rules=rules,
        )
        if table_items is not None:
            virtual.extend(table_items)
            continue
        line_items = split_virtual_lines([text], patterns)
        for item in line_items:
            item["raw_line"] = raw_line
        virtual.extend(line_items)
    # MinerU occasionally repeats the same printed question header twice on
    # one OCR line, with the first occurrence containing only a truncated
    # prefix of the second. Keep all source text, but merge the two virtual
    # fragments so one physical top-level question cannot become two leaves.
    merged: list[dict[str, Any]] = []
    for item in virtual:
        current = match_question(item["text"], patterns)
        previous = match_question(merged[-1]["text"], patterns) if merged else None
        if (
            previous
            and current
            and merged[-1]["raw_line"] == item["raw_line"]
            and previous.group("number") == current.group("number")
        ):
            merged[-1]["text"] = merged[-1]["text"].rstrip() + " " + item["text"].lstrip()
            continue
        merged.append(item)
    return merged


def apply_reviewed_virtual_span_relocations(
    virtual_lines: list[dict[str, Any]],
    raw_lines: list[str],
    note_key: str,
    adapter: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply source-anchored semantic reordering for OCR column spillovers."""
    result = list(virtual_lines)
    for item in adapter.get("content", {}).get("virtual_span_relocations", []):
        if str(item.get("context")) != str(note_key):
            continue
        if item.get("reviewer_confirmed") is not True:
            raise ConfigurationError("Virtual span relocation must be reviewer_confirmed")
        start_line = int(item["start_line"])
        end_before_line = int(item["end_before_line"])
        before_line = int(item["before_line"])
        for line_number, anchor_key, pattern_key in (
            (start_line, "anchor_text", "anchor_pattern"),
            (end_before_line, "end_anchor_text", "end_anchor_pattern"),
            (before_line, "before_anchor_text", "before_anchor_pattern"),
        ):
            if line_number < 1 or line_number > len(raw_lines):
                raise ConfigurationError("Virtual span relocation is outside its hierarchy note")
            anchor_text = str(item.get(anchor_key, "")).strip()
            if anchor_text and raw_lines[line_number - 1].strip() != anchor_text:
                raise ConfigurationError(f"Virtual span relocation {anchor_key} drifted")
            anchor_pattern = item.get(pattern_key)
            if anchor_pattern and not re.search(str(anchor_pattern), raw_lines[line_number - 1]):
                raise ConfigurationError(f"Virtual span relocation {pattern_key} drifted")

        coordinates = {
            "start": (start_line, int(item.get("start_column", 1))),
            "end": (end_before_line, int(item.get("end_before_column", 1))),
            "before": (before_line, int(item.get("before_column", 1))),
        }

        def locate(coordinate: tuple[int, int]) -> int:
            matches = [
                index
                for index, line in enumerate(result)
                if (int(line["raw_line"]), int(line["raw_column"])) == coordinate
            ]
            if len(matches) != 1:
                raise ConfigurationError(
                    f"Virtual span relocation coordinate must resolve once: {coordinate}"
                )
            return matches[0]

        start_index = locate(coordinates["start"])
        end_index = locate(coordinates["end"])
        before_index = locate(coordinates["before"])
        if start_index >= end_index or start_index <= before_index < end_index:
            raise ConfigurationError("Virtual span relocation boundaries are invalid")
        span = result[start_index:end_index]
        del result[start_index:end_index]
        if before_index > start_index:
            before_index -= end_index - start_index
        result[before_index:before_index] = span
    return result


def apply_reviewed_recovered_questions(
    virtual_lines: list[dict[str, Any]],
    raw_lines: list[str],
    note_key: str,
    adapter: dict[str, Any],
    patterns: list[re.Pattern[str]],
) -> list[dict[str, Any]]:
    """Insert reviewer-transcribed PDF questions omitted from raw Markdown."""
    result = list(virtual_lines)
    recoveries = [
        item
        for item in adapter.get("content", {}).get("recovered_questions", [])
        if str(item.get("context")) == str(note_key)
    ]
    for ordinal, item in enumerate(recoveries, 1):
        if item.get("reviewer_confirmed") is not True:
            raise ConfigurationError("Recovered question must be reviewer_confirmed")
        after_line = int(item["after_line"])
        if after_line < 1 or after_line > len(raw_lines):
            raise ConfigurationError("Recovered question anchor is outside its hierarchy note")
        anchor_text = str(item.get("anchor_text", "")).strip()
        if anchor_text and raw_lines[after_line - 1].strip() != anchor_text:
            raise ConfigurationError("Recovered question anchor_text drifted")
        anchor_pattern = item.get("anchor_pattern")
        if anchor_pattern and not re.search(str(anchor_pattern), raw_lines[after_line - 1]):
            raise ConfigurationError("Recovered question anchor_pattern drifted")
        body = str(item["body"]).strip()
        match = match_question(body, patterns)
        if match is None or str(match.group("number")).strip() != str(item["number"]).strip():
            raise ConfigurationError("Recovered question body must start with its reviewed number")
        insertion = max(
            (
                index + 1
                for index, line in enumerate(result)
                if int(line["raw_line"]) <= after_line
            ),
            default=0,
        )
        raw_column = max(
            (
                int(line["raw_column"])
                for line in result
                if int(line["raw_line"]) == after_line
            ),
            default=1,
        ) + ordinal
        result.insert(
            insertion,
            {
                "text": body,
                "raw_line": after_line,
                "raw_column": raw_column,
                "subline": ordinal,
                "evidence": {
                    "reviewed_pdf_recovery": str(item.get("source_page", "reviewed")),
                },
                "source_provenance": {
                    "source_page": item.get("source_page"),
                    "bbox": item.get("source_bbox"),
                    "type": "reviewed-recovery",
                    "match": "reviewed-pdf-recovery",
                },
            },
        )
    return result


def plan_note(
    note_entry: dict[str, Any],
    rules: list[dict[str, Any]],
    question_patterns: list[re.Pattern[str]],
    adapter: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    path = Path(note_entry["path"])
    content_source = Path(note_entry.get("content_source") or path)
    raw_lines = content_source.read_text(encoding="utf-8-sig").splitlines()
    virtual_lines = split_inline_question_headers(
        raw_lines,
        compile_inline_question_patterns(adapter, question_patterns),
        rules,
    )
    virtual_lines = apply_reviewed_virtual_span_relocations(
        virtual_lines, raw_lines, str(note_entry["key"]), adapter
    )
    virtual_lines = apply_reviewed_recovered_questions(
        virtual_lines,
        raw_lines,
        str(note_entry["key"]),
        adapter,
        question_patterns,
    )
    lines = [item["text"] for item in virtual_lines]
    number_overrides = {}
    for item in adapter.get("content", {}).get("question_number_overrides", []):
        if str(item.get("context")) != str(note_entry.get("key")):
            continue
        raw_line = int(item["start_line"])
        if raw_line < 1 or raw_line > len(raw_lines):
            raise ConfigurationError("Question number override is outside its hierarchy note")
        anchor_text = str(item.get("anchor_text", "")).strip()
        if anchor_text and raw_lines[raw_line - 1].strip() != anchor_text:
            raise ConfigurationError("Question number override anchor_text drifted")
        anchor_pattern = item.get("anchor_pattern")
        if anchor_pattern and not re.search(str(anchor_pattern), raw_lines[raw_line - 1]):
            raise ConfigurationError("Question number override anchor_pattern drifted")
        number_overrides[(raw_line, int(item.get("raw_column", 1)))] = str(item["number"])
    number_shift_ranges: list[dict[str, Any]] = []
    for item in adapter.get("content", {}).get("question_number_shift_ranges", []):
        if str(item.get("context")) != str(note_entry.get("key")):
            continue
        start_line = int(item["start_line"])
        end_line = int(item["end_line"])
        for line_number, text_key, pattern_key in (
            (start_line, "anchor_text", "anchor_pattern"),
            (end_line, "end_anchor_text", "end_anchor_pattern"),
        ):
            if line_number < 1 or line_number > len(raw_lines):
                raise ConfigurationError("Question number shift range is outside its hierarchy note")
            anchor_text = str(item.get(text_key, "")).strip()
            if anchor_text and raw_lines[line_number - 1].strip() != anchor_text:
                raise ConfigurationError(f"Question number shift range {text_key} drifted")
            anchor_pattern = item.get(pattern_key)
            if anchor_pattern and not re.search(str(anchor_pattern), raw_lines[line_number - 1]):
                raise ConfigurationError(f"Question number shift range {pattern_key} drifted")
        number_shift_ranges.append(item)
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
                    "source_content": str(content_source),
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

    detach_configured_role_roots(labels, adapter)

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
        elif label.get("detached_root_folder"):
            parent_path = path.parent / safe_name(
                str(label["detached_root_folder"]), "content"
            )[:component_limit]
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
    starts: list[tuple[int, re.Match[str], str]] = []
    for index, line in enumerate(lines, 1):
        match = match_question(line, question_patterns)
        if match:
            coordinate = (
                int(virtual_lines[index - 1]["raw_line"]),
                int(virtual_lines[index - 1]["raw_column"]),
            )
            number = number_overrides.get(
                coordinate, str(match.group("number")).strip()
            )
            for shift in number_shift_ranges:
                start_coordinate = (
                    int(shift["start_line"]),
                    int(shift.get("start_column", 1)),
                )
                end_coordinate = (
                    int(shift["end_line"]),
                    int(shift.get("end_column", 2**31 - 1)),
                )
                if start_coordinate <= coordinate <= end_coordinate:
                    if not number.isdecimal():
                        raise ConfigurationError("Question number shift requires a decimal source number")
                    number = str(int(number) + int(shift["offset"]))
                    if int(number) < 1:
                        raise ConfigurationError("Question number shift produced a non-positive number")
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
            scope_owner = None
            for label in labels:
                if label["start_line"] < index <= label["end_line"]:
                    if scope_owner is None or label["depth"] >= scope_owner["depth"]:
                        scope_owner = label
            if not question_in_reviewed_scope(
                str(note_entry["key"]),
                int(virtual_lines[index - 1]["raw_line"]),
                scope_owner,
                labels,
                adapter,
            ):
                adapter.setdefault("_scope_excluded_candidates", []).append(
                    {
                        "context": str(note_entry["key"]),
                        "raw_line": int(virtual_lines[index - 1]["raw_line"]),
                        "raw_column": int(virtual_lines[index - 1]["raw_column"]),
                        "number": number,
                        "text": line,
                    }
                )
                continue
            starts.append((index, match, number))
    label_start_lines = {label["start_line"] for label in labels}
    question_file_template = str(adapter.get("content", {}).get("question_file_template", "{title}.md"))
    for position, (start, match, number) in enumerate(starts):
        end = starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)
        boundary = min((value for value in label_start_lines if start < value <= end), default=None)
        if boundary:
            end = boundary - 1
        embed_boundary = min((value for value in embed_barriers if start < value <= end), default=None)
        if embed_boundary is not None:
            end = embed_boundary - 1
        heading_boundary = min((i for i in range(start + 1, end + 1) if re.match(r"^\s*#{1,6}\s+\S", lines[i - 1])), default=None)
        if heading_boundary is not None:
            end = heading_boundary - 1
        owner = None
        for label in labels:
            if label["start_line"] < start <= label["end_line"]:
                if owner is None or label["depth"] >= owner["depth"]:
                    owner = label
        evidence = {
            key: str(value).strip()
            for key, value in match.groupdict().items()
            if key != "number" and value is not None and str(value).strip()
        }
        evidence.update(virtual_lines[start - 1].get("evidence", {}))
        if number != str(match.group("number")).strip():
            evidence["reviewed_number_override"] = str(match.group("number")).strip()
        label_by_key = {l["key"]: l for l in labels}
        resolved_context = None
        curr_label = owner
        while curr_label:
            if curr_label.get("answer_context"):
                resolved_context = curr_label.get("answer_context")
                break
            curr_label = label_by_key.get(curr_label.get("parent")) if curr_label.get("parent") else None

        context_key = str(
            resolved_context
            or note_entry.get("answer_context", note_entry["key"])
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
        rendered_body = rebase_local_links(body, path, output)
        source_part = next((item for item in reversed(source_parts) if item["line"] <= start), None)
        local_source_line = int(virtual_lines[start - 1]["raw_line"])
        source_line_map = note_entry.get("source_line_map") or []
        source_markdown_line = (
            source_line_map[local_source_line - 1]
            if 1 <= local_source_line <= len(source_line_map)
            else None
        )
        provenance_candidates = []
        virtual_provenance = virtual_lines[start - 1].get("source_provenance")
        if source_markdown_line is not None:
            provenance_candidates = (
                adapter.get("_source_provenance_line_map", {}).get(
                    str(source_markdown_line), []
                )
            )
        if virtual_provenance:
            provenance_candidates = [virtual_provenance]
        questions.append(
            {
                "id": f"{note_entry['key']}:question:{number}:{start}",
                "number": number,
                "evidence": evidence,
                "title": title,
                "source_note_key": note_entry["key"],
                "source_note": str(path),
                "source_content": str(content_source),
                "context_key": context_key,
                "owner": owner["key"] if owner else None,
                "start_line": start,
                "end_line": end,
                "source_start_line": virtual_lines[start - 1]["raw_line"],
                "source_start_column": virtual_lines[start - 1]["raw_column"],
                "source_end_line": virtual_lines[end - 1]["raw_line"],
                "source_markdown_line": source_markdown_line,
                "source_provenance": provenance_candidates[0] if len(provenance_candidates) == 1 else None,
                "source_provenance_candidates": provenance_candidates,
                "output": str(output.resolve()),
                "body_sha256": sha256_text(body),
                # The source digest remains bound to the immutable hierarchy
                # corpus, while the lexical signature reflects the body as it
                # is rendered at its relocated leaf path.  This matters for
                # HTML table cells whose <img src> values are rebased.
                "body_lexical_signature": lexical_signature(rendered_body),
                "source_part": source_part,
            }
        )
    return labels, questions, unknown



DEFAULT_QUESTION_REPO_PATH = (
    Path(os.environ["QUESTION_TYPE_REPOSITORY_ROOT"]).expanduser().resolve()
    if os.environ.get("QUESTION_TYPE_REPOSITORY_ROOT")
    else None
)


@contextmanager
def locked_registry(path: Path):
    """Serialize question-ID reservations across concurrent book builds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def find_next_q_number(vault_root: Path, extra_roots: list[Path] = None) -> int:
    max_num = 0
    search_paths = [vault_root]
    if extra_roots:
        search_paths.extend(extra_roots)

    if (
        DEFAULT_QUESTION_REPO_PATH is not None
        and DEFAULT_QUESTION_REPO_PATH.exists()
        and DEFAULT_QUESTION_REPO_PATH not in search_paths
    ):
        search_paths.append(DEFAULT_QUESTION_REPO_PATH)

    for root in search_paths:
        if root and root.exists():
            for p in root.rglob("Q[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].md"):
                m = re.search(r"Q(\d{8})\.md$", p.name)
                if m:
                    max_num = max(max_num, int(m.group(1)))
    return max_num + 1


def stable_question_identity(profile: dict[str, Any], question: dict[str, Any], occurrence: int) -> str:
    source_hashes = sorted(str(source.get("sha256", "")) for source in profile["sources"])
    graph_relative = (
        Path(profile["paths"]["graph_root"])
        .resolve()
        .relative_to(Path(profile["paths"]["vault_root"]).resolve())
        .as_posix()
    )
    payload = {
        "sources": source_hashes,
        "graph_root": graph_relative,
        "source_note_key": question.get("source_note_key"),
        "context_key": question.get("context_key"),
        "number": question.get("number"),
        "occurrence": occurrence,
        "body_sha256": question.get("body_sha256"),
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def assign_question_codes(
    profile: dict[str, Any],
    adapter: dict[str, Any],
    questions: list[dict[str, Any]],
) -> None:
    """Assign persistent, concurrency-safe Q codes without renumbering unchanged questions."""
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    configured_registry = (
        adapter.get("content", {}).get("question_id_registry")
        or profile.get("paths", {}).get("question_id_registry")
    )
    registry_path = (
        Path(configured_registry).expanduser().resolve()
        if configured_registry
        else vault_root / ".question-type-graph" / "question-id-registry.json"
    )
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")

    occurrence_by_key: dict[tuple[str, str, str], int] = {}
    identities: list[str] = []
    for question in questions:
        occurrence_key = (
            str(question.get("source_note_key")),
            str(question.get("context_key")),
            str(question.get("number")),
        )
        occurrence_by_key[occurrence_key] = occurrence_by_key.get(occurrence_key, 0) + 1
        identities.append(
            stable_question_identity(profile, question, occurrence_by_key[occurrence_key])
        )

    previous_by_identity: dict[str, str] = {}
    previous_manifest = Path(profile["paths"]["staging_root"]) / "question-type-manifest.json"
    if previous_manifest.is_file():
        previous = load_json(previous_manifest)
        previous_occurrences: dict[tuple[str, str, str], int] = {}
        for item in previous.get("questions", []):
            key = (
                str(item.get("source_note_key")),
                str(item.get("context_key")),
                str(item.get("number")),
            )
            previous_occurrences[key] = previous_occurrences.get(key, 0) + 1
            identity = stable_question_identity(profile, item, previous_occurrences[key])
            code = str(item.get("title", ""))
            if re.fullmatch(r"Q\d{8}", code):
                previous_by_identity[identity] = code

    with locked_registry(lock_path):
        if registry_path.is_file():
            registry = load_json(registry_path)
            if registry.get("schema_version") != 1:
                raise ConfigurationError("Unsupported question-ID registry schema")
        else:
            extra_roots = []
            custom_repo = adapter.get("content", {}).get("question_repository_root") or profile.get("paths", {}).get("question_repository_root")
            if custom_repo:
                extra_roots.append(Path(custom_repo).resolve())
            registry = {
                "schema_version": 1,
                "next_number": find_next_q_number(vault_root, extra_roots),
                "assignments": {},
            }
        assignments = registry.setdefault("assignments", {})
        used_codes = set(str(value) for value in assignments.values())
        for identity, code in previous_by_identity.items():
            if identity not in assignments and code not in used_codes:
                assignments[identity] = code
                used_codes.add(code)
        next_number = max(int(registry.get("next_number", 1)), 1)
        for question, identity in zip(questions, identities):
            code = assignments.get(identity)
            if code is None:
                while f"Q{next_number:08d}" in used_codes:
                    next_number += 1
                code = f"Q{next_number:08d}"
                next_number += 1
                assignments[identity] = code
                used_codes.add(code)
            old_path = Path(question["output"])
            question["output"] = str(old_path.parent / f"{code}.md")
            question["title"] = code
            question["stable_identity"] = identity
        registry["next_number"] = next_number
        write_json_atomic(registry_path, registry, overwrite=registry_path.is_file())


def plan_content(profile_path: Path, adapter_path: Path, hierarchy_coverage_path: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    adapter = require_reviewed_adapter(profile, adapter_path)
    coverage = load_json(hierarchy_coverage_path)
    if coverage.get("status") != "passed":
        raise ConfigurationError("Hierarchy coverage must pass before content planning")
    adapter["_graph_root"] = profile["paths"]["graph_root"]
    provenance_path = Path(profile["paths"]["staging_root"]) / "source-provenance-index.json"
    if provenance_path.is_file():
        provenance = load_json(provenance_path)
        source_role = str(coverage.get("source_role") or adapter.get("hierarchy", {}).get("source_role", ""))
        source_provenance = next(
            (
                item
                for item in provenance.get("sources", [])
                if str(item.get("role")) == source_role
            ),
            None,
        )
        if source_provenance:
            adapter["_source_provenance_line_map"] = source_provenance.get("line_map", {})
    rules = compile_role_rules(adapter)
    patterns = compile_question_patterns(adapter)
    labels: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    hierarchy_adapter = adapter.get("hierarchy", {}).get("entries") or []
    context_by_key = {str(item.get("key")): item.get("answer_context", item.get("key")) for item in hierarchy_adapter}
    hierarchy_manifest_path = hierarchy_coverage_path.parent / "hierarchy-manifest.json"
    hierarchy_entries = load_json(hierarchy_manifest_path).get("entries", []) if hierarchy_manifest_path.is_file() else []
    key_order = {entry["key"]: idx for idx, entry in enumerate(hierarchy_entries)}
    sorted_notes = sorted(coverage.get("notes", []), key=lambda n: key_order.get(str(n.get("key")), 9999))

    for note in sorted_notes:
        if note.get("key") == "root" or note.get("structural_only") is True:
            continue
        note = {**note, "answer_context": context_by_key.get(str(note.get("key")), note.get("key"))}
        note_labels, note_questions, note_review = plan_note(note, rules, patterns, adapter)
        labels.extend(note_labels)
        questions.extend(note_questions)
        review.extend(note_review)

    assign_question_codes(profile, adapter, questions)

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
        "scope_excluded_candidates": adapter.get("_scope_excluded_candidates", []),
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
    source_provenance = question.get("source_provenance")
    if source_provenance:
        frontmatter[6:6] = [
            f"source_pdf_page: {json.dumps(source_provenance.get('source_page'), ensure_ascii=False)}",
            f"source_pdf_bbox: {json.dumps(source_provenance.get('bbox'), ensure_ascii=False)}",
            f"source_provenance_match: {json.dumps(source_provenance.get('match'), ensure_ascii=False)}",
            f"source_markdown_line: {json.dumps(question.get('source_markdown_line'), ensure_ascii=False)}",
        ]
    elif source_part:
        page_range = f"{source_part['start_page']}-{source_part['end_page']}"
        frontmatter[6:6] = [
            f"source_pdf_part: {source_part['part']}",
            f"source_page_range: {json.dumps(page_range)}",
        ]
    return "\n".join(frontmatter)


def extract_note_properties(
    lines: list[str], adapter: dict[str, Any]
) -> tuple[list[str], set[int]]:
    """Extract adapter-declared hierarchy-note properties without changing planning lines.

    Property rules are intentionally format-adapter data: publisher labels vary,
    while the compiler only guarantees that matched source lines move verbatim
    into YAML frontmatter and disappear from the rendered note body.
    """
    properties: list[str] = []
    removed_lines: set[int] = set()
    seen_names: set[str] = set()
    for rule in adapter.get("content", {}).get("note_properties", []):
        name = str(rule.get("name", "")).strip()
        pattern = str(rule.get("pattern", ""))
        if not name or not pattern:
            raise ConfigurationError("content.note_properties entries require name and pattern")
        if name in seen_names:
            raise ConfigurationError(f"Duplicate content.note_properties name: {name}")
        seen_names.add(name)
        compiled = re.compile(pattern)
        if "value" not in compiled.groupindex:
            raise ConfigurationError(
                f"content.note_properties pattern for {name} requires a named value group"
            )
        matches: list[tuple[int, str]] = []
        for line_number, line in enumerate(lines, 1):
            match = compiled.match(line)
            if match:
                matches.append((line_number, str(match.group("value")).strip()))
        if len(matches) > 1 and not rule.get("allow_multiple", False):
            raise ConfigurationError(
                f"content.note_properties pattern for {name} matched more than one line"
            )
        if not matches:
            if rule.get("required", False):
                raise ConfigurationError(f"Required note property not found: {name}")
            continue
        values = [value for _, value in matches]
        value: Any = values if len(values) > 1 else values[0]
        properties.append(f"{name}: {json.dumps(value, ensure_ascii=False)}")
        removed_lines.update(line_number for line_number, _ in matches)
    return properties, removed_lines


def prepend_note_properties(body: str, properties: list[str]) -> str:
    if not properties:
        return body
    return "\n".join(["---", *properties, "---", body.lstrip("\n")])


def apply_content(profile_path: Path, adapter_path: Path, manifest_path: Path, overwrite: bool) -> dict[str, Any]:
    profile = load_profile(profile_path)
    adapter = require_reviewed_adapter(profile, adapter_path)
    manifest = load_json(manifest_path)
    if manifest.get("status") != "passed":
        raise ConfigurationError("Content manifest must pass before application")
    functional = manifest.get("functional_nodes", [])
    questions = manifest.get("questions", [])
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    by_source: dict[str, dict[str, Any]] = {}
    for node in functional:
        group = by_source.setdefault(
            node["source_note"],
            {"nodes": [], "questions": [], "source_content": node.get("source_content")},
        )
        group["nodes"].append(node)
    for question in questions:
        group = by_source.setdefault(
            question["source_note"],
            {"nodes": [], "questions": [], "source_content": question.get("source_content")},
        )
        group["questions"].append(question)

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
        source_content = Path(values.get("source_content") or source)
        raw_lines = source_content.read_text(encoding="utf-8-sig").splitlines()
        question_patterns = compile_question_patterns(adapter)
        virtual_lines = split_inline_question_headers(
            raw_lines,
            compile_inline_question_patterns(adapter, question_patterns),
            compile_role_rules(adapter),
        )
        source_note_key = str(next(
            (
                item.get("source_note_key")
                for item in [*values["questions"], *values["nodes"]]
                if item.get("source_note_key")
            ),
            "",
        ))
        virtual_lines = apply_reviewed_virtual_span_relocations(
            virtual_lines,
            raw_lines,
            source_note_key,
            adapter,
        )
        virtual_lines = apply_reviewed_recovered_questions(
            virtual_lines,
            raw_lines,
            source_note_key,
            adapter,
            question_patterns,
        )
        lines = [item["text"] for item in virtual_lines]
        note_properties, property_lines = extract_note_properties(lines, adapter)
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
            elif line in property_lines:
                line += 1
            else:
                rendered.append(lines[line - 1])
                line += 1
        source_text = "\n".join(rendered).rstrip() + "\n"
        source_text = prepend_note_properties(source_text, note_properties)
        write_text_atomic(source, source_text, overwrite=True)

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
    # Reconcile generated question notes left by an older report lineage. A
    # graph root is agent-owned, but deletion is still restricted to files
    # carrying both the generated question frontmatter and source sentinels.
    expected_questions = {
        str(Path(question["output"]).resolve()).casefold()
        for question in questions
    }
    for candidate in graph_root.rglob("Q[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].md"):
        resolved = candidate.resolve()
        if str(resolved).casefold() in expected_questions:
            continue
        candidate_text = candidate.read_text(encoding="utf-8-sig")
        if (
            re.search(r"(?m)^question_id:\s*", candidate_text)
            and "<!-- question-source:start -->" in candidate_text
            and "<!-- question-source:end -->" in candidate_text
        ):
            candidate.unlink()
            removed_stale.append(str(resolved))

    # Reconcile legacy hierarchy/functional notes left behind by historical
    # path-cleanup implementations. These generated notes predate ownership
    # sentinels, so deletion is limited to the agent's self-titled note shape
    # (folder/FOLDER.md) and excludes all Q/A artifacts. Current hierarchy and
    # content manifests remain the source of truth.
    hierarchy_coverage = load_json(Path(manifest["hierarchy_coverage"]))
    expected_non_questions = {
        str(Path(item["path"]).resolve()).casefold()
        for item in hierarchy_coverage.get("notes", [])
        if item.get("path")
    }
    expected_non_questions.update(
        str(Path(item["output"]).resolve()).casefold()
        for item in functional
        if item.get("output")
    )
    for candidate in graph_root.rglob("*.md"):
        resolved = candidate.resolve()
        if str(resolved).casefold() in expected_non_questions:
            continue
        if re.fullmatch(r"Q\d{8}(?:A\d+)?\.md", candidate.name):
            continue
        if candidate.name != f"{candidate.parent.name}.md":
            continue
        candidate.unlink()
        removed_stale.append(str(resolved))

    removed_empty_directories = prune_empty_directories(graph_root)

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
        "removed_empty_directories": removed_empty_directories,
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

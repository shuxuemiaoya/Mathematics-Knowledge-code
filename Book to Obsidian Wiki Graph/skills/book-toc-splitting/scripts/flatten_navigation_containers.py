#!/usr/bin/env python3
"""Flatten reviewed numbered subsection nodes that are navigation-only containers."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


NUMBERED_SUBSECTION_RE = re.compile(r"^\d+(?:\.\d+){2,}\s+\S")
HEADING_RE = re.compile(r"^#{1,6}\s+")
DISPLAY_DELIMITER_RE = re.compile(r"^\$\$\s*$")
EXAMPLE_RE = re.compile(r"^例(?:题)?\s*\d+")
FORMAL_DEFINITION_RE = re.compile(
    r"(?:叫做|称为|定义为|统称为|我们把.+?(?:叫做|称为))"
)
GENERAL_DEFINITION_RE = re.compile(r"^(?:一般地|通常|一般来说)")
FUNCTIONAL_LABELS = {
    "情景引入",
    "情境引入",
    "问题引入",
    "引入",
    "我们知道：",
    "我们知道:",
}
SENTENCE_END = tuple("。！？.!?；;")
QUESTION_END = tuple("？?")
FIGURE_REFERENCE_RE = re.compile(r"(?:图|fig(?:ure)?\.?)\s*[（(]?\d", re.IGNORECASE)
TABLE_REFERENCE_RE = re.compile(r"(?:表|table)\s*[（(]?\d", re.IGNORECASE)
IMAGE_MARKER_RE = re.compile(r"!\[[^\]]*\]\(|<img\b", re.IGNORECASE)
TABLE_MARKER_RE = re.compile(r"<table\b|^\s*\|.+\|\s*$", re.IGNORECASE)
MEDIA_CAPTION_RE = re.compile(r"^(?:图|表)\s*\d", re.IGNORECASE)
SUBFIGURE_LABEL_RE = re.compile(r"^[（(]\s*\d+\s*[）)]$")
FUNCTIONAL_STANDALONE_RE = re.compile(r"^(?:分析|解|证明)\s*[:：]?$")
NON_CONTEXT_BOUNDARY_RE = re.compile(
    r"^(?:"
    r"练习|习题|复习巩固|综合运用|拓广探索|"
    r"例\s*\d+|例题\s*\d*"
    r")(?:\s|$)"
)
MAX_PARENT_PREVIEW_CHARACTERS = 180


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def substantive(lines: list[str], start: int, end: int) -> list[str]:
    result: list[str] = []
    for line_number in range(start, end + 1):
        text = lines[line_number - 1].strip()
        if (
            not text
            or HEADING_RE.match(text)
            or DISPLAY_DELIMITER_RE.match(text)
            or text in FUNCTIONAL_LABELS
        ):
            continue
        result.append(text)
    return result


def meaningful_preview(lines: list[str], start: int, end: int) -> bool:
    content = [
        text
        for text in substantive(lines, start, end)
        if not IMAGE_MARKER_RE.search(text)
        and not TABLE_MARKER_RE.search(text)
        and not MEDIA_CAPTION_RE.match(text)
        and not SUBFIGURE_LABEL_RE.match(text)
        and not FUNCTIONAL_STANDALONE_RE.match(text)
    ]
    if not content:
        return False
    text = " ".join(content)
    return len(text) >= 12 and text.endswith(SENTENCE_END)


def extend_to_attached_media(
    lines: list[str], start: int, preview_end: int, child_end: int
) -> int:
    preview_text = "\n".join(lines[start - 1 : preview_end])
    needs_figure = bool(FIGURE_REFERENCE_RE.search(preview_text))
    needs_table = bool(TABLE_REFERENCE_RE.search(preview_text))
    if not needs_figure and not needs_table:
        return preview_end
    required_captions = {
        f"图{value}"
        for value in re.findall(
            r"图\s*([0-9]+(?:\.[0-9]+)*(?:-[0-9]+)?)", preview_text
        )
    }
    required_captions.update(
        f"表{value}"
        for value in re.findall(
            r"表\s*([0-9]+(?:\.[0-9]+)*(?:-[0-9]+)?)", preview_text
        )
    )
    lookahead_end = min(child_end, preview_end + 32)
    marker_line: int | None = None
    for line_number in range(preview_end + 1, lookahead_end + 1):
        text = lines[line_number - 1]
        if (
            needs_figure
            and IMAGE_MARKER_RE.search(text)
            or needs_table
            and TABLE_MARKER_RE.search(text)
        ):
            marker_line = line_number
            break
    if marker_line is None:
        return preview_end
    extended = marker_line
    found_captions: set[str] = set()
    last_caption = marker_line
    for line_number in range(marker_line + 1, lookahead_end + 1):
        text = lines[line_number - 1].strip()
        extended = line_number
        if HEADING_RE.match(text):
            return line_number - 1
        compact = re.sub(r"\s+", "", text)
        matched = {
            caption
            for caption in required_captions
            if compact.startswith(caption)
        }
        if matched:
            found_captions.update(matched)
            last_caption = line_number
            if found_captions == required_captions:
                return line_number
        elif not required_captions and MEDIA_CAPTION_RE.match(text):
            return line_number
    return last_caption


def gap_supplies_link_context(
    lines: list[str], start: int, end: int
) -> bool:
    """Return true only when a retained gap can introduce the next topic."""
    if not meaningful_preview(lines, start, end):
        return False
    for line_number in range(start, end + 1):
        text = lines[line_number - 1].strip()
        if not text:
            continue
        heading = HEADING_RE.sub("", text).strip()
        if NON_CONTEXT_BOUNDARY_RE.match(heading):
            return False
        break
    return True


def preview_structurally_complete(
    lines: list[str], start: int, end: int
) -> bool:
    text = "\n".join(lines[start - 1 : end])
    return (
        text.count("$$") % 2 == 0
        and text.lower().count("<table") == text.lower().count("</table>")
        and text.count("```") % 2 == 0
    )


def classify_preview(
    lines: list[str], start: int, end: int
) -> tuple[str, str]:
    text = " ".join(substantive(lines, start, end))
    if EXAMPLE_RE.match(text):
        return "worked-example", "原文例题"
    if FORMAL_DEFINITION_RE.search(text):
        return "exposition", "原文讲解"
    if text.endswith(QUESTION_END):
        return "question", "原文问题"
    return "context", "原文段落"


def extend_to_nearby_general_definition(
    lines: list[str],
    start: int,
    preview_end: int,
    child_end: int,
) -> int:
    """Keep a nearby general definition after concrete introductory cases."""
    first = " ".join(substantive(lines, start, preview_end))
    if GENERAL_DEFINITION_RE.match(first):
        return preview_end
    nonblank = sum(
        bool(lines[index - 1].strip())
        for index in range(start, preview_end + 1)
    )
    candidate_end = preview_end
    found_general = False
    for line_number in range(preview_end + 1, child_end + 1):
        text = lines[line_number - 1].strip()
        if HEADING_RE.match(text):
            break
        if text:
            nonblank += 1
        if GENERAL_DEFINITION_RE.match(text):
            found_general = True
        candidate_end = line_number
        if (
            found_general
            and meaningful_preview(lines, start, candidate_end)
            and preview_structurally_complete(lines, start, candidate_end)
        ):
            return candidate_end
        if nonblank >= 8:
            break
    return preview_end


def derive_preview(
    lines: list[str],
    child: dict[str, Any],
) -> dict[str, Any] | None:
    start = int(child["start_line"])
    end = int(child["end_line"])
    cursor = start
    while cursor <= end:
        text = lines[cursor - 1].strip()
        if text and not HEADING_RE.match(text) and text not in FUNCTIONAL_LABELS:
            break
        cursor += 1
    if cursor > end:
        raise ValueError(f"cannot derive parent preview for {child['title']}")

    candidate_line: int | None = None
    for line_number in range(cursor, end + 1):
        text = lines[line_number - 1].strip()
        if (
            12 <= len(text) <= MAX_PARENT_PREVIEW_CHARACTERS
            and text.endswith(QUESTION_END)
            and not HEADING_RE.match(text)
            and not IMAGE_MARKER_RE.search(text)
            and not TABLE_MARKER_RE.search(text)
            and not FIGURE_REFERENCE_RE.search(text)
            and not TABLE_REFERENCE_RE.search(text)
        ):
            candidate_line = line_number
            break
    if candidate_line is None:
        first = lines[cursor - 1].strip()
        if (
            12 <= len(first) <= MAX_PARENT_PREVIEW_CHARACTERS
            and first.endswith(SENTENCE_END)
            and not FORMAL_DEFINITION_RE.search(first)
            and not FIGURE_REFERENCE_RE.search(first)
            and not TABLE_REFERENCE_RE.search(first)
        ):
            candidate_line = cursor
    if candidate_line is None:
        return None
    cursor = candidate_line
    preview_end = candidate_line
    role, title = classify_preview(lines, cursor, preview_end)
    return {
        "start_line": cursor,
        "end_line": preview_end,
        "role": role,
        "title": title,
        "reason": (
            "Reviewer retained one concise source-derived question or idea "
            "before the promoted knowledge-topic link."
        ),
    }


def residual_nonblank(
    lines: list[str],
    container: dict[str, Any],
    children: list[dict[str, Any]],
) -> int:
    covered: set[int] = set()
    for child in children:
        covered.update(
            range(int(child["start_line"]), int(child["end_line"]) + 1)
        )
    return sum(
        bool(lines[line_number - 1].strip())
        for line_number in range(
            int(container["start_line"]) + 1,
            int(container["end_line"]) + 1,
        )
        if line_number not in covered
    )


def flatten(
    payload: dict[str, Any],
    lines: list[str],
    *,
    maximum_residual_nonblank: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("split manifest nodes must be an array")
    by_key = {str(node["key"]): node for node in nodes}
    reviews = payload.get("semantic_review", {})
    headings = reviews.get("headings", [])
    sections = reviews.get("sections", [])
    heading_by_line = {int(item["line"]): item for item in headings}
    flattened: list[dict[str, Any]] = []
    remove_keys: set[str] = set()

    for container in sorted(
        nodes, key=lambda item: int(item.get("start_line", 0)), reverse=True
    ):
        title = str(container.get("title", "")).strip()
        if (
            container.get("toc_key") is not None
            or container.get("category") != "knowledge"
            or not NUMBERED_SUBSECTION_RE.match(title)
        ):
            continue
        children = sorted(
            (
                node
                for node in nodes
                if node.get("parent_key") == container["key"]
                and node.get("category") == "knowledge"
            ),
            key=lambda item: int(item["start_line"]),
        )
        if not children:
            continue
        if residual_nonblank(lines, container, children) > maximum_residual_nonblank:
            continue

        parent_key = container.get("parent_key")
        if not isinstance(parent_key, str) or parent_key not in by_key:
            raise ValueError(f"container has no valid parent: {container['key']}")
        cursor = int(container["start_line"]) + 1
        for child in children:
            child_start = int(child["start_line"])
            if not gap_supplies_link_context(
                lines, cursor, child_start - 1
            ):
                preview = derive_preview(lines, child)
                if preview is not None:
                    child["parent_preview"] = preview
                else:
                    child.pop("parent_preview", None)
            child["parent_key"] = parent_key
            cursor = int(child["end_line"]) + 1

        heading_review = heading_by_line.get(int(container["start_line"]))
        if heading_review is None:
            raise ValueError(
                f"container heading lacks semantic review: {container['title']}"
            )
        heading_review.clear()
        heading_review.update(
            {
                "line": int(container["start_line"]),
                "title": title,
                "decision": "retain",
                "reason": (
                    "This numbered subsection is a structural navigation "
                    "container; its independently reusable child topics are "
                    "promoted to the lesson entry."
                ),
                "structural_container": True,
                "promote_to_h3": True,
                "child_node_keys": [child["key"] for child in children],
                "confidence": 0.98,
            }
        )
        remove_keys.add(str(container["key"]))
        flattened.append(
            {
                "container": container["key"],
                "title": title,
                "parent": parent_key,
                "promoted_children": [child["key"] for child in children],
            }
        )

    reviews["sections"] = [
        item for item in sections if item.get("node_key") not in remove_keys
    ]
    for section in reviews["sections"]:
        child_keys = section.get("child_node_keys")
        if not isinstance(child_keys, list):
            continue
        expanded: list[str] = []
        for child_key in child_keys:
            match = next(
                (
                    item
                    for item in flattened
                    if item["container"] == child_key
                ),
                None,
            )
            if match is None:
                expanded.append(child_key)
            else:
                expanded.extend(match["promoted_children"])
        section["child_node_keys"] = expanded
    payload["nodes"] = [
        node for node in nodes if str(node["key"]) not in remove_keys
    ]
    current_nodes = payload["nodes"]
    for parent in current_nodes:
        if parent.get("category") != "knowledge":
            continue
        children = sorted(
            (
                node
                for node in current_nodes
                if node.get("parent_key") == parent.get("key")
                and node.get("category") == "knowledge"
            ),
            key=lambda item: int(item["start_line"]),
        )
        cursor = int(parent["start_line"]) + 1
        for child in children:
            child_start = int(child["start_line"])
            preview = derive_preview(lines, child)
            if preview is None:
                child.pop("parent_preview", None)
            else:
                child["parent_preview"] = preview
            cursor = int(child["end_line"]) + 1
    # Parent previews are teaching-path affordances for knowledge nodes only.
    # Auxiliary material is already identified by its category and source
    # title; duplicating its opening body before the link adds unrelated prose
    # to the lesson entry.
    for node in current_nodes:
        if node.get("category") != "knowledge":
            node.pop("parent_preview", None)
    payload["navigation_container_review"] = {
        "status": "passed",
        "flattened": flattened,
    }
    return payload, flattened


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--maximum-residual-nonblank", type=int, default=8)
    parser.add_argument("--reviewer-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.reviewer_confirmed:
        parser.error("--reviewer-confirmed is required")
    if args.manifest.exists() and not args.overwrite:
        parser.error("--overwrite is required for an existing manifest")

    lines = args.formatted_markdown.read_text(
        encoding="utf-8-sig"
    ).splitlines()
    payload = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    payload, flattened = flatten(
        payload,
        lines,
        maximum_residual_nonblank=args.maximum_residual_nonblank,
    )
    atomic_write(args.manifest.resolve(), payload)
    print(
        json.dumps(
            {
                "status": "passed",
                "flattened_containers": len(flattened),
                "promoted_topics": sum(
                    len(item["promoted_children"]) for item in flattened
                ),
                "manifest": str(args.manifest.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

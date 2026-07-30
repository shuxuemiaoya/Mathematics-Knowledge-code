#!/usr/bin/env python3
"""Split formatted book Markdown with a reviewed TOC-based split manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from lesson_flow_manifest import functional_boundary
from lesson_flow_manifest import validate as validate_lesson_flow


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_IMAGE_RE = re.compile(r"""<img\b[^>]*\bsrc=["']([^"']+)["']""", re.I)
EXTERNAL_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*]')
CONTENT_HEADING_RE = re.compile(r"^(#{4,6})\s+(.+?)\s*$")
ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_SUBSECTION_RE = re.compile(r"^\d+(?:\.\d+){2,}\s+\S")
SECTION_EXERCISE_RE = re.compile(r"^习题\s*\d+(?:\.\d+)+(?:\s|$)")
TEXTBOOK_CORE_ROLES = {"knowledge", "concept", "exercise"}
TEXTBOOK_AUXILIARY_ROLES = {"reading", "history", "method", "tool"}
DEFAULT_CONTENT_REVIEW_MIN_LINES = 24


class SplitError(ValueError):
    pass


@dataclass(frozen=True)
class SplitNode:
    key: str
    title: str
    parent_key: str | None
    category: str
    filename: str
    start_line: int
    end_line: int
    toc_key: str | None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_filename(filename: str) -> str:
    cleaned = INVALID_FILENAME_RE.sub("_", filename).strip().rstrip(".")
    if not cleaned:
        raise SplitError("Split filename cannot be empty")
    if not cleaned.lower().endswith(".md"):
        cleaned += ".md"
    return cleaned


def category_map(profile: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in profile.get("categories", []):
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue
        role = item.get("role")
        directory = item.get("directory")
        if isinstance(role, str) and role and isinstance(directory, str) and directory:
            result[role] = directory
    return result


def load_nodes(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    line_count: int,
    toc_keys: set[str],
) -> tuple[dict[str, SplitNode], SplitNode]:
    raw_nodes = manifest.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise SplitError("Split manifest needs a non-empty nodes array")
    categories = category_map(profile)
    book_kind = str(profile.get("book", {}).get("kind", "")).casefold()
    allowed = set(categories)
    if "textbook" in book_kind:
        missing_core = TEXTBOOK_CORE_ROLES - set(categories)
        unsupported = set(categories) - (
            TEXTBOOK_CORE_ROLES | TEXTBOOK_AUXILIARY_ROLES
        )
        if missing_core:
            raise SplitError(
                "Textbook profiles must enable knowledge, concept, and exercise"
            )
        if unsupported:
            raise SplitError(
                "Textbook profile has unsupported categories: "
                + ", ".join(sorted(unsupported))
            )

    nodes: dict[str, SplitNode] = {}
    target_keys: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise SplitError(f"Split node {index} must be an object")
        key = raw.get("key")
        title = raw.get("title")
        parent_key = raw.get("parent_key")
        category = raw.get("category")
        start = raw.get("start_line")
        end = raw.get("end_line")
        toc_key = raw.get("toc_key")
        if not isinstance(key, str) or not key:
            raise SplitError(f"Split node {index} needs a key")
        if key in nodes:
            raise SplitError(f"Duplicate split key: {key}")
        if not isinstance(title, str) or not title.strip():
            raise SplitError(f"Split node {key!r} needs a title")
        if parent_key is not None and not isinstance(parent_key, str):
            raise SplitError(f"Split node {key!r} parent_key must be a string")
        if category != "root" and category not in allowed:
            raise SplitError(
                f"Split node {key!r} uses disabled or unsupported category {category!r}"
            )
        if not isinstance(start, int) or not isinstance(end, int):
            raise SplitError(f"Split node {key!r} needs integer line bounds")
        if start < 1 or end < start or end > line_count:
            raise SplitError(f"Split node {key!r} has invalid line bounds")
        filename = clean_filename(str(raw.get("filename") or f"{title}.md"))
        target_key = (str(category), filename.casefold())
        if target_key in target_keys:
            raise SplitError(f"Duplicate split target: {category}/{filename}")
        target_keys.add(target_key)
        if toc_key is not None and toc_key not in toc_keys:
            raise SplitError(f"Split node {key!r} has unknown toc_key {toc_key!r}")
        nodes[key] = SplitNode(
            key=key,
            title=title.strip(),
            parent_key=parent_key,
            category=str(category),
            filename=filename,
            start_line=start,
            end_line=end,
            toc_key=toc_key,
        )

    roots = [node for node in nodes.values() if node.parent_key is None]
    if len(roots) != 1 or roots[0].category != "root":
        raise SplitError("Split manifest needs exactly one root-category node")
    root = roots[0]

    children: dict[str, list[SplitNode]] = {key: [] for key in nodes}
    for node in nodes.values():
        if node.parent_key is None:
            continue
        parent = nodes.get(node.parent_key)
        if parent is None:
            raise SplitError(f"Split node {node.key!r} has a missing parent")
        if node.start_line < parent.start_line or node.end_line > parent.end_line:
            raise SplitError(f"Split node {node.key!r} lies outside its parent")
        if (
            node.start_line == parent.start_line
            and node.end_line == parent.end_line
            and parent.category != "root"
        ):
            raise SplitError(f"Split node {node.key!r} duplicates its parent range")
        children[parent.key].append(node)

    for parent_key, siblings in children.items():
        ordered = sorted(siblings, key=lambda item: (item.start_line, item.end_line))
        for previous, current in zip(ordered, ordered[1:]):
            if current.start_line <= previous.end_line:
                raise SplitError(
                    f"Sibling ranges overlap under {parent_key!r}: "
                    f"{previous.key!r} and {current.key!r}"
                )

    used_toc_keys = [node.toc_key for node in nodes.values() if node.toc_key]
    if len(used_toc_keys) != len(set(used_toc_keys)):
        raise SplitError("A TOC key is assigned to more than one split node")
    missing_toc = sorted(toc_keys - set(used_toc_keys))
    if missing_toc:
        raise SplitError("Split manifest omits TOC keys: " + ", ".join(missing_toc))
    return nodes, root


def target_path(
    node: SplitNode,
    output_root: Path,
    categories: dict[str, str],
) -> Path:
    if node.category == "root":
        return output_root / node.filename
    return output_root / categories[node.category] / node.filename


def encode_path(path: str, encode_spaces: bool) -> str:
    normalized = path.replace("\\", "/")
    return normalized.replace(" ", "%20") if encode_spaces else normalized


def note_link(
    child: SplitNode,
    parent: SplitNode,
    output_root: Path,
    vault_root: Path,
    categories: dict[str, str],
    links: dict[str, Any],
) -> str:
    child_target = target_path(child, output_root, categories)
    parent_target = target_path(parent, output_root, categories)
    if links.get("note_mode") == "vault-root":
        try:
            href = child_target.relative_to(vault_root).as_posix()
        except ValueError as exc:
            raise SplitError("Split target lies outside the configured vault") from exc
        href = "/" + href
    else:
        href = os.path.relpath(child_target, parent_target.parent).replace("\\", "/")
    href = encode_path(href, bool(links.get("encode_spaces", False)))
    return f"- [{child.title}]({href})"


def normalize_entry_heading(text: str, node: SplitNode, book_title: str) -> str:
    """Give every generated note one valid H1-H3 entry heading.

    TOC formatting intentionally demotes non-TOC headings to H4-H6. Once a
    reviewed range becomes an independent note, its entry heading is promoted
    to H3, matching the textbook example's chapter/lesson/subsection grammar.
    """

    if node.parent_key is None:
        expected = f"# {book_title}".strip()
        if not text.startswith(expected):
            return expected + ("\n\n" + text if text else "")
        return text

    lines = text.splitlines()
    first_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_index is None:
        raise SplitError(f"Rendered note {node.key!r} is empty")
    match = ANY_HEADING_RE.match(lines[first_index])
    if match is None:
        if node.toc_key is None:
            return f"### {node.title}\n\n{text}"
        raise SplitError(
            f"Rendered note {node.key!r} must begin with an H1-H3 heading"
        )
    level = len(match.group(1))
    if level >= 4:
        lines[first_index] = f"### {node.title}"
    elif match.group(2).strip() != node.title:
        lines[first_index] = f"{'#' * level} {node.title}"
    return "\n".join(lines)


def line_exclusions(toc_manifest: dict[str, Any]) -> set[int]:
    excluded: set[int] = set()
    for item in toc_manifest.get("toc_source_ranges", []):
        if isinstance(item, dict):
            start = item.get("start_line")
            end = item.get("end_line")
            if isinstance(start, int) and isinstance(end, int):
                excluded.update(range(start, end + 1))
    return excluded


def validate_semantic_review(
    manifest: dict[str, Any],
    nodes: dict[str, SplitNode],
    lines: list[str],
    excluded: set[int],
    profile: dict[str, Any],
) -> None:
    """Require an explicit disposition for every demoted content heading.

    TOC formatting deliberately pushes all non-TOC headings below H3.  A
    heading-only split can therefore satisfy TOC coverage while still leaving
    an entire lesson, its numbered subsections, and its section exercise in one
    oversized note.  The review ledger makes the semantic-boundary decision
    auditable and lets the splitter enforce textbook boundaries that are not
    optional.
    """

    book_kind = str(profile.get("book", {}).get("kind", "")).casefold()
    if "textbook" not in book_kind:
        return
    decomposition = profile.get("decomposition", {})
    if not isinstance(decomposition, dict):
        raise SplitError("Profile decomposition must be an object")
    if decomposition.get("non_toc_split_default", "retain") != "retain":
        raise SplitError("Textbook non-TOC split default must be retain")
    confidence_threshold = decomposition.get(
        "semantic_split_confidence_threshold", 0.9
    )
    if (
        isinstance(confidence_threshold, bool)
        or not isinstance(confidence_threshold, (int, float))
        or not 0 <= confidence_threshold <= 1
    ):
        raise SplitError(
            "semantic_split_confidence_threshold must be between 0 and 1"
        )

    candidates: dict[int, str] = {}
    for line_number, line in enumerate(lines, start=1):
        if line_number in excluded:
            continue
        match = CONTENT_HEADING_RE.match(line)
        if match:
            candidates[line_number] = match.group(2).strip()

    review = manifest.get("semantic_review")
    raw_headings = review.get("headings") if isinstance(review, dict) else None
    if not isinstance(raw_headings, list):
        raise SplitError(
            "Textbook split manifest needs semantic_review.headings for every H4-H6 content heading"
        )

    reviewed: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(raw_headings):
        if not isinstance(item, dict):
            raise SplitError(f"semantic_review heading {index} must be an object")
        line_number = item.get("line")
        title = item.get("title")
        decision = item.get("decision")
        confidence = item.get("confidence")
        if not isinstance(line_number, int) or line_number not in candidates:
            raise SplitError(
                f"semantic_review heading {index} references no H4-H6 content heading"
            )
        if line_number in reviewed:
            raise SplitError(
                f"semantic_review duplicates heading at line {line_number}"
            )
        if title != candidates[line_number]:
            raise SplitError(
                f"semantic_review title mismatch at line {line_number}: "
                f"expected {candidates[line_number]!r}"
            )
        if decision not in {"split", "retain"}:
            raise SplitError(
                f"semantic_review heading at line {line_number} needs decision split or retain"
            )
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise SplitError(
                f"semantic_review heading at line {line_number} needs confidence between 0 and 1"
            )
        if confidence < confidence_threshold and item.get("reviewed") is not True:
            raise SplitError(
                f"Low-confidence semantic heading {title!r} at line {line_number} "
                "must be routed through review and marked reviewed"
            )
        reviewed[line_number] = item

    missing = sorted(set(candidates) - set(reviewed))
    if missing:
        samples = ", ".join(
            f"{line}:{candidates[line]}" for line in missing[:12]
        )
        raise SplitError(
            f"semantic_review omits {len(missing)} H4-H6 content headings: {samples}"
        )

    for line_number, title in candidates.items():
        item = reviewed[line_number]
        decision = item["decision"]
        must_split_category: str | None = None
        if SECTION_EXERCISE_RE.match(title):
            must_split_category = "exercise"
        elif NUMBERED_SUBSECTION_RE.match(title):
            must_split_category = "knowledge"

        if must_split_category and decision != "split":
            raise SplitError(
                f"Textbook heading {title!r} at line {line_number} must be split as {must_split_category}"
            )

        if decision == "retain":
            if not str(item.get("reason", "")).strip():
                raise SplitError(
                    f"Retained semantic heading {title!r} at line {line_number} needs a reason"
                )
            continue

        if must_split_category is None:
            if not str(item.get("reason", "")).strip():
                raise SplitError(
                    f"Non-TOC split heading {title!r} at line {line_number} "
                    "needs a specific independence reason"
                )
            if item.get("independent_teaching_arc") is not True:
                raise SplitError(
                    f"Non-TOC split heading {title!r} at line {line_number} "
                    "must explicitly confirm independent_teaching_arc"
                )

        node_key = item.get("node_key")
        node = nodes.get(node_key) if isinstance(node_key, str) else None
        if node is None:
            raise SplitError(
                f"Split semantic heading {title!r} at line {line_number} needs a valid node_key"
            )
        if node.start_line != line_number:
            raise SplitError(
                f"Semantic node {node.key!r} must start at reviewed heading line {line_number}"
            )
        if must_split_category and node.category != must_split_category:
            raise SplitError(
                f"Semantic node {node.key!r} must use category {must_split_category!r}"
            )

    minimum_lines = decomposition.get(
        "content_review_min_nonblank_lines",
        DEFAULT_CONTENT_REVIEW_MIN_LINES,
    )
    if (
        isinstance(minimum_lines, bool)
        or not isinstance(minimum_lines, int)
        or minimum_lines < 1
    ):
        raise SplitError(
            "content_review_min_nonblank_lines must be a positive integer"
        )

    section_candidates: dict[str, SplitNode] = {}
    for node in nodes.values():
        if node.category != "knowledge":
            continue
        source_heading = ANY_HEADING_RE.match(lines[node.start_line - 1])
        if source_heading is None:
            continue
        heading_level = len(source_heading.group(1))
        if node.toc_key is not None and heading_level not in {2, 3}:
            continue
        if node.toc_key is None and heading_level not in {4, 5, 6}:
            continue
        nonblank = sum(
            1
            for line in lines[node.start_line - 1 : node.end_line]
            if line.strip()
        )
        if nonblank >= minimum_lines:
            section_candidates[node.key] = node

    raw_sections = review.get("sections")
    if section_candidates and not isinstance(raw_sections, list):
        raise SplitError(
            "Textbook split manifest needs semantic_review.sections for "
            "content-level review of long teaching nodes"
        )
    if raw_sections is None:
        raw_sections = []
    if not isinstance(raw_sections, list):
        raise SplitError("semantic_review.sections must be an array")

    reviewed_sections: set[str] = set()
    for index, item in enumerate(raw_sections):
        if not isinstance(item, dict):
            raise SplitError(f"semantic_review section {index} must be an object")
        node_key = item.get("node_key")
        node = section_candidates.get(node_key) if isinstance(node_key, str) else None
        if node is None:
            raise SplitError(
                f"semantic_review section {index} references no reviewable teaching node"
            )
        if node_key in reviewed_sections:
            raise SplitError(f"semantic_review duplicates section {node_key!r}")
        if (
            item.get("title") != node.title
            or item.get("start_line") != node.start_line
            or item.get("end_line") != node.end_line
        ):
            raise SplitError(
                f"semantic_review section {node_key!r} does not match its node"
            )
        decision = item.get("decision")
        if decision not in {"split", "retain"}:
            raise SplitError(
                f"Content section {node.title!r} needs a reviewed split or retain decision"
            )
        confidence = item.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise SplitError(
                f"Content section {node.title!r} needs confidence between 0 and 1"
            )
        if confidence < confidence_threshold and item.get("reviewed") is not True:
            raise SplitError(
                f"Low-confidence content section {node.title!r} must be routed "
                "through review and marked reviewed"
            )
        if item.get("reviewed_entire_section") is not True:
            raise SplitError(
                f"Content section {node.title!r} must confirm reviewed_entire_section"
            )
        if not str(item.get("reason", "")).strip():
            raise SplitError(
                f"Content section {node.title!r} needs a specific decision reason"
            )
        direct_children = {
            child.key
            for child in nodes.values()
            if child.parent_key == node.key
        }
        if decision == "split":
            child_keys = item.get("child_node_keys")
            if not isinstance(child_keys, list) or not child_keys:
                raise SplitError(
                    f"Split content section {node.title!r} needs child_node_keys"
                )
            if set(child_keys) - direct_children:
                raise SplitError(
                    f"Content section {node.title!r} names children that are not "
                    "direct split nodes"
                )
        elif direct_children:
            raise SplitError(
                f"Retained content section {node.title!r} already has direct child nodes"
            )
        reviewed_sections.add(node_key)

    missing_sections = sorted(set(section_candidates) - reviewed_sections)
    if missing_sections:
        samples = ", ".join(
            section_candidates[key].title for key in missing_sections[:12]
        )
        raise SplitError(
            f"semantic_review.sections omits {len(missing_sections)} long "
            f"teaching sections: {samples}"
        )

    heading_split_nodes = {
        str(item.get("node_key"))
        for item in raw_headings
        if isinstance(item, dict) and item.get("decision") == "split"
    }
    synthetic_nodes = {
        node.key: node
        for node in nodes.values()
        if node.parent_key is not None
        and node.toc_key is None
        and node.key not in heading_split_nodes
    }
    raw_ranges = review.get("ranges")
    if synthetic_nodes and not isinstance(raw_ranges, list):
        raise SplitError(
            "Textbook split manifest needs semantic_review.ranges for "
            "headerless semantic child ranges"
        )
    if raw_ranges is None:
        raw_ranges = []
    if not isinstance(raw_ranges, list):
        raise SplitError("semantic_review.ranges must be an array")
    reviewed_ranges: set[str] = set()
    for index, item in enumerate(raw_ranges):
        if not isinstance(item, dict):
            raise SplitError(f"semantic_review range {index} must be an object")
        node_key = item.get("node_key")
        node = synthetic_nodes.get(node_key) if isinstance(node_key, str) else None
        if node is None:
            raise SplitError(
                f"semantic_review range {index} references no headerless semantic node"
            )
        if node_key in reviewed_ranges:
            raise SplitError(f"semantic_review duplicates range {node_key!r}")
        if (
            item.get("title") != node.title
            or item.get("start_line") != node.start_line
            or item.get("end_line") != node.end_line
        ):
            raise SplitError(
                f"semantic_review range {node_key!r} does not match its node"
            )
        confidence = item.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise SplitError(
                f"Semantic range {node.title!r} needs confidence between 0 and 1"
            )
        if confidence < confidence_threshold and item.get("reviewed") is not True:
            raise SplitError(
                f"Low-confidence semantic range {node.title!r} must be routed "
                "through review and marked reviewed"
            )
        if item.get("decision") != "split":
            raise SplitError(
                f"Semantic range {node.title!r} must record decision split"
            )
        if item.get("independent_teaching_arc") is not True:
            raise SplitError(
                f"Semantic range {node.title!r} must confirm independent_teaching_arc"
            )
        if not str(item.get("reason", "")).strip():
            raise SplitError(
                f"Semantic range {node.title!r} needs a specific independence reason"
            )
        reviewed_ranges.add(node_key)

    missing_ranges = sorted(set(synthetic_nodes) - reviewed_ranges)
    if missing_ranges:
        samples = ", ".join(
            synthetic_nodes[key].title for key in missing_ranges[:12]
        )
        raise SplitError(
            f"semantic_review.ranges omits {len(missing_ranges)} headerless "
            f"semantic nodes: {samples}"
        )


def render_node(
    node: SplitNode,
    nodes: dict[str, SplitNode],
    lines: list[str],
    excluded: set[int],
    output_root: Path,
    vault_root: Path,
    categories: dict[str, str],
    links: dict[str, Any],
    book_title: str,
    lesson_flow: dict[str, Any] | None = None,
) -> str:
    if lesson_flow is not None:
        rendered = render_lesson_flow_node(
            node,
            nodes,
            lines,
            excluded,
            output_root,
            vault_root,
            categories,
            links,
            lesson_flow,
        )
        text = normalize_entry_heading(
            "\n".join(rendered).strip(),
            node,
            book_title,
        )
        return text + "\n"

    children = sorted(
        (item for item in nodes.values() if item.parent_key == node.key),
        key=lambda item: item.start_line,
    )
    rendered: list[str] = []
    cursor = node.start_line
    for child in children:
        for line_number in range(cursor, child.start_line):
            if line_number not in excluded:
                rendered.append(lines[line_number - 1])
        rendered.append(
            note_link(
                child,
                node,
                output_root,
                vault_root,
                categories,
                links,
            )
        )
        cursor = child.end_line + 1
    for line_number in range(cursor, node.end_line + 1):
        if line_number not in excluded:
            rendered.append(lines[line_number - 1])

    text = normalize_entry_heading(
        "\n".join(rendered).strip(),
        node,
        book_title,
    )
    return text + "\n"


def source_range_lines(
    lines: list[str],
    excluded: set[int],
    start_line: int,
    end_line: int,
) -> list[str]:
    return [
        lines[line_number - 1]
        for line_number in range(start_line, end_line + 1)
        if line_number not in excluded
    ]


def quote_callout(
    body: list[str],
    *,
    marker: str,
    title: str,
) -> list[str]:
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        return []
    first_nonblank = next((line for line in body if line.strip()), "")
    if first_nonblank.startswith("> [!"):
        return body
    heading = ANY_HEADING_RE.match(first_nonblank)
    if heading and len(heading.group(1)) >= 4:
        first_index = body.index(first_nonblank)
        body.pop(first_index)
        while body and not body[0].strip():
            body.pop(0)
    elif re.sub(r"\s+", "", first_nonblank) == re.sub(r"\s+", "", title):
        first_index = body.index(first_nonblank)
        body.pop(first_index)
        while body and not body[0].strip():
            body.pop(0)
    if not body:
        return []
    rendered = [f"> [!{marker}] {title}"]
    rendered.extend(">" if not line else f"> {line}" for line in body)
    return rendered


def render_retained_flow_block(
    role: str,
    block_lines: list[str],
) -> list[str]:
    first_nonblank = next((line.strip() for line in block_lines if line.strip()), "")
    detected = functional_boundary(first_nonblank)

    if role == "entry-context":
        first_index = next(
            (index for index, line in enumerate(block_lines) if line.strip()),
            None,
        )
        if first_index is None:
            return block_lines
        heading = ANY_HEADING_RE.match(block_lines[first_index])
        if heading is None or len(heading.group(1)) > 3:
            return quote_callout(
                block_lines,
                marker="info",
                title="情景引入",
            )
        prefix = block_lines[: first_index + 1]
        body = block_lines[first_index + 1 :]
        callout = quote_callout(body, marker="info", title="情景引入")
        return prefix + ([""] if callout else []) + callout
    if role == "context":
        title = (
            detected[1]
            if detected is not None and detected[0] == "context"
            else "情景引入"
        )
        return quote_callout(
            block_lines,
            marker="info",
            title=title,
        )
    if role == "transition":
        return quote_callout(block_lines, marker="info", title="过渡")
    if role == "question":
        title = (
            detected[1]
            if detected is not None and detected[0] == "question"
            else "思考"
        )
        return quote_callout(block_lines, marker="question", title=title)
    if role == "analysis":
        return quote_callout(block_lines, marker="success", title="分析")
    return block_lines


def render_lesson_flow_node(
    node: SplitNode,
    nodes: dict[str, SplitNode],
    lines: list[str],
    excluded: set[int],
    output_root: Path,
    vault_root: Path,
    categories: dict[str, str],
    links: dict[str, Any],
    lesson_flow: dict[str, Any],
) -> list[str]:
    rendered: list[str] = []

    def append_block(block_lines: list[str]) -> None:
        while block_lines and not block_lines[0].strip():
            block_lines.pop(0)
        while block_lines and not block_lines[-1].strip():
            block_lines.pop()
        if not block_lines:
            return
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.extend(block_lines)

    for block in lesson_flow["blocks"]:
        if block["ownership"] == "move-child":
            child = nodes[str(block["child_node_key"])]
            append_block(
                [
                    note_link(
                        child,
                        node,
                        output_root,
                        vault_root,
                        categories,
                        links,
                    )
                ]
            )
            continue
        block_lines = source_range_lines(
            lines,
            excluded,
            int(block["start_line"]),
            int(block["end_line"]),
        )
        append_block(
            render_retained_flow_block(str(block["role"]), block_lines)
        )
    return rendered


def validate_lesson_flow_presence(
    profile: dict[str, Any],
    lesson_flow_manifest: dict[str, Any] | None,
) -> None:
    if lesson_flow_required(profile) and lesson_flow_manifest is None:
        raise SplitError(
            "Textbook splitting requires a validated lesson-flow manifest"
        )


def local_asset_hrefs(markdown: str) -> list[str]:
    return MARKDOWN_IMAGE_RE.findall(markdown) + HTML_IMAGE_RE.findall(markdown)


def materialize_assets(
    markdown: str,
    source_parent: Path,
    target_parent: Path,
    final_parent: Path,
    vault_root: Path,
    links: dict[str, Any],
) -> tuple[str, int]:
    copied = 0
    replacements: dict[str, str] = {}
    for href in dict.fromkeys(local_asset_hrefs(markdown)):
        raw = href.strip().strip("<>")
        if EXTERNAL_RE.match(raw) or raw.startswith(("/", "\\", "#")):
            continue
        path_text = urllib.parse.unquote(raw.split("#", 1)[0].split("?", 1)[0])
        relative = Path(path_text.replace("/", os.sep))
        if relative.is_absolute() or ".." in relative.parts:
            continue
        source = (source_parent / relative).resolve()
        if not source.is_file():
            # MinerU sometimes leaves HTML table images as images/<hash>
            # while split-part assets are stored below a namespaced tree.
            # Recover only an unambiguous hash/basename match.
            asset_root = source_parent / "images"
            matches = (
                sorted(asset_root.rglob(relative.name))
                if asset_root.is_dir() and relative.name
                else []
            )
            matches = [item.resolve() for item in matches if item.is_file()]
            if len(matches) != 1:
                raise SplitError(
                    f"Referenced source asset is missing or ambiguous: {source}"
                )
            source = matches[0]
        output_relative = (
            Path("images") / relative.name
            if relative.parts and relative.parts[0].casefold() == "images"
            else relative
        )
        destination = (target_parent / output_relative).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha256_file(destination) != sha256_file(source):
            raise SplitError(
                f"Flattened asset basename collision: {destination.name}"
            )
        if not destination.exists():
            shutil.copy2(source, destination)
            copied += 1
        if links.get("asset_mode") == "vault-root":
            final_destination = (final_parent / output_relative).resolve()
            try:
                vault_relative = final_destination.relative_to(vault_root).as_posix()
            except ValueError as exc:
                raise SplitError(
                    "Split asset target lies outside the configured vault"
                ) from exc
            replacements[href] = "/" + encode_path(
                vault_relative, bool(links.get("encode_spaces", False))
            )

    if replacements:
        markdown = MARKDOWN_IMAGE_RE.sub(
            lambda match: match.group(0).replace(
                match.group(1), replacements.get(match.group(1), match.group(1))
            ),
            markdown,
        )
        markdown = HTML_IMAGE_RE.sub(
            lambda match: match.group(0).replace(
                match.group(1), replacements.get(match.group(1), match.group(1))
            ),
            markdown,
        )
    return markdown, copied


def write_split(
    source: Path,
    profile: dict[str, Any],
    toc_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    output_root: Path,
    lesson_flow_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_lesson_flow_presence(profile, lesson_flow_manifest)
    markdown = source.read_text(encoding="utf-8-sig")
    lines = markdown.splitlines()
    toc_keys = {
        str(item["key"])
        for item in toc_manifest.get("entries", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    nodes, root = load_nodes(split_manifest, profile, len(lines), toc_keys)
    categories = category_map(profile)
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    links = profile.get("links", {})
    excluded = line_exclusions(toc_manifest)
    validate_semantic_review(
        split_manifest, nodes, lines, excluded, profile
    )
    book_title = str(profile.get("book", {}).get("title", root.title))
    lesson_flow_by_node = {
        str(lesson["node_key"]): lesson
        for lesson in (
            lesson_flow_manifest.get("lessons", [])
            if isinstance(lesson_flow_manifest, dict)
            else []
        )
        if isinstance(lesson, dict) and isinstance(lesson.get("node_key"), str)
    }

    if output_root.exists():
        raise FileExistsError(
            f"Output root already exists; choose a new target or resume explicitly: {output_root}"
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.split-", dir=output_root.parent)
    )
    note_count = 0
    asset_count = 0
    coverage_units: list[dict[str, Any]] = []
    try:
        ordered_nodes = sorted(
            nodes.values(), key=lambda item: (item.start_line, item.end_line, item.key)
        )
        for order, node in enumerate(ordered_nodes, start=1):
            rendered = render_node(
                node,
                nodes,
                lines,
                excluded,
                output_root,
                vault_root,
                categories,
                links,
                book_title,
                lesson_flow=lesson_flow_by_node.get(node.key),
            )
            destination = target_path(node, temporary, categories)
            destination.parent.mkdir(parents=True, exist_ok=True)
            final_target = target_path(node, output_root, categories)
            rendered, copied = materialize_assets(
                rendered,
                source.parent,
                destination.parent,
                final_target.parent,
                vault_root,
                links,
            )
            destination.write_text(rendered, encoding="utf-8")
            asset_count += copied
            note_count += 1
            coverage_units.append(
                {
                    "source_key": node.key,
                    "source_order": order,
                    "role": node.category,
                    "target": final_target.relative_to(output_root).as_posix(),
                    "status": "assigned",
                    "line_range": [node.start_line, node.end_line],
                }
            )
        shutil.move(str(temporary), str(output_root))
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    coverage = {
        "schema_version": 1,
        "profile": split_manifest.get("profile"),
        "source_sha256": split_manifest.get("source_sha256"),
        "units": coverage_units,
    }
    staging_root = Path(profile["paths"]["staging_root"]).resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    coverage_path = staging_root / "coverage-manifest.json"
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "notes": note_count,
        "assets_copied": asset_count,
        "categories": categories,
        "coverage_manifest": str(coverage_path),
        "root_note": str(target_path(root, output_root, categories)),
    }


def validate_identity(
    profile_path: Path,
    profile: dict[str, Any],
    toc_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    source: Path,
) -> None:
    for name, artifact in (
        ("TOC manifest", toc_manifest),
        ("split manifest", split_manifest),
    ):
        raw_profile = artifact.get("profile")
        if not isinstance(raw_profile, str) or Path(raw_profile).resolve() != profile_path:
            raise SplitError(f"{name} profile does not match --profile")
        if artifact.get("source_sha256") != profile.get("source", {}).get("sha256"):
            raise SplitError(f"{name} source_sha256 does not match profile")
    candidate_hash = toc_manifest.get("candidate_markdown_sha256")
    if candidate_hash and candidate_hash != sha256_file(source):
        raise SplitError("Formatted Markdown hash does not match TOC manifest")
    expected_split_hash = split_manifest.get("input_markdown_sha256")
    if expected_split_hash != sha256_file(source):
        raise SplitError("Formatted Markdown hash does not match split manifest")


def lesson_flow_required(profile: dict[str, Any]) -> bool:
    book_kind = str(profile.get("book", {}).get("kind", "")).casefold()
    decomposition = profile.get("decomposition", {})
    return bool(
        "textbook" in book_kind
        and isinstance(decomposition, dict)
        and decomposition.get("require_lesson_flow_manifest", False)
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("toc_manifest", type=Path)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--lesson-flow-manifest", type=Path)
    parser.add_argument("--output-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = args.formatted_markdown.resolve()
        profile_path = args.profile.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Formatted Markdown does not exist: {source}")
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        toc_manifest = json.loads(
            args.toc_manifest.read_text(encoding="utf-8-sig")
        )
        split_manifest = json.loads(
            args.split_manifest.read_text(encoding="utf-8-sig")
        )
        validate_identity(
            profile_path, profile, toc_manifest, split_manifest, source
        )
        lesson_flow_path = (
            args.lesson_flow_manifest.resolve()
            if args.lesson_flow_manifest
            else None
        )
        lesson_flow_summary = None
        lesson_flow_payload = None
        if lesson_flow_required(profile):
            if lesson_flow_path is None or not lesson_flow_path.is_file():
                raise SplitError(
                    "Textbook splitting requires --lesson-flow-manifest"
                )
            lesson_flow_payload = json.loads(
                lesson_flow_path.read_text(encoding="utf-8-sig")
            )
            lesson_flow_summary = validate_lesson_flow(
                lesson_flow_payload,
                formatted_markdown=source,
                split_manifest_path=args.split_manifest.resolve(),
                profile_path=profile_path,
            )
        output_root = (
            args.output_root.resolve()
            if args.output_root
            else Path(profile["paths"]["book_root"]).resolve()
        )
        summary = write_split(
            source,
            profile,
            toc_manifest,
            split_manifest,
            output_root,
            lesson_flow_manifest=lesson_flow_payload,
        )
        result = {
            "schema_version": 1,
            "stage": "book-toc-splitting",
            "status": "completed",
            "profile": str(profile_path),
            "source_sha256": profile["source"]["sha256"],
            "input_markdown": str(source),
            "output_root": str(output_root),
            "lesson_flow_manifest": (
                str(lesson_flow_path) if lesson_flow_path else None
            ),
            "lesson_flow": lesson_flow_summary,
            **summary,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-toc-splitting",
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

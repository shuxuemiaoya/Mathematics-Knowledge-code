#!/usr/bin/env python3
"""Plan a reviewable textbook split manifest from TOC-formatted Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, NamedTuple


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_SUBSECTION_RE = re.compile(r"^\d+(?:\.\d+){2,}\s+\S")
NUMBER_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*)\b")
SECTION_EXERCISE_RE = re.compile(r"^习题\s*\d+(?:\.\d+)+(?:\s|$)")
SECTION_EXERCISE_NUMBER_RE = re.compile(r"^习题\s*(\d+(?:\.\d+)+)")
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
DEFAULT_CONTENT_REVIEW_MIN_LINES = 24


class SplitPlanningError(ValueError):
    pass


class Heading(NamedTuple):
    line: int
    level: int
    title: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def excluded_lines(toc_manifest: dict[str, Any]) -> set[int]:
    excluded: set[int] = set()
    for item in toc_manifest.get("toc_source_ranges", []):
        if not isinstance(item, dict):
            continue
        start = item.get("start_line")
        end = item.get("end_line")
        if isinstance(start, int) and isinstance(end, int):
            excluded.update(range(start, end + 1))
    return excluded


def scan_headings(lines: list[str], excluded: set[int]) -> list[Heading]:
    headings: list[Heading] = []
    for line_number, line in enumerate(lines, start=1):
        if line_number in excluded:
            continue
        match = HEADING_RE.match(line)
        if match:
            headings.append(
                Heading(
                    line=line_number,
                    level=len(match.group(1)),
                    title=match.group(2).strip(),
                )
            )
    return headings


def safe_filename(title: str) -> str:
    value = title.replace("$", "").replace("*", "")
    value = re.sub(
        r"\\frac\s*\{([^{}]+)\}\{([^{}]+)\}",
        r"\1÷\2",
        value,
    )
    for macro, rendered in {
        r"\alpha": "α",
        r"\beta": "β",
        r"\omega": "ω",
        r"\varphi": "φ",
        r"\phi": "φ",
        r"\pi": "π",
        r"\sin": "sin",
        r"\cos": "cos",
        r"\tan": "tan",
    }.items():
        value = value.replace(macro, rendered)
    value = re.sub(r"\\([A-Za-z]+)", r"\1", value)
    value = value.replace("{", "").replace("}", "")
    value = INVALID_FILENAME_RE.sub("－", value)
    value = re.sub(r"\s+", " ", value).strip().rstrip(". ")
    return f"{value or '未命名节点'}.md"


def contextual_toc_title(
    title: str,
    active_chapter_title: str | None,
) -> str:
    if title == "小结" and active_chapter_title:
        return f"{active_chapter_title} 小结"
    if title.startswith("复习参考题") and active_chapter_title:
        return f"{active_chapter_title} {title}"
    return title


def heading_ranges(headings: list[Heading], line_count: int) -> dict[int, int]:
    ranges: dict[int, int] = {}
    for index, heading in enumerate(headings):
        end = line_count
        for later in headings[index + 1 :]:
            if later.level <= heading.level:
                end = later.line - 1
                break
        ranges[heading.line] = end
    return ranges


def toc_heading_map(
    headings: list[Heading],
    toc_entries: list[dict[str, Any]],
) -> list[tuple[Heading, dict[str, Any]]]:
    content_toc = [heading for heading in headings if heading.level <= 3]
    if len(content_toc) != len(toc_entries):
        raise SplitPlanningError(
            "Formatted Markdown H1-H3 count does not equal TOC entry count: "
            f"{len(content_toc)} != {len(toc_entries)}"
        )
    mapped: list[tuple[Heading, dict[str, Any]]] = []
    for heading, entry in zip(content_toc, toc_entries):
        if heading.title != entry.get("title") or heading.level != entry.get("level"):
            raise SplitPlanningError(
                "Formatted TOC heading does not match the manifest at "
                f"line {heading.line}: {heading.title!r}"
            )
        mapped.append((heading, entry))
    return mapped


def retain_reason(title: str) -> str:
    if title in {
        "思考",
        "观察",
        "探究",
        "探究1",
        "探究2",
        "探究3",
        "归纳",
        "练习",
        "复习巩固",
        "综合运用",
        "拓广探索",
    }:
        return "Presentation block belongs to the surrounding lesson or exercise."
    if title in {"● ●", "人民教育出版社"}:
        return "OCR or page-layout marker is not an independent teaching unit."
    if re.match(r"^[一二三四五六七八九十]+、", title) or re.match(
        r"^\d+\.\s+", title
    ):
        return "Local exposition step remains inside its containing teaching unit."
    return "Unnumbered non-TOC heading remains in the nearest TOC note by default."


def content_review_min_lines(profile: dict[str, Any]) -> int:
    decomposition = profile.get("decomposition", {})
    value = (
        decomposition.get(
            "content_review_min_nonblank_lines",
            DEFAULT_CONTENT_REVIEW_MIN_LINES,
        )
        if isinstance(decomposition, dict)
        else DEFAULT_CONTENT_REVIEW_MIN_LINES
    )
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SplitPlanningError(
            "content_review_min_nonblank_lines must be a positive integer"
        )
    return value


def nonblank_line_count(
    lines: list[str],
    start_line: int,
    end_line: int,
) -> int:
    return sum(
        1
        for line in lines[start_line - 1 : end_line]
        if line.strip()
    )


def build_manifest(
    source: Path,
    profile_path: Path,
    toc_manifest_path: Path,
) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    toc_manifest = json.loads(toc_manifest_path.read_text(encoding="utf-8-sig"))
    source_sha = profile.get("source", {}).get("sha256")
    if toc_manifest.get("source_sha256") != source_sha:
        raise SplitPlanningError("TOC manifest source identity does not match profile")

    lines = source.read_text(encoding="utf-8-sig").splitlines()
    ignored = excluded_lines(toc_manifest)
    headings = scan_headings(lines, ignored)
    ranges = heading_ranges(headings, len(lines))
    toc_entries = toc_manifest.get("entries")
    if not isinstance(toc_entries, list) or not toc_entries:
        raise SplitPlanningError("TOC manifest has no entries")
    mapped_toc = toc_heading_map(headings, toc_entries)

    book_title = str(profile.get("book", {}).get("title", "书名"))
    nodes: list[dict[str, Any]] = [
        {
            "key": "book-root",
            "title": book_title,
            "parent_key": None,
            "category": "root",
            "filename": safe_filename(book_title),
            "start_line": 1,
            "end_line": len(lines),
            "toc_key": None,
        }
    ]
    toc_nodes_by_line: dict[int, dict[str, Any]] = {}
    toc_stack: list[tuple[int, str]] = []
    active_chapter_title: str | None = None

    for heading, entry in mapped_toc:
        while toc_stack and toc_stack[-1][0] >= heading.level:
            toc_stack.pop()
        parent_key = toc_stack[-1][1] if toc_stack else "book-root"
        if heading.level == 1 and str(entry.get("category")) == "knowledge":
            active_chapter_title = heading.title
        title = contextual_toc_title(heading.title, active_chapter_title)
        node = {
            "key": f"node-{entry['key']}",
            "title": title,
            "parent_key": parent_key,
            "category": entry.get("category", "knowledge"),
            "filename": safe_filename(title),
            "start_line": heading.line,
            "end_line": ranges[heading.line],
            "toc_key": entry["key"],
        }
        nodes.append(node)
        toc_nodes_by_line[heading.line] = node
        toc_stack.append((heading.level, node["key"]))

    toc_nodes_ordered = sorted(
        toc_nodes_by_line.values(),
        key=lambda item: (item["start_line"], -item["end_line"]),
    )

    def nearest_toc_parent(line_number: int) -> dict[str, Any]:
        candidates = [
            node
            for node in toc_nodes_ordered
            if node["start_line"] <= line_number <= node["end_line"]
        ]
        if not candidates:
            return nodes[0]
        return min(
            candidates,
            key=lambda item: item["end_line"] - item["start_line"],
        )

    def semantic_toc_parent(heading: Heading) -> dict[str, Any]:
        number_match = NUMBER_PREFIX_RE.match(heading.title)
        exercise_match = SECTION_EXERCISE_NUMBER_RE.match(heading.title)
        parent_number: str | None = None
        if number_match and "." in number_match.group(1):
            parent_number = number_match.group(1).rsplit(".", 1)[0]
        elif exercise_match:
            parent_number = exercise_match.group(1)
        if parent_number:
            numbered_candidates = [
                node
                for node in toc_nodes_ordered
                if node["start_line"] <= heading.line <= node["end_line"]
                and (
                    match := NUMBER_PREFIX_RE.match(str(node["title"]))
                )
                and match.group(1) == parent_number
            ]
            if numbered_candidates:
                return min(
                    numbered_candidates,
                    key=lambda item: item["end_line"] - item["start_line"],
                )
        return nearest_toc_parent(heading.line)

    semantic_headings = [heading for heading in headings if heading.level >= 4]
    split_by_parent: dict[str, list[Heading]] = {}
    reviews: list[dict[str, Any]] = []
    for heading in semantic_headings:
        parent = semantic_toc_parent(heading)
        category: str | None = None
        if SECTION_EXERCISE_RE.match(heading.title):
            category = "exercise"
        elif NUMBERED_SUBSECTION_RE.match(heading.title):
            category = "knowledge"

        if category:
            key = f"semantic-{heading.line:05d}"
            split_by_parent.setdefault(parent["key"], []).append(heading)
            reviews.append(
                {
                    "line": heading.line,
                    "title": heading.title,
                    "decision": "split",
                    "node_key": key,
                    "confidence": 0.99,
                }
            )
        else:
            reviews.append(
                {
                    "line": heading.line,
                    "title": heading.title,
                    "decision": "retain",
                    "reason": retain_reason(heading.title),
                    "confidence": 0.99,
                }
            )

    # A printed H3 side-material entry can appear between numbered H4
    # subsections. Markdown heading ranges would otherwise make that H3 absorb
    # the later numbered subsection. Once numeric-prefix routing returns the
    # subsection to their common lesson parent, trim the intervening TOC node
    # at the subsection boundary so the siblings remain disjoint.
    for parent_key, split_headings in split_by_parent.items():
        for heading in split_headings:
            for toc_node in toc_nodes_ordered:
                if (
                    toc_node.get("parent_key") == parent_key
                    and int(toc_node["start_line"]) < heading.line
                    <= int(toc_node["end_line"])
                ):
                    toc_node["end_line"] = heading.line - 1

    node_lookup = {node["key"]: node for node in nodes}
    review_lookup = {item["line"]: item for item in reviews}
    for parent_key, split_headings in split_by_parent.items():
        parent = node_lookup[parent_key]
        ordered = sorted(split_headings, key=lambda item: item.line)
        direct_toc_boundaries = sorted(
            int(node["start_line"])
            for node in toc_nodes_ordered
            if node.get("parent_key") == parent_key
        )
        for index, heading in enumerate(ordered):
            later_boundaries = [
                line
                for line in direct_toc_boundaries
                if line > heading.line
            ]
            if index + 1 < len(ordered):
                later_boundaries.append(ordered[index + 1].line)
            end_line = (
                min(later_boundaries) - 1
                if later_boundaries
                else parent["end_line"]
            )
            category = (
                "exercise"
                if SECTION_EXERCISE_RE.match(heading.title)
                else "knowledge"
            )
            nodes.append(
                {
                    "key": review_lookup[heading.line]["node_key"],
                    "title": heading.title,
                    "parent_key": parent_key,
                    "category": category,
                    "filename": safe_filename(heading.title),
                    "start_line": heading.line,
                    "end_line": end_line,
                    "toc_key": None,
                }
            )

    toc_entries_by_key = {
        str(item["key"]): item
        for item in toc_entries
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    section_reviews: list[dict[str, Any]] = []
    minimum_lines = content_review_min_lines(profile)
    for node in nodes:
        toc_key = node.get("toc_key")
        if node.get("category") != "knowledge":
            continue
        if isinstance(toc_key, str):
            entry = toc_entries_by_key.get(toc_key, {})
            level = entry.get("level")
            if level not in {2, 3}:
                continue
        else:
            source_heading = HEADING_RE.match(lines[int(node["start_line"]) - 1])
            if source_heading is None or len(source_heading.group(1)) < 4:
                continue
        content_lines = nonblank_line_count(
            lines,
            int(node["start_line"]),
            int(node["end_line"]),
        )
        if content_lines < minimum_lines:
            continue
        section_reviews.append(
            {
                "node_key": node["key"],
                "title": node["title"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
                "nonblank_lines": content_lines,
                "decision": "review_required",
                "reason": (
                    "Content-level review must decide whether this teaching node "
                    "contains independently reusable teaching arcs, including "
                    "ranges that have no explicit heading."
                ),
                "confidence": 0.0,
            }
        )

    return {
        "schema_version": 1,
        "profile": str(profile_path),
        "source_sha256": source_sha,
        "input_markdown_sha256": sha256_file(source),
        "semantic_review": {
            "headings": reviews,
            "sections": section_reviews,
            "ranges": [],
        },
        "nodes": nodes,
    }


def atomic_write(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("toc_manifest", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = args.formatted_markdown.resolve()
        toc_manifest = args.toc_manifest.resolve()
        profile = args.profile.resolve()
        output = args.output_manifest.resolve()
        for path in (source, toc_manifest, profile):
            if not path.is_file():
                raise FileNotFoundError(f"Required input does not exist: {path}")
        manifest = build_manifest(source, profile, toc_manifest)
        rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        atomic_write(output, rendered, args.overwrite)
        reviews = manifest["semantic_review"]["headings"]
        sections = manifest["semantic_review"]["sections"]
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-split-manifest-planning",
                    "status": "review_required",
                    "manifest": str(output),
                    "node_count": len(manifest["nodes"]),
                    "semantic_heading_count": len(reviews),
                    "semantic_split_count": sum(
                        1 for item in reviews if item["decision"] == "split"
                    ),
                    "semantic_retain_count": sum(
                        1 for item in reviews if item["decision"] == "retain"
                    ),
                    "content_section_review_count": len(sections),
                    "low_confidence_count": sum(
                        1 for item in reviews if item["confidence"] < 0.9
                    )
                    + sum(
                        1 for item in sections if item["confidence"] < 0.9
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-split-manifest-planning",
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

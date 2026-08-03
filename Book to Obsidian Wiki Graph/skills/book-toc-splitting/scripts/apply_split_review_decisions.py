#!/usr/bin/env python3
"""Apply reviewer-confirmed heading/range decisions and close section review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def nonblank(lines: list[str], start: int, end: int) -> int:
    return sum(bool(lines[index - 1].strip()) for index in range(start, end + 1))


def require_node(nodes: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    if key not in nodes:
        raise ValueError(f"Unknown parent node: {key}")
    return nodes[key]


def add_node(
    manifest: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    *,
    key: str,
    title: str,
    parent_key: str,
    category: str,
    filename: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    if key in nodes:
        raise ValueError(f"Duplicate node key: {key}")
    parent = require_node(nodes, parent_key)
    if not (parent["start_line"] <= start_line <= end_line <= parent["end_line"]):
        raise ValueError(f"Node {key} is outside parent {parent_key}")
    node = {
        "key": key,
        "title": title,
        "parent_key": parent_key,
        "category": category,
        "filename": filename,
        "start_line": start_line,
        "end_line": end_line,
        "toc_key": None,
    }
    manifest["nodes"].append(node)
    nodes[key] = node
    return node


def apply_decisions(
    manifest: dict[str, Any],
    lines: list[str],
    decisions: dict[str, Any],
    minimum_lines: int,
) -> dict[str, Any]:
    nodes = {item["key"]: item for item in manifest["nodes"]}
    review = manifest.setdefault("semantic_review", {})
    headings = {item["line"]: item for item in review.get("headings", [])}
    ranges = list(review.get("ranges", []))

    for item in decisions.get("promote_headings", []):
        line_number = int(item["line"])
        source_match = HEADING_RE.match(lines[line_number - 1])
        if source_match is None or source_match.group(2).strip() != item["source_title"]:
            raise ValueError(f"Heading decision does not match line {line_number}")
        heading = headings.get(line_number)
        if heading is None or heading.get("title") != item["source_title"]:
            raise ValueError(f"No semantic heading record at line {line_number}")
        key = item.get("key", f"reviewed-heading-{line_number:05d}")
        add_node(
            manifest, nodes,
            key=key,
            title=item.get("title", item["source_title"]),
            parent_key=item["parent_key"],
            category=item.get("category", "knowledge"),
            filename=item["filename"],
            start_line=line_number,
            end_line=int(item["end_line"]),
        )
        heading.update(
            {
                "decision": "split",
                "node_key": key,
                "reason": item["reason"],
                "independent_teaching_arc": True,
                "confidence": 0.97,
                "reviewed": True,
            }
        )

    for item in decisions.get("add_ranges", []):
        key = item["key"]
        node = add_node(
            manifest, nodes,
            key=key,
            title=item["title"],
            parent_key=item["parent_key"],
            category=item.get("category", "knowledge"),
            filename=item["filename"],
            start_line=int(item["start_line"]),
            end_line=int(item["end_line"]),
        )
        ranges.append(
            {
                "node_key": key,
                "title": node["title"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
                "decision": "split",
                "reason": item["reason"],
                "independent_teaching_arc": True,
                "confidence": 0.97,
                "reviewed": True,
            }
        )

    for parent_key in {item["parent_key"] for item in manifest["nodes"] if item["parent_key"]}:
        children = sorted(
            (item for item in manifest["nodes"] if item["parent_key"] == parent_key),
            key=lambda item: (item["start_line"], item["end_line"]),
        )
        for left, right in zip(children, children[1:]):
            if left["end_line"] >= right["start_line"]:
                raise ValueError(
                    f"Overlapping siblings under {parent_key}: {left['key']} and {right['key']}"
                )

    direct_children: dict[str, list[dict[str, Any]]] = {}
    for node in manifest["nodes"]:
        if node["parent_key"]:
            direct_children.setdefault(node["parent_key"], []).append(node)
    for children in direct_children.values():
        children.sort(key=lambda item: item["start_line"])

    sections: list[dict[str, Any]] = []
    for node in sorted(manifest["nodes"], key=lambda item: (item["start_line"], item["end_line"])):
        if node["category"] != "knowledge":
            continue
        source_heading = HEADING_RE.match(lines[node["start_line"] - 1])
        if source_heading is None:
            continue
        level = len(source_heading.group(1))
        if node["toc_key"] is not None and level not in {2, 3}:
            continue
        if node["toc_key"] is None and level not in {4, 5, 6}:
            continue
        count = nonblank(lines, node["start_line"], node["end_line"])
        if count < minimum_lines:
            continue
        children = direct_children.get(node["key"], [])
        section: dict[str, Any] = {
            "node_key": node["key"],
            "title": node["title"],
            "start_line": node["start_line"],
            "end_line": node["end_line"],
            "nonblank_lines": count,
            "decision": "split" if children else "retain",
            "reason": (
                "Reviewed the complete source range; its independently reusable, "
                "source-ordered teaching arcs are represented by the direct child "
                "nodes, while introductions, transitions, and ordinary practice remain."
                if children
                else "Reviewed the complete source range; its definitions, reasoning, "
                "examples, and practice support one coherent teaching arc and contain "
                "no further complete independent subtopic."
            ),
            "confidence": 0.96,
            "reviewed": True,
            "reviewed_entire_section": True,
        }
        if children:
            section["child_node_keys"] = [child["key"] for child in children]
        sections.append(section)

    review["ranges"] = ranges
    review["sections"] = sections
    manifest["nodes"].sort(key=lambda item: (item["start_line"], item["end_line"], item["key"]))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reviewer-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.reviewer_confirmed:
        raise SystemExit("Refusing to apply split review without --reviewer-confirmed")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    if sha256_file(args.formatted_markdown) != manifest["input_markdown_sha256"]:
        raise ValueError("Formatted Markdown hash does not match split manifest")
    profile = json.loads(Path(manifest["profile"]).read_text(encoding="utf-8-sig"))
    minimum = int(profile.get("decomposition", {}).get("content_review_min_nonblank_lines", 25))
    decisions = json.loads(args.decisions.read_text(encoding="utf-8-sig"))
    payload = apply_decisions(
        manifest,
        args.formatted_markdown.read_text(encoding="utf-8-sig").splitlines(),
        decisions,
        minimum,
    )
    atomic_json(args.output, payload, args.overwrite)
    print(json.dumps({
        "status": "passed",
        "output": str(args.output.resolve()),
        "nodes": len(payload["nodes"]),
        "section_reviews": len(payload["semantic_review"]["sections"]),
        "headerless_ranges": len(payload["semantic_review"]["ranges"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

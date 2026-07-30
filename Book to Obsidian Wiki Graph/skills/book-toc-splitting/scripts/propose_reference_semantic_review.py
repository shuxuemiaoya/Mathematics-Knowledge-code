#!/usr/bin/env python3
"""Propose same-edition reference note spans inside a formatted source book.

This is a review aid, not a splitter. It never edits the split manifest or the
reference corpus. A reviewer must still accept, adjust, or reject every range.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
HTML_RE = re.compile(r"<!--.*?-->|<[^>]+>", re.S)
LINE_PREFIX_RE = re.compile(
    r"^\s*(?:#{1,6}\s+|>\s*\[![^\]]+\][+-]?\s*|>+\s*|[-*+]\s+)",
    re.M,
)
NORMALIZE_RE = re.compile(
    r"""[\s`*_~\\{}$，。；：、,.!?！？;:()（）\[\]<>《》“”"'—–=+|/]+"""
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def normalize(text: str) -> str:
    text = MARKDOWN_IMAGE_RE.sub("", text)
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = WIKILINK_RE.sub(lambda match: match.group(2) or match.group(1), text)
    text = HTML_RE.sub("", text)
    text = LINE_PREFIX_RE.sub("", text)
    return NORMALIZE_RE.sub("", text).casefold()


def title_key(text: str) -> str:
    return NORMALIZE_RE.sub("", text).casefold()


def shingles(text: str, width: int = 12) -> set[str]:
    if len(text) < width:
        return {text} if text else set()
    return {text[index : index + width] for index in range(len(text) - width + 1)}


def source_text_with_line_map(
    lines: list[str], start_line: int, end_line: int
) -> tuple[str, list[int]]:
    pieces: list[str] = []
    line_map: list[int] = []
    for line_number in range(start_line, end_line + 1):
        piece = normalize(lines[line_number - 1])
        pieces.append(piece)
        line_map.extend([line_number] * len(piece))
    return "".join(pieces), line_map


def matching_spans(reference: str, source: str) -> list[tuple[int, int]]:
    matcher = difflib.SequenceMatcher(
        None,
        reference,
        source,
        autojunk=False,
    )
    return [
        (block.b, block.size)
        for block in matcher.get_matching_blocks()
        if block.size >= 12
    ]


def expand_to_block(
    lines: list[str],
    start_line: int,
    end_line: int,
    node_start: int,
    node_end: int,
    reference_title: str,
) -> tuple[int, int]:
    title = title_key(reference_title)
    for candidate in range(start_line, node_start - 1, -1):
        match = HEADING_RE.match(lines[candidate - 1])
        if match and title_key(match.group(2)) == title:
            start_line = candidate
            break
    if start_line == node_start and title_key(lines[node_start - 1]) != title:
        start_line += 1
        while start_line <= node_end and not lines[start_line - 1].strip():
            start_line += 1
    while start_line > node_start:
        previous = lines[start_line - 2]
        if not previous.strip() or HEADING_RE.match(previous):
            break
        start_line -= 1
    while end_line < node_end:
        following = lines[end_line]
        if not following.strip() or HEADING_RE.match(following):
            break
        end_line += 1
    return start_line, end_line


def propose(
    formatted_markdown: Path,
    split_manifest: Path,
    reference_root: Path,
) -> dict[str, Any]:
    lines = formatted_markdown.read_text(encoding="utf-8-sig").splitlines()
    manifest = json.loads(split_manifest.read_text(encoding="utf-8-sig"))
    nodes = [
        node
        for node in manifest["nodes"]
        if node.get("category") == "knowledge"
    ]
    existing_titles = {title_key(node["title"]) for node in manifest["nodes"]}
    source_documents: list[dict[str, Any]] = []
    for node in nodes:
        text, line_map = source_text_with_line_map(
            lines, int(node["start_line"]), int(node["end_line"])
        )
        source_documents.append(
            {
                "node": node,
                "text": text,
                "line_map": line_map,
                "shingles": shingles(text),
            }
        )

    reference_dir = reference_root / "知识点"
    suggestions: list[dict[str, Any]] = []
    skipped_existing: list[str] = []
    for path in sorted(reference_dir.glob("*.md"), key=lambda item: item.name):
        if title_key(path.stem) in existing_titles:
            skipped_existing.append(path.stem)
            continue
        reference = normalize(path.read_text(encoding="utf-8-sig"))
        reference_shingles = shingles(reference)
        if len(reference) < 36 or not reference_shingles:
            continue
        ranked: list[tuple[float, dict[str, Any]]] = []
        for document in source_documents:
            score = len(reference_shingles & document["shingles"]) / len(
                reference_shingles
            )
            ranked.append((score, document))
        # The manifest contains nested chapter, lesson, and subsection ranges.
        # Equal containment is expected for ancestors, so prefer the smallest
        # owning range rather than attaching every proposal to a chapter.
        ranked.sort(
            key=lambda item: (
                item[0],
                -(
                    int(item[1]["node"]["end_line"])
                    - int(item[1]["node"]["start_line"])
                ),
            ),
            reverse=True,
        )
        best_score = ranked[0][0]
        near_best = [
            document
            for score, document in ranked
            if score >= max(0.0, best_score - 0.03)
        ]
        best = min(
            near_best,
            key=lambda document: int(document["node"]["end_line"])
            - int(document["node"]["start_line"]),
        )
        spans = matching_spans(reference, best["text"])
        matched_character_count = sum(size for _, size in spans)
        matched_reference_ratio = (
            matched_character_count / len(reference) if reference else 0.0
        )
        if not spans:
            start_line = end_line = None
        else:
            start_line = best["line_map"][min(position for position, _ in spans)]
            last_position = min(
                max(position + size - 1 for position, size in spans),
                len(best["line_map"]) - 1,
            )
            end_line = best["line_map"][last_position]
            start_line, end_line = expand_to_block(
                lines,
                start_line,
                end_line,
                int(best["node"]["start_line"]),
                int(best["node"]["end_line"]),
                path.stem,
            )
        suggestions.append(
            {
                "title": path.stem,
                "parent_node_key": best["node"]["key"],
                "parent_title": best["node"]["title"],
                "containment": round(best_score, 3),
                "runner_up_containment": round(ranked[1][0], 3)
                if len(ranked) > 1
                else 0.0,
                "start_line": start_line,
                "end_line": end_line,
                "matched_block_count": len(spans),
                "matched_character_count": matched_character_count,
                "matched_reference_ratio": round(matched_reference_ratio, 3),
                "review_flags": (
                    ["incomplete-reference-body-match"]
                    if matched_reference_ratio < 0.85
                    else []
                ),
                "status": "review_candidate"
                if (
                    best_score >= 0.45
                    and start_line is not None
                    and matched_reference_ratio >= 0.85
                )
                else "ambiguous",
            }
        )
    return {
        "schema_version": 1,
        "stage": "reference-semantic-review-proposal",
        "status": "review_required",
        "formatted_markdown": str(formatted_markdown),
        "split_manifest": str(split_manifest),
        "reference_root": str(reference_root),
        "skipped_existing_titles": skipped_existing,
        "suggestions": suggestions,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("reference_root", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = propose(
        args.formatted_markdown.resolve(),
        args.split_manifest.resolve(),
        args.reference_root.resolve(),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.resolve().write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

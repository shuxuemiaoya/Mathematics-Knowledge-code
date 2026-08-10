from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .common import ConfigurationError, load_json, load_profile, sha256_file, write_json_atomic


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBER_PREFIX_RE = re.compile(r"^\s*([\d一二三四五六七八九十百①②③④⑤⑥⑦⑧⑨⑩]+(?:[.．、]\d+)*)[.．、)）\s]+(.+)$")
LABEL_STEM_RE = re.compile(r"^\s*([^\d\s]{1,12})\s*[\d一二三四五六七八九十百①②③④⑤⑥⑦⑧⑨⑩]+(?:\s|$)")
HEADING_STEM_RE = re.compile(r"^\s*([^\s\d]{1,12})(?:\s+|$)")
INDEX_LEADER_RE = re.compile(r"(?:\.{2,}|…{1,}|\s{2,})")
INDEX_REFERENCE_SUFFIX_RE = re.compile(
    r"(?P<references>(?:\s*(?:[（(]\s*\d{1,4}\s*[）)]|\d{1,4})){1,4})\s*$"
)
PAGE_MARKER_RE = re.compile(r"<!--\s*source-part:(?P<part>\d+)\s+pages:(?P<start>\d+)-(?P<end>\d+)\s*-->")


def parse_index_entry(line: str) -> dict[str, Any] | None:
    """Parse one index line without assigning publisher-specific meaning."""
    leader = INDEX_LEADER_RE.search(line)
    if not leader:
        return None
    title = line[:leader.start()].strip()
    tail = line[leader.end():].strip()
    suffix = INDEX_REFERENCE_SUFFIX_RE.search(tail)
    if not title or not suffix:
        return None
    references = [int(value) for value in re.findall(r"\d{1,4}", suffix.group("references"))]
    if not references:
        return None
    return {
        "title": title,
        "descriptor": tail[:suffix.start()].strip(),
        "references": references,
        "literal": line.strip(),
    }


def contiguous_index_runs(lines: list[str]) -> list[dict[str, Any]]:
    """Propose index-like runs from typography, without assuming literal TOC labels."""
    entries = [
        (number, parsed)
        for number, line in enumerate(lines, 1)
        if (parsed := parse_index_entry(line)) is not None
    ]
    runs: list[list[tuple[int, dict[str, Any]]]] = []
    for item in entries:
        if not runs or item[0] - runs[-1][-1][0] > 2:
            runs.append([item])
        else:
            runs[-1].append(item)
    candidates: list[dict[str, Any]] = []
    for run in runs:
        if len(run) < 2:
            continue
        start = run[0][0]
        end = run[-1][0]
        parsed_lines = {number for number, _ in run}
        candidates.append(
            {
                "start_line": start,
                "end_line": end,
                "entry_count": len(run),
                "entries": [{"source_line": number, **parsed} for number, parsed in run],
                "unparsed_nonblank_lines": [
                    {"source_line": number, "literal": lines[number - 1].strip()}
                    for number in range(start, end + 1)
                    if number not in parsed_lines and lines[number - 1].strip()
                ],
                "sample": [parsed["title"] for _, parsed in run[:5]],
                "authority": None,
                "status": "review_required",
            }
        )
    return candidates


def propose_role(literal: str, role_hints: list[dict[str, str]] | None = None) -> str | None:
    """Apply optional, preset-owned semantic hints to an observed literal."""
    for index, hint in enumerate(role_hints or []):
        role = str(hint.get("role", "")).strip()
        pattern = str(hint.get("pattern", ""))
        if not role or not pattern:
            raise ConfigurationError(f"inventory.role_hints[{index}] is incomplete")
        try:
            if re.search(pattern, literal):
                return role
        except re.error as exc:
            raise ConfigurationError(
                f"Invalid regex in inventory.role_hints[{index}]: {exc}"
            ) from exc
    return None


def inventory_markdown(
    path: Path, role_hints: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    headings: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    numbering: Counter[str] = Counter()
    source_parts: list[dict[str, int]] = []
    image_count = 0
    table_line_count = 0
    wide_spacing_line_count = 0
    for index, line in enumerate(lines, start=1):
        heading = HEADING_RE.match(line)
        title = heading.group(2).strip() if heading else line.strip()
        if heading:
            headings.append({"line": index, "level": len(heading.group(1)), "title": title})
        label = LABEL_STEM_RE.match(title)
        if label:
            label_counts[label.group(1)] += 1
        elif heading and len(heading.group(1)) >= 4:
            heading_stem = HEADING_STEM_RE.match(title)
            if heading_stem:
                label_counts[heading_stem.group(1)] += 1
        numbered = NUMBER_PREFIX_RE.match(line)
        if numbered:
            prefix = numbered.group(1)
            numbering["circled" if prefix.startswith(tuple("①②③④⑤⑥⑦⑧⑨⑩")) else "arabic" if prefix[0].isdigit() else "chinese"] += 1
        marker = PAGE_MARKER_RE.search(line)
        if marker:
            source_parts.append({key: int(value) for key, value in marker.groupdict().items()})
        image_count += len(re.findall(r"!\[[^\]]*\]\([^)]+\)|<img\b", line, flags=re.IGNORECASE))
        table_line_count += int(line.count("|") >= 2)
        wide_spacing_line_count += int(bool(re.search(r"\S\s{4,}\S", line)))
    repeated = [
        {
            "literal": key,
            "count": count,
            "proposed_role": propose_role(key, role_hints),
            "status": "review_required",
        }
        for key, count in label_counts.most_common()
        if count >= 2
    ]
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "line_count": len(lines),
        "heading_count": len(headings),
        "headings": headings,
        "repeated_label_candidates": repeated,
        "numbering_counts": dict(numbering),
        "index_candidates": contiguous_index_runs(lines),
        "source_parts": source_parts,
        "layout_signals": {
            "image_count": image_count,
            "table_line_count": table_line_count,
            "wide_spacing_line_count": wide_spacing_line_count,
        },
    }


def build_inventory(profile_path: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    role_hints: list[dict[str, str]] = []
    preset_meta = profile.get("format", {}).get("preset")
    if preset_meta:
        preset = load_json(Path(str(preset_meta["path"])).resolve())
        configured_hints = preset.get("inventory", {}).get("role_hints", [])
        if not isinstance(configured_hints, list) or any(
            not isinstance(item, dict) for item in configured_hints
        ):
            raise ConfigurationError("Preset inventory.role_hints must be a list of objects")
        role_hints = configured_hints
    sources = []
    unresolved = 0
    layout_candidates: list[dict[str, Any]] = []
    hierarchy_candidates: list[dict[str, Any]] = []
    for source in profile["sources"]:
        markdown = Path(source["markdown_path"])
        if not markdown.is_file() and source.get("kind") == "md":
            markdown = Path(source["path"])
        if not markdown.is_file():
            sources.append({"role": source["role"], "status": "conversion_required", "markdown_path": str(markdown)})
            unresolved += 1
            continue
        detail = inventory_markdown(markdown, role_hints)
        detail["role"] = source["role"]
        detail["status"] = "review_required"
        unresolved += 1 + len(detail["repeated_label_candidates"]) + len(detail["index_candidates"])
        layout_candidates.append(
            {
                "role": source["role"],
                "signals": detail["layout_signals"],
                "candidates": ["single-column", "multi-column", "scanned-spread"],
                "classification": None,
                "reading_order": None,
                "status": "review_required",
            }
        )
        hierarchy_candidates.append(
            {
                "role": source["role"],
                "printed_index_candidates": detail["index_candidates"],
                "heading_count": detail["heading_count"],
                "primary_authority": None,
                "secondary_indexes": [],
                "no_toc_proposal_reviewed": False,
                "status": "review_required",
            }
        )
        sources.append(detail)
    return {
        "schema_version": 1,
        "stage": "format-inventory",
        "status": "review_required",
        "profile": profile["_profile_path"],
        "source_arrangement": (
            "combined"
            if any(source.get("role") == "combined" for source in profile["sources"])
            else "separate"
            if any(source.get("role") == "answers" for source in profile["sources"])
            else "question-only"
        ),
        "sources": sources,
        "layout_candidates": layout_candidates,
        "hierarchy_candidates": hierarchy_candidates,
        "unresolved_count": unresolved,
        "review_instructions": "Classify hierarchy authority, labels, numbering, layout, answer regions, and output paths in format-adapter.json.",
    }


def build_adapter_draft(profile_path: Path, inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a schema-shaped, deliberately unapproved adapter for focused review."""
    profile = load_profile(profile_path)
    inventory = inventory or build_inventory(profile_path)
    hierarchy_role = "combined" if profile["answers"]["mode"] == "embedded" else "questions"
    answer_role = "combined" if profile["answers"]["mode"] == "embedded" else "answers"
    source_detail = next(
        (item for item in inventory.get("sources", []) if item.get("role") == hierarchy_role),
        {},
    )
    draft = {
        "schema_version": 1,
        "status": "review_required",
        "reviewer_confirmed": False,
        "profile": profile["_profile_path"],
        "inventory_evidence": {
            "source_role": hierarchy_role,
            "markdown_sha256": source_detail.get("sha256"),
            "heading_count": source_detail.get("heading_count", 0),
            "index_candidate_count": len(source_detail.get("index_candidates", [])),
        },
        "hierarchy": {
            "source_role": hierarchy_role,
            "root_output": "index.md",
            "primary_authority": None,
            "entries": [],
        },
        "content": {
            "unknown_label_policy": "review",
            "question_folder": "questions",
            "question_patterns": [],
            "inline_question_patterns": [],
            "roles": [],
        },
        "answers": (
            {}
            if profile["answers"]["mode"] == "unavailable"
            else {
                "source_role": answer_role,
                "callout_title": "答案与解析",
                "contexts": [],
                "answer_patterns": [],
                "inline_answer_patterns": [],
                "ignore_ranges": [],
            }
        ),
        "review_items": [
            "Select a printed-TOC authority or provide a reviewed no-TOC decision.",
            "Confirm every hierarchy entry and exact source anchor.",
            "Confirm question patterns, functional roles, and output templates.",
            *(
                []
                if profile["answers"]["mode"] == "unavailable"
                else ["Confirm answer regions, raw-line context anchors, and answer patterns."]
            ),
        ],
    }
    preset_meta = profile.get("format", {}).get("preset")
    if preset_meta:
        preset_path = Path(str(preset_meta.get("path", ""))).resolve()
        if not preset_path.is_file() or sha256_file(preset_path) != preset_meta.get("sha256"):
            raise ConfigurationError("Frozen format preset is missing or changed")
        preset = load_json(preset_path)

        def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
            merged = dict(base)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = merge(merged[key], value)
                else:
                    merged[key] = value
            return merged

        draft = merge(draft, preset)
        draft["preset_evidence"] = preset_meta
        draft["status"] = "review_required"
        draft["reviewer_confirmed"] = False
        draft["profile"] = profile["_profile_path"]
    return draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory a supplementary-book Markdown corpus without publisher constants.")
    parser.add_argument("profile", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = build_inventory(args.profile)
        write_json_atomic(args.output, value, overwrite=args.overwrite)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "format-inventory", "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

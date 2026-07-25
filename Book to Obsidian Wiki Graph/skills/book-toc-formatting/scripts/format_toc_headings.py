#!/usr/bin/env python3
"""Align Markdown headings to an explicit book TOC manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")


class TocFormattingError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"[`*_~]", "", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip()


def validate_manifest(manifest: Any) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        raise TocFormattingError("TOC manifest must be a JSON object")
    if manifest.get("schema_version") != 1:
        raise TocFormattingError("TOC manifest schema_version must be 1")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise TocFormattingError("TOC manifest needs a non-empty entries array")
    keys: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TocFormattingError(f"TOC entry {index} must be an object")
        key = entry.get("key")
        title = entry.get("title")
        level = entry.get("level")
        if not isinstance(key, str) or not key:
            raise TocFormattingError(f"TOC entry {index} needs a key")
        if key in keys:
            raise TocFormattingError(f"Duplicate TOC key: {key}")
        keys.add(key)
        if not isinstance(title, str) or not normalize_title(title):
            raise TocFormattingError(f"TOC entry {key!r} needs a title")
        if level not in {1, 2, 3}:
            raise TocFormattingError(
                f"TOC entry {key!r} level must be 1, 2, or 3"
            )
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) for alias in aliases
        ):
            raise TocFormattingError(f"TOC entry {key!r} aliases must be strings")
        validated.append(entry)
    return validated


def excluded_lines(manifest: dict[str, Any]) -> set[int]:
    excluded: set[int] = set()
    ranges = manifest.get("toc_source_ranges", [])
    if not isinstance(ranges, list):
        raise TocFormattingError("toc_source_ranges must be an array")
    for index, item in enumerate(ranges):
        if not isinstance(item, dict):
            raise TocFormattingError(
                f"toc_source_ranges[{index}] must be an object"
            )
        start = item.get("start_line")
        end = item.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            raise TocFormattingError(
                f"toc_source_ranges[{index}] has an invalid line range"
            )
        excluded.update(range(start, end + 1))
    return excluded


def entry_titles(entry: dict[str, Any]) -> set[str]:
    return {
        normalize_title(value)
        for value in [entry["title"], *entry.get("aliases", [])]
    }


def format_headings(
    markdown: str,
    manifest: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    entries = validate_manifest(manifest)
    ignored_lines = excluded_lines(manifest)
    lines = markdown.splitlines()
    output: list[str] = []
    expected_index = 0
    active_toc_level = 3
    in_fence = False
    matched: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []

    for line_number, line in enumerate(lines, start=1):
        fence = FENCE_RE.match(line)
        if fence:
            in_fence = not in_fence
            output.append(line)
            continue
        match = None if in_fence or line_number in ignored_lines else HEADING_RE.match(line)
        if match is None:
            output.append(line)
            continue

        original_level = len(match.group(1))
        title = match.group(2).strip()
        normalized = normalize_title(title)
        expected = entries[expected_index] if expected_index < len(entries) else None

        if expected is not None and normalized in entry_titles(expected):
            level = expected["level"]
            output.append(f"{'#' * level} {title}")
            matched.append(
                {
                    "key": expected["key"],
                    "title": title,
                    "line": line_number,
                    "old_level": original_level,
                    "new_level": level,
                }
            )
            active_toc_level = level
            expected_index += 1
            continue

        later_match = next(
            (
                item
                for item in entries[expected_index + 1 :]
                if normalized in entry_titles(item)
            ),
            None,
        )
        if later_match is not None and expected is not None:
            raise TocFormattingError(
                f"TOC heading {expected['title']!r} is missing before "
                f"{later_match['title']!r} at line {line_number}"
            )

        new_level = min(6, max(4, active_toc_level + 1, original_level))
        output.append(f"{'#' * new_level} {title}")
        demoted.append(
            {
                "title": title,
                "line": line_number,
                "old_level": original_level,
                "new_level": new_level,
            }
        )

    if expected_index != len(entries):
        missing = [entry["title"] for entry in entries[expected_index:]]
        raise TocFormattingError(
            "Formatted Markdown is missing TOC headings: " + ", ".join(missing)
        )

    candidate = "\n".join(output)
    if markdown.endswith("\n"):
        candidate += "\n"
    report = {
        "toc_entries": len(entries),
        "matched_toc_headings": len(matched),
        "demoted_non_toc_headings": len(demoted),
        "matched": matched,
        "demoted": demoted,
    }
    return candidate, report


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
    parser.add_argument("source_markdown", type=Path)
    parser.add_argument("toc_manifest", type=Path)
    parser.add_argument("output_markdown", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = args.source_markdown.resolve()
        manifest_path = args.toc_manifest.resolve()
        output = args.output_markdown.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Source Markdown does not exist: {source}")
        if not manifest_path.is_file():
            raise FileNotFoundError(f"TOC manifest does not exist: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        expected_input_hash = manifest.get("input_markdown_sha256")
        actual_input_hash = sha256_file(source)
        if expected_input_hash != actual_input_hash:
            raise TocFormattingError(
                "Source Markdown hash does not match TOC manifest"
            )
        if args.profile:
            profile_path = args.profile.resolve()
            profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
            raw_profile = manifest.get("profile")
            if not isinstance(raw_profile, str) or Path(raw_profile).resolve() != profile_path:
                raise TocFormattingError(
                    "TOC manifest profile does not match --profile"
                )
            if manifest.get("source_sha256") != profile.get("source", {}).get(
                "sha256"
            ):
                raise TocFormattingError(
                    "TOC manifest source_sha256 does not match profile"
                )
        candidate, details = format_headings(
            source.read_text(encoding="utf-8-sig"),
            manifest,
        )
        atomic_write(output, candidate, args.overwrite)
        result = {
            "schema_version": 1,
            "stage": "book-toc-formatting",
            "status": "completed",
            "profile": manifest.get("profile"),
            "source_sha256": manifest.get("source_sha256"),
            "input_markdown": str(source),
            "input_markdown_sha256": actual_input_hash,
            "candidate_markdown": str(output),
            "candidate_markdown_sha256": sha256_file(output),
            **details,
        }
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        print(rendered)
        if args.report:
            atomic_write(args.report.resolve(), rendered + "\n", args.overwrite)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-toc-formatting",
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

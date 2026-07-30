#!/usr/bin/env python3
"""Build a reviewable TOC manifest from a printed-TOC block in raw Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
IMAGE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")
PAGE_SUFFIX_RE = re.compile(r"\s*(?:…+|\.{2,}|·{2,})\s*\d+\s*$")
CHAPTER_RE = re.compile(r"^(第[一二三四五六七八九十百千万\d]+章)\s*(.+)$")
SECTION_RE = re.compile(r"^\d+(?:\.\d+)+\s+")
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class TocPlanningError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_title(value: str) -> str:
    value = value.replace("\\*", "*")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def find_toc_range(lines: list[str]) -> tuple[int, int]:
    start_index: int | None = None
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match and normalize_title(match.group(1)) == "目录":
            start_index = index
            break
    if start_index is None:
        raise TocPlanningError("Could not find a Markdown heading named 目录")

    for index in range(start_index + 1, len(lines)):
        if HEADING_RE.match(lines[index]):
            return start_index + 1, index
    raise TocPlanningError("Could not find the first content heading after 目录")


def parse_range(value: str, line_count: int) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+):(\d+)", value)
    if not match:
        raise TocPlanningError("--toc-range must use START:END line numbers")
    start, end = (int(item) for item in match.groups())
    if start < 1 or end < start or end > line_count:
        raise TocPlanningError("--toc-range is outside the source Markdown")
    return start, end


def extract_entries(lines: list[str], start_line: int, end_line: int) -> list[str]:
    entries: list[str] = []
    fragments: list[str] = []

    for raw_line in lines[start_line:end_line]:
        line = normalize_title(raw_line)
        if not line or IMAGE_RE.match(line):
            continue
        if HEADING_RE.match(line):
            continue
        fragments.append(line)
        if PAGE_SUFFIX_RE.search(line):
            joined = fragments[0]
            for fragment in fragments[1:]:
                separator = "" if joined.endswith(("、", "，", "；", "：")) else " "
                joined += separator + fragment
            joined = normalize_title(joined)
            title = PAGE_SUFFIX_RE.sub("", joined).strip()
            if title:
                entries.append(title)
            fragments = []

    if fragments:
        raise TocPlanningError(
            "Printed TOC ended with an entry that has no page-number suffix: "
            + " ".join(fragments)
        )
    if not entries:
        raise TocPlanningError("No printed TOC entries were extracted")
    return entries


def classify(title: str) -> tuple[int, str]:
    if CHAPTER_RE.match(title):
        return 1, "knowledge"
    if title.startswith("数学建模 "):
        return 1, "method"
    if "索引" in title or "词汇表" in title:
        return 1, "root"
    if title.startswith("复习参考题"):
        return 2, "exercise"
    if title.startswith(("阅读与思考 ", "文献阅读与数学写作")):
        return 2, "reading"
    if title.startswith("探究与发现 "):
        # In textbook TOCs this label normally introduces mathematical content
        # to be discovered (a property, relation, or model), not a reusable
        # problem-solving method. Keep it in the knowledge reading path.
        return 2, "knowledge"
    if title.startswith("信息技术应用 "):
        return 2, "tool"
    if SECTION_RE.match(title) or title == "小结":
        return 2, "knowledge"
    return 2, "knowledge"


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
    return f"{value or '未命名目录项'}.md"


def build_manifest(
    source: Path,
    profile_path: Path,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    source_sha = profile.get("source", {}).get("sha256")
    if not isinstance(source_sha, str) or not source_sha:
        raise TocPlanningError("Profile is missing source.sha256")

    lines = source.read_text(encoding="utf-8-sig").splitlines()
    titles = extract_entries(lines, start_line, end_line)
    entries: list[dict[str, Any]] = []
    active_chapter: str | None = None

    for index, title in enumerate(titles, start=1):
        level, category = classify(title)
        chapter_match = CHAPTER_RE.match(title)
        if chapter_match:
            active_chapter = chapter_match.group(1)

        aliases: list[str] = []
        if chapter_match:
            aliases.append(chapter_match.group(2).strip())
        elif title.startswith("数学建模 "):
            aliases.append(title.removeprefix("数学建模 ").strip())

        filename_title = title
        if title == "小结" and active_chapter:
            filename_title = f"{active_chapter} 小结"
        entries.append(
            {
                "key": f"toc-{index:03d}",
                "title": title,
                "level": level,
                "category": category,
                "filename": safe_filename(filename_title),
                "aliases": aliases,
            }
        )

    return {
        "schema_version": 1,
        "profile": str(profile_path),
        "source_sha256": source_sha,
        "input_markdown_sha256": sha256_file(source),
        "toc_source_ranges": [
            {"start_line": start_line, "end_line": end_line}
        ],
        "entries": entries,
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
    parser.add_argument("source_markdown", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument(
        "--toc-range",
        help="Override automatic detection with one-based START:END line numbers",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = args.source_markdown.resolve()
        profile = args.profile.resolve()
        output = args.output_manifest.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Source Markdown does not exist: {source}")
        if not profile.is_file():
            raise FileNotFoundError(f"Profile does not exist: {profile}")
        lines = source.read_text(encoding="utf-8-sig").splitlines()
        if args.toc_range:
            start_line, end_line = parse_range(args.toc_range, len(lines))
        else:
            start_line, end_line = find_toc_range(lines)
        manifest = build_manifest(source, profile, start_line, end_line)
        rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        atomic_write(output, rendered, args.overwrite)
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-toc-manifest-planning",
                    "status": "review_required",
                    "manifest": str(output),
                    "toc_source_range": {
                        "start_line": start_line,
                        "end_line": end_line,
                    },
                    "entry_count": len(manifest["entries"]),
                    "category_counts": {
                        category: sum(
                            1
                            for item in manifest["entries"]
                            if item["category"] == category
                        )
                        for category in sorted(
                            {item["category"] for item in manifest["entries"]}
                        )
                    },
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
                    "stage": "book-toc-manifest-planning",
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

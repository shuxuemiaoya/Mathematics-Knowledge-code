"""Deterministic stage-one Markdown segmentation for MathOS."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


STAGE_NAME = "segmentation-stage1"
SKILL_NAME = "skills/mathos-segmentation-stage1"
SCRIPT_COMMAND = r".\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py"
HEADING_RE = re.compile(r"^(#{1,6})\s+((\d+(?:\.\d+)*)\s+(.+?))\s*$")
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class SegmentationError(Exception):
    """Raised when stage-one segmentation cannot continue safely."""


@dataclass(frozen=True)
class Heading:
    marker: str
    markdown_depth: int
    number: str
    number_depth: int
    title: str
    full_title: str
    line_index: int
    char_start: int
    char_end: int

    @property
    def depth(self) -> int:
        return self.markdown_depth


def extract_numbered_headings(markdown: str) -> list[Heading]:
    headings: list[Heading] = []
    char_offset = 0

    for line_index, line in enumerate(markdown.splitlines(keepends=True)):
        line_text = line.rstrip("\r\n")
        match = HEADING_RE.match(line_text)
        if match:
            marker, full_title, number, title = match.groups()
            headings.append(
                Heading(
                    marker=marker,
                    markdown_depth=len(marker),
                    number=number,
                    number_depth=number.count(".") + 1,
                    title=title,
                    full_title=full_title,
                    line_index=line_index,
                    char_start=char_offset,
                    char_end=char_offset + len(line),
                )
            )
        char_offset += len(line)

    return headings


def select_target_depth(headings: list[Heading], requested_depth: int | None) -> int:
    if not headings:
        raise SegmentationError("No numbered headings detected")

    if requested_depth is None:
        return max(heading.number_depth for heading in headings)

    if not any(heading.number_depth == requested_depth for heading in headings):
        raise SegmentationError(f"Target depth {requested_depth} produced zero segments")

    return requested_depth


@dataclass(frozen=True)
class SegmentPlan:
    heading: Heading
    link_title: str
    filename: str
    output_path: Path
    char_start: int
    char_end: int
    byte_count: int
    warning: str = ""


@dataclass(frozen=True)
class SegmentationPlan:
    source_path: Path
    vault_root: Path
    sandbox_dir: Path
    master_path: Path
    target_depth: int
    detected_number_depths: list[int]
    headings: list[Heading]
    segments: list[SegmentPlan]
    disambiguations: list[dict[str, str]]
    warnings: list[str]
    source_sha256: str
    next_command: str


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def quote_command(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def safe_filename(stem: str) -> str:
    cleaned = INVALID_FILENAME_CHARS_RE.sub("_", stem).strip().rstrip(" .")
    return cleaned or "segment"


def disambiguate_filenames(link_titles: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    seen: dict[str, int] = {}
    filenames: list[str] = []
    disambiguations: list[dict[str, str]] = []

    for link_title in link_titles:
        base = safe_filename(link_title)
        key = base.casefold()
        count = seen.get(key, 0) + 1
        seen[key] = count
        final_stem = base if count == 1 else f"{base} - {count:02d}"
        if final_stem != base:
            disambiguations.append({"original": f"{base}.md", "final": f"{final_stem}.md"})
        filenames.append(f"{final_stem}.md")

    return filenames, disambiguations


def build_segment_command(source_path: Path, vault_root: Path, target_depth: int | None) -> str:
    command = (
        f"python {SCRIPT_COMMAND} segment {quote_command(source_path.resolve())} "
        f"--vault-root {quote_command(vault_root.resolve())}"
    )
    if target_depth is not None:
        command += f" --target-depth {target_depth}"
    return command + " --yes"


def build_segmentation_plan(source_path: Path, vault_root: Path, target_depth: int | None = None) -> SegmentationPlan:
    source_path = source_path.expanduser().resolve()
    vault_root = vault_root.expanduser().resolve()

    if not source_path.exists() or not source_path.is_file():
        raise SegmentationError(f"Source file missing: {source_path}")
    if source_path.suffix.lower() != ".md":
        raise SegmentationError(f"Source file is not Markdown: {source_path}")
    if not vault_root.exists() or not vault_root.is_dir():
        raise SegmentationError(f"Invalid vault root: {vault_root}")
    if not is_relative_to(source_path, vault_root):
        raise SegmentationError(f"Source path {source_path} is not under vault root {vault_root}")

    markdown = source_path.read_text(encoding="utf-8")
    if not markdown.strip():
        raise SegmentationError(f"Source file is empty: {source_path}")

    headings = extract_numbered_headings(markdown)
    selected_depth = select_target_depth(headings, target_depth)
    detected_depths = sorted({heading.number_depth for heading in headings})
    target_headings = [heading for heading in headings if heading.number_depth == selected_depth]
    if not target_headings:
        raise SegmentationError(f"Target depth {selected_depth} produced zero segments")

    sandbox_dir = source_path.with_suffix("")
    master_path = sandbox_dir / f"000_{source_path.stem}目录.md"
    link_titles = [heading.full_title for heading in target_headings]
    filenames, disambiguations = disambiguate_filenames(link_titles)

    segments: list[SegmentPlan] = []
    warnings: list[str] = []
    for index, heading in enumerate(target_headings):
        next_start = len(markdown)
        for later_heading in headings:
            if later_heading.char_start <= heading.char_start:
                continue
            if later_heading.number_depth <= selected_depth:
                next_start = later_heading.char_start
                break
        raw_slice = markdown[heading.char_start:next_start]
        if not raw_slice.strip():
            raise SegmentationError(f"Planned segment is empty: {heading.full_title}")

        warning = ""
        if len(raw_slice) > 200_000:
            warning = f"Large segment: {heading.full_title} ({len(raw_slice)} characters)"
            warnings.append(warning)

        segments.append(
            SegmentPlan(
                heading=heading,
                link_title=link_titles[index],
                filename=filenames[index],
                output_path=sandbox_dir / filenames[index],
                char_start=heading.char_start,
                char_end=next_start,
                byte_count=len(raw_slice.encode("utf-8")),
                warning=warning,
            )
        )

    return SegmentationPlan(
        source_path=source_path,
        vault_root=vault_root,
        sandbox_dir=sandbox_dir,
        master_path=master_path,
        target_depth=selected_depth,
        detected_number_depths=detected_depths,
        headings=headings,
        segments=segments,
        disambiguations=disambiguations,
        warnings=warnings,
        source_sha256=sha256_text(markdown),
        next_command=build_segment_command(source_path, vault_root, target_depth),
    )


def render_master_directory(plan: SegmentationPlan) -> str:
    lines = ["# 目录", ""]
    for segment in plan.segments:
        lines.append(f"- [[{Path(segment.filename).stem}]]")
    return "\n".join(lines).rstrip() + "\n"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_segmentation_package(plan: SegmentationPlan, overwrite: bool = False) -> dict[str, Any]:
    markdown = plan.source_path.read_text(encoding="utf-8")
    before_file_hash = file_sha256(plan.source_path)
    if sha256_text(markdown) != plan.source_sha256:
        raise SegmentationError("Original source hash changed before writing")
    if plan.sandbox_dir.exists():
        if not overwrite:
            raise SegmentationError(f"Output sandbox folder already exists: {plan.sandbox_dir}")
        if not plan.sandbox_dir.is_dir():
            raise SegmentationError(f"Output sandbox path exists and is not a directory: {plan.sandbox_dir}")
        shutil.rmtree(plan.sandbox_dir)

    plan.sandbox_dir.mkdir(parents=True, exist_ok=False)
    plan.master_path.write_text(render_master_directory(plan), encoding="utf-8")
    for segment in plan.segments:
        raw_slice = markdown[segment.char_start:segment.char_end]
        if not raw_slice.strip():
            raise SegmentationError(f"Refusing to write empty segment: {segment.link_title}")
        segment.output_path.write_text(raw_slice, encoding="utf-8")

    after_file_hash = file_sha256(plan.source_path)
    if after_file_hash != before_file_hash:
        raise SegmentationError("Original source hash changed during writing")
    return {"status": "written", "sandbox_dir": str(plan.sandbox_dir), "master_path": str(plan.master_path)}

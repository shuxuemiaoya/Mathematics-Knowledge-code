from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mathos_common import _extract_protected_blocks, _line_in_blocks, _write_text_artifact
from step1_toc_extraction import VerbatimToc


BODY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class ExtractedHeading:
    level: int
    text: str
    raw_line: str
    line_number: int


def extract_body_headings(markdown: str, toc_start_line: int, toc_end_line: int) -> list[ExtractedHeading]:
    lines = markdown.splitlines()
    protected_blocks = _extract_protected_blocks(lines)
    headings: list[ExtractedHeading] = []
    for line_number, line in enumerate(lines, start=1):
        if toc_start_line <= line_number <= toc_end_line:
            continue
        if _line_in_blocks(line_number, protected_blocks, {"code_fence", "math_block"}):
            continue
        match = BODY_HEADING_RE.match(line)
        if match is not None:
            headings.append(ExtractedHeading(len(match.group(1)), match.group(2), line, line_number))
    return headings


def build_toc_and_headings_markdown(toc_markdown: str, headings: list[ExtractedHeading]) -> str:
    heading_lines = "\n".join(f"{heading.line_number}: {heading.raw_line}" for heading in headings)
    return (
        "<!-- BEGIN IMMUTABLE TOC -->\n"
        f"{toc_markdown.rstrip()}\n"
        "<!-- END IMMUTABLE TOC -->\n\n"
        f"<!-- BODY HEADING COUNT: {len(headings)} -->\n"
        "<!-- BEGIN BODY HEADINGS -->\n"
        f"{heading_lines}\n"
        "<!-- END BODY HEADINGS -->\n"
    )


def run_heading_extraction(
    markdown: str,
    toc: VerbatimToc,
    work_dir: Path,
    artifacts: dict[str, Path],
) -> str:
    headings = extract_body_headings(markdown, toc.start_line, toc.end_line)
    payload = build_toc_and_headings_markdown(toc.markdown, headings)
    artifacts["toc_and_headings"] = _write_text_artifact(work_dir / "toc_and_headings.md", payload)
    return payload

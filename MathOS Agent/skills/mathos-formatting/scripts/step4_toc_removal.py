from __future__ import annotations

from pathlib import Path

from mathos_common import FormattingError
from step1_toc_extraction import VerbatimToc


def remove_toc_span(markdown: str, start_line: int, end_line: int) -> str:
    lines = markdown.splitlines(keepends=True)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise FormattingError("validated TOC span is outside the processed document")
    return "".join(lines[: start_line - 1] + lines[end_line:])


def run_toc_removal(markdown: str, toc: VerbatimToc, candidate_path: Path) -> str:
    stripped = remove_toc_span(markdown, toc.start_line, toc.end_line)
    candidate_path.write_text(stripped, encoding="utf-8")
    return stripped

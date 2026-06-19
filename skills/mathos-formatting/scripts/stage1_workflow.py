from __future__ import annotations

import json
import re
from dataclasses import dataclass

from mathos_common import (
    CHINESE_CHAPTER_RE,
    ENGLISH_CHAPTER_RE,
    FormattingError,
    TOC_ENTRY_PAGE_RE,
    TOC_HEADING_RE,
    _extract_protected_blocks,
    _line_in_blocks,
    parse_json_artifact_from_text,
)


NUMBERED_LINE_RE = re.compile(r"^(\d+):(?: (.*))?$")
BODY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PARENT_CONTEXT_RE = re.compile(
    r"^(?:\s*\d+(?:[.．]\d+)+\s+|"
    r"\s*第\s*[一二三四五六七八九十百千万零〇两0-9]+\s*[章节篇部单元]\s*|"
    r"\s*(?:Part|Chapter|Section)\s+[A-Z0-9IVXLC]+\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VerbatimToc:
    start_line: int
    end_line: int
    markdown: str


@dataclass(frozen=True)
class ExtractedHeading:
    level: int
    text: str
    raw_line: str
    line_number: int


def _parse_numbered_lines(text: str, label: str) -> list[tuple[int, str]]:
    parsed: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        match = NUMBERED_LINE_RE.match(raw_line)
        if match is None:
            raise FormattingError(f"{label} must contain only unchanged numbered lines")
        parsed.append((int(match.group(1)), match.group(2) or ""))
    if not parsed:
        raise FormattingError(f"{label} is empty")
    return parsed


def _looks_like_toc_line(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped
        and (
            TOC_HEADING_RE.match(stripped)
            or TOC_ENTRY_PAGE_RE.search(stripped)
            or re.match(r"^(?:#{1,6}\s+)?\d+(?:[.．]\d+)+\s+.+", stripped)
        )
    )


def validate_verbatim_toc_response(numbered_sample: str, response: str) -> VerbatimToc:
    sample_lines = _parse_numbered_lines(numbered_sample, "first-20-page sample")
    response_lines = _parse_numbered_lines(response.strip(), "TOC response")
    sample_by_number = dict(sample_lines)
    response_numbers = [line_number for line_number, _ in response_lines]
    expected_numbers = list(range(response_numbers[0], response_numbers[-1] + 1))
    if response_numbers != expected_numbers:
        raise FormattingError("TOC response must be one contiguous source span")
    for line_number, line in response_lines:
        if sample_by_number.get(line_number) != line:
            raise FormattingError(f"TOC response is not verbatim at source line {line_number}")
    toc_lines: list[str] = []
    seen_heading_titles: set[str] = set()
    in_details = False
    for _, line in response_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^<details(?:\s|>)", stripped, flags=re.IGNORECASE):
            in_details = True
            continue
        if in_details:
            if re.match(r"^</details\s*>", stripped, flags=re.IGNORECASE):
                in_details = False
            continue
        if re.match(r"^!\[[^]]*]\([^)]+\)$", stripped):
            continue
        if not toc_lines:
            if not TOC_HEADING_RE.match(stripped):
                raise FormattingError("TOC response contains unrelated text before the TOC heading")
            toc_lines.append(line)
            continue
        heading_match = BODY_HEADING_RE.match(line)
        if heading_match is not None:
            heading_key = TOC_ENTRY_PAGE_RE.sub("", heading_match.group(2)).strip().casefold()
            if heading_key in seen_heading_titles:
                raise FormattingError("TOC response contains unrelated repeated body heading text")
            seen_heading_titles.add(heading_key)
            toc_lines.append(line)
            continue
        if _looks_like_toc_line(line):
            toc_lines.append(line)
            continue
        raise FormattingError("TOC response contains unrelated text outside the TOC entries")
    if in_details:
        raise FormattingError("TOC response ends inside an incomplete details block")
    if len(toc_lines) < 2:
        raise FormattingError("TOC response is incomplete because it has no TOC entries")
    previous_line = sample_by_number.get(response_numbers[0] - 1, "")
    next_line = sample_by_number.get(response_numbers[-1] + 1, "")
    if _looks_like_toc_line(previous_line) or _looks_like_toc_line(next_line):
        raise FormattingError("TOC response appears incomplete because an adjacent TOC line was omitted")
    markdown = "\n".join(toc_lines) + "\n"
    return VerbatimToc(response_numbers[0], response_numbers[-1], markdown)


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
        if match is None:
            continue
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


def _has_added_parent_context(before_text: str, after_text: str) -> bool:
    before_has_context = bool(
        CHINESE_CHAPTER_RE.search(before_text)
        or ENGLISH_CHAPTER_RE.search(before_text)
        or PARENT_CONTEXT_RE.search(before_text)
    )
    after_has_context = bool(
        CHINESE_CHAPTER_RE.search(after_text)
        or ENGLISH_CHAPTER_RE.search(after_text)
        or PARENT_CONTEXT_RE.search(after_text)
    )
    return after_has_context and not before_has_context


def validate_heading_processor_result(before: str, after: str) -> list[str]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    if len(before_lines) != len(after_lines):
        raise FormattingError("heading processor changed line count")
    protected_blocks = _extract_protected_blocks(before_lines)
    for line_number, (before_line, after_line) in enumerate(zip(before_lines, after_lines), start=1):
        if _line_in_blocks(line_number, protected_blocks, {"code_fence", "math_block"}):
            if before_line != after_line:
                raise FormattingError(f"heading processor changed a protected block at line {line_number}")
            continue
        before_heading = BODY_HEADING_RE.match(before_line)
        after_heading = BODY_HEADING_RE.match(after_line)
        if before_heading is None:
            if before_line != after_line:
                raise FormattingError(f"heading processor changed non-heading content at line {line_number}")
            continue
        if after_heading is None:
            raise FormattingError(f"heading processor removed or split a heading at line {line_number}")
        if _has_added_parent_context(before_heading.group(2), after_heading.group(2)):
            raise FormattingError(f"heading processor added parent context at line {line_number}")
    return ["Stage 1 processor preserved line count, heading order, and non-heading content"]


def remove_toc_span(markdown: str, start_line: int, end_line: int) -> str:
    lines = markdown.splitlines(keepends=True)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise FormattingError("validated TOC span is outside the processed document")
    return "".join(lines[: start_line - 1] + lines[end_line:])


def validate_heading_check_response(response: str, expected_heading_count: int) -> list[str]:
    try:
        payload = json.loads(parse_json_artifact_from_text(response))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise FormattingError(f"heading validation returned invalid JSON: {exc}") from exc
    valid = payload.get("valid")
    checked_count = payload.get("checked_heading_count")
    errors = payload.get("errors")
    if not isinstance(valid, bool):
        raise FormattingError("heading validation valid must be a boolean")
    if not isinstance(checked_count, int) or isinstance(checked_count, bool):
        raise FormattingError("heading validation checked_heading_count must be an integer")
    if not isinstance(errors, list) or not all(isinstance(error, str) for error in errors):
        raise FormattingError("heading validation errors must be a string list")
    if checked_count != expected_heading_count:
        raise FormattingError(
            f"heading validation count mismatch: expected {expected_heading_count}, got {checked_count}"
        )
    if not valid or errors:
        details = "; ".join(errors) if errors else "valid was false"
        raise FormattingError(f"DeepSeek heading validation rejected the candidate: {details}")
    return [f"DeepSeek heading validation passed for {checked_count} headings"]

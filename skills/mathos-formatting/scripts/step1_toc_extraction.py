from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mathos_common import (
    FormattingError,
    TOC_ENTRY_PAGE_RE,
    TOC_HEADING_RE,
    _write_text_artifact,
    extract_first_20_pages,
)


NUMBERED_LINE_RE = re.compile(r"^(\d+):(?: (.*))?$")
ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TOC_TRAILING_REFERENCE_RE = re.compile(
    r"(?:\bP\d+(?:\s+T\d+)?|(?:→|\\rightarrow)\s*大招\s*\d+)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VerbatimToc:
    start_line: int
    end_line: int
    markdown: str


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


def _has_toc_reference(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped
        and (
            TOC_ENTRY_PAGE_RE.search(stripped)
            or TOC_TRAILING_REFERENCE_RE.search(stripped)
        )
    )


def _looks_like_toc_line(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped
        and (
            TOC_HEADING_RE.match(stripped)
            or _has_toc_reference(stripped)
            or re.match(r"^(?:#{1,6}\s+)?\d+(?:[.．]\d+)+\s+.+", stripped)
        )
    )


def _next_semantic_line(
    response_lines: list[tuple[int, str]],
    start_index: int,
    stop_index: int | None = None,
) -> tuple[int, str] | None:
    end_index = len(response_lines) if stop_index is None else stop_index
    in_details = False
    for index in range(start_index, end_index):
        _, line = response_lines[index]
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
        return index, line
    return None


def _has_following_toc_evidence(
    response_lines: list[tuple[int, str]],
    start_index: int,
    stop_index: int | None = None,
) -> bool:
    next_semantic = _next_semantic_line(response_lines, start_index, stop_index)
    while next_semantic is not None:
        index, line = next_semantic
        stripped = line.strip()
        if TOC_HEADING_RE.match(stripped) or ATX_HEADING_RE.match(line):
            next_semantic = _next_semantic_line(response_lines, index + 1, stop_index)
            continue
        if _looks_like_toc_line(line):
            return True
        continuation = _next_semantic_line(response_lines, index + 1, stop_index)
        return continuation is not None and _has_toc_reference(continuation[1])
    return False


def _first_toc_anchor_index(response_lines: list[tuple[int, str]]) -> int | None:
    for index, (_, line) in enumerate(response_lines):
        if TOC_HEADING_RE.match(line.strip()):
            return index
    return None


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
    first_anchor_index = _first_toc_anchor_index(response_lines)
    if first_anchor_index is None:
        raise FormattingError("TOC response must contain a recognized TOC heading anchor")
    toc_lines: list[str] = []
    seen_heading_titles: set[str] = set()
    seen_semantic_toc_line = False
    in_details = False
    for index, (_, line) in enumerate(response_lines):
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
        if TOC_HEADING_RE.match(stripped):
            toc_lines.append(line)
            seen_semantic_toc_line = True
            continue
        heading_match = ATX_HEADING_RE.match(line)
        if heading_match is not None:
            evidence_stop = first_anchor_index if index < first_anchor_index else None
            if not _has_toc_reference(line) and not _has_following_toc_evidence(
                response_lines, index + 1, evidence_stop
            ):
                raise FormattingError("TOC response contains unrelated body text in a heading")
            heading_key = TOC_ENTRY_PAGE_RE.sub("", heading_match.group(2)).strip().casefold()
            if heading_key in seen_heading_titles:
                raise FormattingError("TOC response contains unrelated repeated body heading text")
            seen_heading_titles.add(heading_key)
            toc_lines.append(line)
            seen_semantic_toc_line = True
            continue
        if _looks_like_toc_line(line):
            toc_lines.append(line)
            seen_semantic_toc_line = True
            continue
        evidence_stop = first_anchor_index if index < first_anchor_index else None
        next_semantic = _next_semantic_line(response_lines, index + 1, evidence_stop)
        if (
            seen_semantic_toc_line
            and next_semantic is not None
            and _has_toc_reference(next_semantic[1])
        ):
            toc_lines.append(line)
            seen_semantic_toc_line = True
            continue
        if next_semantic is None:
            raise FormattingError("TOC response ends with an unfinished wrapped TOC entry")
        raise FormattingError("TOC response contains unrelated body text outside the TOC entries")
    if in_details:
        raise FormattingError("TOC response ends inside an incomplete details block")
    if len(toc_lines) < 2:
        raise FormattingError("TOC response is incomplete because it has no TOC entries")
    previous_line = sample_by_number.get(response_numbers[0] - 1, "")
    next_line = sample_by_number.get(response_numbers[-1] + 1, "")
    if _looks_like_toc_line(previous_line) or _looks_like_toc_line(next_line):
        raise FormattingError("TOC response appears incomplete because an adjacent TOC line was omitted")
    return VerbatimToc(response_numbers[0], response_numbers[-1], "\n".join(toc_lines) + "\n")


def run_toc_extraction(
    markdown_path: Path,
    markdown: str,
    provider_client: object,
    work_dir: Path,
    artifacts: dict[str, Path],
    timeout_seconds: int,
) -> VerbatimToc:
    prompt_path = Path(__file__).resolve().parent.parent / "agents" / "step1_toc_detection_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    sample = extract_first_20_pages(markdown, markdown_path)
    artifacts["toc_detection_prompt"] = _write_text_artifact(
        work_dir / "step1_toc_detection_prompt.md", prompt
    )
    artifacts["toc_detection_sample"] = _write_text_artifact(work_dir / "toc_detection_sample.md", sample)
    response = provider_client.chat(prompt, sample, timeout_seconds=timeout_seconds, response_format=None)
    artifacts["toc_detection_response"] = _write_text_artifact(work_dir / "toc_detection_response.md", response)
    toc = validate_verbatim_toc_response(sample, response)
    artifacts["toc"] = _write_text_artifact(work_dir / "toc.md", toc.markdown)
    return toc

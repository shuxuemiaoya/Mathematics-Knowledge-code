from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mathos_common import (
    CHINESE_CHAPTER_RE,
    ENGLISH_CHAPTER_RE,
    FormattingError,
    _extract_protected_blocks,
    _line_in_blocks,
    _write_text_artifact,
    parse_python_source_artifact,
    run_batch_processor_in_sandbox,
    validate_batch_processor_source,
)
from reporting import write_review_report
from step2_heading_extraction import BODY_HEADING_RE


PARENT_CONTEXT_RE = re.compile(
    r"^(?:\s*\d+(?:[.．]\d+)+\s+|"
    r"\s*第\s*[一二三四五六七八九十百千万零〇两0-9]+\s*[章节篇部单元]\s*|"
    r"\s*(?:Part|Chapter|Section)\s+[A-Z0-9IVXLC]+\b)",
    re.IGNORECASE,
)

EXPECTED_RESULT_SECTIONS = (
    "# 修改后的目录",
    "# 标题修改明细",
    "# 预期效果",
)


class HeadingExpectedResultError(FormattingError):
    def __init__(self, message: str, artifact_path: Path):
        super().__init__(message)
        self.error_artifact = artifact_path


@dataclass(frozen=True)
class HeadingProcessingResult:
    markdown: str
    summary: list[str]
    script_path: Path


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


def validate_heading_expected_result(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise FormattingError("heading expected result is empty")
    if "```" in stripped or "~~~" in stripped:
        raise FormattingError("heading expected result must not contain Markdown fences")
    if stripped.startswith(("{", "[")):
        raise FormattingError("heading expected result must not be JSON")
    if re.search(r"(?m)^(?:import\s+|from\s+\S+\s+import\s+|def\s+\w+\s*\()", stripped):
        raise FormattingError("heading expected result must not contain Python")

    h1_sections = re.findall(r"(?m)^# [^#\r\n].*$", stripped)
    if h1_sections != list(EXPECTED_RESULT_SECTIONS):
        raise FormattingError(
            "heading expected result must contain exactly the three required sections in order"
        )
    for index, section in enumerate(EXPECTED_RESULT_SECTIONS):
        start = stripped.index(section) + len(section)
        end = stripped.index(EXPECTED_RESULT_SECTIONS[index + 1]) if index + 1 < len(EXPECTED_RESULT_SECTIONS) else len(stripped)
        if not stripped[start:end].strip():
            raise FormattingError(f"heading expected result section is empty: {section}")
    return text


def _ensure_heading_expected_result(
    heading_payload: str,
    provider_client: object,
    work_dir: Path,
    artifacts: dict[str, Path],
    timeout_seconds: int,
) -> Path:
    path = work_dir / "heading_expected_result.md"
    if path.exists():
        try:
            validate_heading_expected_result(path.read_text(encoding="utf-8"))
            artifacts["heading_expected_result"] = path
            return path
        except FormattingError:
            pass

    prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_expected_result_prompt.md"
    response = provider_client.chat(
        prompt_path.read_text(encoding="utf-8"),
        heading_payload,
        timeout_seconds=timeout_seconds,
        response_format=None,
    )
    artifacts["heading_expected_result"] = _write_text_artifact(path, response)
    try:
        validate_heading_expected_result(response)
    except FormattingError as exc:
        raise HeadingExpectedResultError(str(exc), path) from exc
    return path


def run_heading_processing(
    markdown_path: Path,
    original_text: str,
    heading_payload: str,
    heading_prompt: str,
    provider_client: object,
    work_dir: Path,
    candidate_path: Path,
    artifacts: dict[str, Path],
    timeout_seconds: int,
) -> HeadingProcessingResult:
    script_path = work_dir / "heading_processor.py"
    if script_path.exists():
        source = script_path.read_text(encoding="utf-8")
        validate_batch_processor_source(source)
        artifacts["heading_script"] = script_path
    else:
        artifacts["heading_prompt"] = _write_text_artifact(
            work_dir / "heading_processor_prompt.md", heading_prompt
        )
        response = provider_client.chat(
            heading_prompt, heading_payload, timeout_seconds=timeout_seconds, response_format=None
        )
        artifacts["heading_response"] = _write_text_artifact(
            work_dir / "heading_processor_response.py", response
        )
        source = parse_python_source_artifact(response)
        validate_batch_processor_source(source)
        artifacts["heading_script"] = _write_text_artifact(script_path, source)
    _ensure_heading_expected_result(
        heading_payload,
        provider_client,
        work_dir,
        artifacts,
        timeout_seconds,
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    processed = run_batch_processor_in_sandbox(script_path, original_text, work_dir, "step3-heading-processing")
    summary = validate_heading_processor_result(original_text, processed)
    candidate_path.write_text(processed, encoding="utf-8")
    artifacts["stage1_report"] = write_review_report(
        original_path=markdown_path,
        candidate_path=candidate_path,
        report_path=work_dir / "stage1_heading_report.md",
        heading_summary=["heading_processor.py", "heading_expected_result.md", *summary],
        plugin_summary=[],
        warnings=[],
    )
    return HeadingProcessingResult(processed, summary, script_path)

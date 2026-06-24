from __future__ import annotations

import json
import re
from pathlib import Path

from mathos_common import FormattingError, _write_text_artifact, parse_json_artifact_from_text
from step1_toc_extraction import VerbatimToc
from step2_heading_extraction import build_toc_and_headings_markdown, extract_body_headings

MAX_HEADING_CHECK_ERRORS = 20
SELF_NEGATING_ERROR_MARKERS = (
    "not an error",
    "isn't an error",
    "不是错误",
    "并非错误",
    "不算错误",
    "不属于错误",
)


def extract_h1_h3_headings(text: str) -> list[tuple[int, str]]:
    """Extracts H1-H3 headings from text.
    Returns a list of tuples: (level, text_content).
    """
    headings = []
    lines = text.splitlines()
    from mathos_common import _extract_protected_blocks, _line_in_blocks
    protected_blocks = _extract_protected_blocks(lines)
    
    for line_number, line in enumerate(lines, start=1):
        if _line_in_blocks(line_number, protected_blocks, {"code_fence", "math_block"}):
            continue
        cleaned = line.strip().replace('`', '')
        # Match H1-H3 heading
        match = re.search(r'(?:^|[\s*-])(#{1,3})\s+(.+?)\s*$', cleaned)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((level, title))
    return headings


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
    contradictory_errors = [
        error
        for error in errors
        if any(marker in error.casefold() for marker in SELF_NEGATING_ERROR_MARKERS)
    ]
    if contradictory_errors:
        raise FormattingError(
            "heading validation response is internally contradictory: "
            "errors must contain genuine violations only"
        )
    if len(errors) != len(set(errors)):
        raise FormattingError("heading validation errors must be unique")
    if len(errors) > MAX_HEADING_CHECK_ERRORS:
        raise FormattingError(
            f"heading validation errors must contain at most {MAX_HEADING_CHECK_ERRORS} entries"
        )
    if checked_count != expected_heading_count:
        raise FormattingError(f"heading validation count mismatch: expected {expected_heading_count}, got {checked_count}")
    if not valid or errors:
        details = "; ".join(errors) if errors else "valid was false"
        raise FormattingError(f"DeepSeek heading validation rejected the candidate: {details}")
    return [f"DeepSeek heading validation passed for {checked_count} headings"]


def run_heading_validation(
    markdown: str,
    toc: VerbatimToc,
    provider_client: object,
    work_dir: Path,
    artifacts: dict[str, Path],
    timeout_seconds: int,
) -> list[str]:
    # 1. Write heading_check_input.md for compatibility
    headings = extract_body_headings(markdown, 0, -1)
    payload = build_toc_and_headings_markdown(toc.markdown, headings)
    artifacts["heading_check_input"] = _write_text_artifact(work_dir / "heading_check_input.md", payload)

    # 2. Write step5_heading_validation_prompt.md for compatibility
    prompt_path = (
        Path(__file__).resolve().parent.parent
        / "agents"
        / "step5_heading_validation_prompt.md"
    )
    prompt = prompt_path.read_text(encoding="utf-8")
    artifacts["heading_check_prompt"] = _write_text_artifact(
        work_dir / "step5_heading_validation_prompt.md", prompt
    )

    # 3. Read heading_expected_result.md
    expected_path = work_dir / "heading_expected_result.md"
    if not expected_path.exists():
        raise FormattingError("heading_expected_result.md is missing from work directory")
    expected_text = expected_path.read_text(encoding="utf-8")

    # 4. Extract H1-H3 headings and compare
    expected_headings = extract_h1_h3_headings(expected_text)
    candidate_headings = extract_h1_h3_headings(markdown)

    valid = True
    errors = []
    if expected_headings != candidate_headings:
        valid = False
        details = []
        for i, (exp, cand) in enumerate(zip(expected_headings, candidate_headings)):
            if exp != cand:
                details.append(f"At entry {i+1}: expected level {exp[0]} '{exp[1]}', got level {cand[0]} '{cand[1]}'")
        if len(expected_headings) > len(candidate_headings):
            details.append(f"Missing expected headings: {expected_headings[len(candidate_headings):]}")
        elif len(candidate_headings) > len(expected_headings):
            details.append(f"Extra candidate headings: {candidate_headings[len(expected_headings):]}")
        errors = [f"Heading validation mismatch: {'; '.join(details)}"]

    # 5. Write heading_check_response.json
    response_payload = {
        "valid": valid,
        "checked_heading_count": len(candidate_headings),
        "errors": errors
    }
    response_text = json.dumps(response_payload, ensure_ascii=False, indent=2)
    artifacts["heading_check_response"] = _write_text_artifact(
        work_dir / "heading_check_response.json", response_text
    )

    # 6. Run validation on the generated json response (raising FormattingError if not valid)
    return validate_heading_check_response(response_text, expected_heading_count=len(candidate_headings))

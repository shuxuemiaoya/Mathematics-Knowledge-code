from __future__ import annotations

import json
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
    headings = extract_body_headings(markdown, 0, -1)
    payload = build_toc_and_headings_markdown(toc.markdown, headings)
    artifacts["heading_check_input"] = _write_text_artifact(work_dir / "heading_check_input.md", payload)
    prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_check_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    artifacts["heading_check_prompt"] = _write_text_artifact(work_dir / "heading_check_prompt.md", prompt)
    response = provider_client.chat(
        prompt, payload, timeout_seconds=timeout_seconds, response_format={"type": "json_object"}
    )
    artifacts["heading_check_response"] = _write_text_artifact(
        work_dir / "heading_check_response.json", response
    )
    return validate_heading_check_response(response, expected_heading_count=len(headings))

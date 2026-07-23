from __future__ import annotations
import difflib
import re
import sys
from pathlib import Path
from mathos_common import (
    FormattingError, _strip_single_line_ending,
)

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

def _is_diff_content_line(line: str, original_name: str, candidate_name: str) -> bool:
    if line in {f"--- {original_name}", f"+++ {candidate_name}"}:
        return False
    if line.startswith("@@"):
        return False
    return line.startswith(("+", "-", " "))

def unified_markdown_diff(original_text: str, candidate_text: str, original_name: str, candidate_name: str) -> str:
    diff_lines: list[str] = []
    for raw_line in difflib.unified_diff(
        original_text.splitlines(keepends=True),
        candidate_text.splitlines(keepends=True),
        fromfile=original_name,
        tofile=candidate_name,
        lineterm="",
    ):
        line, had_line_ending = _strip_single_line_ending(raw_line)
        diff_lines.append(line)
        if _is_diff_content_line(line, original_name, candidate_name) and not had_line_ending:
            diff_lines.append(r"\ No newline at end of file")
    return "\n".join(diff_lines) + ("\n" if diff_lines else "")

def _validate_report_path(original_path: Path, candidate_path: Path, report_path: Path) -> None:
    resolved_report = report_path.resolve(strict=False)
    if resolved_report in {original_path.resolve(strict=False), candidate_path.resolve(strict=False)}:
        raise FormattingError(f"report path must not overwrite source or candidate: {report_path}")

def _markdown_code_fence_for(text: str) -> str:
    longest_backtick_run = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    return "`" * max(3, longest_backtick_run + 1)

def write_review_report(
    original_path: Path,
    candidate_path: Path,
    report_path: Path,
    heading_summary: list[str],
    plugin_summary: list[str],
    warnings: list[str],
) -> Path:
    _validate_report_path(original_path, candidate_path, report_path)
    original_text = original_path.read_text(encoding="utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    diff_text = unified_markdown_diff(original_text, candidate_text, str(original_path), str(candidate_path))
    diff_fence = _markdown_code_fence_for(diff_text)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = [
        "# MathOS Formatting Candidate Report", "",
        f"Source file: `{original_path}`", f"Candidate file: `{candidate_path}`", "",
        "## Heading Rules Summary", "", *[f"- {item}" for item in heading_summary], "",
        "## Content Plugin Summary", "", *[f"- {item}" for item in plugin_summary], "",
        "## Warnings", "", *[f"- {item}" for item in warnings], "",
        "## Diff", "", f"{diff_fence}diff", diff_text, diff_fence, "",
        "## Next Actions", "", "- review candidate", "- request source replacement", "- discard", ""
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")
    return report_path

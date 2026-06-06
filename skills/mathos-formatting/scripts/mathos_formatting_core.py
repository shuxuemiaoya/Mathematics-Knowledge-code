"""Core utilities for MathOS adaptive Markdown formatting."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import re
import shutil
from pathlib import Path


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line_number: int


@dataclass(frozen=True)
class TextBlock:
    kind: str
    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class H1Section:
    heading: str
    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class MarkdownStructure:
    source_label: str
    headings: list[Heading]
    toc_block: TextBlock | None
    heading_like_lines: list[str]
    heading_level_distribution: dict[int, int]
    h1_sections: list[H1Section]
    protected_blocks: list[TextBlock]


@dataclass(frozen=True)
class HeadingRule:
    rule_id: str
    pattern: str
    replacement: str
    flags: int


class FormattingError(RuntimeError):
    """Raised when formatting configuration or execution is unsafe."""


def candidate_path_for(original_path: Path) -> Path:
    return original_path.parent / ".mathos-formatting" / f"{original_path.stem}.candidate{original_path.suffix}"


def create_fresh_candidate(original_path: Path) -> Path:
    original_path = original_path.resolve()
    if not original_path.exists():
        raise FormattingError(f"source Markdown file does not exist: {original_path}")
    if original_path.suffix.lower() != ".md":
        raise FormattingError(f"source file must be Markdown: {original_path}")
    if not original_path.is_file():
        raise FormattingError(f"source Markdown file must be a file: {original_path}")

    candidate_path = candidate_path_for(original_path)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    if candidate_path.exists():
        candidate_path.unlink()
    shutil.copy2(original_path, candidate_path)
    return candidate_path


def _strip_single_line_ending(text: str) -> tuple[str, bool]:
    if text.endswith("\r\n"):
        return text[:-2], True
    if text.endswith(("\n", "\r")):
        return text[:-1], True
    return text, False


def _is_diff_content_line(line: str) -> bool:
    return (
        line.startswith(("+", "-", " "))
        and not line.startswith(("+++", "---"))
    )


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
        if _is_diff_content_line(line) and not had_line_ending:
            diff_lines.append(r"\ No newline at end of file")
    return "\n".join(diff_lines) + ("\n" if diff_lines else "")


def _validate_report_path(original_path: Path, candidate_path: Path, report_path: Path) -> None:
    resolved_report = report_path.resolve(strict=False)
    if resolved_report in {
        original_path.resolve(strict=False),
        candidate_path.resolve(strict=False),
    }:
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
    diff_text = unified_markdown_diff(
        original_text,
        candidate_text,
        str(original_path),
        str(candidate_path),
    )
    diff_fence = _markdown_code_fence_for(diff_text)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = [
        "# MathOS Formatting Candidate Report",
        "",
        f"Source file: `{original_path}`",
        f"Candidate file: `{candidate_path}`",
        "",
        "## Heading Rules Summary",
        "",
        *[f"- {item}" for item in heading_summary],
        "",
        "## Content Plugin Summary",
        "",
        *[f"- {item}" for item in plugin_summary],
        "",
        "## Warnings",
        "",
        *[f"- {item}" for item in warnings],
        "",
        "## Diff",
        "",
        f"{diff_fence}diff",
        diff_text,
        diff_fence,
        "",
        "## Next Actions",
        "",
        "- approve",
        "- revise",
        "- discard",
        "",
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")
    return report_path


HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*$")
ATX_CLOSING_SEQUENCE_RE = re.compile(r"\s+#+\s*$")
TOC_HEADING_RE = re.compile(r"^#{1,6}\s*(目录|目\s*录|contents?)\s*$", re.IGNORECASE)
HEADING_LIKE_RE = re.compile(
    r"^(第[一二三四五六七八九十百千万0-9]+[章节篇部].+|"
    r"\d+(?:\.\d+)+\s+.+|"
    r"(阅读与思考|探究与发现|信息技术应用|文献阅读|小结|复习参考题).*)$"
)
TOC_ENTRY_PAGE_RE = re.compile(r"(?:…+|\.{2,}|·{2,}|．{2,})\s*\d+\s*$")
CODE_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,}).*$")
FLAG_MAP = {
    "MULTILINE": re.MULTILINE,
    "IGNORECASE": re.IGNORECASE,
}


def _is_code_fence_close(line: str, fence_character: str, fence_length: int) -> bool:
    candidate = line.rstrip()
    leading_spaces = len(candidate) - len(candidate.lstrip(" "))
    if leading_spaces > 3:
        return False
    candidate = candidate.lstrip(" ")
    return (
        len(candidate) >= fence_length
        and all(character == fence_character for character in candidate)
    )


def _match_code_fence_open(line: str) -> re.Match[str] | None:
    leading_spaces = len(line) - len(line.lstrip(" "))
    if leading_spaces > 3:
        return None
    return CODE_FENCE_OPEN_RE.match(line.lstrip(" "))


def _normalize_toc_page_heading(text: str) -> str:
    return TOC_ENTRY_PAGE_RE.sub("", text).strip()


def _normalize_atx_heading_text(text: str) -> str:
    return ATX_CLOSING_SEQUENCE_RE.sub("", text)


def _line_offsets(markdown: str) -> list[str]:
    return markdown.splitlines()


def _compile_flags(raw_flags: list[str]) -> int:
    flags = 0
    for flag in raw_flags:
        if flag not in FLAG_MAP:
            raise FormattingError(f"unsupported regex flag: {flag}")
        flags |= FLAG_MAP[flag]
    return flags


def validate_heading_rules(payload: dict) -> list[HeadingRule]:
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise FormattingError("heading rules must contain a non-empty rules list")

    validated: list[HeadingRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise FormattingError("heading rule must be an object")
        rule_id = raw_rule.get("id")
        pattern = raw_rule.get("pattern")
        replacement = raw_rule.get("replacement")
        raw_flags = raw_rule.get("flags", [])
        if not isinstance(rule_id, str) or not rule_id:
            raise FormattingError("heading rule id must be a non-empty string")
        if not isinstance(pattern, str) or not pattern:
            raise FormattingError(f"heading rule {rule_id} pattern must be a non-empty string")
        if not isinstance(replacement, str):
            raise FormattingError(f"heading rule {rule_id} replacement must be a string")
        if not isinstance(raw_flags, list) or not all(isinstance(flag, str) for flag in raw_flags):
            raise FormattingError(f"heading rule {rule_id} flags must be a string list")
        flags = _compile_flags(raw_flags)
        try:
            re.compile(pattern, flags)
        except re.error as exc:
            raise FormattingError(f"invalid regex in heading rule {rule_id}: {exc}") from exc
        validated.append(HeadingRule(rule_id, pattern, replacement, flags))
    return validated


def _extract_protected_blocks(lines: list[str]) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    code_fence_character = ""
    code_fence_length = 0
    code_start = 0
    in_math = False
    math_start = 0

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()

        if code_fence_character:
            if _is_code_fence_close(line, code_fence_character, code_fence_length):
                blocks.append(TextBlock("code_fence", "\n".join(lines[code_start - 1:index]), code_start, index))
                code_fence_character = ""
                code_fence_length = 0
            continue

        if in_math:
            if stripped == "$$":
                blocks.append(TextBlock("math_block", "\n".join(lines[math_start - 1:index]), math_start, index))
                in_math = False
            continue

        code_fence_match = _match_code_fence_open(line)
        if code_fence_match:
            code_fence = code_fence_match.group(1)
            code_fence_character = code_fence[0]
            code_fence_length = len(code_fence)
            code_start = index
            continue
        if stripped == "$$":
            in_math = True
            math_start = index
            continue
        if re.search(r"!\[[^\]]*\]\([^)]+\)", line):
            blocks.append(TextBlock("image", line, index, index))

    if code_fence_character:
        blocks.append(TextBlock("code_fence", "\n".join(lines[code_start - 1:]), code_start, len(lines)))
    if in_math:
        blocks.append(TextBlock("math_block", "\n".join(lines[math_start - 1:]), math_start, len(lines)))

    return blocks


def _line_in_blocks(line_number: int, blocks: list[TextBlock], kinds: set[str]) -> bool:
    return any(block.kind in kinds and block.start_line <= line_number <= block.end_line for block in blocks)


def _apply_rules_to_span(markdown: str, rules: list[HeadingRule]) -> str:
    result = markdown
    for rule in rules:
        result = re.sub(rule.pattern, rule.replacement, result, flags=rule.flags)
    return result


def apply_heading_rules(markdown: str, rules: list[HeadingRule]) -> str:
    lines = markdown.splitlines(keepends=True)
    protected_blocks = [
        block
        for block in _extract_protected_blocks(_line_offsets(markdown))
        if block.kind in {"code_fence", "math_block"}
    ]
    if not protected_blocks:
        return _apply_rules_to_span(markdown, rules)

    result_parts: list[str] = []
    current_line = 1
    for block in protected_blocks:
        if current_line < block.start_line:
            result_parts.append(_apply_rules_to_span("".join(lines[current_line - 1:block.start_line - 1]), rules))
        result_parts.append("".join(lines[block.start_line - 1:block.end_line]))
        current_line = block.end_line + 1

    if current_line <= len(lines):
        result_parts.append(_apply_rules_to_span("".join(lines[current_line - 1:]), rules))
    return "".join(result_parts)


def _extract_toc_block(lines: list[str], headings: list[Heading]) -> TextBlock | None:
    toc_heading = next(
        (
            heading
            for heading in headings
            if TOC_HEADING_RE.match("#" * heading.level + " " + heading.text)
        ),
        None,
    )
    if toc_heading is None:
        return None

    following_h1 = None
    toc_page_titles: set[str] = set()
    for heading in headings:
        if heading.level != 1 or heading.line_number <= toc_heading.line_number:
            continue
        if TOC_ENTRY_PAGE_RE.search(heading.text):
            normalized_title = _normalize_toc_page_heading(heading.text)
            if normalized_title in toc_page_titles:
                following_h1 = heading
                break
            toc_page_titles.add(normalized_title)
            continue
        following_h1 = heading
        break

    end_line = (following_h1.line_number - 1) if following_h1 else len(lines)
    text = "\n".join(lines[toc_heading.line_number - 1:end_line])
    return TextBlock("toc", text, toc_heading.line_number, end_line)


def _extract_h1_sections(lines: list[str], headings: list[Heading]) -> list[H1Section]:
    h1_headings = [heading for heading in headings if heading.level == 1]
    sections: list[H1Section] = []
    for index, heading in enumerate(h1_headings):
        end_line = h1_headings[index + 1].line_number - 1 if index + 1 < len(h1_headings) else len(lines)
        sections.append(
            H1Section(
                heading=heading.text,
                text="\n".join(lines[heading.line_number - 1:end_line]),
                start_line=heading.line_number,
                end_line=end_line,
            )
        )
    return sections


def extract_structure(markdown: str, source_label: str) -> MarkdownStructure:
    lines = _line_offsets(markdown)
    protected_blocks = _extract_protected_blocks(lines)
    headings: list[Heading] = []
    heading_like_lines: list[str] = []
    distribution: dict[int, int] = {}

    for line_number, line in enumerate(lines, start=1):
        if _line_in_blocks(line_number, protected_blocks, {"code_fence", "math_block"}):
            continue
        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            headings.append(Heading(level, _normalize_atx_heading_text(heading_match.group(2)), line_number))
            distribution[level] = distribution.get(level, 0) + 1
            continue
        stripped = line.strip()
        if stripped and HEADING_LIKE_RE.match(stripped):
            heading_like_lines.append(stripped)

    return MarkdownStructure(
        source_label=source_label,
        headings=headings,
        toc_block=_extract_toc_block(lines, headings),
        heading_like_lines=heading_like_lines,
        heading_level_distribution=distribution,
        h1_sections=_extract_h1_sections(lines, headings),
        protected_blocks=protected_blocks,
    )

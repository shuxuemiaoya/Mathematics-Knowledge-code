"""Core utilities for MathOS adaptive Markdown formatting."""

from __future__ import annotations

from dataclasses import dataclass
import re


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


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TOC_HEADING_RE = re.compile(r"^#{1,6}\s*(目录|目\s*录|contents?)\s*$", re.IGNORECASE)
HEADING_LIKE_RE = re.compile(
    r"^(第[一二三四五六七八九十百千万0-9]+[章节篇部].+|"
    r"\d+(?:\.\d+)+\s+.+|"
    r"(阅读与思考|探究与发现|信息技术应用|文献阅读|小结|复习参考题).*)$"
)
TOC_ENTRY_PAGE_RE = re.compile(r"(?:…+|\.{2,}|·{2,}|．{2,})\s*\d+\s*$")
CODE_FENCE_RE = re.compile(r"^(```|~~~)")


def _line_offsets(markdown: str) -> list[str]:
    return markdown.splitlines()


def _extract_protected_blocks(lines: list[str]) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    code_fence_marker = ""
    code_start = 0
    in_math = False
    math_start = 0

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()

        if code_fence_marker:
            code_fence_match = CODE_FENCE_RE.match(stripped)
            if code_fence_match and code_fence_match.group(1) == code_fence_marker:
                blocks.append(TextBlock("code_fence", "\n".join(lines[code_start - 1:index]), code_start, index))
                code_fence_marker = ""
            continue

        if in_math:
            if stripped == "$$":
                blocks.append(TextBlock("math_block", "\n".join(lines[math_start - 1:index]), math_start, index))
                in_math = False
            continue

        code_fence_match = CODE_FENCE_RE.match(stripped)
        if code_fence_match:
            code_fence_marker = code_fence_match.group(1)
            code_start = index
            continue
        if stripped == "$$":
            in_math = True
            math_start = index
            continue
        if re.search(r"!\[[^\]]*\]\([^)]+\)", line):
            blocks.append(TextBlock("image", line, index, index))

    if code_fence_marker:
        blocks.append(TextBlock("code_fence", "\n".join(lines[code_start - 1:]), code_start, len(lines)))
    if in_math:
        blocks.append(TextBlock("math_block", "\n".join(lines[math_start - 1:]), math_start, len(lines)))

    return blocks


def _line_in_blocks(line_number: int, blocks: list[TextBlock], kinds: set[str]) -> bool:
    return any(block.kind in kinds and block.start_line <= line_number <= block.end_line for block in blocks)


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

    following_h1 = next(
        (
            heading
            for heading in headings
            if heading.level == 1
            and heading.line_number > toc_heading.line_number
            and not TOC_ENTRY_PAGE_RE.search(heading.text)
        ),
        None,
    )
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
            headings.append(Heading(level, heading_match.group(2), line_number))
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

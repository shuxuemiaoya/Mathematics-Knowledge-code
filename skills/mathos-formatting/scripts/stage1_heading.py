from __future__ import annotations
import re
import sys
from pathlib import Path
from mathos_common import (
    HeadingRule, FormattingError, FLAG_MAP, HEADING_RE,
    _extract_protected_blocks, _line_offsets,
    extract_structure, _normalize_atx_heading_text,
    _chapter_context_from_heading_text
)

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

def _apply_rules_to_span(markdown: str, rules: list[HeadingRule]) -> str:
    result = markdown
    for rule in rules:
        escaped_replacement = rule.replacement.replace("\\", "\\\\")
        py_replacement = re.sub(
            r'\$\$|\$(\d+)',
            lambda m: '$' if m.group(0) == '$$' else f'\\g<{m.group(1)}>',
            escaped_replacement,
        )
        result = re.sub(rule.pattern, py_replacement, result, flags=rule.flags)
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
            rx = re.compile(pattern, flags)
            if rx.groups < 1 and any(tag in replacement for tag in ("$1", "\\1", "\\g<1>")):
                if pattern.endswith(".+$"):
                    pattern = pattern[:-3] + "(.+)$"
                elif pattern.endswith(".+"):
                    pattern = pattern[:-2] + "(.+)"
                rx = re.compile(pattern, flags)
        except re.error as exc:
            raise FormattingError(f"invalid regex in heading rule {rule_id}: {exc}") from exc
        validated.append(HeadingRule(rule_id, pattern, replacement, flags))
    return validated

def _toc_body_boundary(original_text: str) -> int:
    structure = extract_structure(original_text, "stage1-audit-original")
    if structure.toc_block is None:
        raise FormattingError("Stage 1 audit requires a TOC reference")
    return structure.toc_block.end_line

def _toc_chapter_contexts(original_text: str) -> dict[str, str]:
    structure = extract_structure(original_text, "stage1-audit-original")
    if structure.toc_block is None:
        raise FormattingError("Stage 1 audit requires a TOC reference")
    lines = original_text.splitlines()
    contexts: dict[str, str] = {}
    for line in lines[structure.toc_block.start_line - 1:structure.toc_block.end_line]:
        stripped = line.strip()
        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            stripped = _normalize_atx_heading_text(heading_match.group(2)).strip()
        stripped = _normalize_toc_page_heading_with_fallback(stripped)
        context = _chapter_context_from_heading_text(stripped)
        if context is not None:
            contexts[context[1].casefold()] = context[1]
    return contexts

def _normalize_toc_page_heading_with_fallback(text: str) -> str:
    from mathos_common import TOC_ENTRY_PAGE_RE
    return TOC_ENTRY_PAGE_RE.sub("", text).strip()

def audit_stage1_headings(original_text: str, stage1_text: str) -> list[str]:
    toc_end_line = _toc_body_boundary(original_text)
    toc_chapters = _toc_chapter_contexts(original_text)
    stage1_structure = extract_structure(stage1_text, "stage1-audit-candidate")
    original_lines = original_text.splitlines()
    for heading in stage1_structure.headings:
        if heading.line_number <= toc_end_line:
            continue
        if heading.line_number <= len(original_lines):
            orig_line = original_lines[heading.line_number - 1].strip()
            orig_heading_match = HEADING_RE.match(orig_line)
            if orig_heading_match:
                orig_heading_text = _normalize_atx_heading_text(orig_heading_match.group(2)).strip()
                orig_context = _chapter_context_from_heading_text(orig_heading_text)
                if orig_context is not None and orig_context[1].casefold() in toc_chapters and heading.level != 1:
                    raise FormattingError(
                        "Stage 1 audit failed: chapter heading matching TOC must remain H1 "
                        f"at line {heading.line_number}: {heading.text}"
                    )
    return ["Stage 1 audit: chapter headings preserved as H1"]

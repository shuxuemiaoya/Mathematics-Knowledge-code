from __future__ import annotations
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from types import ModuleType
from mathos_common import (
    PreservationCounts, PluginResult, FormattingError,
    HEADING_RE, IMAGE_REFERENCE_RE, DETAILS_OPEN_RE,
    _content_protected_line_mask, _is_table_line, extract_structure
)

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

@dataclass(frozen=True)
class ContentRule:
    rule_id: str
    rule_type: str
    scope: str
    phase: str
    risk_level: str
    pattern: str
    replacement: str
    flags: int
    replacement_mode: str
    search: str
    enabled: bool

CONTENT_REQUIRED_KEYS = {
    "plugin_id", "plugin_version", "schema_version", "stage", "description",
    "safety", "execution_contract", "protected_blocks", "analyze", "rules", "warnings", "summary"
}
CONTENT_ALLOWED_RULE_TYPES = {
    "literal_replace", "regex_replace", "line_regex_replace", "blank_line_normalize",
    "choice_option_split", "callout_spacing_fix", "formula_whitelist_fix", "image_caption_fix", "report_only"
}


def validate_stage2_heading_preservation(before: str, after: str) -> list[str]:
    def heading_lines(markdown: str, label: str) -> list[str]:
        lines = markdown.splitlines()
        structure = extract_structure(markdown, label)
        return [lines[heading.line_number - 1] for heading in structure.headings]

    before_headings = heading_lines(before, "stage2-before")
    after_headings = heading_lines(after, "stage2-after")
    if before_headings != after_headings:
        raise FormattingError("Stage 2 content processor changed finalized heading lines")
    return [f"Stage 2 preserved {len(before_headings)} finalized heading lines"]


def protect_stage2_heading_lines(markdown: str) -> tuple[str, dict[str, str]]:
    lines = markdown.splitlines(keepends=True)
    structure = extract_structure(markdown, "stage2-heading-protection")
    heading_tokens: dict[str, str] = {}
    for index, heading in enumerate(structure.headings, start=1):
        token = f"MATHOSFINALHEADINGTOKEN{index:06d}"
        if token in markdown:
            raise FormattingError("Stage 2 heading token collides with source content")
        line_index = heading.line_number - 1
        raw_line = lines[line_index]
        if raw_line.endswith("\r\n"):
            body, ending = raw_line[:-2], "\r\n"
        elif raw_line.endswith(("\n", "\r")):
            body, ending = raw_line[:-1], raw_line[-1]
        else:
            body, ending = raw_line, ""
        heading_tokens[token] = body
        lines[line_index] = token + ending
    return "".join(lines), heading_tokens


def restore_stage2_heading_lines(markdown: str, heading_tokens: dict[str, str]) -> str:
    restored = markdown
    for token, heading_line in heading_tokens.items():
        if restored.count(token) != 1:
            raise FormattingError(f"Stage 2 heading token was changed or removed: {token}")
        restored = restored.replace(token, heading_line, 1)
    return restored


def protect_stage2_guarded_content(markdown: str) -> tuple[str, dict[str, str]]:
    protected = markdown
    tokens: dict[str, str] = {}

    def replace_match(match: re.Match[str]) -> str:
        token = f"MATHOSPROTECTEDTOKEN{len(tokens) + 1:06d}"
        if token in markdown:
            raise FormattingError("Stage 2 protected token collides with source content")
        tokens[token] = match.group(0)
        return token

    patterns = [
        (r"\A---(?:\r?\n)[\s\S]*?^---[ \t]*(?:\r?\n|$)", re.MULTILINE),
        (r"(?ms)^```[^\n]*\n.*?^```[ \t]*$|^~~~[^\n]*\n.*?^~~~[ \t]*$", 0),
        (r"<details(?:\s|>)[\s\S]*?</details\s*>", re.IGNORECASE),
        (r"<(center|table|figure|div)\b[^>]*>[\s\S]*?</\1\s*>", re.IGNORECASE),
        (r"\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]", 0),
        (r"`[^`\n]+`", 0),
        (r"(?<!\$)\$(?!\$)[^\n$]+\$", 0),
        (r"(?m)^>\s*\[![^\]]+\].*$", 0),
        (r"(?m)^#{1,6}\s+.*$", 0),
        (r"(?m)^.*\|.*$", 0),
        (r"!\[[^\]]*\]\([^)]+\)|<img\s+[^>]*src=[^>]*>", re.IGNORECASE),
    ]
    for pattern, flags in patterns:
        protected = re.sub(pattern, replace_match, protected, flags=flags)
    return protected, tokens


def restore_stage2_guarded_content(markdown: str, tokens: dict[str, str]) -> str:
    restored = markdown
    for token, original in reversed(list(tokens.items())):
        if restored.count(token) != 1:
            raise FormattingError(f"Stage 2 protected token was changed or removed: {token}")
        restored = restored.replace(token, original, 1)
    return restored
CONTENT_ALLOWED_SCOPES = {
    "non_heading_lines", "all_unprotected_text", "all_unprotected_non_heading_text",
    "math_text_only", "image_caption_region", "callout_region", "report_only"
}
CONTENT_ALLOWED_PHASES = {
    "pre_clean", "formula_fix", "choice_fix", "callout_fix", "image_caption_fix",
    "blank_line_fix", "post_clean", "analyze_only"
}
CONTENT_ALLOWED_RISKS = {"low", "medium", "high"}
CONTENT_ALLOWED_REPLACEMENT_MODES = {"regex_template", "literal"}
CONTENT_MUTATING_TYPES = CONTENT_ALLOWED_RULE_TYPES - {"report_only"}

def _compile_flags(raw_flags: list[str]) -> int:
    from mathos_common import FLAG_MAP
    flags = 0
    for flag in raw_flags:
        if flag not in FLAG_MAP:
            raise FormattingError(f"unsupported regex flag: {flag}")
        flags |= FLAG_MAP[flag]
    return flags

def validate_content_rules(payload: dict) -> list[ContentRule]:
    if not isinstance(payload, dict):
        raise FormattingError("content rules must be a JSON object")
    missing = sorted(CONTENT_REQUIRED_KEYS - set(payload))
    if missing:
        raise FormattingError(f"content rules missing required keys: {', '.join(missing)}")
    if payload.get("plugin_id") != "chapter_inner_markdown_formatter":
        raise FormattingError("content rules plugin_id must be chapter_inner_markdown_formatter")
    if payload.get("schema_version") != "1.0.0":
        raise FormattingError("content rules schema_version must be 1.0.0")
    if payload.get("stage") != "chapter_inner_formatting":
        raise FormattingError("content rules stage must be chapter_inner_formatting")
    if not isinstance(payload.get("safety"), dict):
        raise FormattingError("content rules safety must be an object")
    if not payload["safety"].get("never_modify_heading_lines"):
        raise FormattingError("content rules must declare never_modify_heading_lines")
    if not isinstance(payload.get("execution_contract"), dict):
        raise FormattingError("content rules execution_contract must be an object")
    if not isinstance(payload.get("protected_blocks"), list):
        raise FormattingError("content rules protected_blocks must be a list")
    analyze = payload.get("analyze")
    if not isinstance(analyze, dict) or not isinstance(analyze.get("checks"), list):
        raise FormattingError("content rules analyze.checks must be a list")
    if not isinstance(payload.get("summary"), list) or not all(isinstance(item, str) for item in payload["summary"]):
        raise FormattingError("content rules summary must be a string list")
    if not isinstance(payload.get("warnings"), list) or not all(isinstance(item, str) for item in payload["warnings"]):
        raise FormattingError("content rules warnings must be a string list")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise FormattingError("content rules rules must be a list")
    validated: list[ContentRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise FormattingError("content rule must be an object")
        rule_id = raw_rule.get("id")
        rule_type = raw_rule.get("type")
        scope = raw_rule.get("scope", "non_heading_lines")
        phase = raw_rule.get("phase", "pre_clean")
        risk_level = raw_rule.get("risk_level", "low")
        pattern = raw_rule.get("pattern", "")
        search = raw_rule.get("search", "")
        replacement = raw_rule.get("replacement", "")
        raw_flags = raw_rule.get("flags", [])
        replacement_mode = raw_rule.get("replacement_mode", "regex_template")
        enabled = raw_rule.get("enabled", True)
        if not isinstance(rule_id, str) or not rule_id:
            raise FormattingError("content rule id must be a non-empty string")
        if rule_type not in CONTENT_ALLOWED_RULE_TYPES:
            raise FormattingError(f"unsupported content rule type: {rule_type}")
        if scope not in CONTENT_ALLOWED_SCOPES:
            raise FormattingError(f"unsupported content rule scope: {scope}")
        if phase not in CONTENT_ALLOWED_PHASES:
            raise FormattingError(f"unsupported content rule phase: {phase}")
        if risk_level not in CONTENT_ALLOWED_RISKS:
            raise FormattingError(f"unsupported content rule risk_level: {risk_level}")
        if replacement_mode not in CONTENT_ALLOWED_REPLACEMENT_MODES:
            raise FormattingError(f"unsupported content rule replacement_mode: {replacement_mode}")
        if not isinstance(enabled, bool):
            raise FormattingError(f"content rule {rule_id} enabled must be boolean")
        if not isinstance(pattern, str) or not isinstance(search, str) or not isinstance(replacement, str):
            raise FormattingError(f"content rule {rule_id} pattern/search/replacement must be strings")
        if not isinstance(raw_flags, list) or not all(isinstance(flag, str) for flag in raw_flags):
            raise FormattingError(f"content rule {rule_id} flags must be a string list")
        if enabled and rule_type == "image_caption_fix" and raw_rule.get("mode") != "report_only":
            raise FormattingError("enabled image_caption_fix rules are not supported in v1; use report_only or enabled=false")
        flags = _compile_flags(raw_flags)
        if enabled and rule_type not in {"literal_replace", "report_only"}:
            if not pattern:
                raise FormattingError(f"content rule {rule_id} pattern must be a non-empty string")
            try:
                re.compile(pattern, flags)
            except re.error as exc:
                raise FormattingError(f"invalid regex in content rule {rule_id}: {exc}") from exc
        if enabled and rule_type == "literal_replace" and not (search or pattern):
            raise FormattingError(f"content rule {rule_id} search or pattern must be non-empty")
        validated.append(
            ContentRule(
                rule_id=rule_id, rule_type=rule_type, scope=scope, phase=phase, risk_level=risk_level,
                pattern=pattern, replacement=replacement, flags=flags, replacement_mode=replacement_mode,
                search=search, enabled=enabled
            )
        )
    return validated

def _regex_replacement(rule: ContentRule) -> str | object:
    if rule.replacement_mode == "literal":
        return lambda _match: rule.replacement
    escaped_replacement = rule.replacement.replace("\\", "\\\\")
    return re.sub(
        r'\$\$|\$(\d+)',
        lambda m: '$' if m.group(0) == '$$' else f'\\g<{m.group(1)}>',
        escaped_replacement,
    )

def _apply_content_rule_to_text(text: str, rule: ContentRule) -> str:
    if not rule.enabled or rule.rule_type in {"report_only", "image_caption_fix"}:
        return text
    if rule.rule_type == "literal_replace":
        return text.replace(rule.search or rule.pattern, rule.replacement)
    if rule.rule_type in {
        "regex_replace", "blank_line_normalize", "choice_option_split",
        "callout_spacing_fix", "formula_whitelist_fix"
    }:
        return re.sub(rule.pattern, _regex_replacement(rule), text, flags=rule.flags)
    if rule.rule_type == "line_regex_replace":
        parts = text.splitlines(keepends=True)
        return "".join(re.sub(rule.pattern, _regex_replacement(rule), part, flags=rule.flags) for part in parts)
    raise FormattingError(f"unsupported executable content rule type: {rule.rule_type}")

def _apply_content_rules_to_unprotected_text(markdown: str, rules: list[ContentRule]) -> str:
    lines = markdown.splitlines(keepends=True)
    protected = _content_protected_line_mask(lines)
    result_parts: list[str] = []
    current_span: list[str] = []
    def flush_span() -> None:
        if not current_span:
            return
        span = "".join(current_span)
        for rule in rules:
            if rule.scope in {"math_text_only", "image_caption_region", "callout_region", "report_only"}:
                continue
            span = _apply_content_rule_to_text(span, rule)
        result_parts.append(span)
        current_span.clear()
    for line, is_protected in zip(lines, protected):
        if is_protected:
            flush_span()
            result_parts.append(line)
        else:
            current_span.append(line)
    flush_span()
    return "".join(result_parts)

def run_content_rules(payload: dict, markdown: str) -> PluginResult:
    rules = validate_content_rules(payload)
    cleaned = _apply_content_rules_to_unprotected_text(markdown, rules)
    summary = list(payload.get("summary", []))
    warnings = list(payload.get("warnings", []))
    return PluginResult(cleaned_markdown=cleaned, summary=summary, warnings=warnings)

def _heading_lines(markdown: str) -> list[str]:
    return [line.rstrip("\r\n") for line in markdown.splitlines() if HEADING_RE.match(line)]

def content_preservation_counts(markdown: str) -> PreservationCounts:
    lines = markdown.splitlines()
    return PreservationCounts(
        image_references=sum(1 for line in lines if IMAGE_REFERENCE_RE.search(line)),
        details_blocks=sum(1 for line in lines if DETAILS_OPEN_RE.match(line.strip())),
        math_delimiters=markdown.count("$$"),
        table_like_lines=sum(1 for line in lines if "|" in line),
    )

def preservation_summary(before: PreservationCounts, after: PreservationCounts) -> list[str]:
    return [
        f"Preservation images: {before.image_references} -> {after.image_references}",
        f"Preservation details blocks: {before.details_blocks} -> {after.details_blocks}",
        f"Preservation math delimiters: {before.math_delimiters} -> {after.math_delimiters}",
        f"Preservation table-like lines: {before.table_like_lines} -> {after.table_like_lines}",
    ]

def validate_content_preservation(before: PreservationCounts, after: PreservationCounts) -> None:
    if after.image_references < before.image_references:
        raise FormattingError(f"content cleaner removed image references ({before.image_references} before, {after.image_references} after)")
    if after.details_blocks != before.details_blocks:
        raise FormattingError(f"content cleaner changed details block count ({before.details_blocks} before, {after.details_blocks} after)")
    if after.math_delimiters != before.math_delimiters:
        raise FormattingError(f"content cleaner changed math delimiter count ({before.math_delimiters} before, {after.math_delimiters} after)")
    if after.table_like_lines < before.table_like_lines:
        raise FormattingError(f"content cleaner removed table-like lines ({before.table_like_lines} before, {after.table_like_lines} after)")

def run_content_plugin_protecting_headings(plugin: ModuleType, markdown: str) -> PluginResult:
    from mathos_common import run_plugin
    before_headings = _heading_lines(markdown)
    before_counts = content_preservation_counts(markdown)
    result = run_plugin(plugin, markdown)
    after_headings = _heading_lines(result.cleaned_markdown)
    if before_headings != after_headings:
        raise FormattingError("content cleaner modified heading lines")
    after_counts = content_preservation_counts(result.cleaned_markdown)
    validate_content_preservation(before_counts, after_counts)
    return PluginResult(
        cleaned_markdown=result.cleaned_markdown,
        summary=result.summary + preservation_summary(before_counts, after_counts),
        warnings=result.warnings,
    )

def run_content_rules_protecting_headings(payload: dict, markdown: str) -> PluginResult:
    before_headings = _heading_lines(markdown)
    before_counts = content_preservation_counts(markdown)
    result = run_content_rules(payload, markdown)
    after_headings = _heading_lines(result.cleaned_markdown)
    if before_headings != after_headings:
        raise FormattingError("content rules modified heading lines")
    after_counts = content_preservation_counts(result.cleaned_markdown)
    validate_content_preservation(before_counts, after_counts)
    return PluginResult(
        cleaned_markdown=result.cleaned_markdown,
        summary=result.summary + preservation_summary(before_counts, after_counts),
        warnings=result.warnings,
    )

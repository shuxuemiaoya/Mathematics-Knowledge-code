"""Core utilities for MathOS adaptive Markdown formatting."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType


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


@dataclass(frozen=True)
class PluginResult:
    cleaned_markdown: str
    summary: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class PreservationCounts:
    image_references: int
    details_blocks: int
    math_delimiters: int
    table_like_lines: int


@dataclass(frozen=True)
class ApprovedApplyResult:
    candidate_path: Path
    report_path: Path
    summary: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class CandidateRunResult:
    candidate_path: Path
    report_path: Path
    summary: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class LearningRunState:
    source_path: Path
    candidate_path: Path
    provider_base_url: str
    provider_model: str
    stage: str
    status: str
    artifacts: dict[str, Path]
    warnings: list[str]
    errors: list[str]
    approved: bool


@dataclass(frozen=True)
class LearningRunResult:
    status: str
    work_dir: Path
    candidate_path: Path
    report_path: Path
    artifacts: dict[str, Path]
    summary: list[str]
    warnings: list[str]
    errors: list[str]


class FormattingError(RuntimeError):
    """Raised when formatting configuration or execution is unsafe."""


SAFE_IMPORTS = {"re", "math", "typing"}
UNSAFE_CALL_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "getattr",
    "globals",
    "locals",
    "vars",
}
UNSAFE_ATTRIBUTE_ROOTS = {
    "__builtins__",
    "builtins",
    "os",
    "sys",
    "subprocess",
    "pathlib",
    "socket",
    "requests",
    "urllib",
    "http",
    "shutil",
}


def _validate_plugin_ast(source: str) -> None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in SAFE_IMPORTS:
                    raise FormattingError(f"unsafe import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in SAFE_IMPORTS:
                raise FormattingError(f"unsafe import: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in UNSAFE_CALL_NAMES:
                raise FormattingError(f"unsafe call: {node.func.id}")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in UNSAFE_ATTRIBUTE_ROOTS:
                raise FormattingError(f"unsafe attribute access: {node.value.id}.{node.attr}")
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id in UNSAFE_ATTRIBUTE_ROOTS:
                raise FormattingError(f"unsafe subscript access: {node.value.id}")


def load_safe_plugin(plugin_path: Path) -> ModuleType:
    source = plugin_path.read_text(encoding="utf-8")
    _validate_plugin_ast(source)
    module_name = f"mathos_candidate_{abs(hash(plugin_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise FormattingError(f"cannot load plugin: {plugin_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        for attr in ["PLUGIN_ID", "PLUGIN_VERSION", "analyze", "clean"]:
            if not hasattr(module, attr):
                raise FormattingError(f"plugin missing required attribute: {attr}")
        probe = module.clean("probe")
        if not isinstance(probe, str):
            raise FormattingError("plugin clean() must return a string")
        analysis = module.analyze("probe")
        if not isinstance(analysis, dict):
            raise FormattingError("plugin analyze() must return a dict")
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def run_plugin(plugin: ModuleType, markdown: str) -> PluginResult:
    analysis = plugin.analyze(markdown)
    if not isinstance(analysis, dict):
        raise FormattingError("plugin analyze() must return a dict")
    cleaned = plugin.clean(markdown)
    if not isinstance(cleaned, str):
        raise FormattingError("plugin clean() must return a string")
    summary = analysis.get("summary", [])
    warnings = analysis.get("warnings", [])
    if not isinstance(summary, list) or not all(isinstance(item, str) for item in summary):
        raise FormattingError("plugin analysis summary must be a string list")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise FormattingError("plugin analysis warnings must be a string list")
    return PluginResult(cleaned_markdown=cleaned, summary=summary, warnings=warnings)


def candidate_path_for(original_path: Path) -> Path:
    return original_path.parent / "mathos-formatting" / f"{original_path.stem}.candidate{original_path.suffix}"


def learning_work_dir_for(markdown_path: Path) -> Path:
    return markdown_path.parent / "mathos-formatting" / markdown_path.stem


def learning_candidate_path_for(markdown_path: Path, work_dir: Path | None = None) -> Path:
    base = work_dir if work_dir is not None else learning_work_dir_for(markdown_path)
    return base / "candidate.md"


def _json_path_map(paths: dict[str, Path]) -> dict[str, str]:
    return {key: str(value) for key, value in paths.items()}


def write_learning_state(work_dir: Path, state: LearningRunState) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_path": str(state.source_path),
        "candidate_path": str(state.candidate_path),
        "provider_base_url": state.provider_base_url,
        "provider_model": state.provider_model,
        "stage": state.stage,
        "status": state.status,
        "artifacts": _json_path_map(state.artifacts),
        "warnings": state.warnings,
        "errors": state.errors,
        "approved": state.approved,
    }
    state_path = work_dir / "run-state.json"
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path


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


def _split_single_line_ending(text: str) -> tuple[str, str]:
    if text.endswith("\r\n"):
        return text[:-2], "\r\n"
    if text.endswith("\n"):
        return text[:-1], "\n"
    if text.endswith("\r"):
        return text[:-1], "\r"
    return text, ""


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
TOC_ENTRY_PAGE_RE = re.compile(r"(?:…+|\.{2,}|·{2,}|．{2,}|\s+)\s*\d+\s*$")
CODE_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,}).*$")
FLAG_MAP = {
    "MULTILINE": re.MULTILINE,
    "IGNORECASE": re.IGNORECASE,
    "DOTALL": re.DOTALL,
}
CHINESE_CHAPTER_RE = re.compile(r"第\s*([一二三四五六七八九十百千万零〇两0-9]+)\s*章")
ENGLISH_CHAPTER_RE = re.compile(r"\bChapter\s+([0-9]+)\b", re.IGNORECASE)

CHINESE_DIGIT_VALUES = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNIT_VALUES = {
    "十": 10,
    "百": 100,
    "千": 1000,
    "万": 10000,
}
CHINESE_DIGITS = "零一二三四五六七八九"


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


def _chinese_number_to_int(text: str) -> int | None:
    if text.isdecimal():
        return int(text)
    total = 0
    section = 0
    number = 0
    saw_number = False
    for character in text:
        if character in CHINESE_DIGIT_VALUES:
            number = CHINESE_DIGIT_VALUES[character]
            saw_number = True
            continue
        unit = CHINESE_UNIT_VALUES.get(character)
        if unit is None:
            return None
        if unit == 10000:
            section = (section + number) * unit
            total += section
            section = 0
            number = 0
            continue
        section += (number or 1) * unit
        number = 0
    total += section + number
    return total if saw_number or total else None


def _int_to_chinese_number(value: int) -> str:
    if value < 0 or value > 9999:
        return str(value)
    if value < 10:
        return CHINESE_DIGITS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        prefix = "" if tens == 1 else CHINESE_DIGITS[tens]
        return f"{prefix}十{CHINESE_DIGITS[ones] if ones else ''}"
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        if remainder == 0:
            return f"{CHINESE_DIGITS[hundreds]}百"
        zero = "零" if remainder < 10 else ""
        return f"{CHINESE_DIGITS[hundreds]}百{zero}{_int_to_chinese_number(remainder)}"
    thousands, remainder = divmod(value, 1000)
    if remainder == 0:
        return f"{CHINESE_DIGITS[thousands]}千"
    zero = "零" if remainder < 100 else ""
    return f"{CHINESE_DIGITS[thousands]}千{zero}{_int_to_chinese_number(remainder)}"


def _normalize_chinese_chapter_number(raw_number: str) -> str:
    parsed = _chinese_number_to_int(raw_number)
    return _int_to_chinese_number(parsed) if parsed is not None else raw_number


def _chapter_context_from_heading_text(text: str) -> tuple[str, str, str] | None:
    chinese_match = CHINESE_CHAPTER_RE.search(text)
    if chinese_match:
        chapter_number = _normalize_chinese_chapter_number(chinese_match.group(1))
        return ("zh", f"第{chapter_number}章", str(_chinese_number_to_int(chinese_match.group(1)) or chapter_number))
    english_match = ENGLISH_CHAPTER_RE.search(text)
    if english_match:
        chapter_number = english_match.group(1)
        return ("en", f"Chapter {chapter_number}", chapter_number)
    return None



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
        stripped = _normalize_toc_page_heading(stripped)
        context = _chapter_context_from_heading_text(stripped)
        if context is not None:
            contexts[context[1].casefold()] = context[1]
    return contexts


def audit_stage1_headings(original_text: str, stage1_text: str) -> list[str]:
    toc_end_line = _toc_body_boundary(original_text)
    toc_chapters = _toc_chapter_contexts(original_text)
    stage1_structure = extract_structure(stage1_text, "stage1-audit-candidate")

    for heading in stage1_structure.headings:
        if heading.line_number <= toc_end_line:
            continue
        context = _chapter_context_from_heading_text(heading.text)
        if context is not None and context[1].casefold() in toc_chapters and heading.level != 1:
            raise FormattingError(
                "Stage 1 audit failed: chapter heading matching TOC must remain H1 "
                f"at line {heading.line_number}: {heading.text}"
            )

    return [
        "Stage 1 audit: chapter headings preserved as H1",
    ]


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
                # Recompile to validate the corrected pattern
                rx = re.compile(pattern, flags)
        except re.error as exc:
            raise FormattingError(f"invalid regex in heading rule {rule_id}: {exc}") from exc
        validated.append(HeadingRule(rule_id, pattern, replacement, flags))
    return validated


CONTENT_REQUIRED_KEYS = {
    "plugin_id",
    "plugin_version",
    "schema_version",
    "stage",
    "description",
    "safety",
    "execution_contract",
    "protected_blocks",
    "analyze",
    "rules",
    "warnings",
    "summary",
}
CONTENT_ALLOWED_RULE_TYPES = {
    "literal_replace",
    "regex_replace",
    "line_regex_replace",
    "blank_line_normalize",
    "choice_option_split",
    "callout_spacing_fix",
    "formula_whitelist_fix",
    "image_caption_fix",
    "report_only",
}
CONTENT_ALLOWED_SCOPES = {
    "non_heading_lines",
    "all_unprotected_text",
    "all_unprotected_non_heading_text",
    "math_text_only",
    "image_caption_region",
    "callout_region",
    "report_only",
}
CONTENT_ALLOWED_PHASES = {
    "pre_clean",
    "formula_fix",
    "choice_fix",
    "callout_fix",
    "image_caption_fix",
    "blank_line_fix",
    "post_clean",
    "analyze_only",
}
CONTENT_ALLOWED_RISKS = {"low", "medium", "high"}
CONTENT_ALLOWED_REPLACEMENT_MODES = {"regex_template", "literal"}
CONTENT_MUTATING_TYPES = CONTENT_ALLOWED_RULE_TYPES - {"report_only"}


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
                rule_id=rule_id,
                rule_type=rule_type,
                scope=scope,
                phase=phase,
                risk_level=risk_level,
                pattern=pattern,
                replacement=replacement,
                flags=flags,
                replacement_mode=replacement_mode,
                search=search,
                enabled=enabled,
            )
        )
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
        "regex_replace",
        "blank_line_normalize",
        "choice_option_split",
        "callout_spacing_fix",
        "formula_whitelist_fix",
    }:
        return re.sub(rule.pattern, _regex_replacement(rule), text, flags=rule.flags)
    if rule.rule_type == "line_regex_replace":
        parts = text.splitlines(keepends=True)
        return "".join(re.sub(rule.pattern, _regex_replacement(rule), part, flags=rule.flags) for part in parts)
    raise FormattingError(f"unsupported executable content rule type: {rule.rule_type}")


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and bool(stripped)


def _content_protected_line_mask(lines: list[str]) -> list[bool]:
    protected = [False] * len(lines)
    in_yaml = len(lines) > 0 and lines[0].strip() == "---"
    in_code = False
    code_marker = ""
    in_math = False
    in_bracket_math = False
    in_details = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if in_yaml:
            protected[index] = True
            if index > 0 and stripped == "---":
                in_yaml = False
            continue
        if in_code:
            protected[index] = True
            if stripped.startswith(code_marker):
                in_code = False
            continue
        if in_math:
            protected[index] = True
            if stripped == "$$":
                in_math = False
            continue
        if in_bracket_math:
            protected[index] = True
            if stripped == r"\]":
                in_bracket_math = False
            continue
        if in_details:
            protected[index] = True
            if stripped.lower().startswith("</details>"):
                in_details = False
            continue

        if HEADING_RE.match(line):
            protected[index] = True
        elif stripped.startswith("```") or stripped.startswith("~~~"):
            protected[index] = True
            in_code = True
            code_marker = stripped[:3]
        elif stripped == "$$":
            protected[index] = True
            in_math = True
        elif stripped == r"\[":
            protected[index] = True
            in_bracket_math = True
        elif stripped.lower().startswith("<details"):
            protected[index] = True
            in_details = True
        elif _is_table_line(line):
            protected[index] = True
    return protected


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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_approved_program(
    approved_root: Path,
    plugin_id: str,
    heading_rules: dict,
    plugin_path: Path | None,
    content_rules_path: Path | None,
    original_path: Path,
    candidate_path: Path,
    approving_source_path: Path,
    operations_summary: list[str],
) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", plugin_id):
        raise FormattingError("plugin id may contain only letters, numbers, underscores, and hyphens")

    validate_heading_rules(heading_rules)
    if (plugin_path is None) == (content_rules_path is None):
        raise FormattingError("provide exactly one of plugin_path or content_rules_path")
    content_rules_payload: dict | None = None
    if content_rules_path is not None:
        content_rules_payload = json.loads(content_rules_path.read_text(encoding="utf-8"))
        validate_content_rules(content_rules_payload)
    if plugin_path is not None:
        load_safe_plugin(plugin_path)

    program_dir = approved_root / plugin_id
    if program_dir.exists():
        raise FormattingError(f"approved plugin already exists: {plugin_id}")
    program_dir.mkdir(parents=True)

    original_text = original_path.read_text(encoding="utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    original_structure = extract_structure(original_text, str(original_path))
    candidate_structure = extract_structure(candidate_text, str(candidate_path))
    h1_sample = candidate_structure.h1_sections[0].text if candidate_structure.h1_sections else candidate_text[:2000]

    (program_dir / "heading_rules.json").write_text(
        json.dumps(heading_rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if content_rules_payload is not None:
        (program_dir / "content_rules.json").write_text(
            json.dumps(content_rules_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif plugin_path is not None:
        shutil.copy2(plugin_path, program_dir / "content_cleaner.py")
    (program_dir / "sample_before.md").write_text(original_text, encoding="utf-8")
    (program_dir / "sample_after.md").write_text(candidate_text, encoding="utf-8")

    metadata = {
        "plugin_id": plugin_id,
        "version": "1.0.0",
        "approval_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file_family_evidence": str(approving_source_path),
        "heading_signature": candidate_structure.heading_level_distribution,
        "toc_signature": bool(original_structure.toc_block),
        "h1_sample_hash": _sha256_text(h1_sample),
        "operations_summary": operations_summary,
        "original_approving_file_path": str(approving_source_path),
        "allowed_scope": "self-check-only",
    }
    (program_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (program_dir / "approval.md").write_text(
        "\n".join(
            [
                "# Approval",
                "",
                f"Approved program: `{plugin_id}`",
                f"Approving source: `{approving_source_path}`",
                "",
                "Allowed scope: `self-check-only`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return program_dir


def apply_approved_program(program_dir: Path, target_path: Path) -> ApprovedApplyResult:
    heading_rules_payload = json.loads((program_dir / "heading_rules.json").read_text(encoding="utf-8"))
    rules = validate_heading_rules(heading_rules_payload)
    content_rules_path = program_dir / "content_rules.json"
    plugin_path = program_dir / "content_cleaner.py"
    if content_rules_path.exists():
        content_rules_payload = json.loads(content_rules_path.read_text(encoding="utf-8"))
        validate_content_rules(content_rules_payload)
        plugin = None
    elif plugin_path.exists():
        content_rules_payload = None
        plugin = load_safe_plugin(plugin_path)
    else:
        raise FormattingError("approved program must contain content_rules.json or content_cleaner.py")

    candidate_path = create_fresh_candidate(target_path)
    markdown = candidate_path.read_text(encoding="utf-8")
    markdown = apply_heading_rules(markdown, rules)

    # Conditionally strip TOC dynamically using local heuristic if metadata expects it
    metadata_path = program_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("toc_signature", False):
            structure = extract_structure(markdown, "toc-detection")
            if structure.toc_block is not None:
                lines = markdown.splitlines(keepends=True)
                before_toc = lines[:structure.toc_block.start_line - 1]
                after_toc = lines[structure.toc_block.end_line:]
                markdown = "".join(before_toc + after_toc)

    if content_rules_payload is not None:
        plugin_result = run_content_rules_protecting_headings(content_rules_payload, markdown)
    else:
        assert plugin is not None
        plugin_result = run_content_plugin_protecting_headings(plugin, markdown)
    cleaned = plugin_result.cleaned_markdown
    # Apply heading optimizations if present
    opt_path = program_dir / "heading_optimizations.json"
    if opt_path.exists():
        opt_mapping = json.loads(opt_path.read_text(encoding="utf-8"))
        opt_lines = cleaned.splitlines()
        for idx, l in enumerate(opt_lines):
            stripped = l.strip()
            if stripped in opt_mapping:
                opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
        cleaned = "\n".join(opt_lines) + "\n"
    candidate_path.write_text(cleaned, encoding="utf-8")

    report_path = candidate_path.parent / f"{target_path.stem}.approved-report.md"
    write_review_report(
        original_path=target_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=[rule.rule_id for rule in rules],
        plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )
    return ApprovedApplyResult(
        candidate_path=candidate_path,
        report_path=report_path,
        summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )


def run_candidate_from_artifacts(
    markdown_path: Path,
    heading_rules_path: Path,
    plugin_path: Path | None = None,
    content_rules_path: Path | None = None,
    heading_optimizations_path: Path | None = None,
) -> CandidateRunResult:
    heading_payload = json.loads(heading_rules_path.read_text(encoding="utf-8"))
    rules = validate_heading_rules(heading_payload)
    if (plugin_path is None) == (content_rules_path is None):
        raise FormattingError("provide exactly one of plugin_path or content_rules_path")
    content_rules_payload: dict | None = None
    plugin: ModuleType | None = None
    if content_rules_path is not None:
        content_rules_payload = json.loads(content_rules_path.read_text(encoding="utf-8"))
        validate_content_rules(content_rules_payload)
    if plugin_path is not None:
        plugin = load_safe_plugin(plugin_path)
    candidate_path = create_fresh_candidate(markdown_path)

    markdown = candidate_path.read_text(encoding="utf-8")
    markdown = apply_heading_rules(markdown, rules)
    if content_rules_payload is not None:
        plugin_result = run_content_rules_protecting_headings(content_rules_payload, markdown)
    else:
        assert plugin is not None
        plugin_result = run_content_plugin_protecting_headings(plugin, markdown)
    cleaned = plugin_result.cleaned_markdown

    if heading_optimizations_path is not None and heading_optimizations_path.exists():
        opt_mapping = json.loads(heading_optimizations_path.read_text(encoding="utf-8"))
        opt_lines = cleaned.splitlines()
        for idx, l in enumerate(opt_lines):
            stripped = l.strip()
            if stripped in opt_mapping:
                opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
        cleaned = "\n".join(opt_lines) + "\n"

    candidate_path.write_text(cleaned, encoding="utf-8")

    report_path = candidate_path.parent / f"{markdown_path.stem}.candidate-report.md"
    write_review_report(
        original_path=markdown_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=[rule.rule_id for rule in rules],
        plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )
    return CandidateRunResult(candidate_path, report_path, plugin_result.summary, plugin_result.warnings)


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
    first_toc_h1_normalized = None
    for heading in headings:
        if heading.level != 1 or heading.line_number <= toc_heading.line_number:
            continue
        if TOC_ENTRY_PAGE_RE.search(heading.text):
            normalized_title = _normalize_toc_page_heading(heading.text)
            if first_toc_h1_normalized is None:
                first_toc_h1_normalized = normalized_title
            if normalized_title == first_toc_h1_normalized and len(toc_page_titles) > 0:
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


def extract_toc_sample(markdown: str, structure: MarkdownStructure, max_following_lines: int = 80) -> str:
    if structure.toc_block is None:
        raise FormattingError("TOC not found")
    lines = markdown.splitlines()
    start_index = max(structure.toc_block.start_line - 1, 0)
    end_index = min(len(lines), structure.toc_block.end_line + max_following_lines)
    sample_lines = lines[start_index:end_index]
    return "\n".join(sample_lines).strip() + "\n"


def extract_h1_sample(markdown: str, structure: MarkdownStructure, h1_index: int = 0) -> str:
    if h1_index < 0 or h1_index >= len(structure.h1_sections):
        raise FormattingError("H1 section not found")
    return structure.h1_sections[h1_index].text.strip() + "\n"


def _heading_lines(markdown: str) -> list[str]:
    return [
        line.rstrip("\r\n")
        for line in markdown.splitlines()
        if HEADING_RE.match(line)
    ]


IMAGE_REFERENCE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)|<img\s+[^>]*src=", re.IGNORECASE)
DETAILS_OPEN_RE = re.compile(r"^ {0,3}<details(?:\s|>)", re.IGNORECASE)


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
        raise FormattingError(
            "content cleaner removed image references "
            f"({before.image_references} before, {after.image_references} after)"
        )
    if after.details_blocks < before.details_blocks:
        raise FormattingError(
            "content cleaner removed details blocks "
            f"({before.details_blocks} before, {after.details_blocks} after)"
        )
    if after.math_delimiters != before.math_delimiters:
        raise FormattingError(
            "content cleaner changed math delimiter count "
            f"({before.math_delimiters} before, {after.math_delimiters} after)"
        )
    if after.table_like_lines < before.table_like_lines:
        raise FormattingError(
            "content cleaner removed table-like lines "
            f"({before.table_like_lines} before, {after.table_like_lines} after)"
        )


def run_content_plugin_protecting_headings(plugin: ModuleType, markdown: str) -> PluginResult:
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


def _write_text_artifact(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _provider_identity(provider_client: object) -> tuple[str, str]:
    return (
        str(getattr(provider_client, "base_url", "")),
        str(getattr(provider_client, "model", "")),
    )


def parse_python_artifact_from_text(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    if "def clean(" not in stripped or "def analyze(" not in stripped:
        raise FormattingError("python artifact must define analyze() and clean()")
    return stripped


def parse_json_artifact_from_text(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    # Sanitize invalid backslash escape sequences in the JSON string
    # Group 1 matches valid JSON escapes. Group 2 matches invalid backslashes.
    cleaned = re.sub(
        r'(\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})|(\\)',
        lambda m: m.group(1) if m.group(1) else '\\\\',
        stripped,
    )
    return cleaned


def find_total_pages_from_metadata(markdown_path: Path) -> int | None:
    search_roots = [
        Path(r"C:\Mathematics-Knowledge\agent-memory\records"),
        Path(r"C:\Mathematics-Knowledge\Mathematics-Knowledge-code\agent-memory\records"),
    ]
    target_name = markdown_path.name.lower()
    
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for record_dir in root.iterdir():
                if not record_dir.is_dir():
                    continue
                run_state_file = record_dir / "run-state.json"
                if run_state_file.exists():
                    try:
                        state_data = json.loads(run_state_file.read_text(encoding="utf-8"))
                        outputs = state_data.get("outputs", [])
                        matches = False
                        for out in outputs:
                            target_md = out.get("target_md", "")
                            if Path(target_md).name.lower() == target_name:
                                matches = True
                                break
                        if matches:
                            extracted_dir = record_dir / "extracted"
                            if extracted_dir.exists():
                                for part_dir in extracted_dir.iterdir():
                                    layout_file = part_dir / "layout.json"
                                    if layout_file.exists():
                                        try:
                                            layout_data = json.loads(layout_file.read_text(encoding="utf-8"))
                                            if "pdf_info" in layout_data and isinstance(layout_data["pdf_info"], list):
                                                return len(layout_data["pdf_info"])
                                        except Exception:
                                            pass
                    except Exception:
                        pass
        except Exception:
            pass
    return None


def extract_first_20_pages(markdown: str, markdown_path: Path) -> str:
    total_pages = find_total_pages_from_metadata(markdown_path) or 200
    lines = markdown.splitlines()
    total_lines = len(lines)
    
    lines_per_page = total_lines / total_pages if total_pages > 0 else 40
    num_lines = min(total_lines, max(800, int(20 * lines_per_page)))
    
    prepended_lines = [f"{i}: {line}" for i, line in enumerate(lines[:num_lines], start=1)]
    return "\n".join(prepended_lines) + ("\n" if prepended_lines else "")


def run_heading_optimization(
    markdown: str,
    provider_client: object,
    prompt: str,
    timeout_seconds: int = 120,
) -> dict[str, str]:
    heading_lines = [line.strip() for line in markdown.splitlines() if line.strip().startswith("#")]
    if not heading_lines:
        return {}

    input_payload = "\n".join(heading_lines)
    try:
        response = provider_client.chat(
            prompt,
            input_payload,
            timeout_seconds=timeout_seconds,
            response_format={"type": "json_object"}
        )
        payload = json.loads(parse_json_artifact_from_text(response))
        validated = {}
        for k, v in payload.items():
            k_strip = k.strip()
            v_strip = v.strip()
            if not k_strip.startswith("#") or not v_strip.startswith("#"):
                continue
            k_level = len(k_strip) - len(k_strip.lstrip("#"))
            v_level = len(v_strip) - len(v_strip.lstrip("#"))
            if k_level == v_level or 4 <= v_level <= 6:
                validated[k_strip] = v_strip
        return validated
    except Exception:
        return {}







def run_learning_from_provider(
    markdown_path: Path,
    provider_client: object,
    heading_prompt: str,
    content_prompt: str,
    work_dir: Path | None = None,
    timeout_seconds: int = 120,
    h1_index: int = 0,
) -> LearningRunResult:
    markdown_path = markdown_path.resolve()
    work_dir = work_dir or learning_work_dir_for(markdown_path)
    candidate_path = learning_candidate_path_for(markdown_path, work_dir)
    report_path = work_dir / "candidate-report.md"
    artifacts: dict[str, Path] = {}
    warnings: list[str] = []
    errors: list[str] = []
    provider_base_url, provider_model = _provider_identity(provider_client)
    current_stage = "inspect"

    def state(stage: str | None, status: str) -> None:
        write_learning_state(
            work_dir,
            LearningRunState(
                source_path=markdown_path,
                candidate_path=candidate_path,
                provider_base_url=provider_base_url,
                provider_model=provider_model,
                stage=stage or current_stage,
                status=status,
                artifacts=artifacts,
                warnings=warnings,
                errors=errors,
                approved=False,
            ),
        )

    try:
        original_text = markdown_path.read_text(encoding="utf-8")
        original_structure = extract_structure(original_text, str(markdown_path))

        current_stage = "toc-sample"
        toc_sample = extract_toc_sample(original_text, original_structure)
        artifacts["toc_sample"] = _write_text_artifact(work_dir / "toc_sample.md", toc_sample)

        current_stage = "heading-provider"
        heading_rules_file = work_dir / "heading_rules.json"
        if heading_rules_file.exists():
            heading_payload = json.loads(heading_rules_file.read_text(encoding="utf-8"))
            rules = validate_heading_rules(heading_payload)
            artifacts["heading_rules"] = heading_rules_file
        else:
            artifacts["heading_prompt"] = _write_text_artifact(work_dir / "heading_rules_prompt.md", heading_prompt)
            heading_response = provider_client.chat(heading_prompt, toc_sample, timeout_seconds=timeout_seconds, response_format={"type": "json_object"})
            artifacts["heading_response"] = _write_text_artifact(work_dir / "heading_rules_response.json", heading_response)
            heading_payload = json.loads(parse_json_artifact_from_text(heading_response))
            rules = validate_heading_rules(heading_payload)
            artifacts["heading_rules"] = _write_text_artifact(
                work_dir / "heading_rules.json",
                json.dumps(heading_payload, ensure_ascii=False, indent=2),
            )

        current_stage = "stage1-apply"
        work_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(markdown_path, candidate_path)
        candidate_text = candidate_path.read_text(encoding="utf-8")
        stage1_text = apply_heading_rules(candidate_text, rules)
        candidate_path.write_text(stage1_text, encoding="utf-8")
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path,
            candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=[rule.rule_id for rule in rules],
            plugin_summary=[],
            warnings=[],
        )
        current_stage = "stage1-audit"
        stage1_audit_summary = audit_stage1_headings(original_text, stage1_text)
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path,
            candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=[rule.rule_id for rule in rules] + stage1_audit_summary,
            plugin_summary=[],
            warnings=[],
        )

        current_stage = "toc-detection-provider"
        toc_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "toc_detection_prompt.md"
        toc_prompt = toc_prompt_path.read_text(encoding="utf-8")
        artifacts["toc_detection_prompt"] = _write_text_artifact(work_dir / "toc_detection_prompt.md", toc_prompt)
        
        toc_sample_20_pages = extract_first_20_pages(stage1_text, markdown_path)
        artifacts["toc_detection_sample"] = _write_text_artifact(work_dir / "toc_detection_sample.md", toc_sample_20_pages)
        
        toc_detection_response = provider_client.chat(
            toc_prompt,
            toc_sample_20_pages,
            timeout_seconds=timeout_seconds,
            response_format={"type": "json_object"}
        )
        artifacts["toc_detection_response"] = _write_text_artifact(work_dir / "toc_detection_response.json", toc_detection_response)
        
        toc_detection_payload = json.loads(parse_json_artifact_from_text(toc_detection_response))
        toc_start_line = toc_detection_payload.get("toc_start_line")
        main_text_start_line = toc_detection_payload.get("main_text_start_line")
        
        stage1_lines = stage1_text.splitlines(keepends=True)
        
        # 1. Parse and validate main_text_start_line (REQUIRED)
        try:
            main_text_start_line = int(main_text_start_line)
        except (ValueError, TypeError) as exc:
            raise FormattingError(f"LLM returned invalid type/value for main_text_start_line: {main_text_start_line}") from exc

        if main_text_start_line < 1 or main_text_start_line > len(stage1_lines):
            raise FormattingError(f"LLM returned invalid line number: {main_text_start_line}")

        # 2. Parse and validate toc_start_line (OPTIONAL/FALLBACK)
        stripped_text = stage1_text
        if toc_start_line is not None:
            try:
                toc_start_line = int(toc_start_line)
                if 1 <= toc_start_line <= main_text_start_line:
                    before_toc = stage1_lines[:toc_start_line - 1]
                    after_toc = stage1_lines[main_text_start_line - 1:]
                    stripped_text = "".join(before_toc + after_toc)
            except (ValueError, TypeError):
                pass
        candidate_path.write_text(stripped_text, encoding="utf-8")

        current_stage = "h1-sample"
        updated_structure = extract_structure(stripped_text, str(candidate_path))
        h1_sample = extract_h1_sample(stripped_text, updated_structure, h1_index=h1_index)
        artifacts["h1_sample"] = _write_text_artifact(work_dir / "h1_sample.md", h1_sample)

        current_stage = "content-provider"
        artifacts["content_prompt"] = _write_text_artifact(work_dir / "content_cleaner_prompt.md", content_prompt)
        content_response = provider_client.chat(
            content_prompt,
            h1_sample,
            timeout_seconds=timeout_seconds,
            response_format={"type": "json_object"},
        )
        artifacts["content_response"] = _write_text_artifact(work_dir / "content_rules_response.json", content_response)
        content_rules_payload = json.loads(parse_json_artifact_from_text(content_response))
        validate_content_rules(content_rules_payload)
        artifacts["content_rules"] = _write_text_artifact(
            work_dir / "content_rules.json",
            json.dumps(content_rules_payload, ensure_ascii=False, indent=2),
        )

        current_stage = "stage4-apply"
        try:
            plugin_result = run_content_rules_protecting_headings(content_rules_payload, stripped_text)
        except FormattingError:
            candidate_path.write_text(stripped_text, encoding="utf-8")
            raise

        # Stage 5: Heading Optimization
        current_stage = "heading-optimization-provider"
        heading_opt_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_optimization_prompt.md"
        heading_opt_prompt = heading_opt_prompt_path.read_text(encoding="utf-8")
        artifacts["heading_opt_prompt"] = _write_text_artifact(work_dir / "heading_optimization_prompt.md", heading_opt_prompt)

        opt_mapping = run_heading_optimization(
            plugin_result.cleaned_markdown,
            provider_client,
            heading_opt_prompt,
            timeout_seconds=timeout_seconds
        )

        final_markdown = plugin_result.cleaned_markdown
        if opt_mapping:
            artifacts["heading_optimizations"] = _write_text_artifact(
                work_dir / "heading_optimizations.json",
                json.dumps(opt_mapping, ensure_ascii=False, indent=2)
            )
            opt_lines = final_markdown.splitlines()
            for idx, l in enumerate(opt_lines):
                stripped = l.strip()
                if stripped in opt_mapping:
                    opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
            final_markdown = "\n".join(opt_lines) + "\n"

        candidate_path.write_text(final_markdown, encoding="utf-8")
        artifacts["candidate"] = candidate_path
        artifacts["report"] = write_review_report(
            original_path=markdown_path,
            candidate_path=candidate_path,
            report_path=report_path,
            heading_summary=[rule.rule_id for rule in rules],
            plugin_summary=plugin_result.summary,
            warnings=plugin_result.warnings,
        )
        warnings.extend(plugin_result.warnings)
        state("complete", "candidate-written")
        return LearningRunResult("candidate-written", work_dir, candidate_path, report_path, artifacts, plugin_result.summary, warnings, errors)
    except Exception as exc:
        if not errors:
            errors.append(str(exc))
        state(None, "failed")
        raise

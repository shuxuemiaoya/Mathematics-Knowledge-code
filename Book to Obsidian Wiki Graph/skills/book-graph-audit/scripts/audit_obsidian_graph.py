#!/usr/bin/env python3
"""Audit a corpus produced by the Book to Obsidian Wiki Graph agent."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any


LESSON_FLOW_SCRIPT_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "book-toc-splitting"
    / "scripts"
)
if str(LESSON_FLOW_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(LESSON_FLOW_SCRIPT_DIRECTORY))

from lesson_flow_manifest import validate as validate_lesson_flow


MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\(((?:[^()]|\([^()]*\))*)\)"
)
MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)"
)
HTML_IMAGE_RE = re.compile(
    r"""<img\b[^>]*?\bsrc=["']([^"']+)["']""", re.IGNORECASE
)
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
FENCE_RE = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
DISPLAY_MATH_RE = re.compile(r"(?<!\\)\$\$.*?(?<!\\)\$\$", re.DOTALL)
INLINE_MATH_RE = re.compile(
    r"(?<!\\)\$(?!\$).*?(?<!\\)\$",
    re.DOTALL,
)
EXTERNAL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
CALLOUT_RE = re.compile(r"^>\s*\[!([^\]]+)\]")
TOP_CALLOUT_DETAIL_RE = re.compile(
    r"^>\s*\[!([^\]]+)\][+-]?\s*(.*?)\s*$"
)
TOP_LEVEL_CALLOUT_PREFIX_RE = re.compile(r"^>\s*\[!")
NESTED_CALLOUT_RE = re.compile(r"^>\s+>\s*\[!([^\]]+)\]")
NESTED_CALLOUT_DETAIL_RE = re.compile(
    r"^>\s+>\s*\[!([^\]]+)\][+-]?\s*(.*?)\s*$"
)
NESTED_CALLOUT_PREFIX_RE = re.compile(r"^>\s+>\s*\[!")
EXAMPLE_CALLOUT_WITH_STEM_RE = re.compile(
    r"^>\s*\[!example\][+-]?\s+例(?:题)?\s*\d+\s+\S"
)
SUBPART_RE = re.compile(r"(?<![A-Za-z0-9_])[（(]([1-9]\d*)[）)]")
FORMAL_DEFINITION_CUE_RE = re.compile(r"(?:叫做|称为|定义为|称之为)")
COMPARISON_CONDITION_RE = re.compile(
    r"(?:[<>]|\\(?:ne|neq|le|leq|ge|geq|lt|gt)\b)"
)
TOP_REASONING_LABEL_RE = re.compile(
    r"^>\s+(?:\*\*)?(?:分析|思路|点拨|解|证明|解析|解答)"
    r"(?:\s*[：:])"
)
FUNCTIONAL_HEADING_RE = re.compile(
    r"^#{4,6}\s+"
    r"(?:观察|思考|探究|问题|实验|尝试|讨论|情景引入|分析|提示|"
    r"解答?|证明|归纳|结论|小结|注意|警告|定理|性质)"
    r"(?:\s|[：:，。]|$)"
)
PLAIN_FUNCTIONAL_LABEL_RE = re.compile(
    r"^(?:思考|观察|讨论|交流|尝试|想一想|议一议|观察·思考|尝试·交流|"
    r"思考·交流|回顾·反思|探究|实验|做一做|观察与猜想|操作与思考|"
    r"操作·交流|情景引入|情境引入|引入|引导|注意|易错|特别注意|"
    r"背景|旁注|补充材料|联系|区别|归纳|总结|小结|方法|规律|结论|"
    r"性质|定理|公理|法则)$"
)
WORKED_EXAMPLE_RE = re.compile(r"^(例(?:题)?\s*\d+)\s*(.*)$")
PRACTICE_BOUNDARY_RE = re.compile(
    r"^(?:#{4,6}\s+)?(?:练习|习题\s*\d+(?:\.\d+)*)(?:\s|$)"
)
FORMAL_DEFINITION_SCOPE_RE = re.compile(
    r"(?:叫做|定义为|称之为|记作|规定[：:]?|"
    r"(?:就)?称(?!性)[^，。；]{0,40}(?:为|是))"
)
ENTRY_HEADING_RE = re.compile(r"^#{1,3}\s+\S")
ORNAMENT_HEADING_RE = re.compile(r"^#{4,6}\s+[●•·\s]+$")
RUNNING_PUBLISHER_HEADING_RE = re.compile(r"^#{4,6}\s+人民教育出版社\s*$")
PLAIN_RUNNING_CHAPTER_RE = re.compile(
    r"^(?:\d{1,3}\s+)?第[〇零一二三四五六七八九十百\d]+章\s+\S.*$"
)
SPACED_DIGITS_RE = re.compile(r"(?<![\d.])\d(?:[ \t]+\d)+(?![\d.])")
HTML_TABLE_RE = re.compile(r"<table\b.*?</table\s*>", re.IGNORECASE | re.DOTALL)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
ALLOWED_NODE_TYPES = {"group", "text", "file", "link"}
DEFAULT_NODE_COLORS = {None, "1", "2", "3", "4", "5", "6", "#c800ff"}
DEFAULT_EDGE_COLORS = {None, "2", "4", "5", "6"}
AUDIT_STAGES = ("split", "concepts", "formatting", "pre-canvas", "final")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_fenced_code(text: str) -> str:
    return FENCE_RE.sub("", text)


def matches_outside_math(
    pattern: re.Pattern[str], text: str
) -> list[re.Match[str]]:
    """Return syntax matches not wholly contained in one TeX span."""

    display_spans = [match.span() for match in DISPLAY_MATH_RE.finditer(text)]
    inline_scan = list(text)
    for start, end in display_spans:
        inline_scan[start:end] = " " * (end - start)
    inline_spans = [
        match.span() for match in INLINE_MATH_RE.finditer("".join(inline_scan))
    ]
    spans = display_spans + inline_spans
    return [
        match
        for match in pattern.finditer(text)
        if not any(
            start <= match.start() and match.end() <= end
            for start, end in spans
        )
    ]


def category(path: Path, book_root: Path) -> str:
    try:
        relative = path.relative_to(book_root)
    except ValueError:
        return "<external-vault>"
    return relative.parts[0] if len(relative.parts) > 1 else "<root>"


def resolve_href(href: str, source: Path, vault_root: Path) -> Path | None:
    raw = href.strip().strip("<>")
    if EXTERNAL_SCHEME_RE.match(raw):
        return None
    path_text = raw.split("#", 1)[0].split("?", 1)[0]
    if not path_text:
        return source.resolve()

    vault_absolute = path_text.startswith(("/", "\\"))
    decoded = urllib.parse.unquote(path_text).replace("/", os.sep)
    if vault_absolute:
        return (vault_root / decoded.lstrip("/\\")).resolve()
    candidate = Path(decoded)
    if candidate.is_absolute():
        return candidate.resolve()

    relative_candidate = (source.parent / candidate).resolve()
    vault_candidate = (vault_root / candidate).resolve()
    first_part = candidate.parts[0] if candidate.parts else ""

    if relative_candidate.exists():
        return relative_candidate
    if vault_candidate.exists() or (vault_root / first_part).exists():
        return vault_candidate
    return relative_candidate


def target_exists(path: Path) -> bool:
    if path.exists():
        return True
    if not path.suffix and path.with_suffix(".md").exists():
        return True
    return False


def is_unstandardized_worked_example(line: str) -> bool:
    match = WORKED_EXAMPLE_RE.match(line)
    if match is None:
        return False
    suffix = match.group(2).lstrip()
    return not suffix.startswith(
        ("中", "的", "给出", "所述", "所得", "证明用到")
    )


def validate_callouts(
    path: Path,
    text: str,
    require_blank: bool = True,
    body_mode: str | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    malformed: list[dict[str, Any]] = []
    missing_blank: list[dict[str, Any]] = []
    body_violations: list[dict[str, Any]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not TOP_LEVEL_CALLOUT_PREFIX_RE.match(line):
            continue
        if not CALLOUT_RE.match(line):
            malformed.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                }
            )
            continue
        if require_blank and index > 0 and lines[index - 1].strip():
            missing_blank.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "previous": lines[index - 1][:200],
                }
            )
        if body_mode != "quoted-body":
            continue

        if index + 1 >= len(lines) or not lines[index + 1].startswith(">"):
            body_violations.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                    "reason": "missing-quoted-body",
                }
            )
            continue

        end = index + 1
        top_body_seen = bool(EXAMPLE_CALLOUT_WITH_STEM_RE.match(line))
        while end < len(lines) and lines[end].startswith(">"):
            current = lines[end]
            if NESTED_CALLOUT_PREFIX_RE.match(current):
                if not NESTED_CALLOUT_RE.match(current):
                    body_violations.append(
                        {
                            "file": str(path),
                            "line": end + 1,
                            "text": current[:200],
                            "reason": "malformed-nested-callout",
                        }
                    )
                if (
                    end + 1 >= len(lines)
                    or not lines[end + 1].startswith("> >")
                    or NESTED_CALLOUT_PREFIX_RE.match(lines[end + 1])
                ):
                    body_violations.append(
                        {
                            "file": str(path),
                            "line": end + 1,
                            "text": current[:200],
                            "reason": "missing-nested-quoted-body",
                        }
                    )
            elif current.startswith("> >"):
                if not any(
                    NESTED_CALLOUT_PREFIX_RE.match(lines[position])
                    for position in range(index + 1, end)
                ):
                    body_violations.append(
                        {
                            "file": str(path),
                            "line": end + 1,
                            "text": current[:200],
                            "reason": "nested-body-without-nested-marker",
                        }
                    )
            elif current.strip() != ">":
                top_body_seen = True
            end += 1

        if "[!example]" in line and not top_body_seen:
            body_violations.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                    "reason": "example-stem-not-in-parent-callout",
                }
            )
    if body_mode == "quoted-body":
        for index, line in enumerate(lines):
            if not NESTED_CALLOUT_PREFIX_RE.match(line):
                continue
            start = index - 1
            while start >= 0 and lines[start].startswith(">"):
                if TOP_LEVEL_CALLOUT_PREFIX_RE.match(lines[start]):
                    break
                start -= 1
            if start < 0 or not TOP_LEVEL_CALLOUT_PREFIX_RE.match(lines[start]):
                body_violations.append(
                    {
                        "file": str(path),
                        "line": index + 1,
                        "text": line[:200],
                        "reason": "nested-callout-without-parent",
                    }
                )
    return malformed, missing_blank, body_violations


def strip_quote_prefix(line: str) -> tuple[int, str]:
    """Return Obsidian quote depth and the unquoted line body."""

    depth = 0
    remainder = line
    while remainder.startswith(">"):
        depth += 1
        remainder = remainder[1:]
        if remainder.startswith(" "):
            remainder = remainder[1:]
    return depth, remainder


def callout_semantic_scope_issues(
    path: Path,
    text: str,
) -> list[dict[str, Any]]:
    """Reject functional blocks swallowed by an unrelated callout container."""

    issues: list[dict[str, Any]] = []
    active_type: str | None = None
    active_title = ""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        top = TOP_CALLOUT_DETAIL_RE.match(line)
        if top:
            active_type = top.group(1).casefold()
            active_title = top.group(2).strip()
            continue
        if not line.startswith(">"):
            active_type = None
            active_title = ""
            continue
        if active_type is None:
            continue

        depth, body = strip_quote_prefix(line)
        stripped = body.strip()
        if not stripped:
            continue
        nested = NESTED_CALLOUT_DETAIL_RE.match(line)
        if nested:
            nested_type = nested.group(1).casefold()
            if nested_type == "example":
                issues.append(
                    {
                        "file": str(path),
                        "line": index + 1,
                        "text": line[:200],
                        "reason": "worked-example-inside-non-example-callout",
                        "parent_callout": active_type,
                        "quote_depth": depth,
                    }
                )
            continue

        heading_text = stripped
        heading = re.match(r"^#{4,6}\s+(.+?)\s*$", stripped)
        if heading:
            heading_text = heading.group(1).strip()
            if re.fullmatch(r"[●•·\s]+", heading_text):
                issues.append(
                    {
                        "file": str(path),
                        "line": index + 1,
                        "text": line[:200],
                        "reason": "artifact-heading-inside-callout",
                        "parent_callout": active_type,
                        "quote_depth": depth,
                    }
                )
                continue
            if PRACTICE_BOUNDARY_RE.match(stripped):
                issues.append(
                    {
                        "file": str(path),
                        "line": index + 1,
                        "text": line[:200],
                        "reason": "practice-inside-callout",
                        "parent_callout": active_type,
                        "quote_depth": depth,
                    }
                )
                continue
            if FUNCTIONAL_HEADING_RE.match(stripped):
                issues.append(
                    {
                        "file": str(path),
                        "line": index + 1,
                        "text": line[:200],
                        "reason": "functional-heading-inside-callout",
                        "parent_callout": active_type,
                        "quote_depth": depth,
                    }
                )
                continue

        if PRACTICE_BOUNDARY_RE.match(heading_text):
            issues.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                    "reason": "practice-inside-callout",
                    "parent_callout": active_type,
                    "quote_depth": depth,
                }
            )
            continue
        example = WORKED_EXAMPLE_RE.match(heading_text)
        if example and is_unstandardized_worked_example(heading_text):
            issues.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                    "reason": (
                        "worked-example-inside-example-callout"
                        if active_type == "example"
                        else "worked-example-inside-non-example-callout"
                    ),
                    "parent_callout": active_type,
                    "quote_depth": depth,
                }
            )
            continue
        if PLAIN_FUNCTIONAL_LABEL_RE.match(heading_text):
            reason = "functional-label-inside-callout"
            if re.sub(r"\s+", "", heading_text) == re.sub(
                r"\s+", "", active_title
            ):
                reason = "duplicate-functional-label-inside-callout"
            issues.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                    "reason": reason,
                    "parent_callout": active_type,
                    "quote_depth": depth,
                }
            )
            continue
        if (
            active_type == "info"
            and any(label in active_title for label in ("情景引入", "情境引入"))
            and FORMAL_DEFINITION_SCOPE_RE.search(heading_text)
        ):
            issues.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                    "reason": "formal-definition-inside-situation-callout",
                    "parent_callout": active_type,
                    "quote_depth": depth,
                }
            )
    return issues


def content_consistency_issues(
    path: Path,
    text: str,
) -> list[dict[str, Any]]:
    """Find source-completeness defects that presentation checks cannot prove."""

    issues: list[dict[str, Any]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        plain = re.sub(r"^(?:>\s*)+", "", line).strip()
        if FORMAL_DEFINITION_CUE_RE.search(plain):
            math_fragments = [
                match.group(0)
                for match in DISPLAY_MATH_RE.finditer(plain)
            ]
            masked = list(plain)
            for match in DISPLAY_MATH_RE.finditer(plain):
                masked[match.start() : match.end()] = " " * (
                    match.end() - match.start()
                )
            math_fragments.extend(
                match.group(0)
                for match in INLINE_MATH_RE.finditer("".join(masked))
            )
            if any(
                COMPARISON_CONDITION_RE.search(fragment)
                and fragment.count("(") != fragment.count(")")
                for fragment in math_fragments
            ):
                issues.append(
                    {
                        "file": str(path),
                        "line": index + 1,
                        "reason": "unbalanced-parentheses-in-formal-definition",
                        "text": plain[:200],
                    }
                )

        if not re.match(r"^>\s*\[!example\]", line):
            continue
        end = index + 1
        while end < len(lines) and lines[end].startswith(">"):
            end += 1
        block = lines[index:end]
        parent_text: list[str] = [line]
        solution_text: list[str] = []
        in_solution = False
        for block_line in block[1:]:
            if re.match(
                r"^>\s+>\s*\[!(?:success)\][+-]?\s+"
                r"(?:解|证明|解析|解答)\b",
                block_line,
            ):
                in_solution = True
                continue
            if re.match(r"^>\s+>\s*\[!", block_line):
                in_solution = False
                continue
            if block_line.startswith("> >"):
                if in_solution:
                    solution_text.append(block_line)
            else:
                parent_text.append(block_line)
        parent_parts = {int(item) for item in SUBPART_RE.findall("\n".join(parent_text))}
        solution_parts = {
            int(item) for item in SUBPART_RE.findall("\n".join(solution_text))
        }
        # Numbered solution steps can be a proof structure even when the
        # example stem is a single task. Only claim source loss when the stem
        # itself establishes a numbered-subpart contract.
        missing = sorted(solution_parts - parent_parts) if parent_parts else []
        if missing:
            issues.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "reason": "solution-subpart-missing-from-example-stem",
                    "missing_subparts": missing,
                    "text": line[:200],
                }
            )

    for index, line in enumerate(lines):
        if not TOP_LEVEL_CALLOUT_PREFIX_RE.match(line):
            continue
        end = index + 1
        while end < len(lines) and lines[end].startswith(">"):
            candidate = lines[end]
            if TOP_REASONING_LABEL_RE.match(candidate):
                issues.append(
                    {
                        "file": str(path),
                        "line": end + 1,
                        "reason": "reasoning-label-not-nested",
                        "text": candidate[:200],
                    }
                )
            end += 1
    return issues


def suspicious_ocr_math(text: str) -> list[dict[str, Any]]:
    """Find digit groups that OCR split inside TeX spans, such as ``1 2``."""

    display_spans = [match.span() for match in DISPLAY_MATH_RE.finditer(text)]
    inline_scan = list(text)
    for start, end in display_spans:
        inline_scan[start:end] = " " * (end - start)
    math_matches = list(DISPLAY_MATH_RE.finditer(text))
    math_matches.extend(INLINE_MATH_RE.finditer("".join(inline_scan)))
    findings: list[dict[str, Any]] = []
    for math_match in math_matches:
        raw = text[math_match.start() : math_match.end()]
        for digit_match in SPACED_DIGITS_RE.finditer(raw):
            absolute = math_match.start() + digit_match.start()
            findings.append(
                {
                    "line": text.count("\n", 0, absolute) + 1,
                    "text": digit_match.group(0),
                }
            )
    return findings


def malformed_html_tables(text: str) -> list[dict[str, Any]]:
    """Find table blocks with broken tags, TeX delimiters, or braces."""

    findings: list[dict[str, Any]] = []
    for match in HTML_TABLE_RE.finditer(text):
        block = match.group(0)
        reasons: list[str] = []
        for tag in ("table", "tr", "td", "th"):
            opened = len(re.findall(rf"<{tag}\b", block, re.IGNORECASE))
            closed = len(re.findall(rf"</{tag}\s*>", block, re.IGNORECASE))
            if opened != closed:
                reasons.append(f"unbalanced-{tag}-tags")
        if block.count(r"\(") != block.count(r"\)"):
            reasons.append("unbalanced-inline-tex-parentheses")
        if block.count(r"\[") != block.count(r"\]"):
            reasons.append("unbalanced-display-tex-brackets")
        if block.count("{") != block.count("}"):
            reasons.append("unbalanced-tex-braces")
        if reasons:
            findings.append(
                {
                    "line": text.count("\n", 0, match.start()) + 1,
                    "reasons": reasons,
                    "text": re.sub(r"\s+", " ", block)[:240],
                }
            )
    return findings


def audit_coverage(
    coverage_path: Path | None,
    expected_source_sha256: str | None,
    *,
    expected_profile: Path | None = None,
    book_root: Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if coverage_path is None:
        return None, []
    errors: list[dict[str, Any]] = []
    try:
        data = json.loads(coverage_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [
            {
                "code": "coverage-invalid-json",
                "path": str(coverage_path),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]

    units = data.get("units")
    if not isinstance(units, list):
        return None, [
            {
                "code": "coverage-missing-units",
                "path": str(coverage_path),
            }
        ]
    if (
        expected_source_sha256
        and data.get("source_sha256") != expected_source_sha256
    ):
        errors.append(
            {
                "code": "coverage-source-hash-mismatch",
                "expected": expected_source_sha256,
                "actual": data.get("source_sha256"),
            }
        )
    if expected_profile is not None:
        raw_profile = data.get("profile")
        if not isinstance(raw_profile, str) or (
            Path(raw_profile).resolve() != expected_profile
        ):
            errors.append(
                {
                    "code": "coverage-profile-mismatch",
                    "expected": str(expected_profile),
                    "actual": raw_profile,
                }
            )

    keys: set[str] = set()
    orders: set[int] = set()
    unresolved = 0
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            errors.append({"code": "coverage-unit-not-object", "index": index})
            continue
        key = unit.get("source_key")
        order = unit.get("source_order")
        status = unit.get("status")
        target = unit.get("target")
        if not isinstance(key, str) or not key:
            errors.append({"code": "coverage-missing-key", "index": index})
        elif key in keys:
            errors.append({"code": "coverage-duplicate-key", "source_key": key})
        else:
            keys.add(key)
        if not isinstance(order, int):
            errors.append({"code": "coverage-invalid-order", "source_key": key})
        elif order in orders:
            errors.append({"code": "coverage-duplicate-order", "source_order": order})
        else:
            orders.add(order)
        if status not in {"assigned", "retained"}:
            unresolved += 1
            errors.append(
                {
                    "code": "coverage-unresolved-unit",
                    "source_key": key,
                    "status": status,
                }
            )
        if not isinstance(target, str) or not target:
            errors.append({"code": "coverage-missing-target", "source_key": key})
        elif book_root is not None:
            decoded = urllib.parse.unquote(target.split("#", 1)[0])
            target_path = (book_root / decoded.replace("/", os.sep)).resolve()
            if not target_exists(target_path):
                errors.append(
                    {
                        "code": "coverage-target-missing",
                        "source_key": key,
                        "target": target,
                        "resolved": str(target_path),
                    }
                )

    summary = {
        "path": str(coverage_path),
        "units": len(units),
        "assigned": sum(unit.get("status") == "assigned" for unit in units if isinstance(unit, dict)),
        "retained": sum(unit.get("status") == "retained" for unit in units if isinstance(unit, dict)),
        "unresolved": unresolved,
    }
    return summary, errors


def audit_canvas(
    canvas_path: Path,
    vault_root: Path,
    book_root: Path,
    *,
    allowed_node_colors: set[str | None] | None = None,
    allowed_edge_colors: set[str | None] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    allowed_node_colors = allowed_node_colors or DEFAULT_NODE_COLORS
    allowed_edge_colors = allowed_edge_colors or DEFAULT_EDGE_COLORS
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        canvas = json.loads(canvas_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return (
            {"path": str(canvas_path), "parsed": False},
            [
                {
                    "code": "canvas-invalid-json",
                    "path": str(canvas_path),
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            ],
            warnings,
        )

    nodes = canvas.get("nodes")
    edges = canvas.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return (
            {"path": str(canvas_path), "parsed": True},
            [
                {
                    "code": "canvas-invalid-shape",
                    "path": str(canvas_path),
                }
            ],
            warnings,
        )

    node_ids: list[str] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    linked_targets: collections.Counter[str] = collections.Counter()
    missing_links = 0
    node_colors: collections.Counter[str] = collections.Counter()
    edge_colors: collections.Counter[str] = collections.Counter()

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append({"code": "canvas-node-not-object", "index": index})
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        color = node.get("color")
        if not isinstance(node_id, str) or not node_id:
            errors.append({"code": "canvas-node-missing-id", "index": index})
            continue
        node_ids.append(node_id)
        node_by_id[node_id] = node
        if node_type not in ALLOWED_NODE_TYPES:
            errors.append(
                {
                    "code": "canvas-node-invalid-type",
                    "id": node_id,
                    "type": node_type,
                }
            )
        if color not in allowed_node_colors:
            errors.append(
                {
                    "code": "canvas-node-invalid-color",
                    "id": node_id,
                    "color": color,
                }
            )
        node_colors[str(color) if color is not None else "<none>"] += 1

        text = node.get("text", "")
        if isinstance(text, str):
            for _, href in MARKDOWN_LINK_RE.findall(remove_fenced_code(text)):
                target = resolve_href(href, canvas_path, vault_root)
                if target is not None:
                    linked_targets[str(target).casefold()] += 1
                    if not target_exists(target):
                        missing_links += 1
                        errors.append(
                            {
                                "code": "canvas-missing-link",
                                "canvas": str(canvas_path),
                                "node": node_id,
                                "href": href,
                                "resolved": str(target),
                            }
                        )
        if node_type == "file" and isinstance(node.get("file"), str):
            target = resolve_href(node["file"], canvas_path, vault_root)
            if target is not None and not target_exists(target):
                missing_links += 1
                errors.append(
                    {
                        "code": "canvas-missing-file-node",
                        "canvas": str(canvas_path),
                        "node": node_id,
                        "file": node["file"],
                        "resolved": str(target),
                    }
                )

    duplicate_ids = sorted(
        node_id for node_id, count in collections.Counter(node_ids).items() if count > 1
    )
    for node_id in duplicate_ids:
        errors.append({"code": "canvas-duplicate-node-id", "id": node_id})

    edge_ids: list[str] = []
    bad_endpoints = 0
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append({"code": "canvas-edge-not-object", "index": index})
            continue
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id:
            errors.append({"code": "canvas-edge-missing-id", "index": index})
        else:
            edge_ids.append(edge_id)
        for field in ("fromNode", "toNode"):
            if edge.get(field) not in node_by_id:
                bad_endpoints += 1
                errors.append(
                    {
                        "code": "canvas-edge-missing-endpoint",
                        "edge": edge_id,
                        "field": field,
                        "value": edge.get(field),
                    }
                )
        color = edge.get("color")
        if color not in allowed_edge_colors:
            errors.append(
                {
                    "code": "canvas-edge-invalid-color",
                    "edge": edge_id,
                    "color": color,
                }
            )
        edge_colors[str(color) if color is not None else "<none>"] += 1

    duplicate_edge_ids = sorted(
        edge_id
        for edge_id, count in collections.Counter(edge_ids).items()
        if count > 1
    )
    for edge_id in duplicate_edge_ids:
        errors.append({"code": "canvas-duplicate-edge-id", "id": edge_id})

    duplicate_targets = sum(count - 1 for count in linked_targets.values() if count > 1)
    if duplicate_targets:
        warnings.append(
            {
                "code": "canvas-duplicate-linked-targets",
                "count": duplicate_targets,
            }
        )

    summary = {
        "path": str(canvas_path),
        "parsed": True,
        "nodes": len(nodes),
        "groups": sum(
            isinstance(node, dict) and node.get("type") == "group" for node in nodes
        ),
        "edges": len(edges),
        "duplicate_node_ids": len(duplicate_ids),
        "duplicate_edge_ids": len(duplicate_edge_ids),
        "bad_edge_endpoints": bad_endpoints,
        "missing_links": missing_links,
        "node_colors": dict(sorted(node_colors.items())),
        "edge_colors": dict(sorted(edge_colors.items())),
    }
    return summary, errors, warnings


def load_profile(
    profile_path: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [
            {
                "code": "profile-invalid-json",
                "path": str(profile_path),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]
    errors: list[dict[str, Any]] = []
    if profile.get("schema_version") != 1:
        errors.append({"code": "profile-invalid-schema-version"})
    for section in ("book", "source", "paths", "links", "workspace"):
        if not isinstance(profile.get(section), dict):
            errors.append({"code": "profile-invalid-section", "section": section})
    categories = profile.get("categories")
    if not isinstance(categories, list):
        errors.append({"code": "profile-invalid-categories"})
    return profile, errors


def profile_category(
    profile: dict[str, Any] | None, role: str
) -> dict[str, Any] | None:
    if profile is None:
        return None
    for item in profile.get("categories", []):
        if isinstance(item, dict) and item.get("role") == role:
            return item
    return None


def audit_concept_manifest(
    manifest_path: Path | None,
    *,
    expected_source_sha256: str | None,
    expected_profile: Path | None,
    book_root: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if manifest_path is None:
        return None, []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [
            {
                "code": "concept-manifest-invalid-json",
                "path": str(manifest_path),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]
    errors: list[dict[str, Any]] = []
    if expected_source_sha256 and (
        data.get("source_sha256") != expected_source_sha256
    ):
        errors.append(
            {
                "code": "concept-manifest-source-hash-mismatch",
                "expected": expected_source_sha256,
                "actual": data.get("source_sha256"),
            }
        )
    if expected_profile is not None:
        raw_profile = data.get("profile")
        if not isinstance(raw_profile, str) or (
            Path(raw_profile).resolve() != expected_profile
        ):
            errors.append(
                {
                    "code": "concept-manifest-profile-mismatch",
                    "expected": str(expected_profile),
                    "actual": raw_profile,
                }
            )
    concepts = data.get("concepts")
    if not isinstance(concepts, list):
        return None, [
            *errors,
            {
                "code": "concept-manifest-missing-concepts",
                "path": str(manifest_path),
            },
        ]
    targets: set[str] = set()
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            errors.append(
                {"code": "concept-manifest-item-not-object", "index": index}
            )
            continue
        target = concept.get("target")
        if not isinstance(target, str) or not target:
            errors.append(
                {"code": "concept-manifest-target-missing", "index": index}
            )
            continue
        if target in targets:
            errors.append(
                {"code": "concept-manifest-target-duplicate", "target": target}
            )
        targets.add(target)
        decoded = urllib.parse.unquote(target.split("#", 1)[0])
        resolved = (book_root / decoded.replace("/", os.sep)).resolve()
        if not target_exists(resolved):
            errors.append(
                {
                    "code": "concept-manifest-target-missing-on-disk",
                    "target": target,
                    "resolved": str(resolved),
                }
            )
        linked_from = concept.get("linked_from")
        if not isinstance(linked_from, list) or not linked_from:
            errors.append(
                {
                    "code": "concept-manifest-missing-definition-link",
                    "target": target,
                }
            )
    return {
        "path": str(manifest_path),
        "concepts": len(concepts),
        "unique_targets": len(targets),
    }, errors


def audit_book(
    book_root: Path,
    vault_root: Path,
    *,
    source: Path | None = None,
    expected_source_sha256: str | None = None,
    allow_wikilinks: bool = False,
    require_canvas: bool = False,
    coverage_manifest: Path | None = None,
    concept_manifest: Path | None = None,
    lesson_flow_manifest: Path | None = None,
    profile_path: Path | None = None,
    stage: str = "pre-canvas",
) -> dict[str, Any]:
    if stage not in AUDIT_STAGES:
        raise ValueError(f"unsupported audit stage: {stage}")

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    profile: dict[str, Any] | None = None
    profile_canvas_enabled: bool | None = None
    concept_directory = "概念"
    require_callout_blank = True
    callout_body_mode = "quoted-body"
    note_mode: str | None = None
    allowed_node_colors = DEFAULT_NODE_COLORS
    allowed_edge_colors = DEFAULT_EDGE_COLORS
    require_concepts = stage in {"concepts", "formatting", "pre-canvas", "final"}
    require_standardized_markdown = stage in {"formatting", "pre-canvas", "final"}
    require_lesson_flow = False
    lesson_flow_summary: dict[str, Any] | None = None

    if profile_path is not None:
        profile, profile_errors = load_profile(profile_path)
        errors.extend(profile_errors)
        if profile is not None:
            profile_paths = profile.get("paths", {})
            profile_book_root = Path(
                profile_paths.get("book_root", "")
            ).resolve()
            profile_vault_root = Path(
                profile_paths.get("vault_root", "")
            ).resolve()
            if profile_book_root != book_root:
                errors.append(
                    {
                        "code": "profile-book-root-mismatch",
                        "expected": str(profile_book_root),
                        "actual": str(book_root),
                    }
                )
            if profile_vault_root != vault_root:
                errors.append(
                    {
                        "code": "profile-vault-root-mismatch",
                        "expected": str(profile_vault_root),
                        "actual": str(vault_root),
                    }
                )
            profile_sha256 = profile.get("source", {}).get("sha256")
            if expected_source_sha256 is None:
                expected_source_sha256 = profile_sha256
            elif expected_source_sha256 != profile_sha256:
                errors.append(
                    {
                        "code": "profile-source-hash-mismatch",
                        "expected": expected_source_sha256,
                        "actual": profile_sha256,
                    }
                )
            if source is None:
                raw_source = profile.get("source", {}).get("path")
                if isinstance(raw_source, str) and raw_source:
                    source = Path(raw_source).resolve()
            links = profile.get("links", {})
            note_mode = links.get("note_mode")
            if links.get("markdown_only") is False:
                allow_wikilinks = True
            require_callout_blank = profile.get("formatting", {}).get(
                "blank_before_top_level_callout", True
            )
            callout_body_mode = profile.get("formatting", {}).get(
                "callout_body_mode", "quoted-body"
            )
            if callout_body_mode != "quoted-body":
                errors.append(
                    {
                        "code": "invalid-callout-body-mode",
                        "value": callout_body_mode,
                    }
                )
            concept_config = profile_category(profile, "concept")
            if concept_config and concept_config.get("enabled", True):
                concept_directory = str(concept_config.get("directory", "概念"))
            elif concept_config and not concept_config.get("enabled", True):
                concept_directory = ""
            canvas_profile = profile.get("canvas", {})
            profile_canvas_enabled = bool(canvas_profile.get("enabled", False))
            node_palette = canvas_profile.get("node_colors")
            edge_palette = canvas_profile.get("edge_colors")
            if isinstance(node_palette, dict):
                allowed_node_colors = {None, *node_palette.values()}
            if isinstance(edge_palette, dict):
                allowed_edge_colors = {None, *edge_palette.values()}
            decomposition = profile.get("decomposition", {})
            require_lesson_flow = bool(
                isinstance(decomposition, dict)
                and decomposition.get("require_lesson_flow_manifest", False)
                and "textbook"
                in str(profile.get("book", {}).get("kind", "")).casefold()
            )
    if require_lesson_flow:
        if lesson_flow_manifest is None:
            errors.append({"code": "lesson-flow-manifest-not-provided"})
        elif profile_path is None:
            errors.append({"code": "lesson-flow-profile-not-provided"})
        else:
            try:
                lesson_flow_payload = json.loads(
                    lesson_flow_manifest.read_text(encoding="utf-8-sig")
                )
                lesson_flow_summary = validate_lesson_flow(
                    lesson_flow_payload,
                    formatted_markdown=Path(
                        lesson_flow_payload["formatted_markdown"]
                    ).resolve(),
                    split_manifest_path=Path(
                        lesson_flow_payload["split_manifest"]
                    ).resolve(),
                    profile_path=profile_path.resolve(),
                )
                lesson_flow_summary["path"] = str(
                    lesson_flow_manifest.resolve()
                )
            except Exception as exc:
                errors.append(
                    {
                        "code": "lesson-flow-manifest-invalid",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                )
    if stage == "final" and profile_canvas_enabled is not False:
        require_canvas = True
    if require_canvas and profile_canvas_enabled is False:
        errors.append({"code": "canvas-required-but-profile-disabled"})

    if not book_root.is_dir():
        return {
            "schema_version": 1,
            "stage": stage,
            "status": "failed",
            "errors": [{"code": "book-root-missing", "path": str(book_root)}],
            "warnings": [],
        }
    if not vault_root.is_dir():
        return {
            "schema_version": 1,
            "stage": stage,
            "status": "failed",
            "errors": [{"code": "vault-root-missing", "path": str(vault_root)}],
            "warnings": [],
        }
    try:
        book_root.relative_to(vault_root)
    except ValueError:
        errors.append(
            {
                "code": "book-root-outside-vault",
                "book_root": str(book_root),
                "vault_root": str(vault_root),
            }
        )

    source_summary = None
    if source is not None:
        if not source.is_file():
            errors.append({"code": "source-missing", "path": str(source)})
        else:
            actual_hash = sha256_file(source)
            source_summary = {
                "path": str(source),
                "sha256": actual_hash,
                "unchanged": (
                    expected_source_sha256 is None
                    or actual_hash == expected_source_sha256
                ),
            }
            if expected_source_sha256 and actual_hash != expected_source_sha256:
                errors.append(
                    {
                        "code": "source-hash-changed",
                        "expected": expected_source_sha256,
                        "actual": actual_hash,
                    }
                )
    elif expected_source_sha256:
        errors.append({"code": "expected-source-hash-without-source"})

    coverage_summary, coverage_errors = audit_coverage(
        coverage_manifest,
        expected_source_sha256,
        expected_profile=profile_path,
        book_root=book_root,
    )
    errors.extend(coverage_errors)
    if coverage_manifest is None:
        if profile_path is not None:
            errors.append({"code": "coverage-manifest-not-provided"})
        else:
            warnings.append({"code": "coverage-manifest-not-provided"})

    concept_summary, concept_manifest_errors = audit_concept_manifest(
        concept_manifest,
        expected_source_sha256=expected_source_sha256,
        expected_profile=profile_path,
        book_root=book_root,
    )
    errors.extend(concept_manifest_errors)
    if concept_directory and concept_manifest is None and require_concepts:
        if profile_path is not None:
            errors.append({"code": "concept-manifest-not-provided"})
        else:
            warnings.append({"code": "concept-manifest-not-provided"})

    markdown_files = sorted(book_root.rglob("*.md"))
    all_images = sorted(
        path
        for path in book_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    category_files: collections.Counter[str] = collections.Counter()
    transitions: collections.Counter[str] = collections.Counter()
    referenced_images: set[str] = set()
    referenced_concepts: set[str] = set()
    concept_root = book_root / concept_directory if concept_directory else None
    concept_files = (
        sorted(concept_root.rglob("*.md"))
        if concept_root is not None and concept_root.is_dir()
        else []
    )
    standard_links = 0
    wikilinks = 0
    image_references = 0
    missing_markdown_links = 0
    missing_images = 0
    malformed_callouts = 0
    callouts_without_blank = 0
    callout_body_violations = 0
    callout_semantic_scope_violations = 0
    callouts = 0
    unstandardized_functional_blocks = 0
    empty_notes = 0
    empty_concepts = 0
    invalid_entry_headings = 0
    malformed_concept_notes = 0
    non_vault_root_note_links = 0
    residual_artifact_headings = 0
    plain_running_headers = 0
    suspicious_ocr_math_fragments = 0
    malformed_table_blocks = 0
    content_consistency_violations = 0

    for path in markdown_files:
        source_category = category(path, book_root)
        category_files[source_category] += 1
        text = path.read_text(encoding="utf-8-sig")
        if not text.strip():
            empty_notes += 1
            errors.append(
                {
                    "code": "empty-markdown-note",
                    "path": str(path.relative_to(book_root)),
                }
            )
        first_nonblank = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            "",
        )
        is_concept = bool(concept_directory and source_category == concept_directory)
        if not is_concept and not ENTRY_HEADING_RE.match(first_nonblank):
            invalid_entry_headings += 1
            errors.append(
                {
                    "code": "invalid-note-entry-heading",
                    "path": str(path.relative_to(book_root)),
                    "first_line": first_nonblank[:200],
                }
            )
        sanitized = remove_fenced_code(text)
        found_wikilinks = [
            match.group(1)
            for match in matches_outside_math(WIKILINK_RE, sanitized)
        ]
        wikilinks += len(found_wikilinks)
        if found_wikilinks and not allow_wikilinks:
            errors.append(
                {
                    "code": "residual-wikilinks",
                    "path": str(path.relative_to(book_root)),
                    "count": len(found_wikilinks),
                    "samples": found_wikilinks[:10],
                }
            )

        malformed, no_blank, body_scope = validate_callouts(
            path.relative_to(book_root),
            text,
            require_blank=require_callout_blank,
            body_mode=(
                callout_body_mode if require_standardized_markdown else None
            ),
        )
        malformed_callouts += len(malformed)
        callouts_without_blank += len(no_blank)
        callout_body_violations += len(body_scope)
        for item in malformed:
            errors.append({"code": "malformed-callout", **item})
        for item in no_blank:
            errors.append({"code": "callout-missing-blank-line", **item})
        for item in body_scope:
            errors.append({"code": "callout-body-discontinuous", **item})
        callouts += sum(
            1 for line in text.splitlines() if CALLOUT_RE.match(line)
        )

        if (
            require_standardized_markdown
            and profile_path is not None
            and source_category != concept_directory
        ):
            semantic_scope = callout_semantic_scope_issues(
                path.relative_to(book_root),
                text,
            )
            callout_semantic_scope_violations += len(semantic_scope)
            for item in semantic_scope:
                errors.append({"code": "callout-semantic-scope", **item})

            candidates: list[dict[str, Any]] = []
            for index, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if (
                    FUNCTIONAL_HEADING_RE.match(stripped)
                    or PLAIN_FUNCTIONAL_LABEL_RE.match(stripped)
                    or is_unstandardized_worked_example(stripped)
                ):
                    candidates.append(
                        {"line": index, "text": stripped[:160]}
                    )
            if candidates:
                unstandardized_functional_blocks += len(candidates)
                errors.append(
                    {
                        "code": "unstandardized-functional-blocks",
                        "path": str(path.relative_to(book_root)),
                        "count": len(candidates),
                        "samples": candidates[:20],
                    }
                )
            artifact_candidates: list[dict[str, Any]] = []
            for index, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if ORNAMENT_HEADING_RE.match(stripped) or (
                    source_category != "<root>"
                    and RUNNING_PUBLISHER_HEADING_RE.match(stripped)
                ):
                    artifact_candidates.append(
                        {"line": index, "text": stripped[:160]}
                    )
            if artifact_candidates:
                residual_artifact_headings += len(artifact_candidates)
                errors.append(
                    {
                        "code": "residual-artifact-headings",
                        "path": str(path.relative_to(book_root)),
                        "count": len(artifact_candidates),
                        "samples": artifact_candidates[:20],
                    }
                )
            running_candidates = [
                {"line": index, "text": line.strip()[:160]}
                for index, line in enumerate(text.splitlines(), start=1)
                if PLAIN_RUNNING_CHAPTER_RE.match(line.strip())
            ]
            if running_candidates:
                plain_running_headers += len(running_candidates)
                errors.append(
                    {
                        "code": "plain-running-chapter-headers",
                        "path": str(path.relative_to(book_root)),
                        "count": len(running_candidates),
                        "samples": running_candidates[:20],
                    }
                )
            ocr_math_candidates = suspicious_ocr_math(sanitized)
            if ocr_math_candidates:
                suspicious_ocr_math_fragments += len(ocr_math_candidates)
                errors.append(
                    {
                        "code": "suspicious-ocr-spaced-digits-in-math",
                        "path": str(path.relative_to(book_root)),
                        "count": len(ocr_math_candidates),
                        "samples": ocr_math_candidates[:20],
                    }
                )
            table_candidates = malformed_html_tables(sanitized)
            if table_candidates:
                malformed_table_blocks += len(table_candidates)
                errors.append(
                    {
                        "code": "malformed-html-table-content",
                        "path": str(path.relative_to(book_root)),
                        "count": len(table_candidates),
                        "samples": table_candidates[:20],
                    }
                )
            consistency_candidates = content_consistency_issues(
                path.relative_to(book_root),
                text,
            )
            if consistency_candidates:
                content_consistency_violations += len(consistency_candidates)
                errors.append(
                    {
                        "code": "content-consistency-review-required",
                        "path": str(path.relative_to(book_root)),
                        "count": len(consistency_candidates),
                        "samples": consistency_candidates[:20],
                    }
                )

        for link_match in matches_outside_math(MARKDOWN_LINK_RE, sanitized):
            href = link_match.group(2)
            standard_links += 1
            target = resolve_href(href, path, vault_root)
            if target is None:
                transitions[f"{source_category}-><external-url>"] += 1
                continue
            if note_mode == "vault-root" and not href.strip().startswith(("/", "\\")):
                non_vault_root_note_links += 1
                errors.append(
                    {
                        "code": "non-vault-root-note-link",
                        "source": str(path.relative_to(book_root)),
                        "href": href,
                    }
                )
            transitions[f"{source_category}->{category(target, book_root)}"] += 1
            if not target_exists(target):
                missing_markdown_links += 1
                errors.append(
                    {
                        "code": "missing-markdown-link",
                        "source": str(path.relative_to(book_root)),
                        "href": href,
                        "resolved": str(target),
                    }
                )
            if (
                concept_directory
                and source_category != concept_directory
                and category(target, book_root) == concept_directory
            ):
                referenced_concepts.add(str(target).casefold())

        image_hrefs = MARKDOWN_IMAGE_RE.findall(sanitized) + HTML_IMAGE_RE.findall(
            sanitized
        )
        image_references += len(image_hrefs)
        for href in image_hrefs:
            target = resolve_href(href, path, vault_root)
            if target is None:
                continue
            referenced_images.add(str(target).casefold())
            if not target.exists():
                missing_images += 1
                errors.append(
                    {
                        "code": "missing-image",
                        "source": str(path.relative_to(book_root)),
                        "href": href,
                        "resolved": str(target),
                    }
                )

    for concept in concept_files if require_concepts else []:
        text = concept.read_text(encoding="utf-8-sig").strip()
        lines = text.splitlines()
        first_nonblank = next((line.strip() for line in lines if line.strip()), "")
        has_definition_heading = any(
            line.strip() == "## 定义" for line in lines
        )
        if first_nonblank != f"# {concept.stem}" or not has_definition_heading:
            malformed_concept_notes += 1
            errors.append(
                {
                    "code": "malformed-concept-note-structure",
                    "path": str(concept.relative_to(book_root)),
                    "expected_title": f"# {concept.stem}",
                    "has_definition_heading": has_definition_heading,
                }
            )
        semantic_text = MARKDOWN_LINK_RE.sub("", remove_fenced_code(text))
        semantic_text = re.sub(r"^#{1,6}\s+.*$", "", semantic_text, flags=re.MULTILINE)
        semantic_text = re.sub(r"\s+", "", semantic_text)
        if len(semantic_text) < 4:
            empty_concepts += 1
            errors.append(
                {
                    "code": "empty-or-link-only-concept",
                    "path": str(concept.relative_to(book_root)),
                }
            )
        if str(concept.resolve()).casefold() not in referenced_concepts:
            errors.append(
                {
                    "code": "orphan-concept",
                    "path": str(concept.relative_to(book_root)),
                }
            )

    unreferenced_images = [
        str(path.relative_to(book_root))
        for path in all_images
        if str(path.resolve()).casefold() not in referenced_images
    ]
    if unreferenced_images:
        warnings.append(
            {
                "code": "unreferenced-images",
                "count": len(unreferenced_images),
                "samples": unreferenced_images[:30],
            }
        )

    audit_canvas_files = stage in {"pre-canvas", "final"} or require_canvas
    canvas_paths = sorted(book_root.glob("*.canvas")) if audit_canvas_files else []
    if require_canvas and not canvas_paths:
        errors.append({"code": "required-canvas-missing"})
    if len(canvas_paths) > 1:
        warnings.append(
            {
                "code": "multiple-book-root-canvases",
                "count": len(canvas_paths),
                "paths": [str(path) for path in canvas_paths],
            }
        )
    canvas_summaries: list[dict[str, Any]] = []
    for canvas_path in canvas_paths:
        summary, canvas_errors, canvas_warnings = audit_canvas(
            canvas_path,
            vault_root,
            book_root,
            allowed_node_colors=allowed_node_colors,
            allowed_edge_colors=allowed_edge_colors,
        )
        canvas_summaries.append(summary)
        errors.extend(canvas_errors)
        warnings.extend(canvas_warnings)

    report = {
        "schema_version": 1,
        "stage": stage,
        "status": "passed" if not errors else "failed",
        "book_root": str(book_root),
        "vault_root": str(vault_root),
        "source": source_summary,
        "profile": str(profile_path) if profile_path else None,
        "source_sha256": expected_source_sha256,
        "coverage": coverage_summary,
        "concept_manifest": concept_summary,
        "lesson_flow": lesson_flow_summary,
        "counts": {
            "markdown_files": len(markdown_files),
            "category_files": dict(sorted(category_files.items())),
            "concept_files": len(concept_files),
            "images": len(all_images),
            "standard_links": standard_links,
            "wikilinks": wikilinks,
            "image_references": image_references,
            "missing_markdown_links": missing_markdown_links,
            "missing_images": missing_images,
            "empty_notes": empty_notes,
            "empty_concepts": empty_concepts,
            "invalid_entry_headings": invalid_entry_headings,
            "malformed_concept_notes": malformed_concept_notes,
            "non_vault_root_note_links": non_vault_root_note_links,
            "residual_artifact_headings": residual_artifact_headings,
            "plain_running_headers": plain_running_headers,
            "suspicious_ocr_math_fragments": suspicious_ocr_math_fragments,
            "malformed_table_blocks": malformed_table_blocks,
            "content_consistency_violations": (
                content_consistency_violations
            ),
            "malformed_callouts": malformed_callouts,
            "callouts_without_blank": callouts_without_blank,
            "callout_body_violations": callout_body_violations,
            "callout_semantic_scope_violations": (
                callout_semantic_scope_violations
            ),
            "callouts": callouts,
            "unstandardized_functional_blocks": (
                unstandardized_functional_blocks
            ),
            "unreferenced_images": len(unreferenced_images),
        },
        "transitions": dict(sorted(transitions.items())),
        "canvases": canvas_summaries,
        "errors": errors,
        "warnings": warnings,
    }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit linked Markdown, assets, concepts, and canvases."
    )
    parser.add_argument("book_root", type=Path)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--allow-wikilinks", action="store_true")
    parser.add_argument("--require-canvas", action="store_true")
    parser.add_argument(
        "--stage",
        choices=AUDIT_STAGES,
        default="pre-canvas",
        help=(
            "Run a progressive split, concepts, formatting, pre-canvas, "
            "or final gate."
        ),
    )
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--coverage-manifest", type=Path)
    parser.add_argument("--concept-manifest", type=Path)
    parser.add_argument("--lesson-flow-manifest", type=Path)
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = audit_book(
            args.book_root.resolve(),
            args.vault_root.resolve(),
            source=args.source.resolve() if args.source else None,
            expected_source_sha256=args.expected_source_sha256,
            allow_wikilinks=args.allow_wikilinks,
            require_canvas=args.require_canvas,
            coverage_manifest=(
                args.coverage_manifest.resolve() if args.coverage_manifest else None
            ),
            concept_manifest=(
                args.concept_manifest.resolve() if args.concept_manifest else None
            ),
            lesson_flow_manifest=(
                args.lesson_flow_manifest.resolve()
                if args.lesson_flow_manifest
                else None
            ),
            profile_path=args.profile.resolve() if args.profile else None,
            stage=args.stage,
        )
        output = json.dumps(report, ensure_ascii=False, indent=2)
        print(output)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(output + "\n", encoding="utf-8")
        return 0 if report["status"] == "passed" else 1
    except Exception as exc:
        report = {
            "schema_version": 1,
            "stage": args.stage,
            "status": "failed",
            "errors": [
                {
                    "code": "audit-crashed",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            ],
            "warnings": [],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

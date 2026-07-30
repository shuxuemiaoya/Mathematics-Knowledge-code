#!/usr/bin/env python3
"""Compare body-content decomposition when current and reference are the same book."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s+.*$", re.M)
LINE_PREFIX_RE = re.compile(
    r"^\s*(?:#{1,6}\s+|>\s*\[![^\]]+\][+-]?\s*|>+\s*|[-*+]\s+)",
    re.M,
)
NORMALIZE_RE = re.compile(
    r"""[\s`*_~\\{}$，。；：、,.!?！？;:()（）\[\]<>《》“”"'—–=+|/]+"""
)
EXERCISE_UNIT_RE = re.compile(r"(习题\s*\d+(?:\.\d+)?|复习参考题\s*\d+)")
CHAPTER_PREFIX_RE = re.compile(r"^第[一二三四五六七八九十百]+章")
CONTENT_CATEGORIES = {
    "知识点",
    "习题",
    "趣味阅读",
    "数学历史",
    "思维或方法",
    "工具",
    "拓展知识点",
}
COMMON_CONTENT_CATEGORIES = CONTENT_CATEGORIES | {"概念"}
TOP_CALLOUT_RE = re.compile(r"^>\s*\[!([^\]]+)\]")
TOP_CALLOUT_DETAIL_RE = re.compile(
    r"^>\s*\[!([^\]]+)\][+-]?\s*(.*?)\s*$"
)
NESTED_CALLOUT_RE = re.compile(r"^>\s+>\s*\[!([^\]]+)\]")
NESTED_CALLOUT_DETAIL_RE = re.compile(
    r"^>\s+>\s*\[!([^\]]+)\][+-]?\s*(.*?)\s*$"
)
LEGACY_CALLOUT_TYPES = {"think", "explore", "observe"}
EXAMPLE_LABEL_ONLY_RE = re.compile(
    r"^>\s*\[!example\][+-]?\s+例(?:题)?\s*\d+\s*$"
)
FLAT_REASONING_RE = re.compile(
    r"^>\s+(?:\*\*)?(?:分析|思路|点拨|解|证明|解析|解答)\s*[：:]"
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


class ContentParityError(ValueError):
    pass


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def renamed_equivalent(reference: str, current: str) -> bool:
    reference_path = Path(reference)
    current_path = Path(current)
    reference_stem = reference_path.stem
    current_stem = current_path.stem
    reference_category = category(reference)
    current_category = category(current)
    if reference_category == current_category == "习题":
        reference_unit = EXERCISE_UNIT_RE.search(reference_stem)
        current_unit = EXERCISE_UNIT_RE.search(current_stem)
        if (
            reference_unit
            and current_unit
            and normalize_title(reference_unit.group(1))
            == normalize_title(current_unit.group(1))
        ):
            return True
    reference_without_chapter = CHAPTER_PREFIX_RE.sub("", reference_stem).strip()
    current_without_chapter = CHAPTER_PREFIX_RE.sub("", current_stem).strip()
    return (
        reference_category == current_category
        and normalize_title(reference_without_chapter)
        == normalize_title(current_without_chapter)
    )


def normalize_body(text: str) -> str:
    text = MARKDOWN_IMAGE_RE.sub("", text)
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = WIKILINK_RE.sub(
        lambda match: match.group(2) or Path(match.group(1)).name,
        text,
    )
    text = HEADING_LINE_RE.sub("", text)
    text = LINE_PREFIX_RE.sub("", text)
    return NORMALIZE_RE.sub("", text).casefold()


def strip_quote_prefix(line: str) -> tuple[int, str]:
    depth = 0
    remainder = line
    while remainder.startswith(">"):
        depth += 1
        remainder = remainder[1:]
        if remainder.startswith(" "):
            remainder = remainder[1:]
    return depth, remainder


def is_worked_example(line: str) -> bool:
    match = WORKED_EXAMPLE_RE.match(line)
    if match is None:
        return False
    return not match.group(2).lstrip().startswith(
        ("中", "的", "给出", "所述", "所得", "证明用到")
    )


def callout_structure_issues(relative: str, text: str) -> list[dict[str, Any]]:
    """Keep structure checks separate from syntax-stripped content parity."""

    lines = text.splitlines()
    issues: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        top = TOP_CALLOUT_RE.match(line)
        nested = NESTED_CALLOUT_RE.match(line)
        if top:
            if top.group(1).casefold() in LEGACY_CALLOUT_TYPES:
                issues.append(
                    {
                        "path": relative,
                        "line": index + 1,
                        "reason": "legacy-callout-type",
                        "text": line[:200],
                    }
                )
            if index + 1 >= len(lines) or not lines[index + 1].startswith(">"):
                issues.append(
                    {
                        "path": relative,
                        "line": index + 1,
                        "reason": "missing-quoted-body",
                        "text": line[:200],
                    }
                )
        if nested:
            if index + 1 >= len(lines) or not lines[index + 1].startswith("> >"):
                issues.append(
                    {
                        "path": relative,
                        "line": index + 1,
                        "reason": "missing-nested-quoted-body",
                        "text": line[:200],
                    }
                )
            parent = index - 1
            while parent >= 0 and lines[parent].startswith(">"):
                if TOP_CALLOUT_RE.match(lines[parent]):
                    break
                parent -= 1
            if parent < 0 or not TOP_CALLOUT_RE.match(lines[parent]):
                issues.append(
                    {
                        "path": relative,
                        "line": index + 1,
                        "reason": "nested-callout-without-parent",
                        "text": line[:200],
                    }
                )
    active_type: str | None = None
    active_title = ""
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
            if nested.group(1).casefold() == "example":
                issues.append(
                    {
                        "path": relative,
                        "line": index + 1,
                        "reason": "worked-example-inside-non-example-callout",
                        "text": line[:200],
                        "parent_callout": active_type,
                        "quote_depth": depth,
                    }
                )
            continue

        heading_text = stripped
        heading = re.match(r"^#{4,6}\s+(.+?)\s*$", stripped)
        if heading:
            heading_text = heading.group(1).strip()
            if PRACTICE_BOUNDARY_RE.match(stripped):
                reason = "practice-inside-callout"
            elif FUNCTIONAL_HEADING_RE.match(stripped):
                reason = "functional-heading-inside-callout"
            elif re.fullmatch(r"[●•·\s]+", heading_text):
                reason = "artifact-heading-inside-callout"
            else:
                reason = ""
            if reason:
                issues.append(
                    {
                        "path": relative,
                        "line": index + 1,
                        "reason": reason,
                        "text": line[:200],
                        "parent_callout": active_type,
                        "quote_depth": depth,
                    }
                )
                continue
        if PRACTICE_BOUNDARY_RE.match(heading_text):
            reason = "practice-inside-callout"
        elif is_worked_example(heading_text):
            reason = (
                "worked-example-inside-example-callout"
                if active_type == "example"
                else "worked-example-inside-non-example-callout"
            )
        elif PLAIN_FUNCTIONAL_LABEL_RE.match(heading_text):
            reason = "functional-label-inside-callout"
            if normalize_title(heading_text) == normalize_title(active_title):
                reason = "duplicate-functional-label-inside-callout"
        elif (
            active_type == "info"
            and any(label in active_title for label in ("情景引入", "情境引入"))
            and FORMAL_DEFINITION_SCOPE_RE.search(heading_text)
        ):
            reason = "formal-definition-inside-situation-callout"
        else:
            reason = ""
        if reason:
            issues.append(
                {
                    "path": relative,
                    "line": index + 1,
                    "reason": reason,
                    "text": line[:200],
                    "parent_callout": active_type,
                    "quote_depth": depth,
                }
            )
    return issues


def event_label(callout_type: str, title: str) -> str:
    if callout_type == "example":
        example = WORKED_EXAMPLE_RE.match(title)
        if example:
            return re.sub(r"\s+", "", example.group(1))
    compact = re.sub(r"[\s：:。；;，,]+", "", title).casefold()
    known_labels = {
        "情景引入",
        "情境引入",
        "问题引入",
        "过渡",
        "思考",
        "观察",
        "探究",
        "分析",
        "思路",
        "点拨",
        "解",
        "证明",
        "解析",
        "解答",
        "练习",
    }
    if compact in known_labels:
        return compact
    numbered = re.match(r"^(问题\s*\d+)", title)
    if numbered:
        return re.sub(r"\s+", "", numbered.group(1))
    return ""


def functional_topology(text: str) -> list[dict[str, Any]]:
    """Describe functional blocks with their quote depth and owning callout."""

    events: list[dict[str, Any]] = []
    active_type: str | None = None
    for line in text.splitlines():
        top = TOP_CALLOUT_DETAIL_RE.match(line)
        if top:
            active_type = top.group(1).casefold()
            events.append(
                {
                    "kind": "callout",
                    "type": active_type,
                    "label": event_label(active_type, top.group(2).strip()),
                    "quote_depth": 1,
                    "parent_callout": None,
                }
            )
            continue
        depth, body = strip_quote_prefix(line)
        stripped = body.strip()
        if not stripped:
            continue
        nested = NESTED_CALLOUT_DETAIL_RE.match(line)
        if nested:
            nested_type = nested.group(1).casefold()
            events.append(
                {
                    "kind": "callout",
                    "type": nested_type,
                    "label": event_label(nested_type, nested.group(2).strip()),
                    "quote_depth": depth,
                    "parent_callout": active_type,
                }
            )
            continue
        heading = re.match(r"^#{4,6}\s+(.+?)\s*$", stripped)
        candidate = heading.group(1).strip() if heading else stripped
        if PRACTICE_BOUNDARY_RE.match(stripped):
            events.append(
                {
                    "kind": "practice",
                    "label": "练习",
                    "quote_depth": depth,
                    "parent_callout": active_type if depth else None,
                }
            )
            if depth == 0:
                active_type = None
        elif is_worked_example(candidate):
            example = WORKED_EXAMPLE_RE.match(candidate)
            assert example is not None
            events.append(
                {
                    "kind": "worked-example",
                    "label": normalize_title(example.group(1)),
                    "quote_depth": depth,
                    "parent_callout": active_type if depth else None,
                }
            )
            if depth == 0:
                active_type = None
        elif (
            FUNCTIONAL_HEADING_RE.match(stripped)
            or PLAIN_FUNCTIONAL_LABEL_RE.match(candidate)
        ):
            events.append(
                {
                    "kind": "functional-label",
                    "label": normalize_title(candidate),
                    "quote_depth": depth,
                    "parent_callout": active_type if depth else None,
                }
            )
            if depth == 0:
                active_type = None
    return events


def shingles(text: str, width: int = 12) -> set[str]:
    if len(text) < width:
        return {text} if text else set()
    return {text[index : index + width] for index in range(len(text) - width + 1)}


def markdown_inventory(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*.md")
        if path.is_file()
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def style_structure_issues(relative: str, text: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if EXAMPLE_LABEL_ONLY_RE.match(line):
            position = index + 1
            has_parent_stem = False
            while position < len(lines) and lines[position].startswith(">"):
                candidate = lines[position]
                if candidate.startswith("> >") or TOP_CALLOUT_RE.match(candidate):
                    break
                if candidate[1:].strip():
                    has_parent_stem = True
                    break
                position += 1
            if has_parent_stem:
                issues.append(
                    {
                        "path": relative,
                        "line": index + 1,
                        "reason": "example-stem-not-compacted",
                        "text": line[:200],
                    }
                )
        if FLAT_REASONING_RE.match(line):
            issues.append(
                {
                    "path": relative,
                    "line": index + 1,
                    "reason": "reasoning-label-not-nested",
                    "text": line[:200],
                }
            )
    return issues


def category(relative: str) -> str:
    parts = Path(relative).parts
    return parts[0] if len(parts) > 1 else "root"


def best_containment(
    reference_text: str,
    current_documents: list[tuple[str, set[str]]],
) -> tuple[str | None, float]:
    reference_shingles = shingles(reference_text)
    if not reference_shingles:
        return None, 0.0
    best_path: str | None = None
    best_score = -1.0
    for relative, current_shingles in current_documents:
        score = len(reference_shingles & current_shingles) / len(reference_shingles)
        if score > best_score:
            best_path = relative
            best_score = score
    return best_path, max(best_score, 0.0)


def containment(left: set[str], right: set[str]) -> float:
    if not left:
        return 1.0 if not right else 0.0
    return len(left & right) / len(left)


def classify_common_content(
    reference_score: float,
    current_score: float,
    *,
    reference_empty: bool,
    current_empty: bool,
) -> str:
    if reference_empty and current_empty:
        return "both_empty"
    if reference_empty:
        return "reference_empty_current_content"
    if current_empty:
        return "current_empty_reference_content"
    if reference_score >= 0.9 and current_score >= 0.9:
        return "equivalent"
    if reference_score >= 0.9:
        return "reference_preserved_with_extra_current"
    if current_score >= 0.9:
        return "current_preserved_with_extra_reference"
    if max(reference_score, current_score) >= 0.5:
        return "partial_overlap"
    return "content_divergent"


def compare(
    current_root: Path,
    reference_root: Path,
    *,
    profile_path: Path | None = None,
    review_decisions_path: Path | None = None,
) -> dict[str, Any]:
    if not current_root.is_dir():
        raise FileNotFoundError(f"Current corpus does not exist: {current_root}")
    if not reference_root.is_dir():
        raise FileNotFoundError(f"Reference corpus does not exist: {reference_root}")

    same_book = normalize_title(current_root.name) == normalize_title(reference_root.name)
    current = markdown_inventory(current_root)
    reference = markdown_inventory(reference_root)
    current_callout_issues = [
        issue
        for relative, path in sorted(current.items())
        for issue in callout_structure_issues(
            relative,
            path.read_text(encoding="utf-8-sig"),
        )
    ]
    current_style_issues = [
        issue
        for relative, path in sorted(current.items())
        for issue in style_structure_issues(
            relative,
            path.read_text(encoding="utf-8-sig"),
        )
    ]
    common_functional_topology_mismatches: list[dict[str, Any]] = []
    if same_book:
        for relative in sorted(set(current) & set(reference)):
            if category(relative) not in COMMON_CONTENT_CATEGORIES:
                continue
            current_topology = functional_topology(
                current[relative].read_text(encoding="utf-8-sig")
            )
            reference_topology = functional_topology(
                reference[relative].read_text(encoding="utf-8-sig")
            )
            if current_topology == reference_topology:
                continue
            if not current_topology and not reference_topology:
                continue
            common_functional_topology_mismatches.append(
                {
                    "path": relative,
                    "current": current_topology,
                    "reference": reference_topology,
                }
            )
    profile: dict[str, Any] | None = None
    reference_scope: str | None = None
    source_sha256: str | None = None
    reference_sha256 = inventory_tree_sha256(reference_root)
    if profile_path is not None:
        profile_path = profile_path.resolve()
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        configured_reference = profile.get("reference", {})
        configured_current = Path(profile["paths"]["book_root"]).resolve()
        configured_reference_path = Path(
            str(configured_reference.get("path", ""))
        ).resolve()
        if configured_current != current_root:
            raise ContentParityError(
                "current corpus does not match profile paths.book_root"
            )
        if configured_reference_path != reference_root:
            raise ContentParityError(
                "reference corpus does not match profile reference.path"
            )
        if reference_sha256 != configured_reference.get("sha256"):
            raise ContentParityError(
                "reference corpus does not match frozen profile digest"
            )
        reference_scope = configured_reference.get("scope")
        source_sha256 = profile.get("source", {}).get("sha256")
    current_documents = [
        (
            relative,
            shingles(path.read_text(encoding="utf-8-sig")),
        )
        for relative, path in current.items()
        if category(relative) in CONTENT_CATEGORIES
    ]
    # Normalize once after reading. Keeping this separate from inventory makes
    # the report deterministic and avoids comparing link/image destinations.
    current_documents = [
        (
            relative,
            shingles(
                normalize_body(current[relative].read_text(encoding="utf-8-sig"))
            ),
        )
        for relative, _ in current_documents
    ]

    reference_only = sorted(set(reference) - set(current))
    current_only = sorted(set(current) - set(reference))
    common_content: list[dict[str, Any]] = []
    for relative in sorted(set(current) & set(reference)):
        if category(relative) not in COMMON_CONTENT_CATEGORIES:
            continue
        current_body = normalize_body(
            current[relative].read_text(encoding="utf-8-sig")
        )
        reference_body = normalize_body(
            reference[relative].read_text(encoding="utf-8-sig")
        )
        current_shingles = shingles(current_body)
        reference_shingles = shingles(reference_body)
        reference_score = containment(reference_shingles, current_shingles)
        current_score = containment(current_shingles, reference_shingles)
        classification = classify_common_content(
            reference_score,
            current_score,
            reference_empty=not reference_body,
            current_empty=not current_body,
        )
        if classification not in {"equivalent", "both_empty"}:
            common_content.append(
                {
                    "path": relative,
                    "reference_containment": round(reference_score, 3),
                    "current_containment": round(current_score, 3),
                    "reference_characters": len(reference_body),
                    "current_characters": len(current_body),
                    "classification": classification,
                }
            )
    common_content.sort(
        key=lambda item: (
            max(
                item["reference_containment"],
                item["current_containment"],
            ),
            min(
                item["reference_containment"],
                item["current_containment"],
            ),
            item["path"],
        )
    )
    content_candidates: list[dict[str, Any]] = []
    for relative in reference_only:
        if category(relative) not in CONTENT_CATEGORIES:
            continue
        body = normalize_body(reference[relative].read_text(encoding="utf-8-sig"))
        best_path, score = best_containment(body, current_documents)
        classification = (
            "empty_or_link_only"
            if not body
            else "renamed_equivalent"
            if score >= 0.5
            and best_path is not None
            and renamed_equivalent(relative, best_path)
            else "role_mapped_equivalent"
            if score >= 0.5
            and best_path is not None
            and normalize_title(Path(relative).stem)
            == normalize_title(Path(best_path).stem)
            else "preserved_inside_current_note"
            if score >= 0.5
            else "partial_or_ocr_divergent"
            if score >= 0.2
            else "unmatched_content"
        )
        content_candidates.append(
            {
                "reference": relative,
                "best_current": best_path,
                "containment": round(score, 3),
                "classification": classification,
            }
        )

    current_concepts = {
        path.stem
        for relative, path in current.items()
        if category(relative) == "概念"
    }
    reference_concepts = {
        path.stem
        for relative, path in reference.items()
        if category(relative) == "概念"
    }
    missing_concepts = sorted(reference_concepts - current_concepts)
    classification_counts = Counter(
        item["classification"] for item in content_candidates
    )
    reference_only_counts = Counter(category(item) for item in reference_only)
    current_only_counts = Counter(category(item) for item in current_only)

    blocking_decomposition = [
        item
        for item in content_candidates
        if item["classification"] == "preserved_inside_current_note"
    ]
    blocking_unmatched = [
        item
        for item in content_candidates
        if item["classification"] == "unmatched_content"
    ]
    blocking_common_divergence = [
        item
        for item in common_content
        if item["classification"]
        in {"content_divergent", "current_empty_reference_content"}
    ]
    review_payload: dict[str, Any] | None = None
    accepted_reference_notes: set[str] = set()
    accepted_common_notes: set[str] = set()
    accepted_missing_concepts: set[str] = set()
    if review_decisions_path is not None:
        review_decisions_path = review_decisions_path.resolve()
        review_payload = json.loads(
            review_decisions_path.read_text(encoding="utf-8-sig")
        )
        if review_payload.get("schema_version") != 1:
            raise ContentParityError("review decisions schema_version must be 1")
        if review_payload.get("reference_sha256") != reference_sha256:
            raise ContentParityError(
                "review decisions do not match the frozen reference digest"
            )
        if review_payload.get("source_sha256") != source_sha256:
            raise ContentParityError(
                "review decisions do not match the frozen source digest"
            )
        if profile_path is not None and Path(
            str(review_payload.get("profile", ""))
        ).resolve() != profile_path:
            raise ContentParityError(
                "review decisions do not match the current profile"
            )

        def accepted_keys(field: str) -> set[str]:
            raw = review_payload.get(field, {})
            if not isinstance(raw, dict):
                raise ContentParityError(
                    f"review decisions {field} must be an object"
                )
            accepted: set[str] = set()
            for key, decision in raw.items():
                if not isinstance(decision, dict):
                    raise ContentParityError(
                        f"review decision {field}.{key} must be an object"
                    )
                if decision.get("decision") != "accept-current":
                    continue
                reason = decision.get("reason")
                if not isinstance(reason, str) or len(reason.strip()) < 12:
                    raise ContentParityError(
                        f"review decision {field}.{key} needs a specific reason"
                    )
                accepted.add(str(key))
            return accepted

        accepted_reference_notes = accepted_keys("reference_notes")
        accepted_common_notes = accepted_keys("common_notes")
        accepted_missing_concepts = accepted_keys("missing_concepts")

    unresolved_decomposition = [
        item
        for item in blocking_decomposition
        if item["reference"] not in accepted_reference_notes
    ]
    unresolved_unmatched = [
        item
        for item in blocking_unmatched
        if item["reference"] not in accepted_reference_notes
    ]
    unresolved_common_divergence = [
        item
        for item in blocking_common_divergence
        if item["path"] not in accepted_common_notes
    ]
    unresolved_missing_concepts = [
        name for name in missing_concepts if name not in accepted_missing_concepts
    ]
    unresolved_topology_mismatches = [
        item
        for item in common_functional_topology_mismatches
        if item["path"] not in accepted_common_notes
    ]
    status = "architecture_only_required"
    if reference_scope == "style-only":
        status = (
            "content_review_required"
            if current_callout_issues or current_style_issues
            else "passed"
        )
    elif same_book:
        status = (
            "content_review_required"
            if (
                unresolved_decomposition
                or unresolved_unmatched
                or unresolved_common_divergence
                or unresolved_missing_concepts
                or current_callout_issues
                or unresolved_topology_mismatches
            )
            else "passed"
        )

    return {
        "schema_version": 1,
        "stage": "reference-content-parity",
        "status": status,
        "profile": str(profile_path) if profile_path else None,
        "source_sha256": source_sha256,
        "same_book": same_book,
        "current": str(current_root),
        "reference": {
            "path": str(reference_root),
            "sha256": reference_sha256,
            "scope": reference_scope,
        },
        "inventory": {
            "current_markdown": len(current),
            "reference_markdown": len(reference),
            "common_relative_paths": len(set(current) & set(reference)),
            "current_only_by_category": dict(sorted(current_only_counts.items())),
            "reference_only_by_category": dict(sorted(reference_only_counts.items())),
        },
        "content_decomposition": {
            "classification_counts": dict(sorted(classification_counts.items())),
            "reference_only_notes": content_candidates,
            "common_note_differences": common_content,
        },
        "concept_title_coverage": {
            "current": len(current_concepts),
            "reference": len(reference_concepts),
            "missing_from_current": missing_concepts,
        },
        "markdown_structure": {
            "current_callout_issues": current_callout_issues,
            "current_callout_issue_count": len(current_callout_issues),
            "current_style_issues": current_style_issues,
            "current_style_issue_count": len(current_style_issues),
            "common_functional_topology_mismatches": (
                common_functional_topology_mismatches
            ),
            "common_functional_topology_mismatch_count": len(
                common_functional_topology_mismatches
            ),
        },
        "review": {
            "path": str(review_decisions_path)
            if review_decisions_path is not None
            else None,
            "accepted_reference_notes": len(accepted_reference_notes),
            "accepted_common_notes": len(accepted_common_notes),
            "accepted_missing_concepts": len(accepted_missing_concepts),
            "unresolved_reference_notes": [
                item["reference"]
                for item in unresolved_decomposition + unresolved_unmatched
            ],
            "unresolved_common_notes": [
                item["path"] for item in unresolved_common_divergence
            ],
            "unresolved_topology_notes": [
                item["path"] for item in unresolved_topology_mismatches
            ],
            "unresolved_missing_concepts": unresolved_missing_concepts,
        },
        "blocking_summary": {
            "reference_notes_preserved_inside_larger_current_notes": len(
                unresolved_decomposition
            ),
            "reference_notes_with_unmatched_content": len(unresolved_unmatched),
            "common_notes_with_divergent_content": len(
                unresolved_common_divergence
            ),
            "missing_reference_concept_titles": len(
                unresolved_missing_concepts
            ),
            "current_callout_structure_issues": len(current_callout_issues),
            "current_style_structure_issues": len(current_style_issues),
            "common_functional_topology_mismatches": len(
                unresolved_topology_mismatches
            ),
        },
    }


def atomic_write(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current_corpus", type=Path)
    parser.add_argument("reference_corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--review-decisions", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = compare(
            args.current_corpus.resolve(),
            args.reference_corpus.resolve(),
            profile_path=args.profile.resolve() if args.profile else None,
            review_decisions_path=(
                args.review_decisions.resolve()
                if args.review_decisions
                else None
            ),
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            atomic_write(args.output.resolve(), rendered, args.overwrite)
        print(rendered, end="")
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "reference-content-parity",
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Plan and validate source-ordered textbook lesson-flow decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


LESSON_TITLE_RE = re.compile(r"^\d+(?:\.\d+)+\s+\S")
NUMBERED_SUBSECTION_RE = re.compile(r"^\d+(?:\.\d+){2,}\s+\S")
CHAPTER_TITLE_RE = re.compile(r"^第[一二三四五六七八九十百\d]+章")
SUMMARY_TITLE_RE = re.compile(r"(?:小结|复习参考题)")
CONTENT_HEADING_RE = re.compile(r"^#{4,6}\s+(.+?)\s*$")
ANY_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
EXAMPLE_RE = re.compile(r"^(例(?:题)?\s*\d+)\s*(.*)$")
PRACTICE_TITLE_RE = re.compile(r"^(?:练习|习题\s*\d+(?:\.\d+)*)(?:\s|$)")
FIGURE_REFERENCE_RE = re.compile(
    r"(?:图|fig(?:ure)?\.?)\s*[（(]?\d",
    re.IGNORECASE,
)
TABLE_REFERENCE_RE = re.compile(r"(?:表|table)\s*[（(]?\d", re.IGNORECASE)
IMAGE_MARKER_RE = re.compile(r"!\[[^\]]*\]\(|<img\b", re.IGNORECASE)
TABLE_MARKER_RE = re.compile(r"<table\b|^\s*\|.+\|\s*$", re.IGNORECASE | re.MULTILINE)
MEDIA_CAPTION_RE = re.compile(r"^(?:图|表)\s*\d", re.IGNORECASE)
SUBFIGURE_LABEL_RE = re.compile(r"^[（(]\s*\d+\s*[）)]$")
FUNCTIONAL_STANDALONE_RE = re.compile(r"^(?:分析|解|证明)\s*[:：]?$")
MAX_PARENT_PREVIEW_CHARACTERS = 180
QUESTION_TITLES = (
    "思考",
    "观察",
    "讨论",
    "交流",
    "尝试",
    "想一想",
    "议一议",
    "观察·思考",
    "尝试·交流",
    "思考·交流",
    "回顾·反思",
    "探究",
    "实验",
    "做一做",
    "观察与猜想",
    "操作与思考",
)
CONTEXT_TITLES = (
    "情景引入",
    "情境引入",
    "问题引入",
    "操作·交流",
    "引入",
    "引导",
)
ANALYSIS_TITLES = ("分析", "思路", "点拨")
EXPOSITION_TITLES = (
    "归纳",
    "总结",
    "结论",
    "性质",
    "定理",
    "公理",
    "法则",
)
EXPOSITION_CUE_RE = re.compile(
    r"^(?:可以发现|由此可见|综上(?:所述)?|也就是说|一般地[，,]|"
    r"由上述.{0,40}?(?:可以得到|可得|得到))"
)
FORMAL_DEFINITION_CUE_RE = re.compile(
    r"(?:叫做|称为|定义为|称之为|记作|规定[：:]?)"
)
ALLOWED_ROLES = {
    "entry-context",
    "context",
    "question",
    "analysis",
    "exposition",
    "topic",
    "worked-example",
    "representative-example",
    "transition",
    "practice",
    "navigation",
    "section-heading",
}
ALLOWED_OWNERSHIP = {"retain-parent", "move-child"}
RETAIN_PARENT_ROLES = {
    "entry-context",
    "context",
    "question",
    "analysis",
    "exposition",
    "worked-example",
    "representative-example",
    "transition",
    "navigation",
    "section-heading",
}
CHECK_NAMES = {
    "source_order_preserved",
    "complete_source_coverage",
    "introduction_preserved",
    "transitions_preserved",
    "independent_topics_split",
    "exercises_retained_or_routed",
}
CHECK_RESULTS = {"passed", "not_applicable"}


class LessonFlowError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise LessonFlowError(f"JSON root must be an object: {path}")
    return payload


def node_lookup(split_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = split_manifest.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise LessonFlowError("split manifest needs a non-empty nodes array")
    lookup: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise LessonFlowError(f"split node {index} must be an object")
        key = node.get("key")
        if not isinstance(key, str) or not key:
            raise LessonFlowError(f"split node {index}.key is required")
        if key in lookup:
            raise LessonFlowError(f"duplicate split node key: {key}")
        lookup[key] = node
    return lookup


def lesson_nodes(split_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = node_lookup(split_manifest)
    lessons: list[dict[str, Any]] = []
    for node in lookup.values():
        title = str(node.get("title", "")).strip()
        if node.get("category") != "knowledge":
            continue
        if node.get("parent_key") is None:
            continue
        if CHAPTER_TITLE_RE.match(title) or SUMMARY_TITLE_RE.search(title):
            continue
        if LESSON_TITLE_RE.match(title):
            lessons.append(node)
    return sorted(
        lessons,
        key=lambda item: (int(item["start_line"]), int(item["end_line"])),
    )


def direct_children(
    node: dict[str, Any],
    lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (
            child
            for child in lookup.values()
            if child.get("parent_key") == node["key"]
        ),
        key=lambda item: (int(item["start_line"]), int(item["end_line"])),
    )


def make_block(
    lesson_key: str,
    index: int,
    start_line: int,
    end_line: int,
    *,
    child: dict[str, Any] | None = None,
    role: str | None = None,
    boundary_label: str | None = None,
) -> dict[str, Any]:
    if child is None:
        draft_role = role or "unclassified"
        if boundary_label:
            reason = (
                f"Deterministic functional boundary {boundary_label!r}; "
                "review this complete source block."
            )
        elif draft_role == "entry-context":
            reason = (
                "Lesson heading and opening preview before the first "
                "functional boundary; review the retained context."
            )
        else:
            reason = "Classify this retained source range by teaching function."
        return {
            "id": f"{lesson_key}-block-{index:03d}",
            "role": draft_role,
            "ownership": "retain-parent",
            "start_line": start_line,
            "end_line": end_line,
            "child_node_key": None,
            "representative_anchor": False,
            "reason": reason,
            "confidence": 0.0,
        }
    role = "practice" if child.get("category") == "exercise" else "topic"
    block = {
        "id": f"{lesson_key}-block-{index:03d}",
        "role": role,
        "ownership": "move-child",
        "start_line": start_line,
        "end_line": end_line,
        "child_node_key": child["key"],
        "representative_anchor": False,
        "reason": "Existing direct child range; review its teaching boundary.",
        "confidence": 0.0,
    }
    if isinstance(child.get("parent_preview"), dict):
        block["parent_preview"] = child["parent_preview"]
    return block


def is_example_cross_reference(stem: str) -> bool:
    return stem.lstrip().startswith(
        ("中", "的", "给出", "所述", "所得", "证明用到")
    )


def starts_with_title(title: str, candidates: tuple[str, ...]) -> bool:
    compact = re.sub(r"\s+", "", title)
    return any(compact.startswith(candidate) for candidate in candidates)


def equals_title(title: str, candidates: tuple[str, ...]) -> bool:
    compact = re.sub(r"\s+", "", title)
    return compact in candidates


def functional_boundary(line: str) -> tuple[str, str] | None:
    """Return a deterministic lesson-function boundary for one source line."""

    stripped = line.strip()
    if not stripped:
        return None
    heading = CONTENT_HEADING_RE.match(stripped)
    title = heading.group(1).strip() if heading else stripped
    if heading and NUMBERED_SUBSECTION_RE.match(title):
        return "section-heading", title
    example = EXAMPLE_RE.match(title)
    if example and not is_example_cross_reference(example.group(2)):
        return "worked-example", example.group(1)
    if PRACTICE_TITLE_RE.match(title):
        return "practice", title
    title_matches = starts_with_title if heading else equals_title
    if title_matches(title, QUESTION_TITLES):
        return "question", title
    if title_matches(title, CONTEXT_TITLES):
        return "context", title
    if title_matches(title, ANALYSIS_TITLES):
        return "analysis", title
    if title_matches(title, EXPOSITION_TITLES):
        return "exposition", title
    if heading:
        return None
    if EXPOSITION_CUE_RE.search(title) or FORMAL_DEFINITION_CUE_RE.search(title):
        return "exposition", title[:80]
    return None


def retained_draft_blocks(
    lesson: dict[str, Any],
    lines: list[str],
    start_line: int,
    end_line: int,
    index: int,
) -> tuple[list[dict[str, Any]], int]:
    """Split one retained span at every deterministic functional boundary."""

    blocks: list[dict[str, Any]] = []
    cursor = start_line
    current_role = (
        "entry-context"
        if start_line == int(lesson["start_line"])
        else "unclassified"
    )
    boundary_label: str | None = None
    boundaries = [
        (line_number, detected)
        for line_number in range(start_line, end_line + 1)
        if (detected := functional_boundary(lines[line_number - 1])) is not None
        and not (
            line_number == int(lesson["start_line"])
            and detected[0] == "section-heading"
        )
    ]
    for line_number, (role, label) in boundaries:
        has_content_before = any(
            line.strip() for line in lines[cursor - 1 : line_number - 1]
        )
        if has_content_before:
            blocks.append(
                make_block(
                    str(lesson["key"]),
                    index,
                    cursor,
                    line_number - 1,
                    role=current_role,
                    boundary_label=boundary_label,
                )
            )
            index += 1
            cursor = line_number
        current_role = role
        boundary_label = label
    blocks.append(
        make_block(
            str(lesson["key"]),
            index,
            cursor,
            end_line,
            role=current_role,
            boundary_label=boundary_label,
        )
    )
    return blocks, index + 1


def draft_blocks(
    lesson: dict[str, Any],
    children: list[dict[str, Any]],
    lines: list[str],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    cursor = int(lesson["start_line"])
    index = 1
    for child in children:
        child_start = int(child["start_line"])
        child_end = int(child["end_line"])
        if cursor < child_start:
            retained, index = retained_draft_blocks(
                lesson,
                lines,
                cursor,
                child_start - 1,
                index,
            )
            blocks.extend(retained)
        blocks.append(
            make_block(
                lesson["key"],
                index,
                child_start,
                child_end,
                child=child,
            )
        )
        index += 1
        cursor = child_end + 1
    if cursor <= int(lesson["end_line"]):
        retained, _ = retained_draft_blocks(
            lesson,
            lines,
            cursor,
            int(lesson["end_line"]),
            index,
        )
        blocks.extend(retained)
    return blocks


def plan(
    formatted_markdown: Path,
    split_manifest_path: Path,
    profile_path: Path,
) -> dict[str, Any]:
    profile = read_json(profile_path)
    split_manifest = read_json(split_manifest_path)
    source_hash = profile.get("source", {}).get("sha256")
    if split_manifest.get("profile") is None or Path(
        str(split_manifest["profile"])
    ).resolve() != profile_path.resolve():
        raise LessonFlowError("split manifest profile does not match profile")
    if split_manifest.get("source_sha256") != source_hash:
        raise LessonFlowError("split manifest source identity does not match profile")
    validate_same_book_reference_review(split_manifest, profile)
    input_hash = sha256_file(formatted_markdown)
    if split_manifest.get("input_markdown_sha256") != input_hash:
        raise LessonFlowError(
            "formatted Markdown digest does not match split manifest"
        )

    lines = formatted_markdown.read_text(encoding="utf-8-sig").splitlines()
    decomposition = profile.get("decomposition", {})
    max_retained = (
        decomposition.get(
            "max_retained_teaching_block_nonblank_lines",
            40,
        )
        if isinstance(decomposition, dict)
        else 40
    )
    lookup = node_lookup(split_manifest)
    lessons: list[dict[str, Any]] = []
    for node in lesson_nodes(split_manifest):
        blocks = draft_blocks(node, direct_children(node, lookup), lines)
        opening_nonblank = 0
        for block in blocks:
            if block["ownership"] != "retain-parent":
                break
            opening_nonblank += nonblank_count(
                lines,
                int(block["start_line"]),
                int(block["end_line"]),
            )
        findings: list[dict[str, Any]] = []
        first_child_preview = next(
            (
                block.get("parent_preview")
                for block in blocks
                if block.get("ownership") == "move-child"
                and lookup[str(block["child_node_key"])].get("category")
                == "knowledge"
            ),
            None,
        )
        opening_supplied_by_first_child = (
            isinstance(first_child_preview, dict)
            and meaningful_preview(
                lines,
                int(first_child_preview.get("start_line", -1)),
                int(first_child_preview.get("end_line", -1)),
            )
        )
        if opening_nonblank < 2 and not opening_supplied_by_first_child:
            findings.append(
                {
                    "code": "opening-preview-missing",
                    "message": (
                        "The opening retained range contains no substantive "
                        "preview beyond the lesson heading."
                    ),
                    "range": [
                        blocks[0]["start_line"],
                        blocks[0]["end_line"],
                    ],
                    "nonblank_lines": opening_nonblank,
                }
            )
        for block in blocks:
            if block["role"] == "topic":
                preview = block.get("parent_preview")
                child = lookup[str(block["child_node_key"])]
                if child.get("category") != "knowledge":
                    continue
                if not isinstance(preview, dict):
                    continue
            if block["ownership"] != "retain-parent":
                continue
            block_nonblank = nonblank_count(
                lines,
                int(block["start_line"]),
                int(block["end_line"]),
            )
            if (
                block["role"]
                not in {
                    "practice",
                    "worked-example",
                    "representative-example",
                }
                and block_nonblank > max_retained
            ):
                findings.append(
                    {
                        "code": "retained-block-too-large",
                        "message": (
                            "Review this retained range for an independent "
                            "topic child or smaller teaching-function blocks."
                        ),
                        "range": [
                            block["start_line"],
                            block["end_line"],
                        ],
                        "nonblank_lines": block_nonblank,
                        "maximum": max_retained,
                    }
                )
        lessons.append(
            {
                "node_key": node["key"],
                "title": node["title"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
                "reviewed_entire_lesson": False,
                "reason": (
                    "Review the complete lesson as an ordered teaching flow, "
                    "then classify and adjust every block."
                ),
                "confidence": 0.0,
                "blocks": blocks,
                "draft_findings": findings,
                "checks": {
                    name: "review_required" for name in sorted(CHECK_NAMES)
                },
            }
        )
    return {
        "schema_version": 1,
        "stage": "lesson-flow-planning",
        "status": "review_required",
        "profile": str(profile_path.resolve()),
        "source_sha256": source_hash,
        "formatted_markdown": str(formatted_markdown.resolve()),
        "input_markdown_sha256": input_hash,
        "split_manifest": str(split_manifest_path.resolve()),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "lessons": lessons,
    }


def nonblank_count(lines: list[str], start_line: int, end_line: int) -> int:
    return sum(
        bool(line.strip()) for line in lines[start_line - 1 : end_line]
    )


def meaningful_preview(
    lines: list[str],
    start_line: int,
    end_line: int,
) -> bool:
    ignored = {
        "情景引入",
        "情境引入",
        "问题引入",
        "引入",
        "我们知道：",
        "我们知道:",
    }
    content: list[str] = []
    for line in lines[start_line - 1 : end_line]:
        text = line.strip()
        if (
            not text
            or CONTENT_HEADING_RE.match(text)
            or text == "$$"
            or text in ignored
            or IMAGE_MARKER_RE.search(text)
            or TABLE_MARKER_RE.search(text)
            or MEDIA_CAPTION_RE.match(text)
            or SUBFIGURE_LABEL_RE.match(text)
            or FUNCTIONAL_STANDALONE_RE.match(text)
        ):
            continue
        content.append(text)
    if not content:
        return False
    joined = " ".join(content)
    raw = "\n".join(lines[start_line - 1 : end_line])
    structurally_complete = (
        raw.count("$$") % 2 == 0
        and raw.lower().count("<table") == raw.lower().count("</table>")
        and raw.count("```") % 2 == 0
    )
    return (
        structurally_complete
        and len(joined) >= 12
        and joined.endswith(tuple("。！？.!?；;"))
    )


def preview_is_leading_child_context(
    lines: list[str],
    child_start: int,
    preview_start: int,
) -> bool:
    """Require a preview to begin at the child's first substantive source line."""

    if preview_start < child_start:
        return False
    for line in lines[child_start - 1 : preview_start - 1]:
        text = line.strip()
        if text and not ANY_HEADING_RE.match(text):
            return False
    return True


def preview_omits_attached_referenced_media(
    lines: list[str],
    preview_start: int,
    preview_end: int,
    child_end: int,
) -> bool:
    """Detect a preview that strands a nearby explicit figure/table reference."""

    preview_text = "\n".join(lines[preview_start - 1 : preview_end])
    needs_figure = bool(FIGURE_REFERENCE_RE.search(preview_text))
    needs_table = bool(TABLE_REFERENCE_RE.search(preview_text))
    if not needs_figure and not needs_table:
        return False
    if needs_figure and IMAGE_MARKER_RE.search(preview_text):
        needs_figure = False
    if needs_table and TABLE_MARKER_RE.search(preview_text):
        needs_table = False
    if not needs_figure and not needs_table:
        return False
    lookahead_end = min(child_end, preview_end + 8)
    lookahead = "\n".join(lines[preview_end:lookahead_end])
    return bool(
        (needs_figure and IMAGE_MARKER_RE.search(lookahead))
        or (needs_table and TABLE_MARKER_RE.search(lookahead))
    )


def require_confidence(value: Any, label: str, threshold: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not threshold <= value <= 1
    ):
        raise LessonFlowError(
            f"{label} confidence must be between {threshold} and 1"
        )


def validate_same_book_reference_review(
    split_manifest: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    configured = profile.get("reference")
    if not (
        isinstance(configured, dict)
        and configured.get("scope") == "same-book-content-and-style"
    ):
        return
    semantic_review = split_manifest.get("semantic_review")
    reference_review = (
        semantic_review.get("reference")
        if isinstance(semantic_review, dict)
        else None
    )
    if not isinstance(reference_review, dict):
        raise LessonFlowError(
            "same-book reference requires adopted semantic review before lesson-flow"
        )
    if (
        reference_review.get("status") != "passed"
        or reference_review.get("reviewer_confirmed") is not True
    ):
        raise LessonFlowError(
            "same-book reference semantic review is not reviewer-confirmed and passed"
        )
    if Path(str(reference_review.get("path", ""))).resolve() != Path(
        str(configured.get("path", ""))
    ).resolve():
        raise LessonFlowError(
            "same-book reference semantic review path does not match profile"
        )
    if reference_review.get("sha256") != configured.get("sha256"):
        raise LessonFlowError(
            "same-book reference semantic review digest does not match profile"
        )
    proposal_path = Path(
        str(reference_review.get("proposal_report", ""))
    ).resolve()
    if not proposal_path.is_file():
        raise LessonFlowError(
            "same-book reference semantic proposal report is missing"
        )
    if reference_review.get("proposal_report_sha256") != sha256_file(
        proposal_path
    ):
        raise LessonFlowError(
            "same-book reference semantic proposal report digest does not match"
        )
    ambiguous_count = reference_review.get("ambiguous_count", 0)
    resolved_count = reference_review.get("resolved_ambiguity_count", 0)
    if (
        not isinstance(ambiguous_count, int)
        or isinstance(ambiguous_count, bool)
        or ambiguous_count < 0
        or resolved_count != ambiguous_count
    ):
        raise LessonFlowError(
            "same-book reference ambiguities are not completely resolved"
        )
    if ambiguous_count:
        decision_path = Path(
            str(reference_review.get("decision_report", ""))
        ).resolve()
        if not decision_path.is_file():
            raise LessonFlowError(
                "same-book reference ambiguity decision report is missing"
            )
        if reference_review.get("decision_report_sha256") != sha256_file(
            decision_path
        ):
            raise LessonFlowError(
                "same-book reference ambiguity decision report digest does not match"
            )


def validate(
    manifest: dict[str, Any],
    *,
    formatted_markdown: Path,
    split_manifest_path: Path,
    profile_path: Path,
) -> dict[str, Any]:
    profile = read_json(profile_path)
    split_manifest = read_json(split_manifest_path)
    validate_same_book_reference_review(split_manifest, profile)
    lookup = node_lookup(split_manifest)
    expected_lessons = {
        node["key"]: node for node in lesson_nodes(split_manifest)
    }
    lines = formatted_markdown.read_text(encoding="utf-8-sig").splitlines()
    decomposition = profile.get("decomposition", {})
    threshold = decomposition.get("semantic_split_confidence_threshold", 0.9)
    max_retained = decomposition.get(
        "max_retained_teaching_block_nonblank_lines",
        40,
    )
    if isinstance(max_retained, bool) or not isinstance(max_retained, int):
        raise LessonFlowError(
            "max_retained_teaching_block_nonblank_lines must be an integer"
        )
    if max_retained < 1:
        raise LessonFlowError(
            "max_retained_teaching_block_nonblank_lines must be positive"
        )

    if manifest.get("schema_version") != 1:
        raise LessonFlowError("lesson-flow schema_version must be 1")
    if manifest.get("stage") != "lesson-flow-planning":
        raise LessonFlowError("lesson-flow stage is invalid")
    if manifest.get("status") != "passed":
        raise LessonFlowError("lesson-flow manifest status must be passed")
    if Path(str(manifest.get("profile", ""))).resolve() != profile_path.resolve():
        raise LessonFlowError("lesson-flow profile does not match")
    if manifest.get("source_sha256") != profile.get("source", {}).get("sha256"):
        raise LessonFlowError("lesson-flow source identity does not match")
    if Path(str(manifest.get("formatted_markdown", ""))).resolve() != (
        formatted_markdown.resolve()
    ):
        raise LessonFlowError("lesson-flow formatted Markdown path does not match")
    if manifest.get("input_markdown_sha256") != sha256_file(formatted_markdown):
        raise LessonFlowError("lesson-flow input Markdown digest does not match")
    if Path(str(manifest.get("split_manifest", ""))).resolve() != (
        split_manifest_path.resolve()
    ):
        raise LessonFlowError("lesson-flow split manifest path does not match")
    if manifest.get("split_manifest_sha256") != sha256_file(split_manifest_path):
        raise LessonFlowError("lesson-flow split manifest digest does not match")

    raw_lessons = manifest.get("lessons")
    if not isinstance(raw_lessons, list):
        raise LessonFlowError("lesson-flow lessons must be an array")
    reviewed_lessons: set[str] = set()
    for lesson_index, lesson in enumerate(raw_lessons):
        if not isinstance(lesson, dict):
            raise LessonFlowError(
                f"lesson-flow lessons[{lesson_index}] must be an object"
            )
        node_key = lesson.get("node_key")
        node = expected_lessons.get(node_key)
        if node is None:
            raise LessonFlowError(
                f"lesson-flow lesson references no lesson node: {node_key!r}"
            )
        if node_key in reviewed_lessons:
            raise LessonFlowError(f"duplicate lesson-flow lesson: {node_key}")
        reviewed_lessons.add(node_key)
        if (
            lesson.get("title") != node["title"]
            or lesson.get("start_line") != node["start_line"]
            or lesson.get("end_line") != node["end_line"]
        ):
            raise LessonFlowError(
                f"lesson-flow lesson identity mismatch: {node_key}"
            )
        if lesson.get("reviewed_entire_lesson") is not True:
            raise LessonFlowError(
                f"lesson-flow lesson was not reviewed completely: {node_key}"
            )
        if not str(lesson.get("reason", "")).strip():
            raise LessonFlowError(
                f"lesson-flow lesson needs a review reason: {node_key}"
            )
        require_confidence(lesson.get("confidence"), node_key, threshold)

        checks = lesson.get("checks")
        if not isinstance(checks, dict) or set(checks) != CHECK_NAMES:
            raise LessonFlowError(
                f"lesson-flow lesson checks are incomplete: {node_key}"
            )
        if any(value not in CHECK_RESULTS for value in checks.values()):
            raise LessonFlowError(
                f"lesson-flow lesson has unresolved checks: {node_key}"
            )
        for required in ("source_order_preserved", "complete_source_coverage"):
            if checks[required] != "passed":
                raise LessonFlowError(
                    f"lesson-flow {required} must pass: {node_key}"
                )

        blocks = lesson.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise LessonFlowError(
                f"lesson-flow lesson has no logical blocks: {node_key}"
            )
        if blocks[0].get("role") != "entry-context":
            raise LessonFlowError(
                f"lesson-flow first block must be entry-context: {node_key}"
            )
        expected_start = int(node["start_line"])
        moved_children: set[str] = set()
        retained_nonblank = 0
        entry_context_nonblank = 0
        opening_retained_nonblank = 0
        before_first_child = True
        contextual_preview_since_child = False
        first_child_preview_nonblank = 0
        rendered_preview_nonblank = 0
        representative_example_count = 0
        child_keys = {
            child["key"] for child in direct_children(node, lookup)
        }
        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                raise LessonFlowError(
                    f"lesson-flow block {node_key}[{block_index}] must be an object"
                )
            start_line = block.get("start_line")
            end_line = block.get("end_line")
            if (
                not isinstance(start_line, int)
                or not isinstance(end_line, int)
                or start_line != expected_start
                or end_line < start_line
                or end_line > int(node["end_line"])
            ):
                raise LessonFlowError(
                    f"lesson-flow blocks must cover {node_key} contiguously"
                )
            expected_start = end_line + 1
            role = block.get("role")
            ownership = block.get("ownership")
            if role not in ALLOWED_ROLES:
                raise LessonFlowError(
                    f"lesson-flow block has invalid role {role!r}: {node_key}"
                )
            if ownership not in ALLOWED_OWNERSHIP:
                raise LessonFlowError(
                    f"lesson-flow block has invalid ownership: {node_key}"
                )
            if not str(block.get("reason", "")).strip():
                raise LessonFlowError(
                    f"lesson-flow block needs a reason: {node_key}"
                )
            require_confidence(
                block.get("confidence"),
                f"{node_key}[{block_index}]",
                threshold,
            )
            if role in RETAIN_PARENT_ROLES and ownership != "retain-parent":
                raise LessonFlowError(
                    f"{role} must remain in the lesson entry: {node_key}"
                )
            if role == "topic" and ownership != "move-child":
                raise LessonFlowError(
                    f"topic must move to a direct child: {node_key}"
                )
            if role == "entry-context" and block_index != 0:
                raise LessonFlowError(
                    f"entry-context may only be the first block: {node_key}"
                )
            if role == "representative-example":
                representative_example_count += 1
                if ownership != "retain-parent" or block.get(
                    "representative_anchor"
                ) is not True:
                    raise LessonFlowError(
                        "representative-example requires a retained explicit "
                        f"anchor: {node_key}"
                    )
            if role == "worked-example":
                if ownership != "retain-parent":
                    raise LessonFlowError(
                        f"worked-example must remain in the lesson entry: {node_key}"
                    )
                if block.get("representative_anchor") is True:
                    raise LessonFlowError(
                        f"worked-example cannot claim representative_anchor: {node_key}"
                    )
            child_key = block.get("child_node_key")
            if ownership == "move-child":
                is_first_child = before_first_child
                before_first_child = False
                child = lookup.get(child_key)
                if child is None or child_key not in child_keys:
                    raise LessonFlowError(
                        f"moved lesson-flow block needs a direct child: {node_key}"
                    )
                if (
                    start_line != child["start_line"]
                    or end_line != child["end_line"]
                ):
                    raise LessonFlowError(
                        f"moved block range must equal child range: {child_key}"
                    )
                if role == "topic" and child.get("category") not in {
                    "knowledge",
                    "concept",
                    "reading",
                    "history",
                    "method",
                    "tool",
                }:
                    raise LessonFlowError(
                        f"topic block has wrong child category: {child_key}"
                    )
                if role == "practice" and child.get("category") != "exercise":
                    raise LessonFlowError(
                        f"practice block has wrong child category: {child_key}"
                    )
                preview = block.get("parent_preview")
                expected_preview = child.get("parent_preview")
                if preview != expected_preview:
                    raise LessonFlowError(
                        f"parent preview must match split child metadata: {child_key}"
                    )
                allows_parent_preview = (
                    role == "topic" and child.get("category") == "knowledge"
                )
                if isinstance(preview, dict):
                    if not allows_parent_preview:
                        raise LessonFlowError(
                            "non-knowledge child must not carry a parent "
                            f"preview: {child_key}"
                        )
                    preview_start = preview.get("start_line")
                    preview_end = preview.get("end_line")
                    preview_role = preview.get("role")
                    if (
                        not isinstance(preview_start, int)
                        or not isinstance(preview_end, int)
                        or preview_start < int(child["start_line"])
                        or preview_end < preview_start
                        or preview_end > int(child["end_line"])
                        or preview_role
                        not in {
                            "context",
                            "question",
                            "analysis",
                            "exposition",
                            "transition",
                            "worked-example",
                        }
                    ):
                        raise LessonFlowError(
                            f"invalid parent preview range for {child_key}"
                        )
                    if not meaningful_preview(
                        lines,
                        preview_start,
                        preview_end,
                    ):
                        raise LessonFlowError(
                            f"parent preview is incomplete for {child_key}"
                        )
                    preview_text = " ".join(
                        text.strip()
                        for text in lines[preview_start - 1 : preview_end]
                        if text.strip()
                    )
                    if len(preview_text) > MAX_PARENT_PREVIEW_CHARACTERS:
                        raise LessonFlowError(
                            "parent preview exceeds the concise prompt limit "
                            f"for {child_key}"
                        )
                    if preview_omits_attached_referenced_media(
                        lines,
                        preview_start,
                        preview_end,
                        int(child["end_line"]),
                    ):
                        raise LessonFlowError(
                            "parent preview strands an attached figure/table "
                            f"before the child link: {child_key}"
                        )
                    preview_nonblank = nonblank_count(
                        lines,
                        preview_start,
                        preview_end,
                    )
                    rendered_preview_nonblank += preview_nonblank
                    if is_first_child:
                        first_child_preview_nonblank = preview_nonblank
                moved_children.add(str(child_key))
                contextual_preview_since_child = False
            else:
                if child_key is not None:
                    raise LessonFlowError(
                        f"retained block cannot name a child: {node_key}"
                    )
                block_nonblank = nonblank_count(lines, start_line, end_line)
                retained_nonblank += block_nonblank
                if before_first_child:
                    opening_retained_nonblank += block_nonblank
                if block_index == 0:
                    entry_context_nonblank = block_nonblank
                if (
                    role
                    not in {
                        "practice",
                        "worked-example",
                        "representative-example",
                    }
                    and block_nonblank > max_retained
                ):
                    raise LessonFlowError(
                        f"retained teaching block is too large in {node_key}: "
                        f"{block_nonblank} nonblank lines"
                    )
                first_nonblank_line = next(
                    (
                        line_number
                        for line_number in range(start_line, end_line + 1)
                        if lines[line_number - 1].strip()
                    ),
                    None,
                )
                for line_number in range(start_line, end_line + 1):
                    detected = functional_boundary(lines[line_number - 1])
                    if detected is None:
                        continue
                    expected_role, label = detected
                    if (
                        expected_role == "section-heading"
                        and line_number == int(node["start_line"])
                    ):
                        continue
                    if line_number != first_nonblank_line:
                        raise LessonFlowError(
                            f"lesson-flow block crosses functional boundary "
                            f"{label!r} at line {line_number}: {node_key}"
                        )
                    compatible_roles = {expected_role}
                    if expected_role == "worked-example":
                        compatible_roles.add("representative-example")
                    if role not in compatible_roles:
                        raise LessonFlowError(
                            f"lesson-flow block role {role!r} does not match "
                            f"functional boundary {label!r} at line "
                            f"{line_number}: {node_key}"
                        )
                if role == "section-heading":
                    contextual_preview_since_child = meaningful_preview(
                        lines, start_line, end_line
                    )
                elif role in {
                    "entry-context",
                    "context",
                    "question",
                    "exposition",
                    "transition",
                } and meaningful_preview(lines, start_line, end_line):
                    contextual_preview_since_child = True
        if representative_example_count > 1:
            raise LessonFlowError(
                f"lesson-flow has more than one representative example: {node_key}"
            )
        if expected_start != int(node["end_line"]) + 1:
            raise LessonFlowError(
                f"lesson-flow blocks do not cover the full lesson: {node_key}"
            )
        if moved_children != child_keys:
            missing = sorted(child_keys - moved_children)
            extra = sorted(moved_children - child_keys)
            raise LessonFlowError(
                f"lesson-flow child coverage mismatch for {node_key}; "
                f"missing={missing}, extra={extra}"
            )
        if (
            entry_context_nonblank < 2
            and opening_retained_nonblank < 2
            and first_child_preview_nonblank < 1
        ):
            raise LessonFlowError(
                "lesson entry would begin link-only and has no retained "
                f"opening preview: {node_key}"
            )
        if child_keys and retained_nonblank + rendered_preview_nonblank < 2:
            raise LessonFlowError(
                f"lesson entry would be link-only and has no retained preview: "
                f"{node_key}"
            )
        roles = {str(block["role"]) for block in blocks}
        required_check_roles = {
            "introduction_preserved": {"entry-context", "context"},
            "transitions_preserved": {"transition"},
            "independent_topics_split": {"topic"},
            "exercises_retained_or_routed": {"practice"},
        }
        for check_name, relevant_roles in required_check_roles.items():
            if roles & relevant_roles and checks[check_name] != "passed":
                raise LessonFlowError(
                    f"lesson-flow {check_name} must pass when its role is "
                    f"present: {node_key}"
                )
        draft_findings = lesson.get("draft_findings", [])
        if not isinstance(draft_findings, list):
            raise LessonFlowError(
                f"lesson-flow draft_findings must be an array: {node_key}"
            )
        unresolved_findings = [
            finding
            for finding in draft_findings
            if not isinstance(finding, dict)
            or finding.get("resolved") is not True
        ]
        if unresolved_findings:
            raise LessonFlowError(
                f"lesson-flow draft findings remain unresolved: {node_key}"
            )

    missing_lessons = sorted(set(expected_lessons) - reviewed_lessons)
    if missing_lessons:
        raise LessonFlowError(
            "lesson-flow manifest omits lesson nodes: "
            + ", ".join(missing_lessons[:12])
        )
    return {
        "status": "passed",
        "lesson_count": len(reviewed_lessons),
        "logical_block_count": sum(
            len(lesson["blocks"]) for lesson in raw_lessons
        ),
    }


def atomic_write(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {path}")
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("formatted_markdown", type=Path)
    plan_parser.add_argument("split_manifest", type=Path)
    plan_parser.add_argument("profile", type=Path)
    plan_parser.add_argument("output", type=Path)
    plan_parser.add_argument("--overwrite", action="store_true")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("manifest", type=Path)
    validate_parser.add_argument("formatted_markdown", type=Path)
    validate_parser.add_argument("split_manifest", type=Path)
    validate_parser.add_argument("profile", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "plan":
            payload = plan(
                args.formatted_markdown.resolve(),
                args.split_manifest.resolve(),
                args.profile.resolve(),
            )
            atomic_write(
                args.output.resolve(),
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                args.overwrite,
            )
            result = {
                "status": "review_required",
                "manifest": str(args.output.resolve()),
                "lesson_count": len(payload["lessons"]),
                "logical_block_count": sum(
                    len(lesson["blocks"]) for lesson in payload["lessons"]
                ),
                "finding_count": sum(
                    len(lesson["draft_findings"])
                    for lesson in payload["lessons"]
                ),
            }
        else:
            payload = read_json(args.manifest.resolve())
            result = validate(
                payload,
                formatted_markdown=args.formatted_markdown.resolve(),
                split_manifest_path=args.split_manifest.resolve(),
                profile_path=args.profile.resolve(),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
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

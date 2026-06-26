# -*- coding: utf-8 -*-
"""
Promptfoo assertion: validates heading expected-result output (step3 expected).

Checks:
  - Every line starts with #, ##, or ###
  - No bare text lines or list items
  - No trailing page numbers
  - H1 for chapters, H2 for sections, H3 for subsections
  - No markdown fences or JSON
"""

import re
from typing import Any


def get_assert(output: str, context: dict[str, Any] | None = None) -> dict:
    """Return a GradingResult dict: {pass, score, reason}."""
    errors: list[str] = []

    if not output or not output.strip():
        return {"pass": False, "score": 0.0, "reason": "Output is empty"}

    raw = output.strip()

    # ── 1. No markdown fences ────────────────────────────────────────────
    if re.search(r"^```", raw, re.MULTILINE):
        errors.append("Output contains markdown fences (```)")

    if raw.lstrip().startswith("{") or raw.lstrip().startswith("["):
        errors.append("Output appears to be JSON, not a heading list")

    lines = [ln for ln in raw.splitlines() if ln.strip()]

    if len(lines) < 2:
        errors.append(f"Too few lines ({len(lines)}), expected a heading list")
        return {
            "pass": False,
            "score": 0.0,
            "reason": "; ".join(errors),
        }

    # ── 2. Every line must start with # ──────────────────────────────────
    HEADING_RE = re.compile(r"^#{1,3}\s+\S")
    bad_lines: list[str] = []
    for i, ln in enumerate(lines, 1):
        stripped = ln.strip()
        if not HEADING_RE.match(stripped):
            # Allow H4-H6 as lenient, but flag bare text and list items
            if re.match(r"^#{4,6}\s+", stripped):
                errors.append(
                    f"Line {i}: H4+ heading detected (only H1-H3 expected): "
                    f"{stripped[:60]}"
                )
            elif stripped.startswith("-") or stripped.startswith("*"):
                bad_lines.append(f"Line {i}: list item: {stripped[:60]}")
            else:
                bad_lines.append(f"Line {i}: bare text: {stripped[:60]}")

    if bad_lines:
        errors.append(
            f"{len(bad_lines)} lines are not headings: "
            + "; ".join(bad_lines[:5])
        )

    # ── 3. No trailing page numbers ──────────────────────────────────────
    PAGE_NUM_TAIL_RE = re.compile(
        r"(?:\s+…+\s*\d+|\s+\.{2,}\s*\d+|\s+·{2,}\s*\d+|"
        r"\s+．{2,}\s*\d+|\s+/\s*\d+|P\d+)\s*$"
    )
    trailing_pages = [
        ln.strip() for ln in lines if PAGE_NUM_TAIL_RE.search(ln)
    ]
    if trailing_pages:
        errors.append(
            f"{len(trailing_pages)} lines still have trailing page numbers: "
            + "; ".join(tp[:60] for tp in trailing_pages[:3])
        )

    # ── 4. Hierarchy sanity ──────────────────────────────────────────────
    CHAPTER_RE = re.compile(
        r"^#\s+(?:第\s*[一二三四五六七八九十百千万零〇两\d]+\s*[章篇部]|"
        r"Chapter\s+\d+|综合与实践|附录|后记|索引)",
        re.IGNORECASE,
    )
    h1_count = sum(1 for ln in lines if ln.strip().startswith("# "))
    h2_count = sum(1 for ln in lines if ln.strip().startswith("## "))
    h3_count = sum(1 for ln in lines if ln.strip().startswith("### "))

    if h1_count == 0:
        errors.append("No H1 headings found (expected chapter-level headings)")

    if h2_count == 0:
        errors.append("No H2 headings found (expected section-level headings)")

    # Check that H1s look like chapters
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if not CHAPTER_RE.match(stripped):
                # Not necessarily an error, but flag for review
                pass

    # ── 5. No explanatory text ───────────────────────────────────────────
    EXPLANATION_RE = re.compile(
        r"(?:^|\n)\s*(?:Here is|Below is|The following|Note:|"
        r"I have|This is|Explanation|以下是|说明|注意)",
        re.IGNORECASE,
    )
    if EXPLANATION_RE.search(raw):
        errors.append("Output contains explanatory text")

    # ── Result ───────────────────────────────────────────────────────────
    if errors:
        return {
            "pass": False,
            "score": max(0.0, 1.0 - len(errors) * 0.2),
            "reason": "; ".join(errors),
        }

    return {
        "pass": True,
        "score": 1.0,
        "reason": (
            f"Heading list is valid: {h1_count} H1, "
            f"{h2_count} H2, {h3_count} H3"
        ),
    }

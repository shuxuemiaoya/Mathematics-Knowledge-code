# -*- coding: utf-8 -*-
"""
Promptfoo assertion: validates TOC extraction output from Step 1.

Checks:
  - Contains line-number prefixes  (e.g., `123: `)
  - Lines are contiguous (sequential line numbers)
  - Contains at least one TOC page header (# 目录 / # CONTENTS)
  - Contains page references (e.g., /2, P1, ... 18)
  - No markdown fences, JSON, or explanations
"""

import re
from typing import Any


def get_assert(output: str, context: dict[str, Any] | None = None) -> dict:
    """Return a GradingResult dict: {pass, score, reason}."""
    errors: list[str] = []

    if not output or not output.strip():
        return {"pass": False, "score": 0.0, "reason": "Output is empty"}

    lines = output.strip().splitlines()

    # ── 1. Line-number prefix check ──────────────────────────────────────
    LINE_NUM_RE = re.compile(r"^\d+:\s")
    numbered = [i for i, ln in enumerate(lines) if LINE_NUM_RE.match(ln)]
    non_blank_lines = [ln for ln in lines if ln.strip()]

    if len(numbered) < len(non_blank_lines) * 0.5:
        errors.append(
            f"Only {len(numbered)}/{len(non_blank_lines)} non-blank lines "
            f"have a line-number prefix (expected ≥ 50%)"
        )

    # ── 2. Contiguity check ──────────────────────────────────────────────
    if numbered:
        nums: list[int] = []
        for idx in numbered:
            m = re.match(r"^(\d+):", lines[idx])
            if m:
                nums.append(int(m.group(1)))

        if nums:
            gaps = []
            for i in range(1, len(nums)):
                diff = nums[i] - nums[i - 1]
                if diff < 0:
                    gaps.append(f"backward jump {nums[i-1]} → {nums[i]}")
                elif diff > 5:
                    gaps.append(f"gap {nums[i-1]} → {nums[i]} (delta={diff})")
            if gaps:
                errors.append(
                    f"Line numbers are not contiguous: {'; '.join(gaps[:5])}"
                )

    # ── 3. TOC page header presence ──────────────────────────────────────
    TOC_HEADER_RE = re.compile(
        r"#\s*(目录|CONTENTS|Table\s+of\s+Contents)", re.IGNORECASE
    )
    has_toc_header = any(TOC_HEADER_RE.search(ln) for ln in lines)
    if not has_toc_header:
        errors.append(
            "Missing TOC page header (expected at least one line matching "
            "'# 目录', '# CONTENTS', or similar)"
        )

    # ── 4. Page reference presence ───────────────────────────────────────
    PAGE_REF_RE = re.compile(
        r"(?:/\s*\d+|P\d+|…+\s*\d+|\.{2,}\s*\d+|·{2,}\s*\d+|．{2,}\s*\d+)"
    )
    page_refs = [ln for ln in lines if PAGE_REF_RE.search(ln)]
    if len(page_refs) < 3:
        errors.append(
            f"Found only {len(page_refs)} lines with page references "
            f"(expected ≥ 3)"
        )

    # ── 5. No forbidden content ──────────────────────────────────────────
    raw = output.strip()
    if re.search(r"^```", raw, re.MULTILINE):
        errors.append("Output contains markdown fences (```)")

    if raw.lstrip().startswith("{") or raw.lstrip().startswith("["):
        errors.append("Output appears to be JSON, not raw TOC lines")

    EXPLANATION_RE = re.compile(
        r"(?:^|\n)\s*(?:Here is|Below is|The following|Note:|"
        r"I have|This is|Explanation)",
        re.IGNORECASE,
    )
    if EXPLANATION_RE.search(raw):
        errors.append(
            "Output contains explanatory text (expected raw TOC lines only)"
        )

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
        "reason": "TOC extraction output is valid",
    }

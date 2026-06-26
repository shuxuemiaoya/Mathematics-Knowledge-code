# -*- coding: utf-8 -*-
"""
Promptfoo assertion: validates Step 5 heading-validation JSON output.

Checks:
  - Valid JSON
  - Has required keys: valid, checked_heading_count, errors
  - valid is boolean
  - errors is array
  - Consistency: valid=true ⟹ errors is empty; valid=false ⟹ errors non-empty
"""

import json
from typing import Any


def get_assert(output: str, context: dict[str, Any] | None = None) -> dict:
    """Return a GradingResult dict: {pass, score, reason}."""
    errors: list[str] = []

    if not output or not output.strip():
        return {"pass": False, "score": 0.0, "reason": "Output is empty"}

    raw = output.strip()

    # Strip optional markdown fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        # Remove first and last fence lines
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    # ── 1. Valid JSON ────────────────────────────────────────────────────
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"Invalid JSON: {e}",
        }

    if not isinstance(data, dict):
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"Expected JSON object, got {type(data).__name__}",
        }

    # ── 2. Required keys ────────────────────────────────────────────────
    REQUIRED_KEYS = ["valid", "checked_heading_count", "errors"]
    for key in REQUIRED_KEYS:
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    if errors:
        return {
            "pass": False,
            "score": 0.2,
            "reason": "; ".join(errors),
        }

    # ── 3. Type checks ──────────────────────────────────────────────────
    if not isinstance(data["valid"], bool):
        errors.append(
            f"'valid' must be boolean, got {type(data['valid']).__name__}"
        )

    if not isinstance(data["checked_heading_count"], (int, float)):
        errors.append(
            f"'checked_heading_count' must be numeric, got "
            f"{type(data['checked_heading_count']).__name__}"
        )
    elif isinstance(data["checked_heading_count"], float):
        if data["checked_heading_count"] != int(data["checked_heading_count"]):
            errors.append("'checked_heading_count' must be an integer")

    if not isinstance(data["errors"], list):
        errors.append(
            f"'errors' must be array, got {type(data['errors']).__name__}"
        )

    if errors:
        return {
            "pass": False,
            "score": 0.3,
            "reason": "; ".join(errors),
        }

    # ── 4. Consistency checks ────────────────────────────────────────────
    is_valid = data["valid"]
    error_list = data["errors"]

    if is_valid and len(error_list) > 0:
        errors.append(
            f"valid=true but errors array has {len(error_list)} entries "
            f"(must be empty when valid)"
        )

    if not is_valid and len(error_list) == 0:
        errors.append(
            "valid=false but errors array is empty "
            "(must contain at least one error)"
        )

    # ── 5. Error entries should be strings ───────────────────────────────
    non_strings = [e for e in error_list if not isinstance(e, str)]
    if non_strings:
        errors.append(
            f"{len(non_strings)} error entries are not strings"
        )

    # ── 6. No extra text outside JSON ────────────────────────────────────
    original = output.strip()
    # Allow markdown fences, but no other text
    stripped_for_check = original
    if stripped_for_check.startswith("```"):
        lines = stripped_for_check.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped_for_check = "\n".join(lines).strip()

    # Try to detect trailing/leading text
    try:
        json.loads(stripped_for_check)
    except json.JSONDecodeError:
        # Already parsed successfully above, so this is extra text
        errors.append("Extra text found outside the JSON object")

    # ── Result ───────────────────────────────────────────────────────────
    if errors:
        return {
            "pass": False,
            "score": max(0.0, 1.0 - len(errors) * 0.25),
            "reason": "; ".join(errors),
        }

    return {
        "pass": True,
        "score": 1.0,
        "reason": (
            f"JSON schema valid: valid={is_valid}, "
            f"checked_heading_count={data['checked_heading_count']}, "
            f"errors_count={len(error_list)}"
        ),
    }

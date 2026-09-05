#!/usr/bin/env python3
"""Draft digest-bound atom-role decisions from explicit reviewer overrides.

Only title-length cleanup is deterministic. Every semantic flag requires an
explicit override, so this helper cannot silently reclassify teaching content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from semantic_atomization import AtomizationError, atomic_json, load_tagged, seal_artifact


TITLE_FLAG = "title-too-long-for-reusable-atom"


def concise_title(value: str, category: str, limit: int = 40) -> str:
    text = " ".join(str(value).replace("\n", " ").split()).strip()
    prefix = ""
    if category == "exercise" and " · " in text:
        prefix, text = text.split(" · ", 1)
        prefix += " · "
    available = max(8, limit - len(prefix))
    if len(text) <= available:
        return prefix + text
    for mark in ("。", "；", "？", "?", "！", "!", "，", ","):
        position = text.find(mark, 8, available + 1)
        if position >= 0:
            return prefix + text[: position + 1]
    return prefix + text[: available - 1].rstrip() + "…"


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8-sig"))
    values = payload.get("atoms")
    if not isinstance(values, dict) or not all(isinstance(value, dict) for value in values.values()):
        raise AtomizationError("Role override file needs an atoms object")
    return {str(key): value for key, value in values.items()}


def replacement(original: dict[str, Any], raw: dict[str, Any], index: int) -> dict[str, Any]:
    source_range = list(raw.get("source_range", original["source_range"]))
    category = str(raw.get("category", original["category"]))
    owner = str(raw.get("owner_key", original["owner_key"]))
    title = str(raw.get("title", concise_title(str(original["title"]), category)))
    identity = f"{original['atom_id']}:{index}:{source_range}:{category}:{owner}"
    atom_id = str(raw.get("atom_id") or f"role-{hashlib.sha256(identity.encode()).hexdigest()[:12]}")
    result = {
        "atom_id": atom_id, "owner_key": owner, "source_range": source_range,
        "category": category, "title": title,
        "boundary_reason": str(raw.get("boundary_reason", "Role audit preserves a contiguous source-backed teaching boundary.")),
        "cohesion_reason": str(raw.get("cohesion_reason", "These source lines now express one consistent teaching role.")),
        "confidence": float(raw.get("confidence", 0.99)),
    }
    for field in ("standalone_kind", "standalone_reason"):
        if field in raw:
            result[field] = str(raw[field])
    return result


def draft(jobs: dict[str, Any], overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    used: set[str] = set()
    for original in jobs.get("atoms", []):
        if not original.get("requires_decision"):
            continue
        atom_id = str(original["atom_id"])
        flags = set(map(str, original.get("flags", [])))
        override = overrides.get(atom_id)
        if override is None and flags != {TITLE_FLAG}:
            raise AtomizationError(f"Semantic role override required for {atom_id}: {sorted(flags)}")
        if override is None:
            action = "replace"
            replacements = [replacement(original, {}, 0)]
            rationale = "The teaching role is unchanged; only an overlong display title is shortened deterministically."
        else:
            used.add(atom_id)
            action = str(override.get("action", "replace"))
            rationale = str(override.get("rationale", "Explicit Agent review confirms this atom's teaching role and boundary."))
            raw_replacements = override.get("replacement_atoms", [{}]) if action == "replace" else []
            if not isinstance(raw_replacements, list):
                raise AtomizationError(f"replacement_atoms must be a list: {atom_id}")
            replacements = [replacement(original, raw, index) for index, raw in enumerate(raw_replacements)]
        decisions.append({
            "atom_id": atom_id, "action": action, "rationale": rationale,
            "confidence": float((override or {}).get("confidence", 0.99)),
            "replacement_atoms": replacements,
        })
    unused = sorted(set(overrides) - used)
    if unused:
        raise AtomizationError(f"Overrides do not identify flagged atoms: {unused}")
    return seal_artifact({
        "schema_version": 1, "kind": "atom-role-decisions",
        "atom_role_jobs_sha256": jobs["artifact_sha256"],
        "reviewer": {"type": "codex-agent", "model": "current-agent", "method": "explicit semantic overrides plus deterministic title compaction"},
        "decisions": decisions,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", type=Path)
    parser.add_argument("overrides", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        jobs = load_tagged(args.jobs, "atom-role-jobs")
        payload = draft(jobs, load_overrides(args.overrides))
        atomic_json(args.output, payload, overwrite=args.overwrite)
        report, code = {"status": "created", "output": str(args.output.expanduser().resolve()), "decisions": len(payload["decisions"])}, 0
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

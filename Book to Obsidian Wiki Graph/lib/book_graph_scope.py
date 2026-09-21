"""Resolve stage ownership from handoffs before any whole-corpus mutation."""
from __future__ import annotations

import json
from pathlib import Path

from book_graph_integrity import sha256_file


def managed_notes(profile: dict, profile_path: Path) -> tuple[list[Path], dict[Path, str]]:
    root = Path(profile["paths"]["book_root"]).resolve()
    staging = Path(profile["paths"]["staging_root"]).resolve()
    manifests = [(staging / "coverage-manifest.json", "units")]
    if any(item.get("role") == "concept" and item.get("enabled", True) for item in profile.get("categories", [])):
        manifests.append((staging / "concept-manifest.json", "concepts"))
    expected = set()
    evidence = {}
    for path, field in manifests:
        if not path.is_file():
            raise ValueError(f"Missing ownership manifest: {path}")
        evidence[path] = sha256_file(path)
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if (Path(payload.get("profile", "")).resolve() != profile_path.resolve()
                or payload.get("source_sha256") != profile.get("source", {}).get("sha256")):
            raise ValueError(f"Ownership manifest identity mismatch: {path}")
        if not isinstance(payload.get(field), list):
            raise ValueError(f"Ownership manifest has no {field}: {path}")
        for item in payload[field]:
            target = item.get("target")
            if not isinstance(target, str) or not target:
                raise ValueError("Ownership target is missing")
            note = root / target
            if note.resolve() != note or not note.is_relative_to(root) or note.suffix.lower() != ".md":
                raise ValueError(f"Invalid ownership target: {target}")
            expected.add(note)
    actual = {path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".md"}
    if not expected:
        raise ValueError("Ownership manifests contain no Markdown notes")
    if actual != expected:
        unexpected = sorted(str(path.relative_to(root)) for path in actual - expected)
        missing = sorted(str(path.relative_to(root)) for path in expected - actual)
        raise ValueError(f"Corpus ownership mismatch; unmanaged={unexpected[:8]}, missing={missing[:8]}")
    return sorted(expected), evidence

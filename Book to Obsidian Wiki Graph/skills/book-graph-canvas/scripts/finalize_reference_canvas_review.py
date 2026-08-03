#!/usr/bin/env python3
"""Approve an identity-bound review of every skipped reference canvas item."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ALLOWED_DISPOSITIONS = {
    "external-to-current-book",
    "absent-from-current-corpus",
    "represented-by-current-equivalent",
}


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def validate_decisions(
    *,
    kind: str,
    skipped: list[dict[str, Any]],
    decisions: Any,
    equivalent_keys: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(decisions, list):
        raise ValueError(f"{kind} decisions must be a list")
    expected_ids = {str(item["id"]) for item in skipped}
    reviewed: dict[str, dict[str, Any]] = {}
    for item in decisions:
        if not isinstance(item, dict):
            raise ValueError(f"every {kind} decision must be an object")
        item_id = str(item.get("id", ""))
        if not item_id or item_id in reviewed:
            raise ValueError(f"{kind} decisions need unique nonempty ids")
        disposition = item.get("disposition")
        reason = item.get("reason")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(
                f"{kind} {item_id}: unsupported disposition {disposition!r}"
            )
        if not isinstance(reason, str) or len(reason.strip()) < 12:
            raise ValueError(f"{kind} {item_id}: reason is too vague")
        if disposition == "represented-by-current-equivalent":
            equivalent_key = item.get("equivalent_key")
            if equivalent_key not in equivalent_keys:
                raise ValueError(
                    f"{kind} {item_id}: equivalent_key does not exist"
                )
        reviewed[item_id] = item
    if set(reviewed) != expected_ids:
        missing = sorted(expected_ids - set(reviewed))
        extra = sorted(set(reviewed) - expected_ids)
        raise ValueError(
            f"{kind} decisions do not exactly cover skipped ids; "
            f"missing={missing}, extra={extra}"
        )
    return [reviewed[item_id] for item_id in sorted(reviewed)]


def finalize(manifest_path: Path, decisions_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8-sig"))
    review = manifest.get("reference_review")
    if not isinstance(review, dict):
        raise ValueError("manifest has no reference_review")
    if decisions.get("reference_sha256") != review.get("reference_sha256"):
        raise ValueError("decision reference_sha256 does not match manifest")

    node_keys = {
        node.get("key")
        for node in manifest.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("key"), str)
    }
    edge_keys = {
        edge.get("key")
        for edge in manifest.get("edges", [])
        if isinstance(edge, dict) and isinstance(edge.get("key"), str)
    }
    node_decisions = validate_decisions(
        kind="node",
        skipped=review.get("skipped_nodes", []),
        decisions=decisions.get("skipped_nodes", []),
        equivalent_keys=node_keys,
    )
    edge_decisions = validate_decisions(
        kind="edge",
        skipped=review.get("skipped_edges", []),
        decisions=decisions.get("skipped_edges", []),
        equivalent_keys=edge_keys,
    )
    review["decisions"] = {
        "skipped_nodes": node_decisions,
        "skipped_edges": edge_decisions,
    }
    review["status"] = "approved"
    review["reviewer_confirmed"] = True
    atomic_write_json(manifest_path, manifest)
    return {
        "status": "approved",
        "manifest": str(manifest_path),
        "skipped_nodes_reviewed": len(node_decisions),
        "skipped_edges_reviewed": len(edge_decisions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--reviewer-confirmed", action="store_true")
    args = parser.parse_args()
    if not args.reviewer_confirmed:
        parser.error("--reviewer-confirmed is required")
    try:
        result = finalize(args.manifest.resolve(), args.decisions.resolve())
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

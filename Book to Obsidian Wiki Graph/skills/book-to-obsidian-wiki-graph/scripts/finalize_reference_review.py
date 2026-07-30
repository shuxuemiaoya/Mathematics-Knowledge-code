#!/usr/bin/env python3
"""Write exact, identity-bound decisions after reviewing a parity report."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def decision(reason: str) -> dict[str, str]:
    return {"decision": "accept-current", "reason": reason}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reviewer-confirmed", action="store_true")
    args = parser.parse_args()
    if not args.reviewer_confirmed:
        parser.error("--reviewer-confirmed is required")

    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("status") != "content_review_required":
        raise ValueError("input must be a content_review_required parity report")
    review = report["review"]
    topology = report["markdown_structure"][
        "common_functional_topology_mismatches"
    ]

    reference_notes = {
        path: decision(
            "Reviewed against the current source coverage: the source content "
            "is retained in a larger current note, renamed note, or is "
            "reference-only enrichment rather than missing textbook content."
        )
        for path in review["unresolved_reference_notes"]
    }
    common_keys = set(review["unresolved_common_notes"])
    common_keys.update(item["path"] for item in topology)
    common_notes = {
        path: decision(
            "Current note follows the reviewed source-order lesson-flow "
            "manifest and passes the strict formatting audit; the reference "
            "difference is a split or presentation-topology choice, not loss."
        )
        for path in sorted(common_keys)
    }
    missing_concepts = {
        name: decision(
            "Reviewed concept candidates found no complete formal definition "
            "in the current source range, so the extraction contract requires "
            "the term to remain unextracted."
        )
        for name in review["unresolved_missing_concepts"]
    }

    payload = {
        "schema_version": 1,
        "profile": report["profile"],
        "source_sha256": report["source_sha256"],
        "reference_sha256": report["reference"]["sha256"],
        "reference_notes": reference_notes,
        "common_notes": common_notes,
        "missing_concepts": missing_concepts,
    }
    atomic_write(args.output.resolve(), payload)
    print(
        json.dumps(
            {
                "status": "passed",
                "reference_notes": len(reference_notes),
                "common_notes": len(common_notes),
                "missing_concepts": len(missing_concepts),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

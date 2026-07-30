#!/usr/bin/env python3
"""Finalize an explicitly reviewed concept-candidate artifact."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, payload: dict) -> None:
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


def parse_range(value: str) -> tuple[str, int, int]:
    try:
        name, start, end = value.rsplit(":", 2)
        return name, int(start), int(end)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "formula ranges must use NAME:START:END"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path)
    parser.add_argument(
        "--formula-range",
        action="append",
        default=[],
        type=parse_range,
        metavar="NAME:START:END",
    )
    parser.add_argument("--reject-term", action="append", default=[])
    parser.add_argument("--reviewer-confirmed", action="store_true")
    args = parser.parse_args()

    if not args.reviewer_confirmed:
        parser.error("--reviewer-confirmed is required")

    path = args.candidates.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    concepts = {item["name"]: item for item in payload.get("concepts", [])}
    missing = (
        {name for name, _, _ in args.formula_range}
        | set(args.reject_term)
    ) - set(concepts)
    if missing:
        raise ValueError("unknown candidate terms: " + ", ".join(sorted(missing)))

    for name, start, end in args.formula_range:
        item = concepts[name]
        item["definition_start_line"] = start
        item["definition_end_line"] = end
        item["confidence"] = "high"
        item["review_flags"] = []

    rejected = list(payload.get("rejected", []))
    rejected_names = {item["name"] for item in rejected}
    for name in args.reject_term:
        item = concepts.pop(name)
        if name not in rejected_names:
            rejected.append(
                {
                    "name": name,
                    "reason": (
                        "Reviewed source has no compact continuous definition "
                        "range containing every required equation."
                    ),
                    "reviewed_source": item["definition_source"],
                }
            )

    unresolved = [
        item["name"]
        for item in concepts.values()
        if item.get("review_flags")
    ]
    if unresolved:
        raise ValueError(
            "review flags remain unresolved: " + ", ".join(sorted(unresolved))
        )

    for item in concepts.values():
        item["reviewed"] = True
    payload["concepts"] = sorted(concepts.values(), key=lambda item: item["name"])
    payload["rejected"] = sorted(rejected, key=lambda item: item["name"])
    payload["status"] = "approved"
    payload["reviewed"] = True
    atomic_write(path, payload)
    print(
        json.dumps(
            {
                "status": "approved",
                "concepts": len(payload["concepts"]),
                "rejected": len(payload["rejected"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

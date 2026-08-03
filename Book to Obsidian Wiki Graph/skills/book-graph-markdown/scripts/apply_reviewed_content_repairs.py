#!/usr/bin/env python3
"""Apply reviewer-approved, exact Markdown repairs without heuristic rewriting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def exact_text(text: str, repair: dict[str, Any]) -> str:
    old = repair.get("old")
    new = repair.get("new")
    if not isinstance(old, str) or not old:
        raise ValueError("replace-text repair requires non-empty old")
    if not isinstance(new, str):
        raise ValueError("replace-text repair requires string new")
    count = text.count(old)
    if count != 1:
        raise ValueError(
            f"replace-text expected exactly one match, found {count}"
        )
    return text.replace(old, new, 1)


def insert_after(text: str, repair: dict[str, Any]) -> str:
    anchor = repair.get("anchor")
    insertion = repair.get("text")
    if not isinstance(anchor, str) or not anchor:
        raise ValueError("insert-after repair requires non-empty anchor")
    if not isinstance(insertion, str) or not insertion:
        raise ValueError("insert-after repair requires non-empty text")
    count = text.count(anchor)
    if count != 1:
        raise ValueError(
            f"insert-after expected exactly one anchor, found {count}"
        )
    return text.replace(anchor, anchor + insertion, 1)


def replace_line(text: str, repair: dict[str, Any]) -> str:
    contains = repair.get("contains")
    replacement = repair.get("new")
    if not isinstance(contains, str) or not contains:
        raise ValueError("replace-line repair requires non-empty contains")
    if not isinstance(replacement, str):
        raise ValueError("replace-line repair requires string new")
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if contains in line]
    if len(matches) != 1:
        raise ValueError(
            f"replace-line expected exactly one line, found {len(matches)}"
        )
    lines[matches[0] : matches[0] + 1] = replacement.splitlines()
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


OPERATIONS = {
    "replace-text": exact_text,
    "insert-after": insert_after,
    "replace-line": replace_line,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("repairs", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--reviewer-confirmed", action="store_true")
    parser.add_argument("--overwrite-report", action="store_true")
    args = parser.parse_args()
    if not args.reviewer_confirmed:
        parser.error("--reviewer-confirmed is required")
    if args.report.exists() and not args.overwrite_report:
        parser.error("--overwrite-report is required for an existing report")

    profile_path = args.profile.resolve()
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    repairs_path = args.repairs.resolve()
    payload = json.loads(repairs_path.read_text(encoding="utf-8-sig"))
    if payload.get("reviewer_confirmed") is not True:
        raise ValueError("repair artifact is not reviewer-confirmed")
    if payload.get("profile") != str(profile_path):
        raise ValueError("repair artifact profile mismatch")
    if payload.get("source_sha256") != profile["source"]["sha256"]:
        raise ValueError("repair artifact source identity mismatch")

    book_root = Path(profile["paths"]["book_root"]).resolve()
    results: list[dict[str, Any]] = []
    for index, repair in enumerate(payload.get("repairs", []), start=1):
        relative = repair.get("path")
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"repairs[{index}] path is required")
        target = (book_root / relative).resolve()
        try:
            target.relative_to(book_root)
        except ValueError as exc:
            raise ValueError(
                f"repairs[{index}] escapes book root: {relative}"
            ) from exc
        if not target.is_file():
            raise FileNotFoundError(target)
        operation = repair.get("operation")
        handler = OPERATIONS.get(operation)
        if handler is None:
            raise ValueError(
                f"repairs[{index}] has unsupported operation {operation!r}"
            )
        before = target.read_text(encoding="utf-8-sig")
        before_hash = sha256_file(target)
        after = handler(before, repair)
        if after == before:
            raise ValueError(f"repairs[{index}] made no change: {relative}")
        atomic_write(target, after)
        results.append(
            {
                "path": relative,
                "operation": operation,
                "reason": repair.get("reason"),
                "evidence": repair.get("evidence"),
                "before_sha256": before_hash,
                "after_sha256": sha256_file(target),
            }
        )

    report = {
        "schema_version": 1,
        "stage": "reviewed-markdown-content-repairs",
        "status": "passed",
        "profile": str(profile_path),
        "source_sha256": profile["source"]["sha256"],
        "repairs": str(repairs_path),
        "repair_count": len(results),
        "files": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(
        args.report.resolve(),
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

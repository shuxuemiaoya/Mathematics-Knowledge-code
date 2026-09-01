#!/usr/bin/env python3
"""Apply deterministic owner-folder paths to a reviewed split manifest."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from textbook_node_architecture import apply_hierarchical_filenames


def atomic_json(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {path}")
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
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.split_manifest.read_text(encoding="utf-8-sig"))
    report = apply_hierarchical_filenames(payload)
    review = payload.get("node_architecture")
    if not isinstance(review, dict):
        raise ValueError("split manifest needs node_architecture before path review")
    review["physical_hierarchy"] = "passed"
    atomic_json(args.output_manifest.resolve(), payload, args.overwrite)
    print(
        json.dumps(
            {
                **report,
                "output": str(args.output_manifest.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

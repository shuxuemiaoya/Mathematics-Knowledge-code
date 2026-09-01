#!/usr/bin/env python3
"""Create a frozen profile for one Book to Wiki Graph run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ATOM_CATEGORIES = {
    "knowledge": "原子层/知识点",
    "worked-example": "原子层/例题",
    "exercise": "原子层/习题",
    "scenario": "原子层/情景引入",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def create_profile(source: Path, staging_root: Path, book_root: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source does not exist: {source}")
    suffix = source.suffix.casefold()
    if suffix == ".pdf":
        kind = "pdf"
    elif suffix in {".md", ".markdown"}:
        kind = "markdown"
    else:
        raise ValueError("Source must be a PDF or Markdown file")
    return {
        "schema_version": 1,
        "source": {
            "path": str(source),
            "sha256": sha256_file(source),
            "kind": kind,
            "bytes": source.stat().st_size,
        },
        "paths": {
            "staging_root": str(staging_root.expanduser().resolve()),
            "book_root": str(book_root.expanduser().resolve()),
        },
        "organizer_root": "组织层",
        "atom_categories": ATOM_CATEGORIES,
        "canvas": {"enabled": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("staging_root", type=Path)
    parser.add_argument("book_root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output = (
        args.output.expanduser().resolve()
        if args.output
        else args.staging_root.expanduser().resolve() / "book-profile.json"
    )
    profile = create_profile(args.source, args.staging_root, args.book_root)
    atomic_json(output, profile, args.overwrite)
    print(
        json.dumps(
            {
                "status": "created",
                "profile": str(output),
                "source_sha256": profile["source"]["sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

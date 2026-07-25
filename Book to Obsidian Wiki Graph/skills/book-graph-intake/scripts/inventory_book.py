#!/usr/bin/env python3
"""Inspect source and output artifacts for the book-graph intake stage."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_directory(path: Path) -> dict[str, Any]:
    files = sorted(item for item in path.rglob("*") if item.is_file())
    extensions: collections.Counter[str] = collections.Counter()
    categories: collections.Counter[str] = collections.Counter()
    aggregate = hashlib.sha256()
    total_bytes = 0

    for item in files:
        relative = item.relative_to(path)
        item_hash = sha256_file(item)
        size = item.stat().st_size
        total_bytes += size
        extensions[item.suffix.lower() or "<none>"] += 1
        categories[relative.parts[0] if len(relative.parts) > 1 else "<root>"] += 1
        aggregate.update(relative.as_posix().encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(item_hash.encode("ascii"))
        aggregate.update(b"\0")

    return {
        "kind": "directory",
        "path": str(path),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "tree_sha256": aggregate.hexdigest(),
        "extensions": dict(sorted(extensions.items())),
        "categories": dict(sorted(categories.items())),
    }


def inspect_pdf(path: Path) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError:
        PdfReader = None

    if PdfReader is not None:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        media_box = reader.pages[0].mediabox if reader.pages else None
        width = float(media_box.width) if media_box is not None else None
        height = float(media_box.height) if media_box is not None else None
        encrypted = bool(reader.is_encrypted)
    else:
        try:
            import fitz
        except ImportError:
            fitz = None
        if fitz is not None:
            with fitz.open(path) as document:
                page_count = document.page_count
                rectangle = document[0].rect if page_count else None
                width = float(rectangle.width) if rectangle is not None else None
                height = float(rectangle.height) if rectangle is not None else None
                encrypted = bool(document.needs_pass)
        else:
            try:
                completed = subprocess.run(
                    ["pdfinfo", str(path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                raise RuntimeError(
                    "PDF inspection requires pypdf, PyMuPDF, or pdfinfo"
                ) from exc
            page_match = re.search(
                r"^Pages:\s+(\d+)\s*$", completed.stdout, re.MULTILINE
            )
            size_match = re.search(
                r"^Page size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts",
                completed.stdout,
                re.MULTILINE,
            )
            encrypted_match = re.search(
                r"^Encrypted:\s+(yes|no)\s*$",
                completed.stdout,
                re.MULTILINE | re.IGNORECASE,
            )
            if page_match is None:
                raise RuntimeError("pdfinfo did not report a page count")
            page_count = int(page_match.group(1))
            width = float(size_match.group(1)) if size_match else None
            height = float(size_match.group(2)) if size_match else None
            encrypted = bool(
                encrypted_match
                and encrypted_match.group(1).casefold() == "yes"
            )

    return {
        "kind": "pdf",
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "pages": page_count,
        "encrypted": encrypted,
        "first_page_points": (
            {
                "width": width,
                "height": height,
            }
            if width is not None and height is not None
            else None
        ),
    }


def inspect_source(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"source does not exist: {path}")
    if path.is_dir():
        return inventory_directory(path)
    if path.suffix.lower() == ".pdf":
        return inspect_pdf(path)
    return {
        "kind": "file",
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "extension": path.suffix.lower(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a source book and optional target book directory."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--book-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = inspect_source(args.source.resolve())
        target = None
        if args.book_root is not None:
            book_root = args.book_root.resolve()
            target = (
                inventory_directory(book_root)
                if book_root.exists() and book_root.is_dir()
                else {
                    "kind": "target",
                    "path": str(book_root),
                    "exists": book_root.exists(),
                }
            )
        result = {"status": "passed", "source": source, "target": target}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        result = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

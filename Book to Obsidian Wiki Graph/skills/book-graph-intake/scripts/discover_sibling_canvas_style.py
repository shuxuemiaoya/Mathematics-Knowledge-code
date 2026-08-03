#!/usr/bin/env python3
"""Select a deterministic same-series sibling Canvas style reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


VOLUME_PATTERN = re.compile(r"第\s*([一二三四五六七八九十百零〇两\d]+)\s*册")
BRACKETED_PUBLISHER = re.compile(r"^\s*(【[^】]+】)")
CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def chinese_number(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if not value:
        return None
    if "十" in value:
        left, _, right = value.partition("十")
        tens = CHINESE_DIGITS.get(left, 1) if left else 1
        ones = CHINESE_DIGITS.get(right, 0) if right else 0
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if len(value) == 1:
        return CHINESE_DIGITS.get(value)
    return None


def title_facts(title: str) -> dict[str, Any]:
    publisher_match = BRACKETED_PUBLISHER.match(title)
    publisher = publisher_match.group(1) if publisher_match else ""
    volume_match = VOLUME_PATTERN.search(title)
    volume = chinese_number(volume_match.group(1)) if volume_match else None
    family = VOLUME_PATTERN.sub("", title)
    family = re.sub(r"数学电子课本", "", family)
    family = re.sub(r"\s+", "", family)
    return {"publisher": publisher, "family": family, "volume": volume}


def candidate_canvases(books_root: Path, target_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for sibling in sorted(
        (path for path in books_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        if sibling.resolve() == target_root.resolve():
            continue
        preferred = sibling / f"{sibling.name}.canvas"
        if preferred.is_file():
            candidates.append(preferred.resolve())
            continue
        canvases = sorted(sibling.glob("*.canvas"), key=lambda path: path.name)
        if len(canvases) == 1:
            candidates.append(canvases[0].resolve())
    return candidates


def discover(books_root: Path, target_root: Path) -> dict[str, Any]:
    books_root = books_root.resolve()
    target_root = target_root.resolve()
    if not books_root.is_dir():
        raise ValueError(f"books_root is not a directory: {books_root}")
    if target_root.parent != books_root:
        raise ValueError("target_book_root must be an immediate child of books_root")

    target = title_facts(target_root.name)
    ranked: list[dict[str, Any]] = []
    for canvas in candidate_canvases(books_root, target_root):
        facts = title_facts(canvas.parent.name)
        same_publisher = bool(target["publisher"]) and (
            facts["publisher"] == target["publisher"]
        )
        same_family = facts["family"] == target["family"]
        volume_distance = (
            abs(facts["volume"] - target["volume"])
            if facts["volume"] is not None and target["volume"] is not None
            else 10_000
        )
        eligible = same_publisher and same_family
        ranked.append(
            {
                "path": str(canvas),
                "sha256": sha256_file(canvas),
                "eligible": eligible,
                "same_publisher": same_publisher,
                "same_family": same_family,
                "volume": facts["volume"],
                "volume_distance": volume_distance,
            }
        )
    ranked.sort(
        key=lambda item: (
            not item["eligible"],
            item["volume_distance"],
            item["path"].casefold(),
        )
    )
    selected = next((item for item in ranked if item["eligible"]), None)
    return {
        "schema_version": 1,
        "stage": "canvas-style-reference-discovery",
        "status": "selected" if selected else "not_found",
        "target": {
            "book_root": str(target_root),
            "publisher": target["publisher"],
            "family": target["family"],
            "volume": target["volume"],
        },
        "selected": selected,
        "candidates": ranked,
        "selection_policy": (
            "same publisher and normalized series, then nearest volume, "
            "then lexical absolute path"
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("books_root", type=Path)
    parser.add_argument("target_book_root", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = discover(args.books_root, args.target_book_root)
        rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            write_text_atomic(args.output.resolve(), rendered)
        print(rendered, end="")
        return 0 if payload["status"] == "selected" else 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

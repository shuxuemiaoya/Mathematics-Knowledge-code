from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .common import lexical_signature, load_profile, sha256_file, write_json_atomic, write_text_atomic


def standardize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    output: list[str] = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 2:
                output.append("")
            continue
        if (line.startswith("#") or line.startswith("> [!")) and output and output[-1] != "":
            output.append("")
        blank_count = 0
        output.append(line)
    return "\n".join(output).rstrip() + "\n"


def standardize_corpus(profile_path: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    root = Path(profile["paths"]["graph_root"]).resolve()
    files = sorted(root.rglob("*.md"))
    results: list[dict[str, Any]] = []
    for path in files:
        before = path.read_text(encoding="utf-8-sig")
        before_signature = lexical_signature(before)
        after = standardize_text(before)
        after_signature = lexical_signature(after)
        if before_signature != after_signature:
            raise ValueError(f"Markup pass changed lexical content: {path}")
        changed = before != after
        if changed:
            write_text_atomic(path, after, overwrite=True)
        results.append(
            {
                "path": str(path),
                "changed": changed,
                "input_sha256": __import__("hashlib").sha256(before.encode("utf-8")).hexdigest(),
                "output_sha256": sha256_file(path),
                "lexical_signature_unchanged": True,
            }
        )
    return {
        "schema_version": 1,
        "stage": "markdown-standardization",
        "status": "passed",
        "profile": profile["_profile_path"],
        "file_count": len(files),
        "files": results,
        "protected_invariants": {
            "lexical_content": True,
            "formulas": True,
            "numbering": True,
            "links": True,
            "images": True,
            "source_order": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply markup-only formatting to a Question Type Graph corpus.")
    parser.add_argument("profile", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--overwrite-report", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = standardize_corpus(args.profile)
        write_json_atomic(args.report, result, overwrite=args.overwrite_report)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "markdown-standardization", "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

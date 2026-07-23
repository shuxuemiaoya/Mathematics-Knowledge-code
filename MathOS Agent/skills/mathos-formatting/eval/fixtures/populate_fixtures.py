# -*- coding: utf-8 -*-
r"""
populate_fixtures.py — Helper to copy mathos-formatting run artifacts
into the eval/fixtures/bookN/ directory with standardised names.

Usage:
    python populate_fixtures.py --work-dir <path-to-work-dir> [--book book1]

Example:
    python populate_fixtures.py ^
        --work-dir "C:\...\mathos-formatting\【2024版】【北师大版】七年级上册数学" ^
        --book book1

The mapping:
    toc_detection_sample.md     → input_step1.md
    toc.md                      → golden_step1.md
    toc_and_headings.md         → input_step3.md
    heading_processor.py        → golden_step3.py
    heading_expected_result.md  → golden_step3_expected.md
    heading_check_input.md      → input_step5.md
    heading_check_response.json → golden_step5.json
"""

import argparse
import shutil
from pathlib import Path

# Source → destination mapping
FILE_MAP: dict[str, str] = {
    "toc_detection_sample.md":     "input_step1.md",
    "toc.md":                      "golden_step1.md",
    "toc_and_headings.md":         "input_step3.md",
    "heading_processor.py":        "golden_step3.py",
    "heading_expected_result.md":  "golden_step3_expected.md",
    "heading_check_input.md":      "input_step5.md",
    "heading_check_response.json": "golden_step5.json",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy mathos-formatting artifacts to eval fixtures.",
    )
    parser.add_argument(
        "--work-dir",
        required=True,
        type=Path,
        help="Path to the mathos-formatting work directory.",
    )
    parser.add_argument(
        "--book",
        default="book1",
        help="Fixture subdirectory name (default: book1).",
    )
    args = parser.parse_args()

    work_dir: Path = args.work_dir.resolve()
    if not work_dir.is_dir():
        print(f"ERROR: work-dir does not exist: {work_dir}")
        raise SystemExit(1)

    # Determine output directory relative to this script
    script_dir = Path(__file__).resolve().parent
    out_dir = script_dir / args.book
    out_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for src_name, dst_name in FILE_MAP.items():
        src = work_dir / src_name
        dst = out_dir / dst_name
        if src.is_file():
            shutil.copy2(src, dst)
            print(f"  ✓ {src_name:40s} → {dst_name}")
            copied += 1
        else:
            print(f"  ✗ {src_name:40s}   (not found, skipped)")
            skipped += 1

    print(f"\nDone. Copied {copied}, skipped {skipped}.")
    print(f"Fixtures written to: {out_dir}")


if __name__ == "__main__":
    main()

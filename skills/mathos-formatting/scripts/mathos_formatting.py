"""CLI entrypoint for the MathOS adaptive Markdown formatting operator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


import mathos_formatting_core as core


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def command_inspect(args: argparse.Namespace) -> int:
    source = Path(args.markdown)
    markdown = source.read_text(encoding="utf-8")
    structure = core.extract_structure(markdown, str(source))
    _print_json(
        {
            "source_label": structure.source_label,
            "heading_count": len(structure.headings),
            "toc_found": structure.toc_block is not None,
            "heading_level_distribution": structure.heading_level_distribution,
            "heading_like_line_count": len(structure.heading_like_lines),
            "h1_section_count": len(structure.h1_sections),
            "protected_block_count": len(structure.protected_blocks),
        }
    )
    return 0


def command_apply_approved(args: argparse.Namespace) -> int:
    result = core.apply_approved_program(Path(args.program_dir), Path(args.markdown))
    _print_json(
        {
            "status": "candidate-written",
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "summary": result.summary,
            "warnings": result.warnings,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MathOS adaptive Markdown formatting operator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect Markdown structure without modifying files")
    inspect_parser.add_argument("markdown")
    inspect_parser.set_defaults(func=command_inspect)

    apply_parser = subparsers.add_parser("apply-approved", help="Apply an approved program to a fresh candidate backup")
    apply_parser.add_argument("program_dir")
    apply_parser.add_argument("markdown")
    apply_parser.set_defaults(func=command_apply_approved)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

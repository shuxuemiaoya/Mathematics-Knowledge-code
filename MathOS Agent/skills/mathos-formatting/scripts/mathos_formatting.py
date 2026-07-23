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
import mathos_provider as provider
from automation_runner import run_automated_formatting


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _self_check_actions(candidate_path: Path, report_path: Path) -> list[str]:
    actions = [
        f"Review candidate Markdown: {candidate_path}",
        f"Use the formatting report as review evidence: {report_path}",
        "If the candidate is acceptable, ask for explicit approval before replacing the source Markdown.",
        "If the candidate is not useful, discard it and rerun with a better prompt/sample.",
    ]
    return actions


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


def command_learn_from_provider(args: argparse.Namespace) -> int:
    settings = provider.load_provider_settings(Path(args.env))
    provider_client = provider.DeepSeekProviderClient(settings)
    heading_prompt = (SCRIPT_DIR.parent / "agents" / "step3_heading_processor_prompt.md").read_text(encoding="utf-8")
    result = core.run_learning_from_provider(
        markdown_path=Path(args.markdown),
        provider_client=provider_client,
        heading_prompt=heading_prompt,
        work_dir=Path(args.work_dir) if args.work_dir else None,
        timeout_seconds=args.timeout_seconds,
    )
    _print_json(
        {
            "status": result.status,
            "work_dir": str(result.work_dir),
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "summary": result.summary,
            "warnings": result.warnings,
            "errors": result.errors,
            "self_check_required": True,
            "next_actions": _self_check_actions(result.candidate_path, result.report_path),
        }
    )
    return 0


def command_run(args: argparse.Namespace) -> int:
    settings = provider.load_provider_settings(Path(args.env))
    provider_client = provider.DeepSeekProviderClient(settings)
    heading_prompt = (SCRIPT_DIR.parent / "agents" / "step3_heading_processor_prompt.md").read_text(encoding="utf-8")
    result = run_automated_formatting(
        markdown_path=Path(args.markdown),
        provider_client=provider_client,
        heading_prompt=heading_prompt,
        work_dir=Path(args.work_dir) if args.work_dir else None,
        timeout_seconds=args.timeout_seconds,
    )
    _print_json(result.digest)
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MathOS adaptive Markdown formatting operator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect Markdown structure without modifying files")
    inspect_parser.add_argument("markdown")
    inspect_parser.set_defaults(func=command_inspect)

    learn_parser = subparsers.add_parser("learn-from-provider", help="Learn heading artifacts through Step 5 validation")
    learn_parser.add_argument("markdown")
    learn_parser.add_argument("--env", required=True)
    learn_parser.add_argument("--work-dir")
    learn_parser.add_argument("--timeout-seconds", type=int, default=120)
    learn_parser.set_defaults(func=command_learn_from_provider)

    run_parser = subparsers.add_parser(
        "run",
        help="Run provider heading formatting through Step 5, recovery, self-checking, and final judgment",
    )
    run_parser.add_argument("markdown")
    run_parser.add_argument("--env", required=True)
    run_parser.add_argument("--work-dir")
    run_parser.add_argument("--timeout-seconds", type=int, default=120)
    run_parser.set_defaults(func=command_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

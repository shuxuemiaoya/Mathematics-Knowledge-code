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
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/mathos_formatting.py
        h1_index=args.h1_index,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/mathos_formatting.py
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
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/mathos_formatting.py
        h1_index=args.h1_index,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/mathos_formatting.py
    )
    _print_json(result.digest)
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MathOS adaptive Markdown formatting operator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect Markdown structure without modifying files")
    inspect_parser.add_argument("markdown")
    inspect_parser.set_defaults(func=command_inspect)

<<<<<<< Updated upstream:skills/mathos-formatting/scripts/mathos_formatting.py
    apply_parser = subparsers.add_parser("apply-approved", help="Apply an approved program to a fresh candidate backup")
    apply_parser.add_argument("program_dir")
    apply_parser.add_argument("markdown")
    apply_parser.set_defaults(func=command_apply_approved)

    candidate_parser = subparsers.add_parser(
        "candidate-from-artifacts",
        help="Create a fresh candidate backup from Python formatting artifacts",
    )
    candidate_parser.add_argument("markdown")
    candidate_parser.add_argument("--heading-script", help="Python Stage 1 artifact: heading_processor.py")
    candidate_parser.add_argument("--content-script", help="Python Stage 2 artifact: content_processor.py")
    candidate_parser.add_argument("--title-rewrite-map", help="Optional legacy Python artifact: title_rewrite_map.py")
    candidate_parser.add_argument("--heading-rules", help="Legacy JSON heading_rules.json")
    candidate_parser.add_argument("--content-rules", help="Legacy JSON content_rules.json")
    candidate_parser.add_argument("--plugin", help="Legacy Python content_cleaner.py")
    candidate_parser.add_argument("--heading-optimizations", help="Legacy JSON heading_optimizations.json")
    candidate_parser.set_defaults(func=command_candidate_from_artifacts)

    approve_parser = subparsers.add_parser("approve", help="Save a self-check-passing candidate result as a reusable program")
    approve_parser.add_argument("--approved-root", required=True)
    approve_parser.add_argument("--plugin-id", required=True)
    approve_parser.add_argument("--heading-script", help="Python Stage 1 artifact: heading_processor.py")
    approve_parser.add_argument("--content-script", help="Python Stage 2 artifact: content_processor.py")
    approve_parser.add_argument("--title-rewrite-map", help="Optional legacy Python artifact: title_rewrite_map.py")
    approve_parser.add_argument("--heading-rules", help="Legacy JSON heading_rules.json")
    approve_parser.add_argument("--content-rules", help="Legacy JSON content_rules.json")
    approve_parser.add_argument("--plugin", help="Legacy Python content_cleaner.py")
    approve_parser.add_argument("--original", required=True)
    approve_parser.add_argument("--candidate", required=True)
    approve_parser.add_argument("--summary", action="append", default=["self-check passed"])
    approve_parser.set_defaults(func=command_approve)

    learn_parser = subparsers.add_parser("learn-from-provider", help="Learn heading and content cleanup artifacts through DeepSeek")
=======
    learn_parser = subparsers.add_parser("learn-from-provider", help="Learn heading artifacts through Step 5 validation")
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/mathos_formatting.py
    learn_parser.add_argument("markdown")
    learn_parser.add_argument("--env", required=True)
    learn_parser.add_argument("--work-dir")
    learn_parser.add_argument("--timeout-seconds", type=int, default=120)
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/mathos_formatting.py
    learn_parser.add_argument("--h1-index", type=int, default=0)
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/mathos_formatting.py
    learn_parser.set_defaults(func=command_learn_from_provider)

    run_parser = subparsers.add_parser(
        "run",
        help="Run provider formatting, recovery, self-checking, and final judgment",
    )
    run_parser.add_argument("markdown")
    run_parser.add_argument("--env", required=True)
    run_parser.add_argument("--work-dir")
    run_parser.add_argument("--timeout-seconds", type=int, default=120)
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/mathos_formatting.py
    run_parser.add_argument("--h1-index", type=int, default=0)
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/mathos_formatting.py
    run_parser.set_defaults(func=command_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

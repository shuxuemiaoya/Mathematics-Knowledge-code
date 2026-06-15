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


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _review_actions(candidate_path: Path, report_path: Path, approve_command: str | None = None) -> list[str]:
    actions = [
        f"Review the candidate Markdown: {candidate_path}",
        f"Review the formatting report: {report_path}",
        "If the format needs improvement, revise the JSON content rules or rerun learn-from-provider with a better prompt/sample.",
    ]
    if approve_command:
        actions.append(f"If satisfied, save the format modification template: {approve_command}")
    else:
        actions.append("If satisfied, run approve with the heading rules and content_rules.json to save the format modification template.")
    actions.append("If not useful, discard the candidate and mathos-formatting work directory.")
    return actions


def _artifact_path(args: argparse.Namespace, name: str) -> Path | None:
    value = getattr(args, name)
    return Path(value) if value else None


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
            "review_required": True,
            "next_actions": _review_actions(result.candidate_path, result.report_path),
        }
    )
    return 0


def command_candidate_from_artifacts(args: argparse.Namespace) -> int:
    plugin_path = _artifact_path(args, "plugin")
    content_rules_path = _artifact_path(args, "content_rules")
    result = core.run_candidate_from_artifacts(
        markdown_path=Path(args.markdown),
        heading_rules_path=Path(args.heading_rules),
        plugin_path=plugin_path,
        content_rules_path=content_rules_path,
    )
    if hasattr(args, "heading_optimizations") and args.heading_optimizations:
        opt_path = Path(args.heading_optimizations)
        if opt_path.exists():
            candidate_path = result.candidate_path
            cleaned = candidate_path.read_text(encoding="utf-8")
            opt_mapping = json.loads(opt_path.read_text(encoding="utf-8"))
            opt_lines = cleaned.splitlines()
            for idx, l in enumerate(opt_lines):
                stripped = l.strip()
                if stripped in opt_mapping:
                    opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
            candidate_path.write_text("\n".join(opt_lines) + "\n", encoding="utf-8")
    approve_template = (
        "python skills/mathos-formatting/scripts/mathos_formatting.py approve "
        "--approved-root <approved_root> --plugin-id <plugin_id> "
        f"--heading-rules {Path(args.heading_rules)} "
        f"{'--content-rules ' + str(content_rules_path) if content_rules_path else '--plugin ' + str(plugin_path)} "
        f"--original {Path(args.markdown)} --candidate {result.candidate_path}"
    )
    _print_json(
        {
            "status": "candidate-written",
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "summary": result.summary,
            "warnings": result.warnings,
            "review_required": True,
            "next_actions": _review_actions(result.candidate_path, result.report_path, approve_template),
        }
    )
    return 0


def command_approve(args: argparse.Namespace) -> int:
    heading_rules_path = Path(args.heading_rules)
    heading_rules = json.loads(heading_rules_path.read_text(encoding="utf-8"))
    plugin_path = _artifact_path(args, "plugin")
    content_rules_path = _artifact_path(args, "content_rules")
    
    candidate = Path(args.candidate)
    work_dir = candidate.parent
    opt_src = work_dir / "heading_optimizations.json"
    
    program_dir = core.save_approved_program(
        approved_root=Path(args.approved_root),
        plugin_id=args.plugin_id,
        heading_rules=heading_rules,
        plugin_path=plugin_path,
        content_rules_path=content_rules_path,
        original_path=Path(args.original),
        candidate_path=candidate,
        approving_source_path=Path(args.original),
        operations_summary=args.summary,
    )
    if opt_src.exists():
        import shutil
        shutil.copy2(opt_src, program_dir / "heading_optimizations.json")
    _print_json(
        {
            "status": "approved",
            "program_dir": str(program_dir),
            "review_required": False,
            "next_actions": [
                f"Reuse this approved template with apply-approved: {program_dir}",
                "Keep the approved template manual-only until enough reviewed runs justify broader automation.",
            ],
        }
    )
    return 0


def command_learn_from_provider(args: argparse.Namespace) -> int:
    settings = provider.load_provider_settings(Path(args.env))
    provider_client = provider.DeepSeekProviderClient(settings)
    heading_prompt = (SCRIPT_DIR.parent / "agents" / "heading_rules_prompt.md").read_text(encoding="utf-8")
    content_prompt = (SCRIPT_DIR.parent / "agents" / "content_cleaner_prompt.md").read_text(encoding="utf-8")
    result = core.run_learning_from_provider(
        markdown_path=Path(args.markdown),
        provider_client=provider_client,
        heading_prompt=heading_prompt,
        content_prompt=content_prompt,
        work_dir=Path(args.work_dir) if args.work_dir else None,
        timeout_seconds=args.timeout_seconds,
        h1_index=args.h1_index,
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
            "review_required": True,
            "next_actions": _review_actions(
                result.candidate_path,
                result.report_path,
                (
                    "python skills/mathos-formatting/scripts/mathos_formatting.py approve "
                    "--approved-root <approved_root> --plugin-id <plugin_id> "
                    f"--heading-rules {result.artifacts.get('heading_rules')} "
                    f"--content-rules {result.artifacts.get('content_rules')} "
                    f"--original {Path(args.markdown)} --candidate {result.candidate_path}"
                ),
            ),
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

    candidate_parser = subparsers.add_parser(
        "candidate-from-artifacts",
        help="Create a fresh candidate backup from heading rules and JSON content rules or a legacy plugin",
    )
    candidate_parser.add_argument("markdown")
    candidate_parser.add_argument("--heading-rules", required=True)
    candidate_parser.add_argument("--content-rules")
    candidate_parser.add_argument("--plugin")
    candidate_parser.add_argument("--heading-optimizations")
    candidate_parser.set_defaults(func=command_candidate_from_artifacts)

    approve_parser = subparsers.add_parser("approve", help="Save an approved candidate result as a reusable program")
    approve_parser.add_argument("--approved-root", required=True)
    approve_parser.add_argument("--plugin-id", required=True)
    approve_parser.add_argument("--heading-rules", required=True)
    approve_parser.add_argument("--content-rules")
    approve_parser.add_argument("--plugin")
    approve_parser.add_argument("--original", required=True)
    approve_parser.add_argument("--candidate", required=True)
    approve_parser.add_argument("--summary", action="append", default=["user approved candidate result"])
    approve_parser.set_defaults(func=command_approve)

    learn_parser = subparsers.add_parser("learn-from-provider", help="Learn heading and content cleanup artifacts through DeepSeek")
    learn_parser.add_argument("markdown")
    learn_parser.add_argument("--env", required=True)
    learn_parser.add_argument("--work-dir")
    learn_parser.add_argument("--timeout-seconds", type=int, default=120)
    learn_parser.add_argument("--h1-index", type=int, default=0)
    learn_parser.set_defaults(func=command_learn_from_provider)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

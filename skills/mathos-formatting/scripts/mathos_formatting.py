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


def _self_check_actions(candidate_path: Path, report_path: Path, approve_command: str | None = None) -> list[str]:
    actions = [
        f"Run self-check on candidate Markdown: {candidate_path}",
        f"Use the formatting report for self-check evidence: {report_path}",
        "If self-check fails, revise the Python artifacts or rerun learn-from-provider with a better prompt/sample.",
    ]
    if approve_command:
        actions.append(f"If self-check passes, save the format modification template: {approve_command}")
    else:
        actions.append("If self-check passes, run approve with heading_processor.py and content_processor.py to save the format modification template.")
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
            "self_check_required": True,
            "next_actions": _self_check_actions(result.candidate_path, result.report_path),
        }
    )
    return 0


def command_candidate_from_artifacts(args: argparse.Namespace) -> int:
    heading_script_path = _artifact_path(args, "heading_script")
    content_script_path = _artifact_path(args, "content_script")
    title_rewrite_map_path = _artifact_path(args, "title_rewrite_map")
    plugin_path = _artifact_path(args, "plugin")
    content_rules_path = _artifact_path(args, "content_rules")
    opt_path = _artifact_path(args, "heading_optimizations")
    heading_rules_path = _artifact_path(args, "heading_rules")
    result = core.run_candidate_from_artifacts(
        markdown_path=Path(args.markdown),
        heading_script_path=heading_script_path,
        content_script_path=content_script_path,
        title_rewrite_map_path=title_rewrite_map_path,
        heading_rules_path=heading_rules_path,
        plugin_path=plugin_path,
        content_rules_path=content_rules_path,
        heading_optimizations_path=opt_path,
    )
    if heading_script_path and content_script_path:
        artifact_args = (
            f"--heading-script {heading_script_path} "
            f"--content-script {content_script_path} "
            f"{'--title-rewrite-map ' + str(title_rewrite_map_path) + ' ' if title_rewrite_map_path else ''}"
        )
    elif heading_rules_path:
        artifact_args = (
            f"--heading-rules {heading_rules_path} "
            f"{'--content-rules ' + str(content_rules_path) if content_rules_path else '--plugin ' + str(plugin_path)} "
        )
    else:
        artifact_args = ""
    approve_template = (
        "python skills/mathos-formatting/scripts/mathos_formatting.py approve "
        "--approved-root <approved_root> --plugin-id <plugin_id> "
        f"{artifact_args}"
        f"--original {Path(args.markdown)} --candidate {result.candidate_path}"
    )
    _print_json(
        {
            "status": "candidate-written",
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "summary": result.summary,
            "warnings": result.warnings,
            "self_check_required": True,
            "next_actions": _self_check_actions(result.candidate_path, result.report_path, approve_template),
        }
    )
    return 0


def command_approve(args: argparse.Namespace) -> int:
    heading_script_path = _artifact_path(args, "heading_script")
    content_script_path = _artifact_path(args, "content_script")
    title_rewrite_map_path = _artifact_path(args, "title_rewrite_map")
    heading_rules_path = _artifact_path(args, "heading_rules")
    heading_rules = None
    if heading_rules_path is not None:
        heading_rules = json.loads(heading_rules_path.read_text(encoding="utf-8"))
    plugin_path = _artifact_path(args, "plugin")
    content_rules_path = _artifact_path(args, "content_rules")
    candidate = Path(args.candidate)
    program_dir = core.save_approved_program(
        approved_root=Path(args.approved_root),
        plugin_id=args.plugin_id,
        heading_script_path=heading_script_path,
        content_script_path=content_script_path,
        title_rewrite_map_path=title_rewrite_map_path,
        heading_rules=heading_rules,
        plugin_path=plugin_path,
        content_rules_path=content_rules_path,
        original_path=Path(args.original),
        candidate_path=candidate,
        approving_source_path=Path(args.original),
        operations_summary=args.summary,
    )
    _print_json(
        {
            "status": "approved",
            "program_dir": str(program_dir),
            "self_check_required": False,
            "next_actions": [
                f"Reuse this approved template with apply-approved: {program_dir}",
                "Keep the approved Python artifacts self-check-only until enough successful runs justify broader automation.",
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
            "self_check_required": True,
            "next_actions": _self_check_actions(
                result.candidate_path,
                result.report_path,
                (
                    "python skills/mathos-formatting/scripts/mathos_formatting.py approve "
                    "--approved-root <approved_root> --plugin-id <plugin_id> "
                    f"--heading-script {result.artifacts.get('heading_script')} "
                    f"--content-script {result.artifacts.get('content_script')} "
                    f"--title-rewrite-map {result.artifacts.get('title_rewrite_map')} "
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
        help="Create a fresh candidate backup from Python formatting artifacts",
    )
    candidate_parser.add_argument("markdown")
    candidate_parser.add_argument("--heading-script", help="Python Stage 1 artifact: heading_processor.py")
    candidate_parser.add_argument("--content-script", help="Python Stage 4 artifact: content_processor.py")
    candidate_parser.add_argument("--title-rewrite-map", help="Optional Python Stage 5 artifact: title_rewrite_map.py")
    candidate_parser.add_argument("--heading-rules", help="Legacy JSON heading_rules.json")
    candidate_parser.add_argument("--content-rules", help="Legacy JSON content_rules.json")
    candidate_parser.add_argument("--plugin", help="Legacy Python content_cleaner.py")
    candidate_parser.add_argument("--heading-optimizations", help="Legacy JSON heading_optimizations.json")
    candidate_parser.set_defaults(func=command_candidate_from_artifacts)

    approve_parser = subparsers.add_parser("approve", help="Save a self-check-passing candidate result as a reusable program")
    approve_parser.add_argument("--approved-root", required=True)
    approve_parser.add_argument("--plugin-id", required=True)
    approve_parser.add_argument("--heading-script", help="Python Stage 1 artifact: heading_processor.py")
    approve_parser.add_argument("--content-script", help="Python Stage 4 artifact: content_processor.py")
    approve_parser.add_argument("--title-rewrite-map", help="Optional Python Stage 5 artifact: title_rewrite_map.py")
    approve_parser.add_argument("--heading-rules", help="Legacy JSON heading_rules.json")
    approve_parser.add_argument("--content-rules", help="Legacy JSON content_rules.json")
    approve_parser.add_argument("--plugin", help="Legacy Python content_cleaner.py")
    approve_parser.add_argument("--original", required=True)
    approve_parser.add_argument("--candidate", required=True)
    approve_parser.add_argument("--summary", action="append", default=["self-check passed"])
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

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .answers import apply_matches, plan_matches
from .audit import audit_graph
from .canvas import build_canvas
from .common import ConfigurationError, load_json, load_profile, require_reviewed_adapter, write_json_atomic, write_text_atomic
from .content import apply_content, plan_content
from .formatting import standardize_corpus
from .hierarchy import apply_hierarchy, plan_hierarchy
from .inventory import build_inventory
from .mineru import convert as convert_pdf
from .profile import create_profile
from .runtime import artifacts_current, init_state, status_state, update_stage


def artifact_paths(profile: dict[str, Any]) -> dict[str, Path]:
    staging = Path(profile["paths"]["staging_root"])
    graph = Path(profile["paths"]["graph_root"])
    return {
        "inventory": Path(profile["format"]["inventory"]),
        "adapter": Path(profile["format"]["adapter"]),
        "state": staging / "pipeline-state.json",
        "hierarchy": staging / "hierarchy-manifest.json",
        "hierarchy_coverage": staging / "hierarchy-coverage-manifest.json",
        "content": staging / "question-type-manifest.json",
        "content_application": staging / "content-application-report.json",
        "answers": staging / "answer-match-manifest.json",
        "formatting": staging / "markdown-standardization-report.json",
        "graph_manifest": staging / "graph-manifest.json",
        "canvas": graph / f"{profile['title']}.canvas",
        "audit": staging / "final-audit-report.json",
    }


def ensure_raw_sources(profile_path: Path, profile: dict[str, Any], args: argparse.Namespace) -> None:
    for source in profile["sources"]:
        raw = Path(source["markdown_path"])
        if raw.is_file():
            continue
        if source["kind"] == "md":
            write_text_atomic(raw, Path(source["path"]).read_text(encoding="utf-8-sig"), overwrite=False)
            continue
        if args.skip_conversion:
            raise ConfigurationError(f"Converted Markdown is missing for role {source['role']}: {raw}")
        conversion_args = SimpleNamespace(
            output=None,
            report=str(Path(profile["paths"]["staging_root"]) / f"{source['role']}-conversion-report.json"),
            env_file=args.env_file,
            base_url=args.base_url,
            language=args.mineru_language,
            poll_interval=args.poll_interval,
            max_polls=args.max_polls,
            request_timeout=args.request_timeout,
            overwrite=args.overwrite,
        )
        convert_pdf(profile_path, source["role"], conversion_args)


def _run_pipeline(profile_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    profile_path = profile_path.resolve()
    profile = load_profile(profile_path)
    paths = artifact_paths(profile)
    Path(profile["paths"]["staging_root"]).mkdir(parents=True, exist_ok=True)
    if not paths["state"].exists():
        init_state(profile_path, paths["state"])
    update_stage(paths["state"], "pdf-conversion", "running")
    ensure_raw_sources(profile_path, profile, args)
    conversion_artifacts = [Path(source["markdown_path"]) for source in profile["sources"]]
    conversion_artifacts.extend(
        Path(profile["paths"]["staging_root"]) / f"{source['role']}-conversion-report.json"
        for source in profile["sources"] if source.get("kind") == "pdf"
    )
    update_stage(paths["state"], "pdf-conversion", "completed", conversion_artifacts)

    update_stage(paths["state"], "format-inventory", "running")
    inventory = build_inventory(profile_path)
    write_json_atomic(paths["inventory"], inventory, overwrite=True)
    if not paths["adapter"].is_file():
        update_stage(paths["state"], "format-inventory", "review_required", [paths["inventory"]], "Create and review format-adapter.json")
        return {"schema_version": 1, "status": "review_required", "next_stage": "format-adapter-review", "inventory": str(paths["inventory"]), "adapter": str(paths["adapter"])}
    require_reviewed_adapter(profile, paths["adapter"])
    update_stage(paths["state"], "format-inventory", "completed", [paths["inventory"], paths["adapter"]])

    hierarchy_required = [paths["adapter"], paths["hierarchy"], paths["hierarchy_coverage"]]
    hierarchy_reused = artifacts_current(paths["state"], "hierarchy-segmentation", hierarchy_required)
    if hierarchy_reused:
        hierarchy = load_json(paths["hierarchy"])
    else:
        update_stage(paths["state"], "hierarchy-segmentation", "running")
        hierarchy = plan_hierarchy(profile_path, paths["adapter"])
        write_json_atomic(paths["hierarchy"], hierarchy, overwrite=True)
        if hierarchy["status"] != "passed":
            update_stage(paths["state"], "hierarchy-segmentation", "review_required", [paths["adapter"], paths["hierarchy"]])
            return {"schema_version": 1, "status": "review_required", "next_stage": "hierarchy-review", "manifest": str(paths["hierarchy"])}
        apply_hierarchy(profile_path, paths["adapter"], paths["hierarchy"], args.overwrite)
        update_stage(paths["state"], "hierarchy-segmentation", "completed", hierarchy_required)

    content_required = [paths["adapter"], paths["content"], paths["content_application"]]
    content_reused = hierarchy_reused and artifacts_current(paths["state"], "content-segmentation", content_required)
    if content_reused:
        content = load_json(paths["content"])
    else:
        update_stage(paths["state"], "content-segmentation", "running")
        content = plan_content(profile_path, paths["adapter"], paths["hierarchy_coverage"])
        write_json_atomic(paths["content"], content, overwrite=True)
        if content["status"] != "passed":
            update_stage(paths["state"], "content-segmentation", "review_required", [paths["adapter"], paths["content"]])
            return {"schema_version": 1, "status": "review_required", "next_stage": "content-review", "manifest": str(paths["content"])}
        apply_content(profile_path, paths["adapter"], paths["content"], args.overwrite)
        update_stage(paths["state"], "content-segmentation", "completed", content_required)

    update_stage(paths["state"], "answer-matching", "running")
    if paths["answers"].is_file() and load_json(paths["answers"]).get("status") == "passed":
        answers = load_json(paths["answers"])
    else:
        answers = plan_matches(profile_path, paths["adapter"], paths["content"])
        write_json_atomic(paths["answers"], answers, overwrite=True)
    if answers["status"] != "passed":
        update_stage(paths["state"], "answer-matching", "review_required", [paths["answers"]])
        return {"schema_version": 1, "status": "review_required", "next_stage": "answer-review", "manifest": str(paths["answers"])}
    apply_matches(profile_path, paths["answers"], args.overwrite)
    update_stage(paths["state"], "answer-matching", "completed", [paths["answers"]])

    update_stage(paths["state"], "markdown-standardization", "running")
    formatting = standardize_corpus(profile_path)
    write_json_atomic(paths["formatting"], formatting, overwrite=True)
    update_stage(paths["state"], "markdown-standardization", "completed", [paths["formatting"]])

    if profile.get("canvas", {}).get("enabled"):
        update_stage(paths["state"], "canvas", "running")
        build_canvas(profile_path, paths["hierarchy"], paths["content"], paths["graph_manifest"], paths["canvas"], args.overwrite)
        update_stage(paths["state"], "canvas", "completed", [paths["graph_manifest"], paths["canvas"]])
    else:
        update_stage(paths["state"], "canvas", "skipped", message="Canvas disabled in profile")

    update_stage(paths["state"], "final-audit", "running")
    audit = audit_graph(profile_path, paths["hierarchy_coverage"], paths["content"], paths["answers"], paths["canvas"] if profile.get("canvas", {}).get("enabled") else None)
    write_json_atomic(paths["audit"], audit, overwrite=True)
    update_stage(paths["state"], "final-audit", "completed" if audit["status"] == "passed" else "failed", [paths["audit"]])
    return {**audit, "pipeline_state": str(paths["state"]), "graph_root": profile["paths"]["graph_root"]}


def run_pipeline(profile_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    try:
        return _run_pipeline(profile_path, args)
    except Exception as exc:
        try:
            profile = load_profile(profile_path.resolve())
            state_path = artifact_paths(profile)["state"]
            if state_path.is_file():
                state = load_json(state_path)
                running = [name for name, record in state.get("stages", {}).items() if record.get("status") == "running"]
                if running:
                    update_stage(state_path, running[-1], "failed", message=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("profile", type=Path)
    parser.add_argument("--skip-conversion", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--env-file", default="/Users/oven/Documents/Mathematics-Knowledge-code/.env")
    parser.add_argument("--base-url")
    parser.add_argument("--mineru-language")
    parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--request-timeout", type=float, default=120.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coordinate the standalone Question Type Graph pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--source", action="append", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--staging-root", type=Path, required=True)
    init.add_argument("--vault-root", type=Path, required=True)
    init.add_argument("--graph-root", type=Path, required=True)
    init.add_argument("--language", default="zh-CN")
    init.add_argument("--answers-mode", choices=["separate", "embedded", "unavailable"])
    init.add_argument("--canvas", action="store_true")
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--overwrite", action="store_true")
    inventory = sub.add_parser("inventory-format")
    inventory.add_argument("profile", type=Path)
    inventory.add_argument("--output", type=Path)
    inventory.add_argument("--overwrite", action="store_true")
    for command in ("run", "resume"):
        add_run_arguments(sub.add_parser(command))
    status = sub.add_parser("status")
    status.add_argument("profile", type=Path)
    audit = sub.add_parser("audit")
    audit.add_argument("profile", type=Path)
    audit.add_argument("--output", type=Path)
    audit.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            profile = create_profile(args.source, args.title, args.staging_root, args.vault_root, args.graph_root, args.language, args.answers_mode, args.canvas)
            write_json_atomic(args.output, profile, overwrite=args.overwrite)
            result = {"schema_version": 1, "status": "completed", "profile": str(args.output.resolve())}
        elif args.command == "inventory-format":
            profile = load_profile(args.profile)
            output = args.output or Path(profile["format"]["inventory"])
            result = build_inventory(args.profile)
            write_json_atomic(output, result, overwrite=args.overwrite)
        elif args.command in {"run", "resume"}:
            result = run_pipeline(args.profile, args)
        elif args.command == "status":
            profile = load_profile(args.profile)
            result = status_state(artifact_paths(profile)["state"])
        else:
            profile = load_profile(args.profile)
            paths = artifact_paths(profile)
            result = audit_graph(args.profile, paths["hierarchy_coverage"], paths["content"], paths["answers"] if paths["answers"].exists() else None, paths["canvas"] if paths["canvas"].exists() else None)
            write_json_atomic(args.output or paths["audit"], result, overwrite=args.overwrite)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") not in {"failed"} else 1
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

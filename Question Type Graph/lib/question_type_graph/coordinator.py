from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .answers import apply_matches, plan_matches
from .audit import audit_graph
from .canvas import build_canvas
from .common import ConfigurationError, load_json, load_profile, require_reviewed_adapter, sha256_file, write_json_atomic, write_text_atomic
from .content import apply_content, plan_content
from .formatting import standardize_corpus
from .hierarchy import apply_hierarchy, plan_hierarchy
from .inventory import build_adapter_draft, build_inventory
from .mineru import DEFAULT_ENV_FILE, convert as convert_pdf
from .profile import create_profile
from .runtime import artifacts_current, init_state, input_fingerprint, status_state, update_stage
from .supplement import (
    apply_supplement,
    find_questions_requiring_supplement,
    has_substantive_reviewed_solution,
    plan_supplement,
)


def artifact_paths(profile: dict[str, Any]) -> dict[str, Path]:
    staging = Path(profile["paths"]["staging_root"])
    graph = Path(profile["paths"]["graph_root"])
    return {
        "inventory": Path(profile["format"]["inventory"]),
        "adapter": Path(profile["format"]["adapter"]),
        "adapter_draft": staging / "format-adapter.draft.json",
        "state": staging / "pipeline-state.json",
        "hierarchy": staging / "hierarchy-manifest.json",
        "hierarchy_coverage": staging / "hierarchy-coverage-manifest.json",
        "content": staging / "question-type-manifest.json",
        "content_application": staging / "content-application-report.json",
        "answers": staging / "answer-match-manifest.json",
        "answer_application": staging / "answer-application-report.json",
        "supplement_plan": staging / "supplemental-solutions-manifest.json",
        "supplement_application": staging / "supplemental-solution-application-report.json",
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


def stage_has_owned_outputs(state_path: Path, stage: str) -> bool:
    if not state_path.is_file():
        return False
    record = load_json(state_path).get("stages", {}).get(stage, {})
    return bool(record.get("artifacts"))


def _run_pipeline(profile_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    profile_path = profile_path.resolve()
    profile = load_profile(profile_path)
    paths = artifact_paths(profile)
    Path(profile["paths"]["staging_root"]).mkdir(parents=True, exist_ok=True)
    if not paths["state"].exists():
        init_state(profile_path, paths["state"])
    conversion_artifacts = [Path(source["markdown_path"]) for source in profile["sources"]]
    conversion_artifacts.extend(
        Path(profile["paths"]["staging_root"]) / f"{source['role']}-conversion-report.json"
        for source in profile["sources"] if source.get("kind") == "pdf"
    )
    conversion_fingerprint = input_fingerprint(
        [profile_path, *[Path(source["path"]) for source in profile["sources"]]],
        {"stage_contract": 2},
    )
    if not artifacts_current(paths["state"], "pdf-conversion", conversion_artifacts, conversion_fingerprint):
        update_stage(paths["state"], "pdf-conversion", "running", fingerprint=conversion_fingerprint)
        ensure_raw_sources(profile_path, profile, args)
        update_stage(
            paths["state"],
            "pdf-conversion",
            "completed",
            conversion_artifacts,
            fingerprint=conversion_fingerprint,
        )

    inventory_fingerprint = input_fingerprint([profile_path, *conversion_artifacts], {"stage_contract": 3})
    inventory_reused = artifacts_current(
        paths["state"], "format-inventory", [paths["inventory"]], inventory_fingerprint
    )
    if inventory_reused:
        inventory = load_json(paths["inventory"])
    else:
        update_stage(paths["state"], "format-inventory", "running", fingerprint=inventory_fingerprint)
        inventory = build_inventory(profile_path)
        write_json_atomic(paths["inventory"], inventory, overwrite=True)
    if not paths["adapter"].is_file():
        write_json_atomic(
            paths["adapter_draft"],
            build_adapter_draft(profile_path, inventory),
            overwrite=True,
        )
        update_stage(
            paths["state"],
            "format-inventory",
            "review_required",
            [paths["inventory"]],
            "Create and review format-adapter.json",
            inventory_fingerprint,
        )
        return {
            "schema_version": 1,
            "status": "review_required",
            "next_stage": "format-adapter-review",
            "inventory": str(paths["inventory"]),
            "adapter_draft": str(paths["adapter_draft"]),
            "adapter": str(paths["adapter"]),
        }
    require_reviewed_adapter(profile, paths["adapter"])
    if not inventory_reused:
        update_stage(
            paths["state"],
            "format-inventory",
            "completed",
            [paths["inventory"]],
            fingerprint=inventory_fingerprint,
        )

    hierarchy_required = [paths["hierarchy"], paths["hierarchy_coverage"]]
    if paths["hierarchy_coverage"].is_file():
        existing_coverage = load_json(paths["hierarchy_coverage"])
        hierarchy_required.extend(
            Path(item["content_source"])
            for item in existing_coverage.get("notes", [])
            if item.get("content_source")
        )
    hierarchy_fingerprint = input_fingerprint(
        [profile_path, paths["adapter"], *conversion_artifacts],
        {"stage_contract": 2},
    )
    hierarchy_reused = artifacts_current(
        paths["state"], "hierarchy-segmentation", hierarchy_required, hierarchy_fingerprint
    )
    if hierarchy_reused:
        hierarchy = load_json(paths["hierarchy"])
    else:
        update_stage(paths["state"], "hierarchy-segmentation", "running", fingerprint=hierarchy_fingerprint)
        hierarchy = plan_hierarchy(profile_path, paths["adapter"])
        write_json_atomic(paths["hierarchy"], hierarchy, overwrite=True)
        if hierarchy["status"] != "passed":
            update_stage(
                paths["state"],
                "hierarchy-segmentation",
                "review_required",
                [paths["hierarchy"]],
                fingerprint=hierarchy_fingerprint,
            )
            return {"schema_version": 1, "status": "review_required", "next_stage": "hierarchy-review", "manifest": str(paths["hierarchy"])}
        hierarchy_owned_overwrite = (
            args.overwrite
            or paths["hierarchy_coverage"].is_file()
            or stage_has_owned_outputs(paths["state"], "hierarchy-segmentation")
        )
        coverage = apply_hierarchy(
            profile_path, paths["adapter"], paths["hierarchy"], hierarchy_owned_overwrite
        )
        hierarchy_required.extend(
            Path(item["content_source"])
            for item in coverage.get("notes", [])
            if item.get("content_source")
        )
        update_stage(
            paths["state"],
            "hierarchy-segmentation",
            "completed",
            hierarchy_required,
            fingerprint=hierarchy_fingerprint,
        )

    content_required = [paths["content"], paths["content_application"]]
    hierarchy_coverage = load_json(paths["hierarchy_coverage"])
    content_inputs = [profile_path, paths["adapter"], paths["hierarchy"], paths["hierarchy_coverage"]]
    content_inputs.extend(
        Path(item["content_source"])
        for item in hierarchy_coverage.get("notes", [])
        if item.get("content_source")
    )
    content_fingerprint = input_fingerprint(content_inputs, {"stage_contract": 4})
    content_reused = hierarchy_reused and artifacts_current(
        paths["state"], "content-segmentation", content_required, content_fingerprint
    )
    if content_reused:
        content = load_json(paths["content"])
    else:
        update_stage(paths["state"], "content-segmentation", "running", fingerprint=content_fingerprint)
        content = plan_content(profile_path, paths["adapter"], paths["hierarchy_coverage"])
        write_json_atomic(paths["content"], content, overwrite=True)
        if content["status"] != "passed":
            update_stage(
                paths["state"],
                "content-segmentation",
                "review_required",
                [paths["content"]],
                fingerprint=content_fingerprint,
            )
            return {"schema_version": 1, "status": "review_required", "next_stage": "content-review", "manifest": str(paths["content"])}
        content_owned_overwrite = (
            args.overwrite
            or paths["content_application"].is_file()
            or stage_has_owned_outputs(paths["state"], "content-segmentation")
        )
        apply_content(profile_path, paths["adapter"], paths["content"], content_owned_overwrite)
        update_stage(
            paths["state"],
            "content-segmentation",
            "completed",
            content_required,
            fingerprint=content_fingerprint,
        )

    answer_inputs = [profile_path, paths["adapter"], paths["content"]]
    if profile.get("answers", {}).get("mode") != "unavailable":
        answer_role = "combined" if profile["answers"]["mode"] == "embedded" else "answers"
        answer_inputs.extend(
            Path(source["markdown_path"])
            for source in profile["sources"]
            if source.get("role") == answer_role
        )
    answer_fingerprint = input_fingerprint(answer_inputs, {"stage_contract": 6})
    answer_required = [paths["answers"], paths["answer_application"]]
    answer_reused = content_reused and artifacts_current(
        paths["state"], "answer-matching", answer_required, answer_fingerprint
    )
    if answer_reused:
        answers = load_json(paths["answers"])
    else:
        update_stage(paths["state"], "answer-matching", "running", fingerprint=answer_fingerprint)
        existing_answers = load_json(paths["answers"]) if paths["answers"].is_file() else {}
        manually_reviewed_current = bool(
            existing_answers.get("status") == "passed"
            and existing_answers.get("reviewer_confirmed") is True
            and existing_answers.get("adapter_sha256") == sha256_file(paths["adapter"])
            and existing_answers.get("content_manifest_sha256") == sha256_file(paths["content"])
            and (
                profile.get("answers", {}).get("mode") == "unavailable"
                or existing_answers.get("answer_markdown_sha256") == sha256_file(answer_inputs[-1])
            )
        )
        if manually_reviewed_current:
            answers = existing_answers
        else:
            answers = plan_matches(profile_path, paths["adapter"], paths["content"])
            write_json_atomic(paths["answers"], answers, overwrite=True)
    if answers["status"] != "passed":
        update_stage(
            paths["state"],
            "answer-matching",
            "review_required",
            [paths["answers"]],
            fingerprint=answer_fingerprint,
        )
        return {"schema_version": 1, "status": "review_required", "next_stage": "answer-review", "manifest": str(paths["answers"])}
    if not answer_reused:
        apply_matches(
            profile_path,
            paths["answers"],
            args.overwrite
            or paths["answer_application"].is_file()
            or stage_has_owned_outputs(paths["state"], "answer-matching"),
        )
        update_stage(
            paths["state"],
            "answer-matching",
            "completed",
            answer_required,
            fingerprint=answer_fingerprint,
        )

    if profile.get("answers", {}).get("mode") != "unavailable":
        supplement_candidates = find_questions_requiring_supplement(profile_path)
        supplement_required_ids = {
            str(item.get("question_id")) for item in supplement_candidates
        }
        supplemental_application = (
            load_json(paths["supplement_application"])
            if paths["supplement_application"].is_file()
            else {"questions": []}
        )
        supplemented_ids = {
            str(item.get("question_id"))
            for item in supplemental_application.get("questions", [])
            if item.get("answer_note_records")
        }
        unresolved_supplements = supplement_required_ids - supplemented_ids
        if unresolved_supplements:
            supplement_plan = plan_supplement(profile_path, paths["supplement_plan"])
            planned_questions = supplement_plan.get("questions", [])
            if planned_questions and all(
                has_substantive_reviewed_solution(item)
                for item in planned_questions
            ):
                adapter_data = load_json(paths["adapter"])
                supplement_result = apply_supplement(
                    profile_path,
                    paths["supplement_plan"],
                    callout_title=str(
                        adapter_data.get("answers", {}).get(
                            "supplement_callout_title", "AI生成解析"
                        )
                    ),
                )
                if supplement_result.get("status") != "completed":
                    return {
                        "schema_version": 1,
                        "status": "review_required",
                        "next_stage": "solution-supplement-review",
                        "manifest": str(paths["supplement_plan"]),
                        "unresolved_count": len(unresolved_supplements),
                    }
            else:
                update_stage(
                    paths["state"],
                    "solution-supplement",
                    "review_required",
                    [paths["supplement_plan"]],
                    message=f"{len(unresolved_supplements)} questions require reviewed solutions",
                )
                return {
                    "schema_version": 1,
                    "status": "review_required",
                    "next_stage": "solution-supplement-review",
                    "manifest": str(paths["supplement_plan"]),
                    "unresolved_count": len(unresolved_supplements),
                }
        supplement_status = load_json(paths["state"]).get("stages", {}).get("solution-supplement", {}).get("status")
        if not supplement_required_ids and supplement_status not in {"completed", "skipped"}:
            update_stage(
                paths["state"],
                "solution-supplement",
                "skipped",
                message="All questions have complete authoritative solutions",
            )
    else:
        supplement_status = load_json(paths["state"]).get("stages", {}).get("solution-supplement", {}).get("status")
        if supplement_status not in {"completed", "skipped"}:
            update_stage(
                paths["state"],
                "solution-supplement",
                "skipped",
                message="Answers are unavailable by profile design",
            )

    graph_markdown = sorted(Path(profile["paths"]["graph_root"]).rglob("*.md"))
    formatting_fingerprint = input_fingerprint(graph_markdown, {"stage_contract": 2})
    if not artifacts_current(
        paths["state"],
        "markdown-standardization",
        [paths["formatting"]],
        formatting_fingerprint,
    ):
        update_stage(paths["state"], "markdown-standardization", "running", fingerprint=formatting_fingerprint)
        formatting = standardize_corpus(profile_path)
        write_json_atomic(paths["formatting"], formatting, overwrite=True)
        graph_markdown = sorted(Path(profile["paths"]["graph_root"]).rglob("*.md"))
        formatting_fingerprint = input_fingerprint(graph_markdown, {"stage_contract": 2})
        update_stage(
            paths["state"],
            "markdown-standardization",
            "completed",
            [paths["formatting"]],
            fingerprint=formatting_fingerprint,
        )

    if profile.get("canvas", {}).get("enabled"):
        canvas_fingerprint = input_fingerprint(
            [profile_path, paths["hierarchy"], paths["content"]], {"stage_contract": 2}
        )
        canvas_required = [paths["graph_manifest"], paths["canvas"]]
        if not (content_reused and hierarchy_reused) or not artifacts_current(
            paths["state"], "canvas", canvas_required, canvas_fingerprint
        ):
            update_stage(paths["state"], "canvas", "running", fingerprint=canvas_fingerprint)
            canvas_owned_overwrite = (
                args.overwrite
                or any(path.is_file() for path in canvas_required)
                or stage_has_owned_outputs(paths["state"], "canvas")
            )
            build_canvas(
                profile_path,
                paths["hierarchy"],
                paths["content"],
                paths["graph_manifest"],
                paths["canvas"],
                canvas_owned_overwrite,
            )
            update_stage(
                paths["state"],
                "canvas",
                "completed",
                canvas_required,
                fingerprint=canvas_fingerprint,
            )
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
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
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
    init.add_argument("--format-preset", type=Path)
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
            profile = create_profile(
                args.source,
                args.title,
                args.staging_root,
                args.vault_root,
                args.graph_root,
                args.language,
                args.answers_mode,
                args.canvas,
                args.format_preset,
            )
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
        if result.get("status") == "review_required":
            return 2
        return 0 if result.get("status") != "failed" else 1
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import (
    ConfigurationError,
    load_json,
    pdf_page_count,
    sha256_file,
    write_json_atomic,
)


VALID_ROLES = {"questions", "answers", "combined"}


def parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ConfigurationError("--source must use ROLE=PATH")
    role, raw_path = value.split("=", 1)
    role = role.strip().casefold()
    if role not in VALID_ROLES:
        raise ConfigurationError(f"Unsupported source role: {role}")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in {".pdf", ".md"}:
        raise ConfigurationError(f"Source must be an existing PDF or Markdown file: {path}")
    return role, path


def create_profile(
    source_specs: list[str],
    title: str,
    staging_root: Path,
    vault_root: Path,
    graph_root: Path,
    language: str,
    answers_mode: str | None,
    canvas_enabled: bool,
    format_preset: Path | None = None,
) -> dict[str, Any]:
    parsed = [parse_source(value) for value in source_specs]
    roles = [role for role, _ in parsed]
    if roles.count("combined") and len(parsed) != 1:
        raise ConfigurationError("combined input cannot be mixed with separate sources")
    if not roles.count("combined") and roles.count("questions") != 1:
        raise ConfigurationError("separate input requires exactly one questions source")
    if roles.count("answers") > 1:
        raise ConfigurationError("v1 supports at most one answers source")
    inferred_answers_mode = (
        "embedded"
        if "combined" in roles
        else "separate"
        if "answers" in roles
        else "unavailable"
    )
    if answers_mode and answers_mode != inferred_answers_mode:
        raise ConfigurationError(
            f"answers mode {answers_mode!r} conflicts with source arrangement {inferred_answers_mode!r}"
        )
    staging_root = staging_root.expanduser().resolve()
    vault_root = vault_root.expanduser().resolve()
    graph_root = graph_root.expanduser().resolve()
    preset_meta = None
    if format_preset is not None:
        preset_path = format_preset.expanduser().resolve()
        load_json(preset_path)
        preset_meta = {"path": str(preset_path), "sha256": sha256_file(preset_path)}
    if staging_root == graph_root or graph_root in staging_root.parents:
        raise ConfigurationError("staging_root must be outside graph_root")
    try:
        graph_root.relative_to(vault_root)
    except ValueError as exc:
        raise ConfigurationError("graph_root must be inside vault_root for Obsidian embeds") from exc
    sources = []
    for role, path in parsed:
        sources.append(
            {
                "role": role,
                "path": str(path),
                "sha256": sha256_file(path),
                "kind": path.suffix.lower().lstrip("."),
                "page_count": pdf_page_count(path) if path.suffix.lower() == ".pdf" else None,
                "size_bytes": path.stat().st_size,
                "markdown_path": str(staging_root / "raw" / f"{role}.raw.md"),
            }
        )
    return {
        "schema_version": 1,
        "title": title,
        "language": language,
        "sources": sources,
        "paths": {
            "staging_root": str(staging_root),
            "vault_root": str(vault_root),
            "graph_root": str(graph_root),
        },
        "format": {
            "inventory": str(staging_root / "format-inventory.json"),
            "adapter": str(staging_root / "format-adapter.json"),
            "preset": preset_meta,
            "toc_authority": {"primary": None, "secondary_indexes": []},
            "label_to_role_mappings": [],
            "question_numbering": {"patterns": [], "restart_scopes": []},
            "layout_hints": {"classification": None, "reading_order": None},
        },
        "answers": {
            "mode": inferred_answers_mode,
            "completion_policy": "strict" if inferred_answers_mode != "unavailable" else "not-applicable",
            "regions": [],
            "matching_strategies": [
                "explicit-reference",
                "hierarchy-number",
                "source-page-number",
                "normalized-stem-exact",
            ] if inferred_answers_mode != "unavailable" else [],
        },
        "output": {
            "folder_layout": "adapter-controlled",
            "question_folder": "questions",
            "link_mode": "obsidian-embed",
            "embed_children": True,
            "list_prefix": None,
            "atomic_question_heading": False,
        },
        "canvas": {"enabled": canvas_enabled, "question_type_color": "6"},
        "knowledge_linking": {"status": "deferred", "enabled": False},
        "backup_policy": "none",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or validate a Question Type Graph profile.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("init")
    create.add_argument("--source", action="append", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--staging-root", type=Path, required=True)
    create.add_argument("--vault-root", type=Path, required=True)
    create.add_argument("--graph-root", type=Path, required=True)
    create.add_argument("--language", default="zh-CN")
    create.add_argument("--answers-mode", choices=["separate", "embedded", "unavailable"])
    create.add_argument("--canvas", action="store_true")
    create.add_argument("--format-preset", type=Path)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--overwrite", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("profile", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    from .common import load_profile

    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            profile = load_profile(args.profile)
            result = {"schema_version": 1, "status": "passed", "profile": profile["_profile_path"]}
        else:
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
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

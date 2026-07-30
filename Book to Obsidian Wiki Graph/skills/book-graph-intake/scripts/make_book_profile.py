#!/usr/bin/env python3
"""Create or validate a per-book conversion profile."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from inventory_book import inspect_source


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


TEXTBOOK_CATEGORIES = [
    {"role": "knowledge", "directory": "知识点", "enabled": True, "flat": False},
    {"role": "concept", "directory": "概念", "enabled": True, "flat": True},
    {"role": "exercise", "directory": "习题", "enabled": True, "flat": False},
]
TEXTBOOK_AUXILIARY_CATEGORIES = {
    "reading": {
        "role": "reading",
        "directory": "趣味阅读",
        "enabled": True,
        "flat": False,
    },
    "history": {
        "role": "history",
        "directory": "数学历史",
        "enabled": True,
        "flat": False,
    },
    "method": {
        "role": "method",
        "directory": "思维或方法",
        "enabled": True,
        "flat": False,
    },
    "tool": {
        "role": "tool",
        "directory": "工具",
        "enabled": True,
        "flat": False,
    },
}
GENERAL_CATEGORIES = [
    {"role": "content", "directory": "内容", "enabled": True, "flat": False},
]
NOTE_LINK_MODES = {"relative", "vault-root"}
BACKUP_POLICIES = {"none", "task-scoped"}
CALLOUT_BODY_MODES = {"quoted-body"}
REFERENCE_SCOPES = {"style-only", "same-book-content-and-style"}


def _vault_relative(book_root: Path, vault_root: Path) -> str:
    try:
        relative = book_root.relative_to(vault_root)
    except ValueError as exc:
        raise ValueError("book_root must be inside vault_root") from exc
    return "/" + relative.as_posix()


def create_profile(
    source: Path,
    vault_root: Path,
    book_root: Path,
    title: str,
    *,
    edition: str = "",
    language: str = "zh-CN",
    book_kind: str = "mathematics-textbook",
    staging_root: Path | None = None,
    textbook_aux_roles: list[str] | None = None,
    reference_corpus: Path | None = None,
    reference_scope: str = "style-only",
) -> dict[str, Any]:
    source = source.resolve()
    vault_root = vault_root.resolve()
    book_root = book_root.resolve()
    source_inventory = inspect_source(source)
    source_sha256 = source_inventory.get("sha256") or source_inventory.get(
        "tree_sha256"
    )
    if not source_sha256:
        raise ValueError("source inventory did not produce a stable hash")
    if staging_root is None:
        staging_root = (
            Path(tempfile.gettempdir())
            / "book-to-obsidian-wiki-graph"
            / book_root.name
        )
    is_textbook = "textbook" in book_kind.casefold()
    auxiliary_roles = list(dict.fromkeys(textbook_aux_roles or []))
    unknown_auxiliary_roles = sorted(
        set(auxiliary_roles) - set(TEXTBOOK_AUXILIARY_CATEGORIES)
    )
    if unknown_auxiliary_roles:
        raise ValueError(
            "unsupported textbook auxiliary roles: "
            + ", ".join(unknown_auxiliary_roles)
        )
    if auxiliary_roles and not is_textbook:
        raise ValueError("textbook auxiliary roles require a textbook book kind")
    categories = [
        dict(item)
        for item in (TEXTBOOK_CATEGORIES if is_textbook else GENERAL_CATEGORIES)
    ]
    categories.extend(
        dict(TEXTBOOK_AUXILIARY_CATEGORIES[role])
        for role in auxiliary_roles
    )

    profile: dict[str, Any] = {
        "schema_version": 1,
        "book": {
            "title": title,
            "edition": edition,
            "language": language,
            "kind": book_kind,
        },
        "source": {
            "path": str(source),
            "kind": source_inventory["kind"],
            "sha256": source_sha256,
        },
        "paths": {
            "vault_root": str(vault_root),
            "book_root": str(book_root),
            "staging_root": str(staging_root.resolve()),
        },
        "categories": categories,
        "links": {
            "note_mode": (
                "vault-root"
                if "textbook" in book_kind.casefold()
                else "relative"
            ),
            "canvas_mode": "vault-root",
            "asset_mode": "vault-root",
            "asset_base": _vault_relative(book_root, vault_root),
            "encode_spaces": True,
            "markdown_only": True,
        },
        "formatting": {
            "blank_before_top_level_callout": True,
            "callout_body_mode": "quoted-body",
            "callouts": {
                "lead_in": "info",
                "question": "question",
                "observe": "question",
                "think": "question",
                "explore": "question",
                "example": "example",
                "hint": "tip",
                "solution": "success",
                "warning": "warning",
                "conclusion": "summary",
                "quotation": "quote",
            },
        },
        "decomposition": {
            "preserve_source_order": True,
            "preserve_complete_source_blocks": True,
            "lesson_entry_is_ordered_index": True,
            "require_lesson_flow_manifest": True,
            "non_toc_split_default": "retain",
            "semantic_split_confidence_threshold": 0.9,
            "max_retained_teaching_block_nonblank_lines": 40,
        },
        "canvas": {
            "enabled": True,
            "node_colors": {
                "super_core": "1",
                "knowledge_or_concept": "2",
                "cross_domain": "3",
                "method": "4",
                "reading": "5",
                "question_type": "6",
                "tool": "#c800ff",
            },
            "edge_colors": {
                "reasoning": "2",
                "method_transfer": "4",
                "calculation": "5",
                "application": "6",
            },
        },
        "workspace": {"backup_policy": "none"},
    }
    if reference_corpus is not None:
        reference_corpus = reference_corpus.resolve()
        reference_inventory = inspect_source(reference_corpus)
        if reference_inventory.get("kind") != "directory":
            raise ValueError("reference_corpus must be a directory")
        if reference_scope not in REFERENCE_SCOPES:
            raise ValueError(
                "reference_scope must be style-only or "
                "same-book-content-and-style"
            )
        profile["reference"] = {
            "path": str(reference_corpus),
            "sha256": reference_inventory["tree_sha256"],
            "scope": reference_scope,
        }
    errors = profile_errors(profile)
    if errors:
        raise ValueError("; ".join(errors))
    return profile


def profile_errors(profile: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(profile, dict):
        return ["profile must be a JSON object"]
    if profile.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    for section in ("book", "source", "paths", "links", "workspace"):
        if not isinstance(profile.get(section), dict):
            errors.append(f"{section} must be an object")

    book = profile.get("book", {})
    if not str(book.get("title", "")).strip():
        errors.append("book.title is required")

    source = profile.get("source", {})
    if not str(source.get("path", "")).strip():
        errors.append("source.path is required")
    sha256 = str(source.get("sha256", ""))
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        errors.append("source.sha256 must be a lowercase SHA-256 digest")

    paths = profile.get("paths", {})
    for field in ("vault_root", "book_root", "staging_root"):
        if not str(paths.get(field, "")).strip():
            errors.append(f"paths.{field} is required")
    if paths.get("vault_root") and paths.get("book_root"):
        try:
            Path(paths["book_root"]).resolve().relative_to(
                Path(paths["vault_root"]).resolve()
            )
        except (TypeError, ValueError):
            errors.append("paths.book_root must be inside paths.vault_root")

    categories = profile.get("categories")
    enabled_categories: dict[str, str] = {}
    if not isinstance(categories, list):
        errors.append("categories must be an array")
    else:
        roles: set[str] = set()
        directories: set[str] = set()
        for index, item in enumerate(categories):
            if not isinstance(item, dict):
                errors.append(f"categories[{index}] must be an object")
                continue
            role = str(item.get("role", "")).strip()
            directory = str(item.get("directory", "")).strip()
            if not role:
                errors.append(f"categories[{index}].role is required")
            elif role in roles:
                errors.append(f"duplicate category role: {role}")
            roles.add(role)
            if item.get("enabled", True):
                if not directory:
                    errors.append(
                        f"categories[{index}].directory is required when enabled"
                    )
                elif directory in directories:
                    errors.append(f"duplicate category directory: {directory}")
                directories.add(directory)
                enabled_categories[role] = directory
    if "textbook" in str(book.get("kind", "")).casefold():
        required_textbook_categories = {
            "knowledge": "知识点",
            "concept": "概念",
            "exercise": "习题",
        }
        allowed_textbook_categories = {
            **required_textbook_categories,
            **{
                role: str(item["directory"])
                for role, item in TEXTBOOK_AUXILIARY_CATEGORIES.items()
            },
        }
        missing_or_changed = {
            role: directory
            for role, directory in required_textbook_categories.items()
            if enabled_categories.get(role) != directory
        }
        unsupported_or_changed = {
            role: directory
            for role, directory in enabled_categories.items()
            if allowed_textbook_categories.get(role) != directory
        }
        if missing_or_changed:
            errors.append(
                "textbook categories must include knowledge/知识点, "
                "concept/概念, and exercise/习题"
            )
        if unsupported_or_changed:
            errors.append(
                "textbook auxiliary categories must use the supported "
                "role/directory mappings"
            )

    links = profile.get("links", {})
    for field in ("note_mode", "canvas_mode", "asset_mode"):
        if links.get(field) not in NOTE_LINK_MODES:
            errors.append(f"links.{field} must be relative or vault-root")
    if not isinstance(links.get("markdown_only"), bool):
        errors.append("links.markdown_only must be boolean")

    formatting = profile.get("formatting", {})
    if not isinstance(formatting, dict):
        errors.append("formatting must be an object")
    elif formatting.get("callout_body_mode", "quoted-body") not in CALLOUT_BODY_MODES:
        errors.append(
            "formatting.callout_body_mode must be quoted-body"
        )

    decomposition = profile.get("decomposition", {})
    if not isinstance(decomposition, dict):
        errors.append("decomposition must be an object")
    else:
        if not isinstance(
            decomposition.get("require_lesson_flow_manifest", True),
            bool,
        ):
            errors.append(
                "decomposition.require_lesson_flow_manifest must be boolean"
            )
        if decomposition.get("non_toc_split_default", "retain") != "retain":
            errors.append("decomposition.non_toc_split_default must be retain")
        threshold = decomposition.get("semantic_split_confidence_threshold", 0.9)
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 <= threshold <= 1
        ):
            errors.append(
                "decomposition.semantic_split_confidence_threshold must be between 0 and 1"
            )
        max_retained = decomposition.get(
            "max_retained_teaching_block_nonblank_lines",
            40,
        )
        if (
            isinstance(max_retained, bool)
            or not isinstance(max_retained, int)
            or max_retained < 1
        ):
            errors.append(
                "decomposition.max_retained_teaching_block_nonblank_lines "
                "must be a positive integer"
            )

    reference = profile.get("reference")
    if reference is not None:
        if not isinstance(reference, dict):
            errors.append("reference must be an object")
        else:
            if not str(reference.get("path", "")).strip():
                errors.append("reference.path is required")
            reference_hash = str(reference.get("sha256", ""))
            if len(reference_hash) != 64 or any(
                char not in "0123456789abcdef" for char in reference_hash
            ):
                errors.append(
                    "reference.sha256 must be a lowercase SHA-256 digest"
                )
            if reference.get("scope") not in REFERENCE_SCOPES:
                errors.append(
                    "reference.scope must be style-only or "
                    "same-book-content-and-style"
                )

    workspace = profile.get("workspace", {})
    if workspace.get("backup_policy") not in BACKUP_POLICIES:
        errors.append("workspace.backup_policy must be none or task-scoped")
    return errors


def profile_location_errors(profile: dict[str, Any], profile_path: Path) -> list[str]:
    """Validate live identity facts that are inappropriate during creation."""

    errors: list[str] = []
    source_path = Path(str(profile.get("source", {}).get("path", ""))).resolve()
    if not source_path.exists():
        errors.append(f"source.path does not exist: {source_path}")
    vault_root = Path(
        str(profile.get("paths", {}).get("vault_root", ""))
    ).resolve()
    if not vault_root.is_dir():
        errors.append(f"paths.vault_root is not a directory: {vault_root}")
    staging_root = Path(
        str(profile.get("paths", {}).get("staging_root", ""))
    ).resolve()
    if profile_path.resolve().parent != staging_root:
        errors.append(
            "profile file is outside paths.staging_root; the run may have "
            "been moved or copied"
        )
    reference = profile.get("reference")
    if isinstance(reference, dict):
        reference_path = Path(str(reference.get("path", ""))).resolve()
        if not reference_path.is_dir():
            errors.append(
                f"reference.path is not a directory: {reference_path}"
            )
        else:
            reference_inventory = inspect_source(reference_path)
            if reference_inventory.get("tree_sha256") != reference.get("sha256"):
                errors.append(
                    "reference.sha256 does not match the current reference corpus"
                )
    return errors


def write_json_atomic(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"profile already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("source", type=Path)
    create.add_argument("--vault-root", type=Path, required=True)
    create.add_argument("--book-root", type=Path, required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--edition", default="")
    create.add_argument("--language", default="zh-CN")
    create.add_argument("--book-kind", default="mathematics-textbook")
    create.add_argument(
        "--textbook-aux-role",
        action="append",
        choices=sorted(TEXTBOOK_AUXILIARY_CATEGORIES),
        default=[],
        help=(
            "Enable a source-supported textbook side-material role; repeat for "
            "reading, history, method, or tool."
        ),
    )
    create.add_argument("--staging-root", type=Path)
    create.add_argument("--reference-corpus", type=Path)
    create.add_argument(
        "--reference-scope",
        choices=sorted(REFERENCE_SCOPES),
        default="style-only",
    )
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--overwrite", action="store_true")
    validate = subparsers.add_parser("validate")
    validate.add_argument("profile", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "create":
            profile = create_profile(
                args.source,
                args.vault_root,
                args.book_root,
                args.title,
                edition=args.edition,
                language=args.language,
                book_kind=args.book_kind,
                staging_root=args.staging_root,
                textbook_aux_roles=args.textbook_aux_role,
                reference_corpus=args.reference_corpus,
                reference_scope=args.reference_scope,
            )
            write_json_atomic(args.output.resolve(), profile, args.overwrite)
            result = {
                "status": "passed",
                "profile": str(args.output.resolve()),
                "source_sha256": profile["source"]["sha256"],
            }
        else:
            profile = json.loads(args.profile.read_text(encoding="utf-8"))
            errors = profile_errors(profile)
            if not errors:
                errors.extend(profile_location_errors(profile, args.profile))
            result = {
                "status": "passed" if not errors else "failed",
                "profile": str(args.profile.resolve()),
                "errors": errors,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

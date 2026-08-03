#!/usr/bin/env python3
"""Coordinate one book-graph run with strict handoffs and same-run recovery."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


SCHEMA_VERSION = 1
SHA256_LENGTH = 64
TEST_OPTIONS_FILENAME = "book-graph-test-options.json"
REVIEW_DECISIONS = {"accepted", "revised", "rejected"}
STAGE_NAMES = {
    "intake",
    "pdf-conversion",
    "markdown-registration",
    "toc-formatting",
    "toc-splitting",
    "concepts",
    "markdown-standardization",
    "pre-canvas-audit",
    "canvas",
    "final-audit",
}
PASS_STATUS_KINDS = {
    "toc-format-report",
    "lesson-flow-manifest",
    "markdown-report",
    "audit-report",
    "reference-parity-report",
    "canvas-style-report",
}
STAGE_AUDIT_NAMES = {
    "toc-splitting": "split",
    "concepts": "concepts",
    "markdown-standardization": "formatting",
    "pre-canvas-audit": "pre-canvas",
    "final-audit": "final",
}


class PipelineError(RuntimeError):
    pass


class SchemaError(PipelineError):
    pass


class IdentityError(PipelineError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_directory(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content_hash = bytes.fromhex(sha256_file(item))
        digest.update(content_hash)
    return digest.hexdigest()


def inventory_tree_sha256(path: Path) -> str:
    """Match the directory identity frozen by book-graph-intake."""

    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def sha256_path(path: Path) -> str:
    if path.is_file():
        return sha256_file(path)
    if path.is_dir():
        return sha256_directory(path)
    raise FileNotFoundError(f"artifact does not exist: {path}")


def path_is_within(path: Path, root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SchemaError(f"cannot read JSON {path}: {exc}") from exc


def write_json_atomic(path: Path, payload: Any, *, overwrite: bool = True) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {path}")
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


def nested(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def require_fields(
    payload: Any,
    *,
    kind: str,
    fields: dict[str, type | tuple[type, ...]],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"{kind}: root must be an object"]
    for field, expected_type in fields.items():
        value = nested(payload, field)
        if value is None:
            errors.append(f"{kind}: missing {field}")
        elif not isinstance(value, expected_type):
            type_names = (
                ", ".join(item.__name__ for item in expected_type)
                if isinstance(expected_type, tuple)
                else expected_type.__name__
            )
            errors.append(f"{kind}: {field} must be {type_names}")
    return errors


ARTIFACT_FIELDS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "file": {},
    "directory": {},
    "tree": {},
    "book-profile": {
        "schema_version": int,
        "book": dict,
        "source.path": str,
        "source.sha256": str,
        "paths.vault_root": str,
        "paths.book_root": str,
        "paths.staging_root": str,
        "categories": list,
    },
    "toc-manifest": {
        "schema_version": int,
        "profile": str,
        "source_sha256": str,
        "input_markdown_sha256": str,
        "toc_source_ranges": list,
        "entries": list,
    },
    "toc-format-report": {
        "schema_version": int,
        "stage": str,
        "status": str,
        "profile": str,
        "source_sha256": str,
        "input_markdown_sha256": str,
        "candidate_markdown_sha256": str,
        "matched": list,
        "demoted": list,
    },
    "split-manifest": {
        "schema_version": int,
        "profile": str,
        "source_sha256": str,
        "input_markdown_sha256": str,
        "semantic_review.headings": list,
        "nodes": list,
    },
    "lesson-flow-manifest": {
        "schema_version": int,
        "stage": str,
        "status": str,
        "profile": str,
        "source_sha256": str,
        "input_markdown_sha256": str,
        "split_manifest": str,
        "split_manifest_sha256": str,
        "lessons": list,
    },
    "coverage-manifest": {
        "schema_version": int,
        "profile": str,
        "source_sha256": str,
        "units": list,
    },
    "concept-manifest": {
        "schema_version": int,
        "profile": str,
        "source_sha256": str,
        "concepts": list,
    },
    "markdown-report": {
        "schema_version": int,
        "stage": str,
        "status": str,
        "profile": str,
        "source_sha256": str,
        "input_corpus_sha256": str,
        "output_corpus_sha256": str,
        "protected_invariants": dict,
        "files": list,
    },
    "graph-manifest": {
        "version": int,
        "profile": str,
        "source_sha256": str,
        "nodes": list,
        "edges": list,
    },
    "audit-report": {
        "schema_version": int,
        "stage": str,
        "status": str,
        "source.sha256": str,
        "profile": str,
        "counts": dict,
        "errors": list,
        "warnings": list,
    },
    "reference-parity-report": {
        "schema_version": int,
        "stage": str,
        "status": str,
        "profile": str,
        "source_sha256": str,
        "same_book": bool,
        "reference.path": str,
        "reference.sha256": str,
        "blocking_summary": dict,
    },
    "canvas-style-report": {
        "schema_version": int,
        "stage": str,
        "status": str,
        "profile": str,
        "source_sha256": str,
        "reference.path": str,
        "reference.sha256": str,
        "candidate.path": str,
        "candidate.sha256": str,
        "metrics": dict,
        "blocking_differences": list,
    },
    "review-queue": {
        "schema_version": int,
        "profile": str,
        "source_sha256": str,
        "threshold": (int, float),
        "items": list,
        "counts": dict,
    },
    "note-workplan": {
        "schema_version": int,
        "profile": str,
        "source_sha256": str,
        "workers": int,
        "jobs": list,
        "lanes": list,
    },
    "note-results": {
        "schema_version": int,
        "profile": str,
        "source_sha256": str,
        "workplan": str,
        "results": list,
        "metrics": dict,
    },
    "pipeline-state": {
        "schema_version": int,
        "profile": str,
        "source.path": str,
        "source.sha256": str,
        "staging_root": str,
        "status": str,
        "stages": list,
        "telemetry": dict,
    },
}


PROFILE_BOUND_KINDS = {
    "toc-manifest",
    "toc-format-report",
    "split-manifest",
    "lesson-flow-manifest",
    "coverage-manifest",
    "concept-manifest",
    "markdown-report",
    "graph-manifest",
    "audit-report",
    "reference-parity-report",
    "canvas-style-report",
    "review-queue",
    "note-workplan",
    "note-results",
    "pipeline-state",
}


def same_book_reference_review_errors(
    split_manifest: dict[str, Any],
    profile: dict[str, Any],
) -> list[str]:
    configured = profile.get("reference")
    if not (
        isinstance(configured, dict)
        and configured.get("scope") == "same-book-content-and-style"
    ):
        return []
    errors: list[str] = []
    semantic_review = split_manifest.get("semantic_review")
    reference_review = (
        semantic_review.get("reference")
        if isinstance(semantic_review, dict)
        else None
    )
    if not isinstance(reference_review, dict):
        return [
            "split-manifest: same-book reference requires adopted semantic review"
        ]
    if reference_review.get("status") != "passed":
        errors.append(
            "split-manifest: same-book reference semantic review must pass"
        )
    if reference_review.get("reviewer_confirmed") is not True:
        errors.append(
            "split-manifest: same-book reference semantic review needs reviewer confirmation"
        )
    try:
        review_path = Path(str(reference_review.get("path", ""))).resolve()
        configured_path = Path(str(configured.get("path", ""))).resolve()
    except (TypeError, ValueError):
        review_path = configured_path = None
    if review_path != configured_path:
        errors.append(
            "split-manifest: same-book reference semantic review path mismatch"
        )
    if reference_review.get("sha256") != configured.get("sha256"):
        errors.append(
            "split-manifest: same-book reference semantic review digest mismatch"
        )
    proposal = Path(str(reference_review.get("proposal_report", ""))).resolve()
    if not proposal.is_file():
        errors.append(
            "split-manifest: same-book reference semantic proposal report is missing"
        )
    elif reference_review.get("proposal_report_sha256") != sha256_file(
        proposal
    ):
        errors.append(
            "split-manifest: same-book reference semantic proposal digest mismatch"
        )
    ambiguous_count = reference_review.get("ambiguous_count", 0)
    resolved_count = reference_review.get("resolved_ambiguity_count", 0)
    if (
        not isinstance(ambiguous_count, int)
        or isinstance(ambiguous_count, bool)
        or ambiguous_count < 0
        or resolved_count != ambiguous_count
    ):
        errors.append(
            "split-manifest: same-book reference ambiguities are not completely resolved"
        )
    elif ambiguous_count:
        decision_report = Path(
            str(reference_review.get("decision_report", ""))
        ).resolve()
        if not decision_report.is_file():
            errors.append(
                "split-manifest: same-book reference ambiguity decision report is missing"
            )
        elif reference_review.get("decision_report_sha256") != sha256_file(
            decision_report
        ):
            errors.append(
                "split-manifest: same-book reference ambiguity decision digest mismatch"
            )
    return errors


def artifact_errors(
    payload: Any,
    kind: str,
    *,
    expected_profile: Path | None = None,
    expected_source_sha256: str | None = None,
) -> list[str]:
    if kind not in ARTIFACT_FIELDS:
        return [f"unknown artifact kind: {kind}"]
    errors = require_fields(payload, kind=kind, fields=ARTIFACT_FIELDS[kind])
    if errors or not isinstance(payload, dict):
        return errors

    version_field = "version" if kind == "graph-manifest" else "schema_version"
    if payload.get(version_field) != SCHEMA_VERSION:
        errors.append(f"{kind}: {version_field} must be {SCHEMA_VERSION}")

    source_hash = (
        nested(payload, "source.sha256")
        if kind in {"book-profile", "audit-report", "pipeline-state"}
        else payload.get("source_sha256")
    )
    if source_hash is not None and not is_sha256(source_hash):
        errors.append(f"{kind}: source SHA-256 is invalid")
    if expected_source_sha256 and source_hash != expected_source_sha256:
        errors.append(
            f"{kind}: source SHA-256 mismatch "
            f"(expected {expected_source_sha256}, got {source_hash})"
        )

    if kind in PROFILE_BOUND_KINDS and expected_profile is not None:
        raw_profile = payload.get("profile")
        try:
            resolved_profile = Path(raw_profile).resolve()
        except (TypeError, ValueError):
            resolved_profile = None
        if resolved_profile != expected_profile.resolve():
            errors.append(
                f"{kind}: profile mismatch "
                f"(expected {expected_profile.resolve()}, got {raw_profile})"
            )

    if kind == "toc-format-report" and payload.get("status") not in {
        "passed",
        "failed",
    }:
        errors.append("toc-format-report: status must be passed or failed")
    if kind == "split-manifest" and expected_profile is not None:
        try:
            profile_payload = read_json(expected_profile)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(
                "split-manifest: cannot load expected profile for reference validation "
                f"({type(exc).__name__})"
            )
        else:
            errors.extend(
                same_book_reference_review_errors(payload, profile_payload)
            )
    if kind == "coverage-manifest":
        source_keys: set[str] = set()
        source_orders: set[int] = set()
        for index, unit in enumerate(payload.get("units", [])):
            if not isinstance(unit, dict):
                errors.append(f"coverage-manifest: units[{index}] must be an object")
                continue
            for field in ("source_key", "status", "target"):
                if not isinstance(unit.get(field), str) or not unit[field]:
                    errors.append(
                        f"coverage-manifest: units[{index}].{field} is required"
                    )
            source_key = unit.get("source_key")
            if source_key in source_keys:
                errors.append(
                    f"coverage-manifest: duplicate source_key {source_key}"
                )
            elif isinstance(source_key, str):
                source_keys.add(source_key)
            source_order = unit.get("source_order")
            if not isinstance(source_order, int):
                errors.append(
                    f"coverage-manifest: units[{index}].source_order is required"
                )
            elif source_order in source_orders:
                errors.append(
                    f"coverage-manifest: duplicate source_order {source_order}"
                )
            else:
                source_orders.add(source_order)
            if unit.get("status") not in {"assigned", "retained"}:
                errors.append(
                    f"coverage-manifest: units[{index}].status is unresolved"
                )
    if kind == "lesson-flow-manifest":
        if payload.get("stage") != "lesson-flow-planning":
            errors.append("lesson-flow-manifest: stage is invalid")
        if payload.get("status") not in {"review_required", "passed", "failed"}:
            errors.append("lesson-flow-manifest: status is invalid")
        if not is_sha256(payload.get("input_markdown_sha256")):
            errors.append(
                "lesson-flow-manifest: input Markdown SHA-256 is invalid"
            )
        if not is_sha256(payload.get("split_manifest_sha256")):
            errors.append(
                "lesson-flow-manifest: split manifest SHA-256 is invalid"
            )
    if kind == "concept-manifest":
        targets: set[str] = set()
        for index, concept in enumerate(payload.get("concepts", [])):
            if not isinstance(concept, dict):
                errors.append(f"concept-manifest: concepts[{index}] must be an object")
                continue
            target = concept.get("target")
            linked_from = concept.get("linked_from")
            if not isinstance(target, str) or not target:
                errors.append(
                    f"concept-manifest: concepts[{index}].target is required"
                )
            elif target in targets:
                errors.append(f"concept-manifest: duplicate target {target}")
            else:
                targets.add(target)
            if not isinstance(linked_from, list) or not linked_from:
                errors.append(
                    f"concept-manifest: concepts[{index}].linked_from is required"
                )
    if kind == "markdown-report":
        if payload.get("status") not in {"passed", "failed"}:
            errors.append("markdown-report: status must be passed or failed")
        invariants = payload.get("protected_invariants", {})
        if not invariants or any(
            not isinstance(value, bool) for value in invariants.values()
        ):
            errors.append(
                "markdown-report: protected invariants must be booleans"
            )
        if payload.get("status") == "passed" and not all(invariants.values()):
            errors.append(
                "markdown-report: passed status requires all invariants"
            )
    if kind == "canvas-style-report":
        if payload.get("stage") != "canvas-style-parity":
            errors.append(
                "canvas-style-report: stage must be canvas-style-parity"
            )
        if payload.get("status") not in {
            "passed",
            "style_review_required",
            "failed",
        }:
            errors.append(
                "canvas-style-report: status must be passed, "
                "style_review_required, or failed"
            )
        if not is_sha256(nested(payload, "reference.sha256")):
            errors.append(
                "canvas-style-report: reference.sha256 must be a lowercase SHA-256 digest"
            )
        if not is_sha256(nested(payload, "candidate.sha256")):
            errors.append(
                "canvas-style-report: candidate.sha256 must be a lowercase SHA-256 digest"
            )
        if (
            payload.get("status") == "passed"
            and payload.get("blocking_differences")
        ):
            errors.append(
                "canvas-style-report: passed status requires no blocking differences"
            )
    if kind == "graph-manifest":
        node_keys: set[str] = set()
        for index, node in enumerate(payload.get("nodes", [])):
            if not isinstance(node, dict):
                errors.append(
                    f"graph-manifest: nodes[{index}] must be an object"
                )
                continue
            key = node.get("key")
            if not isinstance(key, str) or not key:
                errors.append(
                    f"graph-manifest: nodes[{index}].key is required"
                )
            elif key in node_keys:
                errors.append(f"graph-manifest: duplicate node key {key}")
            else:
                node_keys.add(key)
        edge_keys: set[str] = set()
        for index, edge in enumerate(payload.get("edges", [])):
            if not isinstance(edge, dict):
                errors.append(
                    f"graph-manifest: edges[{index}] must be an object"
                )
                continue
            key = edge.get("key")
            if key is not None:
                if not isinstance(key, str) or not key:
                    errors.append(
                        f"graph-manifest: edges[{index}].key is invalid"
                    )
                elif key in edge_keys:
                    errors.append(
                        f"graph-manifest: duplicate edge key {key}"
                    )
                else:
                    edge_keys.add(key)
            for endpoint in ("from", "to"):
                if edge.get(endpoint) not in node_keys:
                    errors.append(
                        f"graph-manifest: edges[{index}].{endpoint} "
                        "does not reference a node"
                    )
    if kind == "audit-report":
        if payload.get("status") not in {"passed", "failed"}:
            errors.append("audit-report: status must be passed or failed")
        if payload.get("stage") not in {
            "split",
            "concepts",
            "formatting",
            "pre-canvas",
            "final",
        }:
            errors.append("audit-report: stage is invalid")
        if payload.get("status") == "passed" and payload.get("errors"):
            errors.append("audit-report: passed status requires zero errors")
    if kind == "reference-parity-report":
        if payload.get("status") not in {
            "passed",
            "content_review_required",
            "architecture_only_required",
            "failed",
        }:
            errors.append("reference-parity-report: status is invalid")
        if payload.get("stage") != "reference-content-parity":
            errors.append("reference-parity-report: stage is invalid")
        reference_hash = nested(payload, "reference.sha256")
        if not is_sha256(reference_hash):
            errors.append("reference-parity-report: reference SHA-256 is invalid")
    if kind == "review-queue":
        errors.extend(review_queue_errors(payload))
    if kind == "note-workplan":
        errors.extend(note_workplan_errors(payload))
    if kind == "pipeline-state":
        errors.extend(pipeline_state_errors(payload))
    return errors


def validate_artifact(
    path: Path,
    kind: str,
    *,
    expected_profile: Path | None = None,
    expected_source_sha256: str | None = None,
) -> dict[str, Any]:
    path = path.resolve()
    if kind == "file":
        errors = [] if path.is_file() else [f"file artifact does not exist: {path}"]
        return {
            "status": "passed" if not errors else "failed",
            "kind": kind,
            "path": str(path),
            "sha256": sha256_file(path) if not errors else None,
            "errors": errors,
        }
    if kind in {"directory", "tree"}:
        errors = [] if path.is_dir() else [f"directory artifact does not exist: {path}"]
        return {
            "status": "passed" if not errors else "failed",
            "kind": kind,
            "path": str(path),
            "sha256": sha256_directory(path) if not errors else None,
            "errors": errors,
        }
    if not path.is_file():
        return {
            "status": "failed",
            "kind": kind,
            "path": str(path),
            "errors": [f"artifact does not exist: {path}"],
        }
    payload = read_json(path)
    errors = artifact_errors(
        payload,
        kind,
        expected_profile=expected_profile,
        expected_source_sha256=expected_source_sha256,
    )
    return {
        "status": "passed" if not errors else "failed",
        "kind": kind,
        "path": str(path),
        "sha256": sha256_file(path),
        "errors": errors,
    }


def load_profile(path: Path) -> tuple[Path, dict[str, Any]]:
    resolved = path.resolve()
    result = validate_artifact(resolved, "book-profile")
    if result["status"] != "passed":
        raise SchemaError("; ".join(result["errors"]))
    profile = read_json(resolved)
    source_path = Path(profile["source"]["path"]).resolve()
    if not source_path.is_file():
        raise IdentityError(f"profile source does not exist: {source_path}")
    actual_hash = sha256_file(source_path)
    if actual_hash != profile["source"]["sha256"]:
        raise IdentityError(
            "profile source hash does not match the current source artifact"
        )
    reference = profile.get("reference")
    if reference is not None:
        if not isinstance(reference, dict):
            raise SchemaError("profile reference must be an object")
        reference_path = Path(str(reference.get("path", ""))).resolve()
        if not reference_path.is_dir():
            raise IdentityError(
                f"profile reference corpus does not exist: {reference_path}"
            )
        if inventory_tree_sha256(reference_path) != reference.get("sha256"):
            raise IdentityError(
                "profile reference hash does not match the current reference corpus"
            )
    style_reference = profile.get("canvas", {}).get("style_reference")
    if style_reference is not None:
        if not isinstance(style_reference, dict):
            raise SchemaError("profile Canvas style reference must be an object")
        if style_reference.get("scope") != "same-series-style":
            raise SchemaError(
                "profile Canvas style reference scope must be same-series-style"
            )
        style_path = Path(str(style_reference.get("path", ""))).resolve()
        if not style_path.is_file() or style_path.suffix.casefold() != ".canvas":
            raise IdentityError(
                f"profile Canvas style reference does not exist: {style_path}"
            )
        if sha256_file(style_path) != style_reference.get("sha256"):
            raise IdentityError(
                "profile Canvas style reference hash does not match the current file"
            )
    return resolved, profile


def artifact_record(kind: str, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    digest = sha256_path(resolved)
    return {"kind": kind, "path": str(resolved), "sha256": digest}


def stage_sequence(profile: dict[str, Any]) -> list[str]:
    source_kind = str(profile.get("source", {}).get("kind", "")).casefold()
    conversion = (
        "pdf-conversion" if source_kind == "pdf" else "markdown-registration"
    )
    stages = [
        "intake",
        conversion,
        "toc-formatting",
        "toc-splitting",
        "concepts",
        "markdown-standardization",
        "pre-canvas-audit",
    ]
    if profile.get("canvas", {}).get("enabled", False):
        stages.append("canvas")
    stages.append("final-audit")
    return stages


def make_stage(name: str, *, status: str = "pending") -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "attempts": 0,
        "inputs": [],
        "outputs": [],
        "report": None,
        "review_queue": None,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "error": None,
    }


def default_test_options(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "preserve_stage_artifacts": False,
        "config": None,
        "config_sha256": None,
        "checkpoint_root": None,
        "run_id": None,
        "latest_checkpoint": None,
    }


def load_test_options(
    profile: dict[str, Any],
    config_path: Path | None = None,
) -> dict[str, Any]:
    if config_path is None:
        candidate = (
            Path(profile["paths"]["vault_root"]).resolve()
            / TEST_OPTIONS_FILENAME
        )
        if not candidate.is_file():
            return default_test_options(profile)
        config_path = candidate
    resolved_config = config_path.expanduser().resolve()
    if not resolved_config.is_file():
        raise SchemaError(f"test options file does not exist: {resolved_config}")
    payload = read_json(resolved_config)
    if not isinstance(payload, dict):
        raise SchemaError("test options: root must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SchemaError(
            f"test options: schema_version must be {SCHEMA_VERSION}"
        )
    preserve = payload.get("preserve_stage_artifacts")
    if not isinstance(preserve, bool):
        raise SchemaError(
            "test options: preserve_stage_artifacts must be true or false"
        )
    checkpoint_value = payload.get("checkpoint_root")
    if checkpoint_value is not None and (
        not isinstance(checkpoint_value, str) or not checkpoint_value.strip()
    ):
        raise SchemaError(
            "test options: checkpoint_root must be a non-empty path"
        )
    if checkpoint_value:
        checkpoint_root = Path(checkpoint_value).expanduser()
        if not checkpoint_root.is_absolute():
            checkpoint_root = resolved_config.parent / checkpoint_root
        checkpoint_root = checkpoint_root.resolve()
    else:
        title = str(profile.get("book", {}).get("title", "book")).strip()
        checkpoint_root = (
            resolved_config.parent / ".book-graph-checkpoints" / title
        ).resolve()
    staging_root = Path(profile["paths"]["staging_root"]).resolve()
    book_root = Path(profile["paths"]["book_root"]).resolve()
    if (
        path_is_within(checkpoint_root, staging_root)
        or path_is_within(staging_root, checkpoint_root)
        or path_is_within(checkpoint_root, book_root)
        or path_is_within(book_root, checkpoint_root)
    ):
        raise SchemaError(
            "test options: checkpoint_root must be outside both staging_root "
            "and book_root"
        )
    return {
        "preserve_stage_artifacts": preserve,
        "config": str(resolved_config),
        "config_sha256": sha256_file(resolved_config),
        "checkpoint_root": str(checkpoint_root) if preserve else None,
        "run_id": (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            if preserve
            else None
        ),
        "latest_checkpoint": None,
    }


def init_state(
    profile_path: Path,
    *,
    test_options_path: Path | None = None,
) -> dict[str, Any]:
    profile_path, profile = load_profile(profile_path)
    source_path = Path(profile["source"]["path"]).resolve()
    staging_root = Path(profile["paths"]["staging_root"]).resolve()
    sequence = stage_sequence(profile)
    stages = [make_stage(name) for name in sequence]
    intake_outputs = [artifact_record("book-profile", profile_path)]
    inventory_path = staging_root / "source-inventory.json"
    if inventory_path.is_file():
        intake_outputs.append(artifact_record("file", inventory_path))
    stages[0].update(
        {
            "status": "completed",
            "attempts": 1,
            "outputs": intake_outputs,
            "started_at": utc_now(),
            "completed_at": utc_now(),
            "duration_seconds": 0.0,
        }
    )
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": str(profile_path),
        "profile_sha256": sha256_file(profile_path),
        "source": {
            "path": str(source_path),
            "sha256": profile["source"]["sha256"],
        },
        "staging_root": str(staging_root),
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "stages": stages,
        "telemetry": {
            "stage_attempts": {"intake": 1},
            "stage_duration_seconds": {"intake": 0.0},
            "review_items": 0,
            "manual_review_items": 0,
            "parallel_note_jobs": 0,
            "failures": [],
        },
        "reuse_policy": "same-run-only",
        "test_options": load_test_options(profile, test_options_path),
    }


def pipeline_state_errors(state: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["pipeline-state: root must be an object"]
    names: list[str] = []
    for index, stage in enumerate(state.get("stages", [])):
        if not isinstance(stage, dict):
            errors.append(f"pipeline-state: stages[{index}] must be an object")
            continue
        name = stage.get("name")
        status = stage.get("status")
        if name not in STAGE_NAMES:
            errors.append(f"pipeline-state: invalid stage name {name}")
        if name in names:
            errors.append(f"pipeline-state: duplicate stage name {name}")
        names.append(name)
        if status not in {"pending", "running", "completed", "failed"}:
            errors.append(f"pipeline-state: invalid status for {name}: {status}")
    if state.get("reuse_policy") != "same-run-only":
        errors.append("pipeline-state: reuse_policy must be same-run-only")
    test_options = state.get("test_options")
    if test_options is not None:
        if not isinstance(test_options, dict):
            errors.append("pipeline-state: test_options must be an object")
        elif not isinstance(
            test_options.get("preserve_stage_artifacts"), bool
        ):
            errors.append(
                "pipeline-state: test_options.preserve_stage_artifacts "
                "must be boolean"
            )
        elif test_options["preserve_stage_artifacts"] and (
            not isinstance(test_options.get("run_id"), str)
            or not test_options["run_id"]
        ):
            errors.append(
                "pipeline-state: enabled test options require run_id"
            )
    return errors


def load_state(path: Path) -> tuple[Path, dict[str, Any]]:
    resolved = path.resolve()
    payload = read_json(resolved)
    errors = artifact_errors(payload, "pipeline-state")
    if errors:
        raise SchemaError("; ".join(errors))
    return resolved, payload


def stage_index(state: dict[str, Any], name: str) -> int:
    for index, stage in enumerate(state["stages"]):
        if stage["name"] == name:
            return index
    raise PipelineError(f"stage is not enabled for this run: {name}")


def first_incomplete_stage(state: dict[str, Any]) -> dict[str, Any] | None:
    for stage in state["stages"]:
        if stage["status"] != "completed":
            return stage
    return None


def ensure_state_identity(state: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    profile_path, profile = load_profile(Path(state["profile"]))
    if sha256_file(profile_path) != state.get("profile_sha256"):
        raise IdentityError(
            "book profile changed after run initialization; start a new run state"
        )
    source_path = Path(state["source"]["path"]).resolve()
    if source_path != Path(profile["source"]["path"]).resolve():
        raise IdentityError("pipeline state source path no longer matches the profile")
    actual_hash = sha256_file(source_path)
    if actual_hash != state["source"]["sha256"]:
        raise IdentityError("pipeline state source digest changed")
    test_options = state.get("test_options", {})
    config_value = test_options.get("config")
    config_hash = test_options.get("config_sha256")
    if config_value:
        config_path = Path(config_value).resolve()
        if not config_path.is_file() or sha256_file(config_path) != config_hash:
            raise IdentityError(
                "test options changed after run initialization; start a new "
                "run state"
            )
    return profile_path, profile


def unresolved_review_items(queue: dict[str, Any]) -> list[dict[str, Any]]:
    unresolved: list[dict[str, Any]] = []
    for item in queue.get("items", []):
        if item.get("route") == "needs_review" and item.get("decision") not in (
            REVIEW_DECISIONS
        ):
            unresolved.append(item)
    return unresolved


def review_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "auto_ready": sum(item.get("route") == "auto_ready" for item in items),
        "needs_review": sum(
            item.get("route") == "needs_review" for item in items
        ),
        "unresolved": sum(
            item.get("route") == "needs_review"
            and item.get("decision") not in REVIEW_DECISIONS
            for item in items
        ),
    }


def review_queue_errors(queue: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(queue, dict):
        return ["review-queue: root must be an object"]
    identifiers: set[str] = set()
    for index, item in enumerate(queue.get("items", [])):
        if not isinstance(item, dict):
            errors.append(f"review-queue: items[{index}] must be an object")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"review-queue: items[{index}].id is required")
        elif identifier in identifiers:
            errors.append(f"review-queue: duplicate item id {identifier}")
        else:
            identifiers.add(identifier)
        if item.get("route") not in {"auto_ready", "needs_review"}:
            errors.append(f"review-queue: items[{index}].route is invalid")
        if item.get("stage") not in STAGE_NAMES:
            errors.append(f"review-queue: items[{index}].stage is invalid")
        for field in ("kind", "source"):
            if not isinstance(item.get(field), str) or not item[field]:
                errors.append(
                    f"review-queue: items[{index}].{field} is required"
                )
        if "proposal" not in item or item["proposal"] is None:
            errors.append(
                f"review-queue: items[{index}].proposal is required"
            )
        confidence = item.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            errors.append(
                f"review-queue: items[{index}].confidence must be 0..1"
            )
        decision = item.get("decision")
        if decision is not None and decision not in REVIEW_DECISIONS:
            errors.append(f"review-queue: items[{index}].decision is invalid")
        if decision == "revised" and not item.get("resolution"):
            errors.append(
                f"review-queue: items[{index}].resolution is required "
                "for a revised decision"
            )
    return errors


def review_route(candidate: dict[str, Any], threshold: float) -> str:
    confidence = candidate.get("confidence")
    ambiguous = bool(candidate.get("ambiguous"))
    unresolved = bool(candidate.get("unresolved"))
    conflicts = candidate.get("conflicts")
    has_conflicts = isinstance(conflicts, list) and bool(conflicts)
    if (
        not isinstance(confidence, (int, float))
        or confidence < threshold
        or ambiguous
        or unresolved
        or has_conflicts
    ):
        return "needs_review"
    return "auto_ready"


def make_review_queue(
    candidates_payload: Any,
    *,
    profile_path: Path,
    source_sha256: str,
    threshold: float,
) -> dict[str, Any]:
    candidates = (
        candidates_payload
        if isinstance(candidates_payload, list)
        else candidates_payload.get("candidates")
        if isinstance(candidates_payload, dict)
        else None
    )
    if not isinstance(candidates, list):
        raise SchemaError("candidate input must be an array or contain candidates")
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            raise SchemaError(f"candidate {index} must be an object")
        for field in ("stage", "kind", "source", "proposal", "confidence"):
            if field not in raw or raw[field] is None:
                raise SchemaError(f"candidate {index}.{field} is required")
        if raw["stage"] not in STAGE_NAMES:
            raise SchemaError(f"candidate {index}.stage is invalid")
        if not isinstance(raw["kind"], str) or not raw["kind"]:
            raise SchemaError(f"candidate {index}.kind is required")
        if not isinstance(raw["source"], str) or not raw["source"]:
            raise SchemaError(f"candidate {index}.source is required")
        confidence = raw["confidence"]
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise SchemaError(
                f"candidate {index}.confidence must be between 0 and 1"
            )
        identifier = raw.get("id") or f"candidate-{index + 1:05d}"
        item = dict(raw)
        item["id"] = str(identifier)
        item["route"] = review_route(item, threshold)
        item.setdefault("decision", None)
        items.append(item)
    counts = review_counts(items)
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": str(profile_path.resolve()),
        "source_sha256": source_sha256,
        "threshold": threshold,
        "items": items,
        "counts": counts,
        "created_at": utc_now(),
    }


def decide_review_item(
    queue: dict[str, Any],
    item_id: str,
    decision: str,
    resolution: str | None,
) -> dict[str, Any]:
    errors = artifact_errors(queue, "review-queue")
    if errors:
        raise SchemaError("; ".join(errors))
    if decision not in REVIEW_DECISIONS:
        raise SchemaError(f"invalid review decision: {decision}")
    if decision == "revised" and not resolution:
        raise SchemaError("a revised decision requires --resolution")
    matches = [item for item in queue["items"] if item["id"] == item_id]
    if not matches:
        raise PipelineError(f"review item not found: {item_id}")
    item = matches[0]
    if item.get("route") != "needs_review":
        raise PipelineError(f"review item is auto-ready: {item_id}")
    item["decision"] = decision
    if resolution:
        item["resolution"] = resolution
    elif decision != "revised":
        item.pop("resolution", None)
    item["decided_at"] = utc_now()
    queue["counts"] = review_counts(queue["items"])
    queue["updated_at"] = utc_now()
    return item


def parse_artifact_argument(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("artifact must use KIND=PATH")
    kind, raw_path = value.split("=", 1)
    if kind not in ARTIFACT_FIELDS:
        raise argparse.ArgumentTypeError(f"unknown artifact kind: {kind}")
    return kind, Path(raw_path).expanduser().resolve()


def validate_records(
    records: Iterable[tuple[str, Path]],
    *,
    profile_path: Path,
    source_sha256: str,
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for kind, path in records:
        result = validate_artifact(
            path,
            kind,
            expected_profile=profile_path,
            expected_source_sha256=source_sha256,
        )
        if result["status"] != "passed":
            raise SchemaError("; ".join(result["errors"]))
        validated.append(
            {"kind": kind, "path": result["path"], "sha256": result["sha256"]}
        )
    return validated


def begin_stage(
    state: dict[str, Any],
    stage_name: str,
    inputs: list[tuple[str, Path]],
) -> dict[str, Any]:
    profile_path, _ = ensure_state_identity(state)
    index = stage_index(state, stage_name)
    stage = state["stages"][index]
    expected = first_incomplete_stage(state)
    if expected is None:
        raise PipelineError("pipeline is already complete")
    if expected["name"] != stage_name:
        raise PipelineError(
            f"next stage is {expected['name']}, not {stage_name}"
        )
    if stage["status"] not in {"pending", "failed"}:
        raise PipelineError(f"stage cannot begin from status {stage['status']}")
    stage["inputs"] = validate_records(
        inputs,
        profile_path=profile_path,
        source_sha256=state["source"]["sha256"],
    )
    stage["status"] = "running"
    stage["attempts"] += 1
    stage["started_at"] = utc_now()
    stage["completed_at"] = None
    stage["duration_seconds"] = None
    stage["error"] = None
    state["status"] = "active"
    state["updated_at"] = utc_now()
    telemetry = state["telemetry"]
    telemetry["stage_attempts"][stage_name] = stage["attempts"]
    return stage


def seconds_between(start: str | None, end: str) -> float:
    if not start:
        return 0.0
    start_time = datetime.fromisoformat(start)
    end_time = datetime.fromisoformat(end)
    return max(0.0, (end_time - start_time).total_seconds())


def required_output_kinds(
    stage_name: str, profile: dict[str, Any]
) -> set[str]:
    requirements = {
        "pdf-conversion": {"file"},
        "markdown-registration": {"file"},
        "toc-formatting": {"file", "toc-manifest", "toc-format-report"},
        "toc-splitting": {
            "directory",
            "split-manifest",
            "coverage-manifest",
            "audit-report",
        },
        "concepts": {"audit-report"},
        "markdown-standardization": {"markdown-report", "audit-report"},
        "pre-canvas-audit": {"audit-report"},
        "canvas": {"file", "graph-manifest"},
        "final-audit": {"audit-report", "tree"},
    }
    required = set(requirements.get(stage_name, set()))
    concept_enabled = any(
        item.get("role") == "concept" and item.get("enabled", True)
        for item in profile.get("categories", [])
    )
    if stage_name == "concepts" and concept_enabled:
        required.add("concept-manifest")
    decomposition = profile.get("decomposition", {})
    if (
        stage_name == "toc-splitting"
        and isinstance(decomposition, dict)
        and decomposition.get("require_lesson_flow_manifest", False)
    ):
        required.add("lesson-flow-manifest")
    if stage_name == "final-audit" and profile.get("reference"):
        required.add("reference-parity-report")
    style_reference = profile.get("canvas", {}).get("style_reference")
    if stage_name == "canvas" and isinstance(style_reference, dict):
        required.add("canvas-style-report")
    return required


def complete_stage(
    state: dict[str, Any],
    stage_name: str,
    outputs: list[tuple[str, Path]],
    *,
    report: tuple[str, Path] | None = None,
    review_queue: Path | None = None,
) -> dict[str, Any]:
    profile_path, profile = ensure_state_identity(state)
    index = stage_index(state, stage_name)
    stage = state["stages"][index]
    if stage["status"] != "running":
        raise PipelineError(f"stage {stage_name} is not running")
    validated_outputs = validate_records(
        outputs,
        profile_path=profile_path,
        source_sha256=state["source"]["sha256"],
    )
    report_record = None
    if report is not None:
        report_records = validate_records(
            [report],
            profile_path=profile_path,
            source_sha256=state["source"]["sha256"],
        )
        report_record = report_records[0]
        report_payload = read_json(Path(report_record["path"]))
        if report_payload.get("status") != "passed":
            raise PipelineError("stage report status is not passed")
    declared = [*outputs, *([report] if report is not None else [])]
    declared_kinds = {kind for kind, _ in declared}
    missing_kinds = required_output_kinds(stage_name, profile) - declared_kinds
    if missing_kinds:
        raise PipelineError(
            f"stage {stage_name} is missing required artifact kinds: "
            f"{sorted(missing_kinds)}"
        )
    for kind, path in declared:
        if kind not in PASS_STATUS_KINDS:
            continue
        payload = read_json(path)
        if payload.get("status") != "passed":
            raise PipelineError(
                f"{kind} cannot complete a stage with status "
                f"{payload.get('status')}"
            )
        if kind == "reference-parity-report":
            configured_reference = profile.get("reference", {})
            if Path(payload["reference"]["path"]).resolve() != Path(
                configured_reference.get("path", "")
            ).resolve():
                raise IdentityError(
                    "reference parity report path does not match the profile"
                )
            if (
                payload["reference"]["sha256"]
                != configured_reference.get("sha256")
            ):
                raise IdentityError(
                    "reference parity report digest does not match the profile"
                )
            if (
                configured_reference.get("scope")
                == "same-book-content-and-style"
                and not payload.get("same_book")
            ):
                raise IdentityError(
                    "same-book reference scope requires a same-book parity report"
                )
        if kind == "canvas-style-report":
            configured_style = profile.get("canvas", {}).get(
                "style_reference", {}
            )
            if Path(payload["reference"]["path"]).resolve() != Path(
                configured_style.get("path", "")
            ).resolve():
                raise IdentityError(
                    "canvas style report reference path does not match the profile"
                )
            if (
                payload["reference"]["sha256"]
                != configured_style.get("sha256")
            ):
                raise IdentityError(
                    "canvas style report reference digest does not match the profile"
                )
            candidate_path = Path(payload["candidate"]["path"]).resolve()
            candidate_outputs = [
                path.resolve() for output_kind, path in outputs
                if output_kind == "file"
            ]
            if candidate_path not in candidate_outputs:
                raise IdentityError(
                    "canvas style report candidate is not the declared Canvas file"
                )
            if sha256_file(candidate_path) != payload["candidate"]["sha256"]:
                raise IdentityError(
                    "canvas style report candidate digest does not match the Canvas file"
                )
    expected_audit_stage = STAGE_AUDIT_NAMES.get(stage_name)
    if expected_audit_stage is not None:
        audit_paths = [
            path for kind, path in declared if kind == "audit-report"
        ]
        if not any(
            read_json(path).get("stage") == expected_audit_stage
            for path in audit_paths
        ):
            raise PipelineError(
                f"stage {stage_name} requires audit stage "
                f"{expected_audit_stage}"
            )
    if review_queue is not None:
        queue_result = validate_artifact(
            review_queue,
            "review-queue",
            expected_profile=profile_path,
            expected_source_sha256=state["source"]["sha256"],
        )
        if queue_result["status"] != "passed":
            raise SchemaError("; ".join(queue_result["errors"]))
        queue = read_json(review_queue)
        unresolved = unresolved_review_items(queue)
        if unresolved:
            raise PipelineError(
                f"review queue has {len(unresolved)} unresolved items"
            )
        stage["review_queue"] = {
            "kind": "review-queue",
            "path": str(review_queue.resolve()),
            "sha256": sha256_file(review_queue),
        }
        state["telemetry"]["review_items"] += len(queue["items"])
        state["telemetry"]["manual_review_items"] += queue["counts"][
            "needs_review"
        ]
    stage["outputs"] = validated_outputs
    stage["report"] = report_record
    completed_at = utc_now()
    duration = seconds_between(stage["started_at"], completed_at)
    stage["status"] = "completed"
    stage["completed_at"] = completed_at
    stage["duration_seconds"] = duration
    state["telemetry"]["stage_duration_seconds"][stage_name] = duration
    state["updated_at"] = completed_at
    if first_incomplete_stage(state) is None:
        state["status"] = "completed"
    return stage


def fail_stage(
    state: dict[str, Any],
    stage_name: str,
    *,
    message: str,
    error_artifact: Path | None = None,
) -> dict[str, Any]:
    ensure_state_identity(state)
    stage = state["stages"][stage_index(state, stage_name)]
    if stage["status"] != "running":
        raise PipelineError(f"stage {stage_name} is not running")
    artifact_record_value = None
    if error_artifact is not None:
        artifact_record_value = artifact_record("audit-report", error_artifact)
    failed_at = utc_now()
    stage["status"] = "failed"
    stage["completed_at"] = failed_at
    stage["duration_seconds"] = seconds_between(stage["started_at"], failed_at)
    stage["error"] = {
        "message": message,
        "artifact": artifact_record_value,
        "failed_at": failed_at,
    }
    state["status"] = "failed"
    state["updated_at"] = failed_at
    state["telemetry"]["failures"].append(
        {"stage": stage_name, "message": message, "failed_at": failed_at}
    )
    return stage


def invalidate_stage_and_downstream(
    state: dict[str, Any], index: int, reason: str
) -> None:
    for stage in state["stages"][index:]:
        stage.update(make_stage(stage["name"]))
    state["status"] = "active"
    state["updated_at"] = utc_now()
    state.setdefault("resume_events", []).append(
        {
            "invalidated_from": state["stages"][index]["name"],
            "reason": reason,
            "at": utc_now(),
        }
    )


def validate_resume(state: dict[str, Any]) -> dict[str, Any]:
    ensure_state_identity(state)
    for index, stage in enumerate(state["stages"]):
        if stage["status"] != "completed":
            continue
        records = [
            *stage.get("inputs", []),
            *stage.get("outputs", []),
        ]
        if stage.get("report"):
            records.append(stage["report"])
        if stage.get("review_queue"):
            records.append(stage["review_queue"])
        for record in records:
            path = Path(record["path"])
            kind = record.get("kind")
            exists = path.is_dir() if kind in {"directory", "tree"} else path.is_file()
            if not exists:
                invalidate_stage_and_downstream(
                    state, index, f"artifact missing: {path}"
                )
                return state
            if kind == "directory":
                continue
            actual = sha256_path(path)
            if actual != record["sha256"]:
                invalidate_stage_and_downstream(
                    state, index, f"artifact digest changed: {path}"
                )
                return state
    if state.get("status") == "failed":
        state["status"] = "active"
    state["updated_at"] = utc_now()
    return state


def checkpoint_enabled(state: dict[str, Any]) -> bool:
    return bool(
        state.get("test_options", {}).get("preserve_stage_artifacts", False)
    )


def checkpoint_stage_directory(
    state: dict[str, Any],
    stage_name: str,
) -> Path:
    options = state.get("test_options", {})
    root_value = options.get("checkpoint_root")
    if not root_value:
        raise PipelineError("stage artifact preservation is not enabled")
    index = stage_index(state, stage_name)
    stage = state["stages"][index]
    return (
        Path(root_value).resolve()
        / str(options["run_id"])
        / f"{index + 1:02d}-{stage_name}"
        / f"attempt-{stage['attempts']:02d}"
    )


def completed_output_records(
    state: dict[str, Any],
    through_stage: str,
) -> list[dict[str, Any]]:
    through_index = stage_index(state, through_stage)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for stage in state["stages"][: through_index + 1]:
        if stage.get("status") != "completed":
            raise PipelineError(
                f"cannot checkpoint before completed stage {stage['name']}"
            )
        stage_records = list(stage.get("outputs", []))
        if stage.get("report"):
            stage_records.append(stage["report"])
        if stage.get("review_queue"):
            stage_records.append(stage["review_queue"])
        for record in stage_records:
            resolved = str(Path(record["path"]).resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            records.append(record)
    book_root = Path(
        read_json(Path(state["profile"]))["paths"]["book_root"]
    ).resolve()
    split_index = stage_index(state, "toc-splitting")
    if (
        through_index >= split_index
        and book_root.is_dir()
        and str(book_root) not in seen
    ):
        records.append(
            {
                "kind": "tree",
                "path": str(book_root),
                "sha256": sha256_directory(book_root),
            }
        )
    return records


def copy_checkpoint_artifact(
    source: Path,
    destination: Path,
) -> Path:
    if source.is_dir():
        destination.parent.mkdir(parents=True, exist_ok=True)
        archive = Path(
            shutil.make_archive(
                str(destination),
                "zip",
                root_dir=str(source),
            )
        )
        return archive
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination
    else:
        raise PipelineError(f"checkpoint artifact is missing: {source}")


def capture_stage_checkpoint(
    state_path: Path,
    state: dict[str, Any],
    stage_name: str,
) -> dict[str, Any] | None:
    if not checkpoint_enabled(state):
        return None
    ensure_state_identity(state)
    stage = state["stages"][stage_index(state, stage_name)]
    if stage.get("status") != "completed":
        raise PipelineError(f"stage {stage_name} is not completed")
    target = checkpoint_stage_directory(state, stage_name)
    if target.exists():
        replay = 1
        base = target
        while target.exists():
            target = base.with_name(f"{base.name}-replay-{replay:02d}")
            replay += 1
    checkpoint_root = Path(
        state["test_options"]["checkpoint_root"]
    ).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=".checkpoint-", dir=str(checkpoint_root))
    )
    try:
        artifacts: list[dict[str, Any]] = []
        for index, record in enumerate(
            completed_output_records(state, stage_name), 1
        ):
            source = Path(record["path"]).resolve()
            source_digest = sha256_path(source)
            relative_base = Path("artifacts") / f"{index:03d}"
            stored = copy_checkpoint_artifact(
                source,
                temporary / relative_base,
            )
            stored_digest = sha256_file(stored)
            if source.is_file() and stored_digest != source_digest:
                raise PipelineError(
                    f"checkpoint copy digest mismatch: {source}"
                )
            artifacts.append(
                {
                    "kind": record["kind"],
                    "original_path": str(source),
                    "stored_path": stored.relative_to(temporary).as_posix(),
                    "sha256": source_digest,
                    "stored_sha256": stored_digest,
                    "is_directory": source.is_dir(),
                }
            )
        manifest_path = target / "checkpoint-manifest.json"
        checkpoint_entry = {
            "stage": stage_name,
            "attempt": stage["attempts"],
            "manifest": str(manifest_path),
            "created_at": utc_now(),
        }
        snapshot_state = copy.deepcopy(state)
        snapshot_stage = snapshot_state["stages"][
            stage_index(snapshot_state, stage_name)
        ]
        snapshot_stage["checkpoint"] = checkpoint_entry
        snapshot_state["test_options"]["latest_checkpoint"] = checkpoint_entry
        snapshot_state["updated_at"] = checkpoint_entry["created_at"]
        snapshot_state_path = temporary / "pipeline-state.json"
        write_json_atomic(snapshot_state_path, snapshot_state)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "stage": stage_name,
            "attempt": stage["attempts"],
            "created_at": checkpoint_entry["created_at"],
            "profile": state["profile"],
            "profile_sha256": state["profile_sha256"],
            "source": copy.deepcopy(state["source"]),
            "staging_root": state["staging_root"],
            "book_root": read_json(Path(state["profile"]))["paths"][
                "book_root"
            ],
            "state": {
                "original_path": str(state_path.resolve()),
                "stored_path": "pipeline-state.json",
                "sha256": sha256_file(snapshot_state_path),
            },
            "artifacts": artifacts,
            "next_stage": (
                first_incomplete_stage(snapshot_state) or {}
            ).get("name"),
            "reuse_policy": "same-source-test-checkpoint-only",
        }
        write_json_atomic(
            temporary / "checkpoint-manifest.json",
            manifest,
        )
        temporary.replace(target)
        state.clear()
        state.update(snapshot_state)
        write_json_atomic(state_path.resolve(), state)
        return manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def checkpoint_manifest_errors(payload: Any, manifest_path: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["checkpoint manifest root must be an object"]
    required = {
        "schema_version": int,
        "stage": str,
        "attempt": int,
        "profile": str,
        "profile_sha256": str,
        "source": dict,
        "staging_root": str,
        "book_root": str,
        "state": dict,
        "artifacts": list,
        "reuse_policy": str,
    }
    errors.extend(
        require_fields(payload, kind="checkpoint-manifest", fields=required)
    )
    if errors:
        return errors
    if payload["schema_version"] != SCHEMA_VERSION:
        errors.append(
            f"checkpoint manifest schema_version must be {SCHEMA_VERSION}"
        )
    if payload["stage"] not in STAGE_NAMES:
        errors.append("checkpoint manifest stage is invalid")
    if payload["reuse_policy"] != "same-source-test-checkpoint-only":
        errors.append("checkpoint manifest reuse_policy is invalid")
    source_path = Path(payload["source"].get("path", "")).resolve()
    source_hash = payload["source"].get("sha256")
    if not source_path.is_file():
        errors.append(f"checkpoint source is missing: {source_path}")
    elif not is_sha256(source_hash) or sha256_file(source_path) != source_hash:
        errors.append("checkpoint source digest changed")
    roots = [
        Path(payload["staging_root"]).resolve(),
        Path(payload["book_root"]).resolve(),
    ]
    for index, artifact in enumerate(payload["artifacts"]):
        if not isinstance(artifact, dict):
            errors.append(f"checkpoint artifact {index} must be an object")
            continue
        original = Path(artifact.get("original_path", "")).resolve()
        stored_value = artifact.get("stored_path")
        digest = artifact.get("sha256")
        stored_digest = artifact.get("stored_sha256")
        if not any(path_is_within(original, root) for root in roots):
            errors.append(
                f"checkpoint artifact target is outside frozen roots: {original}"
            )
        if not isinstance(stored_value, str) or not stored_value:
            errors.append(f"checkpoint artifact {index} stored_path is invalid")
            continue
        stored = (manifest_path.parent / stored_value).resolve()
        if not path_is_within(stored, manifest_path.parent):
            errors.append(
                f"checkpoint artifact {index} escapes checkpoint directory"
            )
        elif not stored.exists():
            errors.append(f"checkpoint artifact is missing: {stored}")
        elif not is_sha256(digest):
            errors.append(f"checkpoint artifact source digest is invalid")
        elif (
            not is_sha256(stored_digest)
            or sha256_file(stored) != stored_digest
        ):
            errors.append(f"checkpoint artifact digest changed: {stored}")
    state_record = payload["state"]
    stored_state_value = state_record.get("stored_path")
    stored_state = (
        manifest_path.parent / str(stored_state_value)
    ).resolve()
    if not path_is_within(stored_state, manifest_path.parent):
        errors.append("checkpoint state escapes checkpoint directory")
    elif not stored_state.is_file():
        errors.append(f"checkpoint state is missing: {stored_state}")
    elif (
        not is_sha256(state_record.get("sha256"))
        or sha256_file(stored_state) != state_record["sha256"]
    ):
        errors.append("checkpoint state digest changed")
    return errors


def replace_from_checkpoint(
    source: Path,
    destination: Path,
    *,
    overwrite: bool,
    is_directory: bool | None = None,
    expected_digest: str | None = None,
) -> str:
    source_is_directory = (
        source.is_dir() if is_directory is None else is_directory
    )
    if destination.exists():
        same_kind = source_is_directory == destination.is_dir()
        comparison_digest = (
            expected_digest
            if expected_digest is not None
            else sha256_path(source)
        )
        if (
            same_kind
            and comparison_digest == sha256_path(destination)
        ):
            return "already-current"
        if not overwrite:
            raise PipelineError(
                f"restore target differs and already exists: {destination}; "
                "rerun with --overwrite after checking the target"
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source_is_directory:
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.restore"
        )
        try:
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.restore-",
                dir=str(destination.parent),
            )
        )
        shutil.rmtree(temporary)
        try:
            shutil.unpack_archive(str(source), str(temporary), "zip")
            if (
                expected_digest is not None
                and sha256_directory(temporary) != expected_digest
            ):
                raise PipelineError(
                    f"restored directory digest mismatch: {destination}"
                )
            if destination.exists():
                shutil.rmtree(destination)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return "restored"


def restore_stage_checkpoint(
    manifest_path: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    resolved_manifest = manifest_path.resolve()
    payload = read_json(resolved_manifest)
    errors = checkpoint_manifest_errors(payload, resolved_manifest)
    if errors:
        raise SchemaError("; ".join(errors))
    restored: list[dict[str, str]] = []
    ordered = sorted(
        payload["artifacts"],
        key=lambda item: not bool(item.get("is_directory")),
    )
    for artifact in ordered:
        source = (
            resolved_manifest.parent / artifact["stored_path"]
        ).resolve()
        destination = Path(artifact["original_path"]).resolve()
        action = replace_from_checkpoint(
            source,
            destination,
            overwrite=overwrite,
            is_directory=bool(artifact.get("is_directory")),
            expected_digest=artifact["sha256"],
        )
        restored.append({"path": str(destination), "action": action})
    stored_state = (
        resolved_manifest.parent / payload["state"]["stored_path"]
    ).resolve()
    state_target = Path(payload["state"]["original_path"]).resolve()
    replace_from_checkpoint(
        stored_state,
        state_target,
        overwrite=overwrite,
    )
    _, restored_state = load_state(state_target)
    validate_resume(restored_state)
    write_json_atomic(state_target, restored_state)
    return {
        "status": "passed",
        "checkpoint": str(resolved_manifest),
        "restored_state": str(state_target),
        "restored_stage": payload["stage"],
        "next_stage": (
            first_incomplete_stage(restored_state) or {}
        ).get("name"),
        "artifacts": restored,
    }


def note_workplan_errors(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["note-workplan: root must be an object"]
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    for index, job in enumerate(payload.get("jobs", [])):
        if not isinstance(job, dict):
            errors.append(f"note-workplan: jobs[{index}] must be an object")
            continue
        identifier = job.get("id")
        path = job.get("path")
        digest = job.get("sha256")
        if identifier in seen_ids:
            errors.append(f"note-workplan: duplicate job id {identifier}")
        seen_ids.add(identifier)
        if path in seen_paths:
            errors.append(f"note-workplan: duplicate note owner for {path}")
        seen_paths.add(path)
        if not is_sha256(digest):
            errors.append(f"note-workplan: jobs[{index}].sha256 is invalid")
    lane_jobs = [
        job_id
        for lane in payload.get("lanes", [])
        if isinstance(lane, dict)
        for job_id in lane.get("jobs", [])
    ]
    if sorted(lane_jobs) != sorted(seen_ids):
        errors.append("note-workplan: lanes must own every job exactly once")
    return errors


def make_note_workplan(
    profile_path: Path,
    *,
    workers: int,
    roles: set[str],
    tasks: list[str],
) -> dict[str, Any]:
    profile_path, profile = load_profile(profile_path)
    if workers < 1 or workers > 64:
        raise PipelineError("workers must be between 1 and 64")
    book_root = Path(profile["paths"]["book_root"]).resolve()
    if not book_root.is_dir():
        raise FileNotFoundError(f"book root does not exist: {book_root}")
    directories = {
        item["role"]: item["directory"]
        for item in profile.get("categories", [])
        if item.get("enabled", True)
    }
    unknown_roles = roles - set(directories)
    if unknown_roles:
        raise PipelineError(f"unknown enabled roles: {sorted(unknown_roles)}")
    paths: list[Path] = []
    for role in sorted(roles):
        root = book_root / directories[role]
        if root.is_dir():
            paths.extend(sorted(root.rglob("*.md")))
    jobs: list[dict[str, Any]] = []
    for index, path in enumerate(sorted(set(paths))):
        jobs.append(
            {
                "id": f"note-{index + 1:05d}",
                "path": str(path.resolve()),
                "relative_path": path.relative_to(book_root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "tasks": tasks,
            }
        )
    lanes = [
        {"lane": index + 1, "jobs": [], "bytes": 0}
        for index in range(min(workers, max(1, len(jobs))))
    ]
    for job in sorted(jobs, key=lambda item: item["bytes"], reverse=True):
        lane = min(lanes, key=lambda item: (item["bytes"], item["lane"]))
        lane["jobs"].append(job["id"])
        lane["bytes"] += job["bytes"]
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": str(profile_path),
        "source_sha256": profile["source"]["sha256"],
        "book_root": str(book_root),
        "workers": len(lanes),
        "roles": sorted(roles),
        "tasks": tasks,
        "jobs": jobs,
        "lanes": lanes,
        "created_at": utc_now(),
        "ownership": "one-owner-per-note",
    }


def merge_note_results(
    workplan_path: Path, result_directory: Path
) -> dict[str, Any]:
    workplan = read_json(workplan_path)
    errors = artifact_errors(workplan, "note-workplan")
    if errors:
        raise SchemaError("; ".join(errors))
    expected = {job["id"]: job for job in workplan["jobs"]}
    results: dict[str, dict[str, Any]] = {}
    output_paths: set[str] = set()
    for path in sorted(result_directory.glob("*.json")):
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise SchemaError(f"result must be an object: {path}")
        job_id = payload.get("job_id")
        if job_id not in expected:
            raise SchemaError(f"unknown result job_id {job_id}: {path}")
        if job_id in results:
            raise SchemaError(f"duplicate result for {job_id}")
        job = expected[job_id]
        if payload.get("source_sha256") != job["sha256"]:
            raise IdentityError(f"source digest mismatch for {job_id}")
        source_path = Path(job["path"])
        if not source_path.is_file() or sha256_file(source_path) != job["sha256"]:
            raise IdentityError(f"source note changed before merge: {source_path}")
        for output in payload.get("outputs", []):
            if output in output_paths:
                raise PipelineError(f"duplicate output ownership: {output}")
            output_paths.add(output)
        results[job_id] = payload
    missing = sorted(set(expected) - set(results))
    if missing:
        raise PipelineError(f"missing results for {len(missing)} jobs: {missing[:20]}")
    ordered = [results[job["id"]] for job in workplan["jobs"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": workplan["profile"],
        "source_sha256": workplan["source_sha256"],
        "workplan": str(workplan_path.resolve()),
        "results": ordered,
        "metrics": {
            "jobs": len(ordered),
            "passed": sum(item.get("status") == "passed" for item in ordered),
            "failed": sum(item.get("status") == "failed" for item in ordered),
            "candidates": sum(
                len(item.get("candidates", [])) for item in ordered
            ),
        },
        "merged_at": utc_now(),
    }


def state_summary(state: dict[str, Any]) -> dict[str, Any]:
    next_stage = first_incomplete_stage(state)
    return {
        "pipeline_status": state["status"],
        "profile": state["profile"],
        "source_sha256": state["source"]["sha256"],
        "next_stage": next_stage["name"] if next_stage else None,
        "stages": [
            {
                "name": stage["name"],
                "status": stage["status"],
                "attempts": stage["attempts"],
                "duration_seconds": stage["duration_seconds"],
            }
            for stage in state["stages"]
        ],
        "telemetry": state["telemetry"],
        "test_options": {
            "preserve_stage_artifacts": checkpoint_enabled(state),
            "checkpoint_root": state.get("test_options", {}).get(
                "checkpoint_root"
            ),
            "run_id": state.get("test_options", {}).get("run_id"),
            "latest_checkpoint": state.get("test_options", {}).get(
                "latest_checkpoint"
            ),
        },
    }


def default_state_path(profile: dict[str, Any]) -> Path:
    return Path(profile["paths"]["staging_root"]).resolve() / "pipeline-state.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("profile", type=Path)
    init.add_argument("--state", type=Path)
    init.add_argument(
        "--test-options",
        type=Path,
        help=(
            f"Optional {TEST_OPTIONS_FILENAME}; when omitted, the runtime "
            "auto-discovers that filename at paths.vault_root."
        ),
    )
    init.add_argument("--overwrite", action="store_true")

    plan = commands.add_parser("plan")
    plan.add_argument("state", type=Path)

    resume = commands.add_parser("resume")
    resume.add_argument("state", type=Path)

    restore_checkpoint = commands.add_parser("restore-checkpoint")
    restore_checkpoint.add_argument("manifest", type=Path)
    restore_checkpoint.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace differing frozen staging/book targets.",
    )

    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("state", type=Path)
    checkpoint.add_argument("stage")

    begin = commands.add_parser("begin")
    begin.add_argument("state", type=Path)
    begin.add_argument("stage")
    begin.add_argument(
        "--input", action="append", default=[], type=parse_artifact_argument
    )

    apply = commands.add_parser("apply")
    apply.add_argument("state", type=Path)
    apply.add_argument("stage")
    apply.add_argument(
        "--input", action="append", default=[], type=parse_artifact_argument
    )
    apply.add_argument(
        "--command",
        dest="stage_command",
        nargs=argparse.REMAINDER,
        required=True,
        help="Component executable and arguments; success still requires complete.",
    )

    complete = commands.add_parser("complete")
    complete.add_argument("state", type=Path)
    complete.add_argument("stage")
    complete.add_argument(
        "--artifact", action="append", default=[], type=parse_artifact_argument
    )
    complete.add_argument("--report", type=parse_artifact_argument)
    complete.add_argument("--review-queue", type=Path)

    fail = commands.add_parser("fail")
    fail.add_argument("state", type=Path)
    fail.add_argument("stage")
    fail.add_argument("--message", required=True)
    fail.add_argument("--error-artifact", type=Path)

    validate = commands.add_parser("validate")
    validate.add_argument("kind", choices=sorted(ARTIFACT_FIELDS))
    validate.add_argument("artifact", type=Path)
    validate.add_argument("--profile", type=Path)
    validate.add_argument("--source-sha256")

    queue = commands.add_parser("make-review-queue")
    queue.add_argument("candidates", type=Path)
    queue.add_argument("--profile", type=Path, required=True)
    queue.add_argument("--threshold", type=float, default=0.9)
    queue.add_argument("--output", type=Path, required=True)
    queue.add_argument("--overwrite", action="store_true")

    queue_status = commands.add_parser("review-status")
    queue_status.add_argument("queue", type=Path)

    decide = commands.add_parser("decide-review")
    decide.add_argument("queue", type=Path)
    decide.add_argument("item_id")
    decide.add_argument("decision", choices=sorted(REVIEW_DECISIONS))
    decide.add_argument("--resolution")

    partition = commands.add_parser("partition-notes")
    partition.add_argument("profile", type=Path)
    partition.add_argument("--workers", type=int, default=4)
    partition.add_argument("--roles", default="knowledge,exercise")
    partition.add_argument(
        "--tasks", default="concept-planning,markdown-planning"
    )
    partition.add_argument("--output", type=Path, required=True)
    partition.add_argument("--overwrite", action="store_true")

    merge = commands.add_parser("merge-note-results")
    merge.add_argument("workplan", type=Path)
    merge.add_argument("result_directory", type=Path)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--overwrite", action="store_true")

    summary = commands.add_parser("summary")
    summary.add_argument("state", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result: dict[str, Any]
        if args.command == "init":
            profile_path, profile = load_profile(args.profile)
            state_path = (
                args.state.resolve()
                if args.state
                else default_state_path(profile)
            )
            state = init_state(
                profile_path,
                test_options_path=(
                    args.test_options.resolve()
                    if args.test_options
                    else None
                ),
            )
            write_json_atomic(state_path, state, overwrite=args.overwrite)
            checkpoint = capture_stage_checkpoint(
                state_path,
                state,
                "intake",
            )
            result = {
                "status": "passed",
                "state": str(state_path),
                "checkpoint": (
                    str(
                        checkpoint_stage_directory(state, "intake")
                        / "checkpoint-manifest.json"
                    )
                    if checkpoint is not None
                    else None
                ),
                **state_summary(state),
            }
        elif args.command == "restore-checkpoint":
            result = restore_stage_checkpoint(
                args.manifest,
                overwrite=args.overwrite,
            )
        elif args.command == "validate":
            expected_profile = args.profile.resolve() if args.profile else None
            result = validate_artifact(
                args.artifact,
                args.kind,
                expected_profile=expected_profile,
                expected_source_sha256=args.source_sha256,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "passed" else 1
        elif args.command == "make-review-queue":
            profile_path, profile = load_profile(args.profile)
            payload = read_json(args.candidates)
            queue = make_review_queue(
                payload,
                profile_path=profile_path,
                source_sha256=profile["source"]["sha256"],
                threshold=args.threshold,
            )
            write_json_atomic(
                args.output.resolve(), queue, overwrite=args.overwrite
            )
            result = {
                "status": "passed",
                "queue": str(args.output.resolve()),
                "counts": queue["counts"],
            }
        elif args.command == "review-status":
            queue = read_json(args.queue)
            errors = artifact_errors(queue, "review-queue")
            if errors:
                raise SchemaError("; ".join(errors))
            counts = review_counts(queue["items"])
            result = {
                "status": (
                    "passed" if not unresolved_review_items(queue) else "blocked"
                ),
                "queue": str(args.queue.resolve()),
                "counts": counts,
                "unresolved": [
                    item["id"] for item in unresolved_review_items(queue)
                ],
            }
        elif args.command == "decide-review":
            queue_path = args.queue.resolve()
            queue = read_json(queue_path)
            item = decide_review_item(
                queue,
                args.item_id,
                args.decision,
                args.resolution,
            )
            write_json_atomic(queue_path, queue, overwrite=True)
            result = {
                "status": "passed",
                "queue": str(queue_path),
                "item": item,
                "counts": queue["counts"],
            }
        elif args.command == "partition-notes":
            roles = {
                value.strip()
                for value in args.roles.split(",")
                if value.strip()
            }
            tasks = [
                value.strip()
                for value in args.tasks.split(",")
                if value.strip()
            ]
            workplan = make_note_workplan(
                args.profile,
                workers=args.workers,
                roles=roles,
                tasks=tasks,
            )
            write_json_atomic(
                args.output.resolve(), workplan, overwrite=args.overwrite
            )
            result = {
                "status": "passed",
                "workplan": str(args.output.resolve()),
                "jobs": len(workplan["jobs"]),
                "workers": workplan["workers"],
                "lane_bytes": [lane["bytes"] for lane in workplan["lanes"]],
            }
        elif args.command == "merge-note-results":
            merged = merge_note_results(
                args.workplan.resolve(), args.result_directory.resolve()
            )
            write_json_atomic(
                args.output.resolve(), merged, overwrite=args.overwrite
            )
            result = {
                "status": (
                    "passed"
                    if merged["metrics"]["failed"] == 0
                    else "failed"
                ),
                "output": str(args.output.resolve()),
                "metrics": merged["metrics"],
            }
        else:
            state_path, state = load_state(args.state)
            if args.command == "checkpoint":
                manifest = capture_stage_checkpoint(
                    state_path,
                    state,
                    args.stage,
                )
                if manifest is None:
                    raise PipelineError(
                        "stage artifact preservation is not enabled"
                    )
                result = {
                    "status": "passed",
                    "state": str(state_path),
                    "stage": args.stage,
                    "checkpoint": str(
                        checkpoint_stage_directory(state, args.stage)
                        / "checkpoint-manifest.json"
                    ),
                    "next_stage": (
                        first_incomplete_stage(state) or {}
                    ).get("name"),
                }
            elif args.command in {"plan", "resume"}:
                validate_resume(state)
                write_json_atomic(state_path, state)
                result = {
                    "status": "passed",
                    "operation": args.command,
                    **state_summary(state),
                }
            elif args.command in {"begin", "apply"}:
                stage_command = getattr(args, "stage_command", [])
                if args.command == "apply" and not stage_command:
                    raise PipelineError("apply requires a component command")
                stage = begin_stage(state, args.stage, args.input)
                write_json_atomic(state_path, state)
                if args.command == "begin":
                    result = {
                        "status": "passed",
                        "state": str(state_path),
                        "stage": stage,
                        "next_stage": args.stage,
                    }
                else:
                    try:
                        process = subprocess.run(
                            stage_command,
                            check=False,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                        )
                    except OSError as exc:
                        fail_stage(
                            state,
                            args.stage,
                            message=f"component launch failed: {exc}",
                        )
                        write_json_atomic(state_path, state)
                        raise PipelineError(
                            f"component launch failed: {exc}"
                        ) from exc
                    if process.returncode != 0:
                        stage = fail_stage(
                            state,
                            args.stage,
                            message=(
                                "component command returned "
                                f"{process.returncode}"
                            ),
                        )
                        write_json_atomic(state_path, state)
                        result = {
                            "status": "failed",
                            "state": str(state_path),
                            "stage": stage,
                            "returncode": process.returncode,
                            "stdout": process.stdout[-50000:],
                            "stderr": process.stderr[-50000:],
                        }
                    else:
                        result = {
                            "status": "passed",
                            "state": str(state_path),
                            "stage": stage,
                            "returncode": process.returncode,
                            "stdout": process.stdout[-50000:],
                            "stderr": process.stderr[-50000:],
                            "next_action": (
                                "validate outputs, then run complete"
                            ),
                        }
            elif args.command == "complete":
                stage = complete_stage(
                    state,
                    args.stage,
                    args.artifact,
                    report=args.report,
                    review_queue=(
                        args.review_queue.resolve()
                        if args.review_queue
                        else None
                    ),
                )
                write_json_atomic(state_path, state)
                checkpoint = capture_stage_checkpoint(
                    state_path,
                    state,
                    args.stage,
                )
                result = {
                    "status": "passed",
                    "state": str(state_path),
                    "stage": stage,
                    "checkpoint": (
                        str(
                            checkpoint_stage_directory(state, args.stage)
                            / "checkpoint-manifest.json"
                        )
                        if checkpoint is not None
                        else None
                    ),
                    "next_stage": (
                        first_incomplete_stage(state) or {}
                    ).get("name"),
                }
            elif args.command == "fail":
                stage = fail_stage(
                    state,
                    args.stage,
                    message=args.message,
                    error_artifact=(
                        args.error_artifact.resolve()
                        if args.error_artifact
                        else None
                    ),
                )
                write_json_atomic(state_path, state)
                result = {
                    "status": "failed",
                    "state": str(state_path),
                    "stage": stage,
                }
            else:
                result = {"status": "passed", **state_summary(state)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"passed", "completed"} else 1
    except Exception as exc:
        result = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

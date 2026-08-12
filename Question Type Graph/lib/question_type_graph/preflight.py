from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .common import ConfigurationError, load_json, load_profile, pdf_page_count, sha256_file
from .environment import parse_env_file, resolve_env_file


def build_preflight_report(
    profile_path: Path,
    *,
    env_file: str | Path | None = None,
    skip_conversion: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate a frozen run before OCR or graph mutation and expose no secrets."""
    profile = load_profile(profile_path)
    staging = Path(profile["paths"]["staging_root"]).resolve()
    vault = Path(profile["paths"]["vault_root"]).resolve()
    graph = Path(profile["paths"]["graph_root"]).resolve()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    source_checks: list[dict[str, Any]] = []
    conversion_required = False

    for source in profile["sources"]:
        path = Path(source["path"]).resolve()
        raw = Path(source["markdown_path"]).resolve()
        check = {
            "role": source["role"],
            "path": str(path),
            "kind": source["kind"],
            "sha256": source["sha256"],
            "size_bytes": path.stat().st_size,
            "page_count": pdf_page_count(path) if source["kind"] == "pdf" else None,
            "raw_markdown": str(raw),
            "conversion_required": source["kind"] == "pdf" and not raw.is_file(),
        }
        conversion_required = conversion_required or bool(check["conversion_required"])
        if check["size_bytes"] != source.get("size_bytes"):
            errors.append({"kind": "source-size-drift", "role": source["role"], "path": str(path)})
        if source["kind"] == "pdf" and check["page_count"] != source.get("page_count"):
            errors.append({"kind": "source-page-count-drift", "role": source["role"], "path": str(path)})
        if sha256_file(path) != source.get("sha256"):
            errors.append({"kind": "source-hash-drift", "role": source["role"], "path": str(path)})
        source_checks.append(check)

    if conversion_required and skip_conversion:
        errors.append(
            {
                "kind": "conversion-disabled-but-required",
                "message": "At least one frozen PDF has no converted Markdown",
            }
        )

    resolved_env: Path | None = None
    credential_source = "process-environment" if os.environ.get("MINERU_API_KEY") else None
    if conversion_required and not skip_conversion and credential_source is None:
        try:
            resolved_env = resolve_env_file(profile_path, env_file)
        except ConfigurationError as exc:
            errors.append({"kind": "environment-file-invalid", "message": str(exc)})
        if resolved_env is None:
            errors.append(
                {
                    "kind": "mineru-credential-missing",
                    "message": "MINERU_API_KEY is absent and no deterministic .env candidate exists",
                }
            )
        elif not parse_env_file(resolved_env).get("MINERU_API_KEY"):
            errors.append(
                {
                    "kind": "mineru-credential-missing",
                    "message": f"MINERU_API_KEY is absent from {resolved_env}",
                }
            )
        else:
            credential_source = "environment-file"
    existing_state = staging / "pipeline-state.json"
    state_owns_outputs = False
    if existing_state.is_file():
        try:
            state_owns_outputs = any(
                record.get("artifacts")
                for name, record in load_json(existing_state).get("stages", {}).items()
                if name not in {"intake", "preflight", "pdf-conversion", "format-inventory"}
            )
        except ConfigurationError:
            state_owns_outputs = False
    if graph.is_dir() and any(graph.iterdir()) and not state_owns_outputs and not overwrite:
        errors.append(
            {
                "kind": "unowned-graph-output",
                "path": str(graph),
                "message": "Graph root is non-empty but no resumable pipeline state owns it",
            }
        )
    if graph.exists() and not graph.is_dir():
        errors.append({"kind": "graph-root-not-directory", "path": str(graph)})
    if staging.exists() and not staging.is_dir():
        errors.append({"kind": "staging-root-not-directory", "path": str(staging)})

    storage_probe = next((path for path in (staging, staging.parent, vault, vault.parent) if path.exists()), None)
    storage: dict[str, Any] | None = None
    if storage_probe:
        usage = shutil.disk_usage(storage_probe)
        source_bytes = sum(int(item["size_bytes"]) for item in source_checks)
        recommended_free = max(512 * 1024 * 1024, source_bytes * 2)
        storage = {
            "path": str(storage_probe.resolve()),
            "free_bytes": usage.free,
            "recommended_free_bytes": recommended_free,
            "sufficient": usage.free >= recommended_free,
        }
        if not storage["sufficient"]:
            errors.append(
                {
                    "kind": "insufficient-free-space",
                    "free_bytes": usage.free,
                    "recommended_free_bytes": recommended_free,
                }
            )
    else:
        warnings.append({"kind": "storage-not-inspected"})

    return {
        "schema_version": 1,
        "stage": "preflight",
        "status": "failed" if errors else "passed",
        "profile": profile["_profile_path"],
        "source_checks": source_checks,
        "paths": {
            "staging_root": str(staging),
            "vault_root": str(vault),
            "graph_root": str(graph),
            "staging_outside_graph": staging != graph and graph not in staging.parents,
            "graph_inside_vault": graph == vault or vault in graph.parents,
        },
        "conversion_required": conversion_required,
        "credentials": {
            "required": conversion_required and not skip_conversion,
            "source": credential_source,
            "env_file": str(resolved_env) if resolved_env else None,
        },
        "storage": storage,
        "errors": errors,
        "warnings": warnings,
    }


def require_passed_preflight(*args: Any, **kwargs: Any) -> dict[str, Any]:
    report = build_preflight_report(*args, **kwargs)
    if report["status"] != "passed":
        summary = "; ".join(
            str(item.get("message") or item.get("kind")) for item in report["errors"]
        )
        raise ConfigurationError(f"Preflight failed: {summary}")
    return report

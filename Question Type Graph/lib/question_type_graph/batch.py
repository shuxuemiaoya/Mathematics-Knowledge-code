"""Universal batch pipeline runner for processing collections of math exercise PDFs / Markdown into Obsidian vaults."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .archetypes import ARCHETYPE_REGISTRY, build_archetype_adapter
from .audit import audit_graph
from .common import (
    ConfigurationError,
    load_json,
    load_profile,
    safe_name,
    write_json_atomic,
)
from .coordinator import artifact_paths, run_pipeline
from .profile import create_profile


def discover_source_files(
    source_dir: Path,
    patterns: list[str] | None = None,
    recursive: bool = True,
) -> list[Path]:
    """Find source PDF or Markdown files in a directory."""
    if not source_dir.is_dir():
        raise ConfigurationError(f"Source directory does not exist: {source_dir}")

    target_patterns = patterns or ["*.pdf", "*.md"]
    found: list[Path] = []
    for pat in target_patterns:
        if recursive:
            found.extend(source_dir.rglob(pat))
        else:
            found.extend(source_dir.glob(pat))

    # Deduplicate and sort
    seen = set()
    result = []
    for p in sorted(found):
        resolved = p.resolve()
        # Filter out hidden, temporary or system files
        if resolved.name.startswith((".", "~$")):
            continue
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def derive_book_title(source_file: Path, base_dir: Path | None = None) -> str:
    """Clean and derive standard book / lesson title from file path."""
    name = source_file.stem
    name = re.sub(r"[（(]答案解析[）)]$", "", name).strip()
    name = re.sub(r"[（(]解析版[）)]$", "", name).strip()
    name = re.sub(r"[（(]学生版[）)]$", "", name).strip()
    name = re.sub(r"[（(]教师版[）)]$", "", name).strip()
    return safe_name(name)


def auto_confirm_manifests(staging_path: Path) -> list[str]:
    """Safely auto-confirm pending stage manifests that only require approval without structural error."""
    manifest_files = [
        staging_path / "hierarchy-manifest.json",
        staging_path / "question-type-manifest.json",
        staging_path / "answer-match-manifest.json",
        staging_path / "supplemental-solutions-manifest.json",
    ]
    confirmed = []
    for mf in manifest_files:
        if mf.is_file():
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                if data.get("status") == "review_required" or not data.get("reviewer_confirmed"):
                    # Check if there are blocking hard discontinuities
                    discontinuities = data.get("discontinuities") or []
                    has_blockers = any(item.get("kind") == "question-sequence-discontinuity" for item in data.get("review", []))
                    if not has_blockers and not discontinuities:
                        data["status"] = "passed"
                        data["reviewer_confirmed"] = True
                        mf.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        confirmed.append(mf.name)
            except Exception:
                pass
    return confirmed


def process_single_source(
    source_file: Path,
    staging_base: Path,
    vault_root: Path,
    graph_base: Path,
    archetype: str,
    answers_mode: str = "embedded",
    skip_conversion: bool = False,
    safe_auto_approve: bool = True,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Execute complete Question Type Graph pipeline for a single source file."""
    title = derive_book_title(source_file)
    slug = safe_name(title)
    staging_path = staging_base / f"{slug}-staging"
    staging_path.mkdir(parents=True, exist_ok=True)
    profile_path = staging_path / "question-type-profile.json"

    # 1. Create Profile
    is_pdf = source_file.suffix.lower() == ".pdf"
    source_arg = f"questions={source_file}" if is_pdf else f"questions={source_file}"
    profile = create_profile(
        sources=[source_arg],
        title=title,
        staging_root=staging_path,
        vault_root=vault_root,
        graph_root=graph_base / slug,
        language="zh-CN",
        answers_mode=answers_mode,
        canvas=False,
    )
    write_json_atomic(profile_path, profile, overwrite=overwrite)

    # 2. Build Adapter using Archetype if needed
    adapter_path = staging_path / "format-adapter.json"
    if not adapter_path.is_file() or overwrite:
        # Pre-ensure raw directory if source is markdown
        if not is_pdf:
            raw_dir = staging_path / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_target = raw_dir / "questions.raw.md"
            if not raw_target.exists() or overwrite:
                raw_target.write_text(source_file.read_text(encoding="utf-8-sig"), encoding="utf-8")
        build_archetype_adapter(profile_path, archetype=archetype, output_path=adapter_path, overwrite=overwrite)

    # 3. Pipeline Execution Loop with controlled resume
    args = argparse.Namespace(
        skip_conversion=skip_conversion,
        overwrite=overwrite,
        env_file=None,
        base_url=None,
        mineru_language="zh-CN",
        poll_interval=5,
        max_polls=60,
        request_timeout=300,
        archetype=archetype,
    )

    max_loops = 5
    last_result = None
    for loop in range(max_loops):
        last_result = run_pipeline(profile_path, args)
        if last_result.get("status") == "completed":
            break
        elif last_result.get("status") == "review_required":
            if safe_auto_approve:
                confirmed = auto_confirm_manifests(staging_path)
                if not confirmed:
                    break
            else:
                break
        else:
            break

    # 4. Final Audit
    paths = artifact_paths(profile)
    audit_res = audit_graph(
        profile_path,
        paths["hierarchy_coverage"],
        paths["content"],
        paths["answers"] if paths["answers"].exists() else None,
        paths["canvas"] if paths["canvas"].exists() else None,
    )
    write_json_atomic(paths["audit"], audit_res, overwrite=True)

    status = "passed" if audit_res.get("status") == "passed" else ("review_required" if audit_res.get("warnings") else "failed")
    return {
        "title": title,
        "source": str(source_file),
        "status": status,
        "staging": str(staging_path),
        "graph_root": str(graph_base / slug),
        "audit": audit_res,
    }


def run_batch(
    source_dir: Path,
    staging_base: Path,
    vault_root: Path,
    graph_base: Path,
    archetype: str,
    patterns: list[str] | None = None,
    parallel: int = 1,
    skip_conversion: bool = False,
    safe_auto_approve: bool = True,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Run batch processing across all discovered sources."""
    sources = discover_source_files(source_dir, patterns=patterns)
    print(f"Discovered {len(sources)} sources in {source_dir}")

    results: list[dict[str, Any]] = []

    if parallel > 1 and len(sources) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
            future_to_src = {
                executor.submit(
                    process_single_source,
                    src,
                    staging_base,
                    vault_root,
                    graph_base,
                    archetype,
                    skip_conversion=skip_conversion,
                    safe_auto_approve=safe_auto_approve,
                    overwrite=overwrite,
                ): src
                for src in sources
            }
            for fut in concurrent.futures.as_completed(future_to_src):
                src = future_to_src[fut]
                try:
                    res = fut.result()
                    results.append(res)
                    print(f"[{res['status'].upper()}] {res['title']}")
                except Exception as e:
                    results.append({"source": str(src), "status": "failed", "error": str(e)})
                    print(f"[ERROR] {src.name}: {e}")
    else:
        for src in sources:
            try:
                res = process_single_source(
                    src,
                    staging_base,
                    vault_root,
                    graph_base,
                    archetype,
                    skip_conversion=skip_conversion,
                    safe_auto_approve=safe_auto_approve,
                    overwrite=overwrite,
                )
                results.append(res)
                print(f"[{res['status'].upper()}] {res['title']}")
            except Exception as e:
                results.append({"source": str(src), "status": "failed", "error": str(e)})
                print(f"[ERROR] {src.name}: {e}")

    summary = {
        "schema_version": 1,
        "total": len(sources),
        "passed": sum(1 for r in results if r.get("status") == "passed"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
        "review_required": sum(1 for r in results if r.get("status") == "review_required"),
        "results": results,
    }
    return summary


def add_batch_subparser(subparsers: argparse._SubParsersAction) -> None:
    batch_parser = subparsers.add_parser("batch", description="Batch process exercise PDFs or Markdown collections.")
    batch_parser.add_argument("--source-dir", type=Path, required=True, help="Directory containing source files.")
    batch_parser.add_argument("--staging-base", type=Path, required=True, help="Base staging directory for book profiles.")
    batch_parser.add_argument("--vault-root", type=Path, required=True, help="Root of destination Obsidian vault.")
    batch_parser.add_argument("--graph-base", type=Path, required=True, help="Subdirectory in vault to place generated graphs.")
    batch_parser.add_argument("--archetype", choices=list(ARCHETYPE_REGISTRY.keys()), required=True, help="Adapter archetype.")
    batch_parser.add_argument("--parallel", type=int, default=1, help="Concurrent worker count.")
    batch_parser.add_argument("--skip-conversion", action="store_true", help="Skip MinerU PDF conversion if markdown exists.")
    batch_parser.add_argument("--safe-auto-approve", action="store_true", default=True, help="Safely confirm clean review manifests.")
    batch_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing targets.")

from __future__ import annotations
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from mathos_common import (
    FormattingError, extract_structure, _sha256_text, load_safe_plugin,
    create_fresh_candidate, ApprovedApplyResult, CandidateRunResult
)
from stage1_heading import validate_heading_rules, apply_heading_rules
from stage4_content import (
    validate_content_rules, run_content_rules_protecting_headings,
    run_content_plugin_protecting_headings
)
from stage5_optimize import write_review_report

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

def save_approved_program(
    approved_root: Path,
    plugin_id: str,
    heading_rules: dict,
    plugin_path: Path | None,
    content_rules_path: Path | None,
    original_path: Path,
    candidate_path: Path,
    approving_source_path: Path,
    operations_summary: list[str],
) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", plugin_id):
        raise FormattingError("plugin id may contain only letters, numbers, underscores, and hyphens")
    validate_heading_rules(heading_rules)
    if (plugin_path is None) == (content_rules_path is None):
        raise FormattingError("provide exactly one of plugin_path or content_rules_path")
    content_rules_payload: dict | None = None
    if content_rules_path is not None:
        content_rules_payload = json.loads(content_rules_path.read_text(encoding="utf-8"))
        validate_content_rules(content_rules_payload)
    if plugin_path is not None:
        load_safe_plugin(plugin_path)
    program_dir = approved_root / plugin_id
    if program_dir.exists():
        raise FormattingError(f"approved plugin already exists: {plugin_id}")
    program_dir.mkdir(parents=True)
    original_text = original_path.read_text(encoding="utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    original_structure = extract_structure(original_text, str(original_path))
    candidate_structure = extract_structure(candidate_text, str(candidate_path))
    h1_sample = candidate_structure.h1_sections[0].text if candidate_structure.h1_sections else candidate_text[:2000]
    (program_dir / "heading_rules.json").write_text(json.dumps(heading_rules, ensure_ascii=False, indent=2), encoding="utf-8")
    if content_rules_payload is not None:
        (program_dir / "content_rules.json").write_text(json.dumps(content_rules_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    elif plugin_path is not None:
        shutil.copy2(plugin_path, program_dir / "content_cleaner.py")
    (program_dir / "sample_before.md").write_text(original_text, encoding="utf-8")
    (program_dir / "sample_after.md").write_text(candidate_text, encoding="utf-8")
    metadata = {
        "plugin_id": plugin_id,
        "version": "1.0.0",
        "approval_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file_family_evidence": str(approving_source_path),
        "heading_signature": candidate_structure.heading_level_distribution,
        "toc_signature": bool(original_structure.toc_block),
        "h1_sample_hash": _sha256_text(h1_sample),
        "operations_summary": operations_summary,
        "original_approving_file_path": str(approving_source_path),
        "allowed_scope": "self-check-only",
    }
    (program_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (program_dir / "approval.md").write_text(
        f"# Approval\n\nApproved program: `{plugin_id}`\nApproving source: `{approving_source_path}`\n\nAllowed scope: `self-check-only`\n\n",
        encoding="utf-8"
    )
    return program_dir

def apply_approved_program(program_dir: Path, target_path: Path) -> ApprovedApplyResult:
    heading_rules_payload = json.loads((program_dir / "heading_rules.json").read_text(encoding="utf-8"))
    rules = validate_heading_rules(heading_rules_payload)
    content_rules_path = program_dir / "content_rules.json"
    plugin_path = program_dir / "content_cleaner.py"
    if content_rules_path.exists():
        content_rules_payload = json.loads(content_rules_path.read_text(encoding="utf-8"))
        validate_content_rules(content_rules_payload)
        plugin = None
    elif plugin_path.exists():
        content_rules_payload = None
        plugin = load_safe_plugin(plugin_path)
    else:
        raise FormattingError("approved program must contain content_rules.json or content_cleaner.py")
    candidate_path = create_fresh_candidate(target_path)
    markdown = candidate_path.read_text(encoding="utf-8")
    markdown = apply_heading_rules(markdown, rules)
    metadata_path = program_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("toc_signature", False):
            structure = extract_structure(markdown, "toc-detection")
            if structure.toc_block is not None:
                lines = markdown.splitlines(keepends=True)
                before_toc = lines[:structure.toc_block.start_line - 1]
                after_toc = lines[structure.toc_block.end_line:]
                markdown = "".join(before_toc + after_toc)
    if content_rules_payload is not None:
        plugin_result = run_content_rules_protecting_headings(content_rules_payload, markdown)
    else:
        assert plugin is not None
        plugin_result = run_content_plugin_protecting_headings(plugin, markdown)
    cleaned = plugin_result.cleaned_markdown
    opt_path = program_dir / "heading_optimizations.json"
    if opt_path.exists():
        opt_mapping = json.loads(opt_path.read_text(encoding="utf-8"))
        opt_lines = cleaned.splitlines()
        for idx, l in enumerate(opt_lines):
            stripped = l.strip()
            if stripped in opt_mapping:
                opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
        cleaned = "\n".join(opt_lines) + "\n"
    candidate_path.write_text(cleaned, encoding="utf-8")
    report_path = candidate_path.parent / f"{target_path.stem}.approved-report.md"
    write_review_report(
        original_path=target_path, candidate_path=candidate_path, report_path=report_path,
        heading_summary=[rule.rule_id for rule in rules], plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings
    )
    return ApprovedApplyResult(
        candidate_path=candidate_path, report_path=report_path,
        summary=plugin_result.summary, warnings=plugin_result.warnings
    )

def run_candidate_from_artifacts(
    markdown_path: Path,
    heading_rules_path: Path,
    plugin_path: Path | None = None,
    content_rules_path: Path | None = None,
    heading_optimizations_path: Path | None = None,
) -> CandidateRunResult:
    heading_payload = json.loads(heading_rules_path.read_text(encoding="utf-8"))
    rules = validate_heading_rules(heading_payload)
    if (plugin_path is None) == (content_rules_path is None):
        raise FormattingError("provide exactly one of plugin_path or content_rules_path")
    content_rules_payload: dict | None = None
    plugin = None
    if content_rules_path is not None:
        content_rules_payload = json.loads(content_rules_path.read_text(encoding="utf-8"))
        validate_content_rules(content_rules_payload)
    if plugin_path is not None:
        plugin = load_safe_plugin(plugin_path)
    candidate_path = create_fresh_candidate(markdown_path)
    markdown = candidate_path.read_text(encoding="utf-8")
    markdown = apply_heading_rules(markdown, rules)
    if content_rules_payload is not None:
        plugin_result = run_content_rules_protecting_headings(content_rules_payload, markdown)
    else:
        assert plugin is not None
        plugin_result = run_content_plugin_protecting_headings(plugin, markdown)
    cleaned = plugin_result.cleaned_markdown
    if heading_optimizations_path is not None and heading_optimizations_path.exists():
        opt_mapping = json.loads(heading_optimizations_path.read_text(encoding="utf-8"))
        opt_lines = cleaned.splitlines()
        for idx, l in enumerate(opt_lines):
            stripped = l.strip()
            if stripped in opt_mapping:
                opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
        cleaned = "\n".join(opt_lines) + "\n"
    candidate_path.write_text(cleaned, encoding="utf-8")
    report_path = candidate_path.parent / f"{markdown_path.stem}.candidate-report.md"
    write_review_report(
        original_path=markdown_path, candidate_path=candidate_path, report_path=report_path,
        heading_summary=[rule.rule_id for rule in rules], plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings
    )
    return CandidateRunResult(candidate_path, report_path, plugin_result.summary, plugin_result.warnings)

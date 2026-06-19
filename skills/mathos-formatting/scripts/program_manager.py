from __future__ import annotations
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from mathos_common import (
    ApprovedApplyResult,
    CandidateRunResult,
    FormattingError,
    create_fresh_candidate,
    extract_structure,
    load_safe_plugin,
    run_batch_processor_in_sandbox,
    validate_batch_processor_source,
    validate_candidate_not_too_short,
    validate_title_rewrite_source,
    _sha256_text,
)
from stage1_heading import apply_heading_rules, validate_heading_rules, audit_final_headings
from stage4_content import (
    content_preservation_counts,
    preservation_summary,
    run_content_plugin_protecting_headings,
    run_content_rules_protecting_headings,
    validate_content_preservation,
    validate_content_rules,
)
from stage5_optimize import apply_title_rewrite_map, write_review_report

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _plugin_summary(before_text: str, after_text: str, prefix: str) -> list[str]:
    before = content_preservation_counts(before_text)
    after = content_preservation_counts(after_text)
    validate_content_preservation(before, after)
    return [prefix] + preservation_summary(before, after)


def _copy_validated_batch_script(source_path: Path, target_path: Path) -> None:
    source = source_path.read_text(encoding="utf-8")
    validate_batch_processor_source(source)
    shutil.copy2(source_path, target_path)


def _copy_validated_title_map(source_path: Path, target_path: Path) -> dict[str, str]:
    source = source_path.read_text(encoding="utf-8")
    mapping = validate_title_rewrite_source(source)
    shutil.copy2(source_path, target_path)
    return mapping


def _legacy_save_approved_program(
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
    _write_program_metadata(
        program_dir,
        plugin_id,
        original_text,
        candidate_text,
        approving_source_path,
        operations_summary,
        bool(original_structure.toc_block),
        candidate_structure.heading_level_distribution,
        _sha256_text(h1_sample),
        artifact_mode="legacy-json",
    )
    return program_dir


def _write_program_metadata(
    program_dir: Path,
    plugin_id: str,
    original_text: str,
    candidate_text: str,
    approving_source_path: Path,
    operations_summary: list[str],
    toc_signature: bool,
    heading_signature: dict[int, int],
    h1_sample_hash: str,
    artifact_mode: str,
) -> None:
    (program_dir / "sample_before.md").write_text(original_text, encoding="utf-8")
    (program_dir / "sample_after.md").write_text(candidate_text, encoding="utf-8")
    metadata = {
        "plugin_id": plugin_id,
        "version": "1.0.0",
        "artifact_mode": artifact_mode,
        "approval_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file_family_evidence": str(approving_source_path),
        "heading_signature": heading_signature,
        "toc_signature": toc_signature,
        "h1_sample_hash": h1_sample_hash,
        "operations_summary": operations_summary,
        "original_approving_file_path": str(approving_source_path),
        "allowed_scope": "self-check-only",
    }
    (program_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (program_dir / "approval.md").write_text(
        f"# Approval\n\nApproved program: `{plugin_id}`\nApproving source: `{approving_source_path}`\n\nAllowed scope: `self-check-only`\nArtifact mode: `{artifact_mode}`\n\n",
        encoding="utf-8",
    )


def save_approved_program(
    approved_root: Path,
    plugin_id: str,
    original_path: Path,
    candidate_path: Path,
    approving_source_path: Path,
    operations_summary: list[str],
    heading_script_path: Path | None = None,
    content_script_path: Path | None = None,
    title_rewrite_map_path: Path | None = None,
    heading_rules: dict | None = None,
    plugin_path: Path | None = None,
    content_rules_path: Path | None = None,
) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", plugin_id):
        raise FormattingError("plugin id may contain only letters, numbers, underscores, and hyphens")
    if heading_script_path is None or content_script_path is None:
        if heading_rules is None:
            raise FormattingError("provide Python artifacts or legacy heading_rules")
        return _legacy_save_approved_program(
            approved_root,
            plugin_id,
            heading_rules,
            plugin_path,
            content_rules_path,
            original_path,
            candidate_path,
            approving_source_path,
            operations_summary,
        )

    program_dir = approved_root / plugin_id
    if program_dir.exists():
        raise FormattingError(f"approved plugin already exists: {plugin_id}")
    program_dir.mkdir(parents=True)
    _copy_validated_batch_script(heading_script_path, program_dir / "heading_processor.py")
    _copy_validated_batch_script(content_script_path, program_dir / "content_processor.py")
    if title_rewrite_map_path is not None:
        _copy_validated_title_map(title_rewrite_map_path, program_dir / "title_rewrite_map.py")

    original_text = original_path.read_text(encoding="utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    original_structure = extract_structure(original_text, str(original_path))
    candidate_structure = extract_structure(candidate_text, str(candidate_path))
    h1_sample = candidate_structure.h1_sections[0].text if candidate_structure.h1_sections else candidate_text[:2000]
    _write_program_metadata(
        program_dir,
        plugin_id,
        original_text,
        candidate_text,
        approving_source_path,
        operations_summary,
        bool(original_structure.toc_block),
        candidate_structure.heading_level_distribution,
        _sha256_text(h1_sample),
        artifact_mode="python",
    )
    return program_dir


def _strip_toc_if_needed(markdown: str, program_dir: Path, toc_block = None) -> str:
    metadata_path = program_dir / "metadata.json"
    if not metadata_path.exists():
        return markdown
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not metadata.get("toc_signature", False):
        return markdown
    if toc_block is None:
        structure = extract_structure(markdown, "toc-detection")
        toc_block = structure.toc_block
    if toc_block is None:
        return markdown
    lines = markdown.splitlines(keepends=True)
    before_toc = lines[:toc_block.start_line - 1]
    after_toc = lines[toc_block.end_line:]
    return "".join(before_toc + after_toc)


def _apply_python_program(program_dir: Path, target_path: Path) -> ApprovedApplyResult:
    candidate_path = create_fresh_candidate(target_path)
    markdown = candidate_path.read_text(encoding="utf-8")
    original_text = markdown
    
    # Detect TOC block on the original text before running the heading script
    orig_structure = extract_structure(original_text, "original-toc-detection")
    toc_block = orig_structure.toc_block
    
    heading_script = program_dir / "heading_processor.py"
    content_script = program_dir / "content_processor.py"
    title_map_script = program_dir / "title_rewrite_map.py"
    
    heading_summary = []
    
    # 1. Run heading_processor.py if it exists
    if heading_script.exists():
        markdown = run_batch_processor_in_sandbox(heading_script, markdown, candidate_path.parent, "approved-stage1")
        heading_summary.append("heading_processor.py applied")
        
    # 2. Strip TOC if needed
    markdown = _strip_toc_if_needed(markdown, program_dir, toc_block)
    
    # 3. Run content_processor.py if it exists
    if content_script.exists():
        before_content = markdown
        cleaned = run_batch_processor_in_sandbox(content_script, markdown, candidate_path.parent, "approved-stage4")
        validate_candidate_not_too_short(before_content, cleaned, "approved-stage4")
        summary = _plugin_summary(before_content, cleaned, "Python content processor applied")
        markdown = cleaned
    else:
        summary = []
        
    # 4. Run title_rewrite_map.py if it exists
    if title_map_script.exists():
        mapping = validate_title_rewrite_source(title_map_script.read_text(encoding="utf-8"))
        markdown = apply_title_rewrite_map(markdown, mapping)
        heading_summary.append("title_rewrite_map.py applied")
        
    # 5. Run final heading audit
    final_audit = audit_final_headings(original_text, markdown)
    heading_summary.extend(final_audit)
    
    candidate_path.write_text(markdown, encoding="utf-8")
    report_path = candidate_path.parent / f"{target_path.stem}.approved-report.md"
    write_review_report(
        original_path=target_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=heading_summary,
        plugin_summary=summary,
        warnings=[],
    )
    return ApprovedApplyResult(candidate_path=candidate_path, report_path=report_path, summary=summary, warnings=[])


def _apply_legacy_program(program_dir: Path, target_path: Path) -> ApprovedApplyResult:
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
        raise FormattingError("legacy approved program must contain content_rules.json or content_cleaner.py")
    candidate_path = create_fresh_candidate(target_path)
    markdown = candidate_path.read_text(encoding="utf-8")
    if content_rules_payload is not None:
        plugin_result = run_content_rules_protecting_headings(content_rules_payload, markdown)
    else:
        assert plugin is not None
        plugin_result = run_content_plugin_protecting_headings(plugin, markdown)
    cleaned = plugin_result.cleaned_markdown
    candidate_path.write_text(cleaned, encoding="utf-8")
    report_path = candidate_path.parent / f"{target_path.stem}.approved-report.md"
    write_review_report(
        original_path=target_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=[],
        plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )
    return ApprovedApplyResult(candidate_path, report_path, plugin_result.summary, plugin_result.warnings)


def apply_approved_program(program_dir: Path, target_path: Path) -> ApprovedApplyResult:
    if (program_dir / "heading_processor.py").exists() or (program_dir / "content_processor.py").exists():
        return _apply_python_program(program_dir, target_path)
    return _apply_legacy_program(program_dir, target_path)


def run_candidate_from_artifacts(
    markdown_path: Path,
    heading_script_path: Path | None = None,
    content_script_path: Path | None = None,
    title_rewrite_map_path: Path | None = None,
    heading_rules_path: Path | None = None,
    plugin_path: Path | None = None,
    content_rules_path: Path | None = None,
    heading_optimizations_path: Path | None = None,
) -> CandidateRunResult:
    if heading_script_path is None or content_script_path is None:
        if heading_rules_path is None:
            raise FormattingError("provide Python artifacts or legacy heading_rules_path")
        return _legacy_run_candidate_from_artifacts(
            markdown_path,
            heading_rules_path,
            plugin_path,
            content_rules_path,
            heading_optimizations_path,
        )

    candidate_path = create_fresh_candidate(markdown_path)
    markdown = candidate_path.read_text(encoding="utf-8")
    original_text = markdown
    
    # Detect TOC on original markdown before heading script runs
    orig_structure = extract_structure(original_text, "original-toc-detection")
    toc_block = orig_structure.toc_block
    
    stage1 = run_batch_processor_in_sandbox(heading_script_path, markdown, candidate_path.parent, "candidate-stage1")
    
    # Strip TOC locally if present
    if toc_block is not None:
        lines = stage1.splitlines(keepends=True)
        before_toc = lines[:toc_block.start_line - 1]
        after_toc = lines[toc_block.end_line:]
        stage1 = "".join(before_toc + after_toc)
        
    stage4 = run_batch_processor_in_sandbox(content_script_path, stage1, candidate_path.parent, "candidate-stage4")
    validate_candidate_not_too_short(stage1, stage4, "candidate-stage4")
    summary = _plugin_summary(stage1, stage4, "Python content processor applied")
    if title_rewrite_map_path is not None:
        mapping = validate_title_rewrite_source(title_rewrite_map_path.read_text(encoding="utf-8"))
        stage4 = apply_title_rewrite_map(stage4, mapping)
        
    # Run final heading audit
    final_audit = audit_final_headings(original_text, stage4)
    heading_summary = ["heading_processor.py"] + final_audit
    
    candidate_path.write_text(stage4, encoding="utf-8")
    report_path = candidate_path.parent / f"{markdown_path.stem}.candidate-report.md"
    write_review_report(
        original_path=markdown_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=heading_summary,
        plugin_summary=summary,
        warnings=[],
    )
    return CandidateRunResult(candidate_path, report_path, summary, [])


def _legacy_run_candidate_from_artifacts(
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
        cleaned = apply_title_rewrite_map(cleaned, opt_mapping)
    candidate_path.write_text(cleaned, encoding="utf-8")
    report_path = candidate_path.parent / f"{markdown_path.stem}.candidate-report.md"
    write_review_report(
        original_path=markdown_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=[rule.rule_id for rule in rules],
        plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )
    return CandidateRunResult(candidate_path, report_path, plugin_result.summary, plugin_result.warnings)

from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path
from mathos_common import (
    FormattingError, extract_structure, _write_text_artifact, write_learning_state,
    learning_work_dir_for, learning_candidate_path_for, LearningRunState, LearningRunResult,
    find_total_pages_from_metadata, extract_first_20_pages, parse_json_artifact_from_text
)
from stage1_heading import validate_heading_rules, apply_heading_rules, audit_stage1_headings
from stage2_3_toc import extract_toc_sample, extract_h1_sample
from stage4_content import validate_content_rules, run_content_rules_protecting_headings
from stage5_optimize import run_heading_optimization, write_review_report

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

def _provider_identity(provider_client: object) -> tuple[str, str]:
    return (
        str(getattr(provider_client, "base_url", "")),
        str(getattr(provider_client, "model", "")),
    )

def run_learning_from_provider(
    markdown_path: Path,
    provider_client: object,
    heading_prompt: str,
    content_prompt: str,
    work_dir: Path | None = None,
    timeout_seconds: int = 120,
    h1_index: int = 0,
) -> LearningRunResult:
    markdown_path = markdown_path.resolve()
    work_dir = work_dir or learning_work_dir_for(markdown_path)
    candidate_path = learning_candidate_path_for(markdown_path, work_dir)
    report_path = work_dir / "candidate-report.md"
    artifacts: dict[str, Path] = {}
    warnings: list[str] = []
    errors: list[str] = []
    provider_base_url, provider_model = _provider_identity(provider_client)
    current_stage = "inspect"
    def state(stage: str | None, status: str) -> None:
        write_learning_state(
            work_dir,
            LearningRunState(
                source_path=markdown_path, candidate_path=candidate_path,
                provider_base_url=provider_base_url, provider_model=provider_model,
                stage=stage or current_stage, status=status, artifacts=artifacts,
                warnings=warnings, errors=errors, approved=False
            ),
        )
    try:
        original_text = markdown_path.read_text(encoding="utf-8")
        original_structure = extract_structure(original_text, str(markdown_path))
        current_stage = "toc-sample"
        toc_sample = extract_toc_sample(original_text, original_structure)
        h1_headings = [h for h in original_structure.headings if h.level == 1]
        h1_list = "\n".join(f"# {h.text}" for h in h1_headings)
        toc_and_h1 = (
            "# Table of Contents Sample\n"
            f"{toc_sample.strip()}\n\n"
            "# All H1 Headings in Original Text\n"
            f"{h1_list}\n"
        )
        artifacts["toc_sample"] = _write_text_artifact(work_dir / "toc_sample.md", toc_and_h1)
        current_stage = "heading-provider"
        heading_rules_file = work_dir / "heading_rules.json"
        if heading_rules_file.exists():
            heading_payload = json.loads(heading_rules_file.read_text(encoding="utf-8"))
            rules = validate_heading_rules(heading_payload)
            artifacts["heading_rules"] = heading_rules_file
        else:
            artifacts["heading_prompt"] = _write_text_artifact(work_dir / "heading_rules_prompt.md", heading_prompt)
            heading_response = provider_client.chat(heading_prompt, toc_and_h1, timeout_seconds=timeout_seconds, response_format={"type": "json_object"})
            artifacts["heading_response"] = _write_text_artifact(work_dir / "heading_rules_response.json", heading_response)
            heading_payload = json.loads(parse_json_artifact_from_text(heading_response))
            rules = validate_heading_rules(heading_payload)
            artifacts["heading_rules"] = _write_text_artifact(
                work_dir / "heading_rules.json",
                json.dumps(heading_payload, ensure_ascii=False, indent=2),
            )
        current_stage = "stage1-apply"
        work_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(markdown_path, candidate_path)
        candidate_text = candidate_path.read_text(encoding="utf-8")
        stage1_text = apply_heading_rules(candidate_text, rules)
        candidate_path.write_text(stage1_text, encoding="utf-8")
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=[rule.rule_id for rule in rules], plugin_summary=[], warnings=[]
        )
        current_stage = "stage1-audit"
        stage1_audit_summary = audit_stage1_headings(original_text, stage1_text)
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=[rule.rule_id for rule in rules] + stage1_audit_summary,
            plugin_summary=[], warnings=[]
        )
        current_stage = "toc-detection-provider"
        toc_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "toc_detection_prompt.md"
        toc_prompt = toc_prompt_path.read_text(encoding="utf-8")
        artifacts["toc_detection_prompt"] = _write_text_artifact(work_dir / "toc_detection_prompt.md", toc_prompt)
        toc_sample_20_pages = extract_first_20_pages(stage1_text, markdown_path)
        artifacts["toc_detection_sample"] = _write_text_artifact(work_dir / "toc_detection_sample.md", toc_sample_20_pages)
        toc_detection_response = provider_client.chat(
            toc_prompt, toc_sample_20_pages, timeout_seconds=timeout_seconds, response_format={"type": "json_object"}
        )
        artifacts["toc_detection_response"] = _write_text_artifact(work_dir / "toc_detection_response.json", toc_detection_response)
        toc_detection_payload = json.loads(parse_json_artifact_from_text(toc_detection_response))
        toc_start_line = toc_detection_payload.get("toc_start_line")
        main_text_start_line = toc_detection_payload.get("main_text_start_line")
        stage1_lines = stage1_text.splitlines(keepends=True)
        try:
            main_text_start_line = int(main_text_start_line)
        except (ValueError, TypeError) as exc:
            raise FormattingError(f"LLM returned invalid type/value for main_text_start_line: {main_text_start_line}") from exc
        if main_text_start_line < 1 or main_text_start_line > len(stage1_lines):
            raise FormattingError(f"LLM returned invalid line number: {main_text_start_line}")
        stripped_text = stage1_text
        if toc_start_line is not None:
            try:
                toc_start_line = int(toc_start_line)
                if 1 <= toc_start_line <= main_text_start_line:
                    before_toc = stage1_lines[:toc_start_line - 1]
                    after_toc = stage1_lines[main_text_start_line - 1:]
                    stripped_text = "".join(before_toc + after_toc)
            except (ValueError, TypeError):
                pass
        candidate_path.write_text(stripped_text, encoding="utf-8")
        current_stage = "h1-sample"
        updated_structure = extract_structure(stripped_text, str(candidate_path))
        h1_sample = extract_h1_sample(stripped_text, updated_structure, h1_index=h1_index)
        artifacts["h1_sample"] = _write_text_artifact(work_dir / "h1_sample.md", h1_sample)
        current_stage = "content-provider"
        artifacts["content_prompt"] = _write_text_artifact(work_dir / "content_cleaner_prompt.md", content_prompt)
        content_response = provider_client.chat(
            content_prompt, h1_sample, timeout_seconds=timeout_seconds, response_format={"type": "json_object"}
        )
        artifacts["content_response"] = _write_text_artifact(work_dir / "content_rules_response.json", content_response)
        content_rules_payload = json.loads(parse_json_artifact_from_text(content_response))
        validate_content_rules(content_rules_payload)
        artifacts["content_rules"] = _write_text_artifact(
            work_dir / "content_rules.json", json.dumps(content_rules_payload, ensure_ascii=False, indent=2)
        )
        current_stage = "stage4-apply"
        try:
            plugin_result = run_content_rules_protecting_headings(content_rules_payload, stripped_text)
        except FormattingError:
            candidate_path.write_text(stripped_text, encoding="utf-8")
            raise
        current_stage = "heading-optimization-provider"
        heading_opt_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_optimization_prompt.md"
        heading_opt_prompt = heading_opt_prompt_path.read_text(encoding="utf-8")
        artifacts["heading_opt_prompt"] = _write_text_artifact(work_dir / "heading_optimization_prompt.md", heading_opt_prompt)
        opt_mapping = run_heading_optimization(
            plugin_result.cleaned_markdown, provider_client, heading_opt_prompt, timeout_seconds=timeout_seconds
        )
        final_markdown = plugin_result.cleaned_markdown
        if opt_mapping:
            artifacts["heading_optimizations"] = _write_text_artifact(
                work_dir / "heading_optimizations.json", json.dumps(opt_mapping, ensure_ascii=False, indent=2)
            )
            opt_lines = final_markdown.splitlines()
            for idx, l in enumerate(opt_lines):
                stripped = l.strip()
                if stripped in opt_mapping:
                    opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
            final_markdown = "\n".join(opt_lines) + "\n"
        candidate_path.write_text(final_markdown, encoding="utf-8")
        artifacts["candidate"] = candidate_path
        artifacts["report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path, report_path=report_path,
            heading_summary=[rule.rule_id for rule in rules], plugin_summary=plugin_result.summary,
            warnings=plugin_result.warnings
        )
        warnings.extend(plugin_result.warnings)
        state("complete", "candidate-written")
        return LearningRunResult("candidate-written", work_dir, candidate_path, report_path, artifacts, plugin_result.summary, warnings, errors)
    except Exception as exc:
        if not errors:
            errors.append(str(exc))
        state(None, "failed")
        raise

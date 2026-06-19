from __future__ import annotations
import json
import sys
from pathlib import Path
from mathos_common import (
    FormattingError, extract_structure, _write_text_artifact, write_learning_state,
    learning_work_dir_for, learning_candidate_path_for, LearningRunState, LearningRunResult,
    extract_first_20_pages, parse_json_artifact_from_text, parse_python_source_artifact,
    run_batch_processor_in_sandbox, validate_batch_processor_source, validate_title_rewrite_source,
    validate_candidate_not_too_short,
)
from stage1_heading import audit_stage1_headings, audit_final_headings
from stage2_3_toc import extract_toc_sample, extract_h1_sample
from stage4_content import content_preservation_counts, validate_content_preservation, preservation_summary
from stage5_optimize import apply_title_rewrite_map, write_review_report

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
        heading_script_file = work_dir / "heading_processor.py"
        if heading_script_file.exists():
            heading_source = heading_script_file.read_text(encoding="utf-8")
            validate_batch_processor_source(heading_source)
            artifacts["heading_script"] = heading_script_file
        else:
            artifacts["heading_prompt"] = _write_text_artifact(work_dir / "heading_processor_prompt.md", heading_prompt)
            heading_response = provider_client.chat(heading_prompt, toc_and_h1, timeout_seconds=timeout_seconds, response_format=None)
            artifacts["heading_response"] = _write_text_artifact(work_dir / "heading_processor_response.py", heading_response)
            heading_source = parse_python_source_artifact(heading_response)
            validate_batch_processor_source(heading_source)
            artifacts["heading_script"] = _write_text_artifact(heading_script_file, heading_source)
        current_stage = "stage1-apply"
        work_dir.mkdir(parents=True, exist_ok=True)
        candidate_text = original_text
        stage1_text = run_batch_processor_in_sandbox(heading_script_file, candidate_text, work_dir, "stage1-heading")
        candidate_path.write_text(stage1_text, encoding="utf-8")
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=["heading_processor.py"], plugin_summary=[], warnings=[]
        )
        current_stage = "stage1-audit"
        stage1_audit_summary = audit_stage1_headings(original_text, stage1_text)
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=["heading_processor.py"] + stage1_audit_summary,
            plugin_summary=[], warnings=[]
        )
        current_stage = "h1-sample"
        stage1_structure = extract_structure(stage1_text, str(markdown_path))
        h1_sample = extract_h1_sample(stage1_text, stage1_structure, h1_index=h1_index)
        artifacts["h1_sample"] = _write_text_artifact(work_dir / "h1_sample.md", h1_sample)
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
        content_script_file = work_dir / "content_processor.py"
        if content_script_file.exists():
            content_source = content_script_file.read_text(encoding="utf-8")
            validate_batch_processor_source(content_source)
            artifacts["content_script"] = content_script_file
        else:
            current_stage = "content-provider"
            artifacts["content_prompt"] = _write_text_artifact(work_dir / "content_cleaner_prompt.md", content_prompt)
            content_response = provider_client.chat(
                content_prompt, h1_sample, timeout_seconds=timeout_seconds, response_format=None
            )
            artifacts["content_response"] = _write_text_artifact(work_dir / "content_processor_response.py", content_response)
            content_source = parse_python_source_artifact(content_response)
            validate_batch_processor_source(content_source)
            artifacts["content_script"] = _write_text_artifact(content_script_file, content_source)
        current_stage = "stage4-apply"
        try:
            cleaned_text = run_batch_processor_in_sandbox(content_script_file, stripped_text, work_dir, "stage4-content")
            validate_candidate_not_too_short(stripped_text, cleaned_text, "stage4-content")
            before_preservation = content_preservation_counts(stripped_text)
            after_preservation = content_preservation_counts(cleaned_text)
            validate_content_preservation(before_preservation, after_preservation)
        except FormattingError:
            candidate_path.write_text(stripped_text, encoding="utf-8")
            raise
        plugin_summary = ["content_processor.py applied", *preservation_summary(before_preservation, after_preservation)]
        current_stage = "heading-optimization-provider"
        heading_opt_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_optimization_prompt.md"
        heading_opt_prompt = heading_opt_prompt_path.read_text(encoding="utf-8")
        artifacts["heading_opt_prompt"] = _write_text_artifact(work_dir / "heading_optimization_prompt.md", heading_opt_prompt)
        opt_response = provider_client.chat(
            heading_opt_prompt, cleaned_text, timeout_seconds=timeout_seconds, response_format=None
        )
        artifacts["title_rewrite_response"] = _write_text_artifact(work_dir / "title_rewrite_map_response.py", opt_response)
        title_source = parse_python_source_artifact(opt_response)
        opt_mapping = validate_title_rewrite_source(title_source)
        title_map_path = work_dir / "title_rewrite_map.py"
        artifacts["title_rewrite_map"] = _write_text_artifact(title_map_path, title_source)
        final_markdown = cleaned_text
        if opt_mapping:
            final_markdown = apply_title_rewrite_map(final_markdown, opt_mapping)
        final_audit_summary = audit_final_headings(original_text, final_markdown)
        plugin_summary.extend(final_audit_summary)
        candidate_path.write_text(final_markdown, encoding="utf-8")
        artifacts["candidate"] = candidate_path
        artifacts["report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path, report_path=report_path,
            heading_summary=["heading_processor.py"], plugin_summary=plugin_summary,
            warnings=warnings
        )
        state("complete", "candidate-written")
        return LearningRunResult("candidate-written", work_dir, candidate_path, report_path, artifacts, plugin_summary, warnings, errors)
    except Exception as exc:
        if not errors:
            errors.append(str(exc))
        state(None, "failed")
        raise

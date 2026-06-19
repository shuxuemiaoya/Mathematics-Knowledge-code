from __future__ import annotations
import sys
from pathlib import Path
from mathos_common import (
    FormattingError, extract_structure, _write_text_artifact, write_learning_state,
    learning_work_dir_for, learning_candidate_path_for, LearningRunState, LearningRunResult,
    extract_first_20_pages, parse_python_source_artifact,
    run_batch_processor_in_sandbox, validate_batch_processor_source,
    validate_candidate_not_too_short,
)
from stage1_workflow import (
    build_toc_and_headings_markdown, extract_body_headings, remove_toc_span,
    validate_heading_check_response, validate_heading_processor_result,
    validate_verbatim_toc_response,
)
from stage2_3_toc import extract_h1_sample
from stage4_content import (
    content_preservation_counts, preservation_summary,
    protect_stage2_guarded_content, restore_stage2_guarded_content,
    validate_content_preservation, validate_stage2_heading_preservation,
)
from stage5_optimize import write_review_report

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
    toc_start_line: int | None = None
    toc_end_line: int | None = None
    stage1_validated = False
    def state(stage: str | None, status: str) -> None:
        write_learning_state(
            work_dir,
            LearningRunState(
                source_path=markdown_path, candidate_path=candidate_path,
                provider_base_url=provider_base_url, provider_model=provider_model,
                stage=stage or current_stage, status=status, artifacts=artifacts,
                warnings=warnings, errors=errors, approved=False,
                toc_start_line=toc_start_line, toc_end_line=toc_end_line,
                stage1_validated=stage1_validated,
            ),
        )
    try:
        original_text = markdown_path.read_text(encoding="utf-8")
        current_stage = "toc-extraction"
        toc_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "toc_detection_prompt.md"
        toc_prompt = toc_prompt_path.read_text(encoding="utf-8")
        first_20_pages = extract_first_20_pages(original_text, markdown_path)
        artifacts["toc_detection_prompt"] = _write_text_artifact(work_dir / "toc_detection_prompt.md", toc_prompt)
        artifacts["toc_detection_sample"] = _write_text_artifact(work_dir / "toc_detection_sample.md", first_20_pages)
        toc_response = provider_client.chat(toc_prompt, first_20_pages, timeout_seconds=timeout_seconds, response_format=None)
        artifacts["toc_detection_response"] = _write_text_artifact(work_dir / "toc_detection_response.md", toc_response)
        toc = validate_verbatim_toc_response(first_20_pages, toc_response)
        toc_start_line = toc.start_line
        toc_end_line = toc.end_line
        artifacts["toc"] = _write_text_artifact(work_dir / "toc.md", toc.markdown)
        body_headings = extract_body_headings(original_text, toc.start_line, toc.end_line)
        toc_and_headings = build_toc_and_headings_markdown(toc.markdown, body_headings)
        artifacts["toc_and_headings"] = _write_text_artifact(work_dir / "toc_and_headings.md", toc_and_headings)
        current_stage = "heading-provider"
        heading_script_file = work_dir / "heading_processor.py"
        if heading_script_file.exists():
            heading_source = heading_script_file.read_text(encoding="utf-8")
            validate_batch_processor_source(heading_source)
            artifacts["heading_script"] = heading_script_file
        else:
            artifacts["heading_prompt"] = _write_text_artifact(work_dir / "heading_processor_prompt.md", heading_prompt)
            heading_response = provider_client.chat(
                heading_prompt, toc_and_headings, timeout_seconds=timeout_seconds, response_format=None
            )
            artifacts["heading_response"] = _write_text_artifact(work_dir / "heading_processor_response.py", heading_response)
            heading_source = parse_python_source_artifact(heading_response)
            validate_batch_processor_source(heading_source)
            artifacts["heading_script"] = _write_text_artifact(heading_script_file, heading_source)
        current_stage = "stage1-apply"
        work_dir.mkdir(parents=True, exist_ok=True)
        candidate_text = original_text
        stage1_text = run_batch_processor_in_sandbox(heading_script_file, candidate_text, work_dir, "stage1-heading")
        processor_summary = validate_heading_processor_result(original_text, stage1_text)
        candidate_path.write_text(stage1_text, encoding="utf-8")
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=["heading_processor.py", *processor_summary], plugin_summary=[], warnings=[]
        )
        current_stage = "toc-removal"
        stripped_text = remove_toc_span(stage1_text, toc.start_line, toc.end_line)
        candidate_path.write_text(stripped_text, encoding="utf-8")
        current_stage = "heading-validation"
        final_headings = extract_body_headings(stripped_text, 0, -1)
        heading_check_input = build_toc_and_headings_markdown(toc.markdown, final_headings)
        artifacts["heading_check_input"] = _write_text_artifact(
            work_dir / "heading_check_input.md", heading_check_input
        )
        heading_check_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_check_prompt.md"
        heading_check_prompt = heading_check_prompt_path.read_text(encoding="utf-8")
        artifacts["heading_check_prompt"] = _write_text_artifact(
            work_dir / "heading_check_prompt.md", heading_check_prompt
        )
        heading_check_response = provider_client.chat(
            heading_check_prompt,
            heading_check_input,
            timeout_seconds=timeout_seconds,
            response_format={"type": "json_object"},
        )
        artifacts["heading_check_response"] = _write_text_artifact(
            work_dir / "heading_check_response.json", heading_check_response
        )
        heading_check_summary = validate_heading_check_response(
            heading_check_response, expected_heading_count=len(final_headings)
        )
        stage1_validated = True
        state(current_stage, "stage1-validated")
        current_stage = "h1-sample"
        stripped_structure = extract_structure(stripped_text, str(markdown_path))
        h1_sample = extract_h1_sample(stripped_text, stripped_structure, h1_index=h1_index)
        artifacts["h1_sample"] = _write_text_artifact(work_dir / "h1_sample.md", h1_sample)
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
            protected_stage2_text, guarded_tokens = protect_stage2_guarded_content(stripped_text)
            processed_stage2_text = run_batch_processor_in_sandbox(
                content_script_file, protected_stage2_text, work_dir, "stage4-content"
            )
            cleaned_text = restore_stage2_guarded_content(processed_stage2_text, guarded_tokens)
            validate_candidate_not_too_short(stripped_text, cleaned_text, "stage4-content")
            stage2_heading_summary = validate_stage2_heading_preservation(stripped_text, cleaned_text)
            before_preservation = content_preservation_counts(stripped_text)
            after_preservation = content_preservation_counts(cleaned_text)
            validate_content_preservation(before_preservation, after_preservation)
        except FormattingError:
            candidate_path.write_text(stripped_text, encoding="utf-8")
            raise
        plugin_summary = [
            "content_processor.py applied",
            *stage2_heading_summary,
            *preservation_summary(before_preservation, after_preservation),
        ]
        plugin_summary.extend(processor_summary)
        plugin_summary.extend(heading_check_summary)
        final_markdown = cleaned_text
        candidate_path.write_text(final_markdown, encoding="utf-8")
        artifacts["candidate"] = candidate_path
        artifacts["report"] = write_review_report(
            original_path=markdown_path, candidate_path=candidate_path, report_path=report_path,
            heading_summary=["heading_processor.py", *heading_check_summary], plugin_summary=plugin_summary,
            warnings=warnings
        )
        state("complete", "candidate-written")
        return LearningRunResult("candidate-written", work_dir, candidate_path, report_path, artifacts, plugin_summary, warnings, errors)
    except Exception as exc:
        if not errors:
            errors.append(str(exc))
        state(None, "failed")
        raise

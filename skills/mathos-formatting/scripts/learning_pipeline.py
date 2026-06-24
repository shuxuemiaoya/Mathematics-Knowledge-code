from __future__ import annotations

from pathlib import Path

from mathos_common import (
    LearningRunResult,
    LearningRunState,
    learning_candidate_path_for,
    learning_work_dir_for,
    write_learning_state,
)
from reporting import write_review_report
from step1_toc_extraction import run_toc_extraction
from step2_heading_extraction import run_heading_extraction
from step3_heading_processing import run_heading_processing
from step4_toc_removal import run_toc_removal
from step5_heading_validation import run_heading_validation
from step6_content_processing import run_content_processing


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
    current_step = "inspect"
    toc_start_line: int | None = None
    toc_end_line: int | None = None
    stage1_validated = False

    def state(step: str | None, status: str) -> None:
        write_learning_state(
            work_dir,
            LearningRunState(
                source_path=markdown_path,
                candidate_path=candidate_path,
                provider_base_url=provider_base_url,
                provider_model=provider_model,
                stage=step or current_step,
                status=status,
                artifacts=artifacts,
                warnings=warnings,
                errors=errors,
                approved=False,
                toc_start_line=toc_start_line,
                toc_end_line=toc_end_line,
                stage1_validated=stage1_validated,
            ),
        )

    try:
        original_text = markdown_path.read_text(encoding="utf-8")

        current_step = "step1-toc-extraction"
        toc = run_toc_extraction(
            markdown_path, original_text, provider_client, work_dir, artifacts, timeout_seconds
        )
        toc_start_line, toc_end_line = toc.start_line, toc.end_line

        current_step = "step2-heading-extraction"
        heading_payload = run_heading_extraction(original_text, toc, work_dir, artifacts)

        current_step = "step3-heading-processing"
        heading_result = run_heading_processing(
            markdown_path,
            original_text,
            heading_payload,
            heading_prompt,
            provider_client,
            work_dir,
            candidate_path,
            artifacts,
            timeout_seconds,
            toc_markdown=toc.markdown,
        )

        current_step = "step4-toc-removal"
        stripped_text = run_toc_removal(heading_result.markdown, toc, candidate_path)

        current_step = "step5-heading-validation"
        heading_check_summary = run_heading_validation(
            stripped_text, toc, provider_client, work_dir, artifacts, timeout_seconds
        )
        stage1_validated = True
        state(current_step, "stage1-validated")

        current_step = "step6-content-processing"
        content_result = run_content_processing(
            markdown_path,
            stripped_text,
            content_prompt,
            provider_client,
            work_dir,
            candidate_path,
            artifacts,
            timeout_seconds,
            h1_index,
        )

        summary = [*content_result.summary, *heading_result.summary, *heading_check_summary]
        candidate_path.write_text(content_result.markdown, encoding="utf-8")
        artifacts["candidate"] = candidate_path
        artifacts["report"] = write_review_report(
            original_path=markdown_path,
            candidate_path=candidate_path,
            report_path=report_path,
            heading_summary=["heading_processor.py", *heading_check_summary],
            plugin_summary=summary,
            warnings=warnings,
        )
        state("complete", "candidate-written")
        return LearningRunResult(
            "candidate-written", work_dir, candidate_path, report_path, artifacts, summary, warnings, errors
        )
    except Exception as exc:
        if not errors:
            errors.append(str(exc))
        state(None, "failed")
        raise

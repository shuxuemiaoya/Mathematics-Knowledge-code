from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from learning_pipeline import run_learning_from_provider
from mathos_common import (
    FormattingError,
    content_preservation_counts,
    learning_work_dir_for,
    validate_candidate_not_too_short,
    validate_content_preservation,
)


@dataclass(frozen=True)
class AutomatedRunResult:
    exit_code: int
    digest_path: Path
    digest: dict[str, object]


ERROR_ARTIFACTS = {
    "step1-toc-extraction": "toc_detection_response.md",
    "step2-heading-extraction": "toc_and_headings.md",
    "step3-heading-processing": "heading_processor_response.py",
    "step4-toc-removal": "stage1_heading_report.md",
    "step5-heading-validation": "heading_check_response.json",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _execution_fingerprint(
    source_bytes: bytes,
    heading_prompt: str,
    provider_client: object,
    timeout_seconds: int,
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/automation_runner.py
    h1_index: int,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/automation_runner.py
) -> str:
    payload = {
        "source_sha256": _sha256_bytes(source_bytes),
        "heading_prompt_sha256": _sha256_bytes(heading_prompt.encode("utf-8")),
        "provider_base_url": str(getattr(provider_client, "base_url", "")),
        "provider_model": str(getattr(provider_client, "model", "")),
        "timeout_seconds": timeout_seconds,
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/automation_runner.py
        "h1_index": h1_index,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/automation_runner.py
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return _sha256_bytes(encoded)


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def _prepare_recovery(work_dir: Path, fingerprint: str) -> bool:
    checkpoint_path = work_dir / "automation-checkpoint.json"
    resumed = False
    if checkpoint_path.exists():
        try:
            previous = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            resumed = previous.get("execution_fingerprint") == fingerprint
        except (json.JSONDecodeError, OSError):
            resumed = False
    if not resumed:
        for name in ("heading_processor.py",):
            artifact = work_dir / name
            if artifact.exists():
                artifact.unlink()
    _write_json(
        checkpoint_path,
        {"execution_fingerprint": fingerprint, "recovery_enabled": True},
    )
    return resumed


def _load_run_state(work_dir: Path) -> dict[str, object]:
    path = work_dir / "run-state.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _failure_artifact(work_dir: Path, failed_stage: str) -> Path:
    preferred = work_dir / ERROR_ARTIFACTS.get(failed_stage, "run-state.json")
    if preferred.exists():
        return preferred
    state_path = work_dir / "run-state.json"
    if state_path.exists():
        return state_path
    return _write_json(
        work_dir / "run-error.json",
        {"failed_stage": failed_stage, "message": "No stage artifact was written."},
    )


def _self_check(
    source_path: Path,
    source_bytes: bytes,
    candidate_path: Path,
    report_path: Path,
) -> None:
    if source_path.read_bytes() != source_bytes:
        raise FormattingError("source Markdown changed during automated formatting")
    if not candidate_path.is_file():
        raise FormattingError("candidate Markdown is missing")
    if not report_path.is_file():
        raise FormattingError("candidate report is missing")
    source_text = source_bytes.decode("utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    validate_candidate_not_too_short(source_text, candidate_text, "automated self-check")
    if not any(line.lstrip().startswith("#") for line in candidate_text.splitlines()):
        raise FormattingError("candidate contains no Markdown headings")
    validate_content_preservation(
        content_preservation_counts(source_text),
        content_preservation_counts(candidate_text),
    )


def run_automated_formatting(
    markdown_path: Path,
    provider_client: object,
    heading_prompt: str,
    work_dir: Path | None = None,
    timeout_seconds: int = 120,
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/automation_runner.py
    h1_index: int = 0,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/automation_runner.py
) -> AutomatedRunResult:
    markdown_path = markdown_path.resolve()
    work_dir = (work_dir or learning_work_dir_for(markdown_path)).resolve()
    digest_path = work_dir / "result-summary.json"
    source_bytes = b""
    resumed = False
    try:
        source_bytes = markdown_path.read_bytes()
        fingerprint = _execution_fingerprint(
            source_bytes,
            heading_prompt,
            provider_client,
            timeout_seconds,
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/automation_runner.py
            h1_index,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/automation_runner.py
        )
        resumed = _prepare_recovery(work_dir, fingerprint)
        result = run_learning_from_provider(
            markdown_path=markdown_path,
            provider_client=provider_client,
            heading_prompt=heading_prompt,
            work_dir=work_dir,
            timeout_seconds=timeout_seconds,
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/automation_runner.py
            h1_index=h1_index,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/automation_runner.py
        )
        state = _load_run_state(work_dir)
        if state.get("status") != "candidate-written" or state.get("stage1_validated") is not True:
            raise FormattingError("learning pipeline did not reach a validated candidate state")
        _self_check(markdown_path, source_bytes, result.candidate_path, result.report_path)
        digest: dict[str, object] = {
            "status": "passed",
            "failed_stage": None,
            "error_artifact": None,
            "source_unchanged": True,
            "stage1_validated": True,
            "preservation_validated": True,
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "run_state_path": str(work_dir / "run-state.json"),
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/automation_runner.py
            "safe_to_approve": True,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/automation_runner.py
            "resumed": resumed,
            "warnings": result.warnings,
            "errors": [],
            "next_action": "review-candidate",
        }
        _write_json(digest_path, digest)
        return AutomatedRunResult(0, digest_path, digest)
    except Exception as exc:
        state = _load_run_state(work_dir)
        failed_stage = str(state.get("stage") or "automation-setup")
        explicit_artifact = getattr(exc, "error_artifact", None)
        if isinstance(explicit_artifact, Path) and explicit_artifact.is_file():
            error_artifact = explicit_artifact
        else:
            error_artifact = _failure_artifact(work_dir, failed_stage)
        source_unchanged = bool(source_bytes) and markdown_path.exists() and markdown_path.read_bytes() == source_bytes
        digest = {
            "status": "failed",
            "failed_stage": failed_stage,
            "error_artifact": str(error_artifact),
            "source_unchanged": source_unchanged,
            "stage1_validated": state.get("stage1_validated") is True,
            "preservation_validated": False,
            "candidate_path": str(state.get("candidate_path") or work_dir / "candidate.md"),
            "report_path": str(work_dir / "candidate-report.md"),
            "run_state_path": str(work_dir / "run-state.json"),
<<<<<<< Updated upstream:skills/mathos-formatting/scripts/automation_runner.py
            "safe_to_approve": False,
=======
>>>>>>> Stashed changes:MathOS Agent/skills/mathos-formatting/scripts/automation_runner.py
            "resumed": resumed,
            "warnings": state.get("warnings", []),
            "errors": [str(exc)],
            "next_action": "inspect-error-artifact",
        }
        _write_json(digest_path, digest)
        return AutomatedRunResult(1, digest_path, digest)

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_VERSION = 1
ALLOWED_STAGE_STATUSES = {
    "pending",
    "in_progress",
    "completed",
    "not_applicable",
    "failed",
    "blocked",
    "stale",
    "failed_visual_qa",
}
REUSABLE_STAGE_STATUSES = {"completed", "not_applicable"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_REQUIRED_STAGES = {
    "order",
    "convert",
    "question_only_bootstrap",
    "reformat",
    "supplement",
    "render",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
        return True
    except ValueError:
        return False


def load_state(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Pipeline state root must be a JSON object.")
    return value


def validate_pipeline_state(folder: Path, state_path: Path) -> dict[str, Any]:
    folder = folder.resolve()
    state_path = state_path.resolve()
    errors: list[str] = []
    artifact_results: list[dict[str, Any]] = []

    if not folder.is_dir():
        errors.append(f"Exam folder does not exist: {folder}")
    if not state_path.is_file():
        errors.append(f"Pipeline state does not exist: {state_path}")
        return {
            "status": "stale",
            "folder": str(folder),
            "pipeline_state": str(state_path),
            "errors": errors,
            "artifact_results": artifact_results,
            "reusable_stages": [],
            "resume_from": None,
        }

    try:
        state = load_state(state_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"Cannot read pipeline state: {exc}")
        return {
            "status": "stale",
            "folder": str(folder),
            "pipeline_state": str(state_path),
            "errors": errors,
            "artifact_results": artifact_results,
            "reusable_stages": [],
            "resume_from": None,
        }

    if state.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        errors.append(
            f"Unsupported schema_version: {state.get('schema_version')!r}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}."
        )

    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("run_id must be a nonempty string.")

    recorded_folder = state.get("folder")
    if not isinstance(recorded_folder, str):
        errors.append("Missing absolute folder field.")
    else:
        recorded_path = Path(recorded_folder).expanduser().resolve()
        if recorded_path != folder:
            errors.append(f"Folder mismatch: state records {recorded_path}, requested {folder}.")

    stage_order = state.get("stage_order")
    if not isinstance(stage_order, list) or not all(isinstance(item, str) for item in stage_order):
        errors.append("stage_order must be an array of stage names.")
        stage_order = []
    elif len(stage_order) != len(set(stage_order)):
        errors.append("stage_order must not contain duplicate stage names.")

    stages = state.get("stages")
    if not isinstance(stages, dict):
        errors.append("stages must be an object.")
        stages = {}
    for stage, payload in stages.items():
        status = payload.get("status") if isinstance(payload, dict) else None
        if status not in ALLOWED_STAGE_STATUSES:
            errors.append(f"Stage {stage!r} has invalid status {status!r}.")

    artifacts = state.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be an array.")
        artifacts = []

    artifact_failures_by_stage: set[str] = set()
    artifact_stages: set[str] = set()
    for index, artifact in enumerate(artifacts):
        result: dict[str, Any] = {"index": index, "valid": False}
        if not isinstance(artifact, dict):
            errors.append(f"Artifact {index} must be an object.")
            artifact_results.append(result)
            continue

        stage = artifact.get("stage")
        role = artifact.get("role")
        raw_path = artifact.get("path")
        expected_hash = artifact.get("sha256")
        result.update({"stage": stage, "role": role, "path": raw_path})

        if not isinstance(stage, str) or not stage:
            errors.append(f"Artifact {index} has no stage.")
            stage = f"<artifact-{index}>"
        else:
            artifact_stages.add(stage)
        if not isinstance(role, str) or not role:
            errors.append(f"Artifact {index} has no role.")
        if not isinstance(raw_path, str):
            errors.append(f"Artifact {index} has no path.")
            artifact_failures_by_stage.add(stage)
            artifact_results.append(result)
            continue
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            errors.append(f"Artifact {index} has an invalid sha256.")
            artifact_failures_by_stage.add(stage)
            artifact_results.append(result)
            continue

        artifact_path = Path(raw_path).expanduser()
        if not artifact_path.is_absolute():
            errors.append(f"Artifact {index} path is not absolute: {artifact_path}")
            artifact_failures_by_stage.add(stage)
            artifact_results.append(result)
            continue
        artifact_path = artifact_path.resolve()
        if not is_within(artifact_path, folder):
            errors.append(f"Artifact {index} is outside the exam folder: {artifact_path}")
            artifact_failures_by_stage.add(stage)
            artifact_results.append(result)
            continue
        if not artifact_path.is_file():
            errors.append(f"Artifact {index} is missing: {artifact_path}")
            artifact_failures_by_stage.add(stage)
            artifact_results.append(result)
            continue

        actual_hash = sha256(artifact_path)
        result["actual_sha256"] = actual_hash
        if actual_hash != expected_hash:
            errors.append(f"Artifact {index} hash mismatch: {artifact_path}")
            artifact_failures_by_stage.add(stage)
            artifact_results.append(result)
            continue
        result["valid"] = True
        artifact_results.append(result)

    for stage, payload in stages.items():
        status = payload.get("status") if isinstance(payload, dict) else None
        if (
            status == "completed"
            and stage in ARTIFACT_REQUIRED_STAGES
            and stage not in artifact_stages
        ):
            errors.append(f"Completed stage {stage!r} has no reusable artifact record.")
            artifact_failures_by_stage.add(stage)

    image_cleaning = state.get("image_cleaning")
    if not isinstance(image_cleaning, dict):
        errors.append("image_cleaning must be an object.")
        image_cleaning = {}
    if not isinstance(state.get("papers"), list):
        errors.append("papers must be an array.")
    if not isinstance(state.get("eligible_to_render"), bool):
        errors.append("eligible_to_render must be a boolean.")
    if not isinstance(state.get("publishing_complete"), bool):
        errors.append("publishing_complete must be a boolean.")

    image_stage = stages.get("batch_clean_images")
    image_status = image_stage.get("status") if isinstance(image_stage, dict) else None
    if image_status == "completed":
        if image_cleaning.get("image_replacement_status") != "completed":
            errors.append("Completed image stage requires image_replacement_status 'completed'.")
            artifact_failures_by_stage.add("batch_clean_images")
        if image_cleaning.get("image_quality_status") not in {"unverified", "passed", "failed"}:
            errors.append("image_quality_status must be unverified, passed, or failed.")
            artifact_failures_by_stage.add("batch_clean_images")
        backup = image_cleaning.get("backup_folder")
        if not isinstance(backup, str):
            errors.append("Completed image stage requires backup_folder.")
            artifact_failures_by_stage.add("batch_clean_images")
        else:
            backup_path = Path(backup).expanduser()
            if (
                not backup_path.is_absolute()
                or not is_within(backup_path.resolve(), folder)
                or not backup_path.is_dir()
            ):
                errors.append(f"Image backup folder is missing or invalid: {backup_path}")
                artifact_failures_by_stage.add("batch_clean_images")
        if not isinstance(image_cleaning.get("replacements"), list):
            errors.append("Completed image stage requires a replacements array.")
            artifact_failures_by_stage.add("batch_clean_images")
            replacements: list[Any] = []
        else:
            replacements = image_cleaning["replacements"]
        if not isinstance(image_cleaning.get("failed_paths"), list):
            errors.append("Completed image stage requires a failed_paths array.")
            artifact_failures_by_stage.add("batch_clean_images")

        if isinstance(backup, str):
            backup_path = Path(backup).expanduser().resolve()
            backup_parent = backup_path.parent
            for index, replacement in enumerate(replacements):
                if not isinstance(replacement, dict):
                    errors.append(f"Image replacement {index} must be an object.")
                    artifact_failures_by_stage.add("batch_clean_images")
                    continue
                raw_path = replacement.get("path")
                source_hash = replacement.get("source_sha256")
                replacement_hash = replacement.get("replacement_sha256")
                if not isinstance(raw_path, str):
                    errors.append(f"Image replacement {index} has no path.")
                    artifact_failures_by_stage.add("batch_clean_images")
                    continue
                if not isinstance(source_hash, str) or not SHA256_PATTERN.fullmatch(source_hash):
                    errors.append(f"Image replacement {index} has invalid source_sha256.")
                    artifact_failures_by_stage.add("batch_clean_images")
                    continue
                if not isinstance(replacement_hash, str) or not SHA256_PATTERN.fullmatch(
                    replacement_hash
                ):
                    errors.append(f"Image replacement {index} has invalid replacement_sha256.")
                    artifact_failures_by_stage.add("batch_clean_images")
                    continue
                current_path = Path(raw_path).expanduser()
                if not current_path.is_absolute():
                    errors.append(f"Image replacement {index} path is not absolute.")
                    artifact_failures_by_stage.add("batch_clean_images")
                    continue
                current_path = current_path.resolve()
                if not is_within(current_path, backup_parent) or not current_path.is_file():
                    errors.append(f"Image replacement {index} current path is missing or invalid.")
                    artifact_failures_by_stage.add("batch_clean_images")
                    continue
                try:
                    relative_path = current_path.relative_to(backup_parent)
                except ValueError:
                    errors.append(f"Image replacement {index} is outside the image folder.")
                    artifact_failures_by_stage.add("batch_clean_images")
                    continue
                original_path = backup_path / relative_path
                if not original_path.is_file() or sha256(original_path) != source_hash:
                    errors.append(
                        f"Image replacement {index} original backup is missing or mismatched."
                    )
                    artifact_failures_by_stage.add("batch_clean_images")
                if sha256(current_path) != replacement_hash:
                    errors.append(f"Image replacement {index} current hash mismatches.")
                    artifact_failures_by_stage.add("batch_clean_images")

    eligible_to_render = state.get("eligible_to_render")
    publishing_complete = state.get("publishing_complete")
    quality_status = image_cleaning.get("image_quality_status") if isinstance(image_cleaning, dict) else None
    if eligible_to_render is True and quality_status == "failed":
        errors.append("eligible_to_render cannot be true when image_quality_status is failed.")
    if publishing_complete is True and quality_status != "passed":
        errors.append("publishing_complete requires image_quality_status 'passed'.")
    if publishing_complete is True and eligible_to_render is not True:
        errors.append("publishing_complete requires eligible_to_render true.")

    reusable_stages: list[str] = []
    resume_from: str | None = None
    for stage in stage_order:
        payload = stages.get(stage)
        status = payload.get("status") if isinstance(payload, dict) else None
        if status in REUSABLE_STAGE_STATUSES and stage not in artifact_failures_by_stage:
            reusable_stages.append(stage)
            continue
        resume_from = stage
        break

    return {
        "status": "valid" if not errors else "stale",
        "folder": str(folder),
        "pipeline_state": str(state_path),
        "schema_version": state.get("schema_version"),
        "run_id": state.get("run_id"),
        "errors": errors,
        "artifact_results": artifact_results,
        "reusable_stages": reusable_stages,
        "resume_from": resume_from,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an Exam Paper Organizer pipeline state before resuming a run."
    )
    parser.add_argument("folder", help="Resolved exam folder.")
    parser.add_argument("pipeline_state", help="Path to pipeline-state.json.")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    result = validate_pipeline_state(
        Path(args.folder).expanduser(),
        Path(args.pipeline_state).expanduser(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())

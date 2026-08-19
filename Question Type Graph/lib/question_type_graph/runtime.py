from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import ConfigurationError, load_json, load_profile, sha256_file, write_json_atomic


STAGES = [
    "intake",
    "preflight",
    "pdf-conversion",
    "format-inventory",
    "hierarchy-segmentation",
    "content-segmentation",
    "answer-matching",
    "solution-supplement",
    "markdown-standardization",
    "canvas",
    "final-audit",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def input_fingerprint(paths: list[Path], values: dict[str, Any] | None = None) -> str:
    """Hash a stage's immutable inputs and relevant configuration values."""
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=str):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii") if path.is_file() else b"missing")
        digest.update(b"\0")
    digest.update(json.dumps(values or {}, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def implementation_paths(*module_names: str) -> list[Path]:
    """Return local compiler modules that must participate in stage caching.

    Stage contracts describe data-shape versions, but they do not change on
    every implementation fix. Hashing the concrete modules prevents a resume
    from reusing manifests produced by older compiler semantics.
    """
    package_root = Path(__file__).resolve().parent
    paths = [package_root / f"{name}.py" for name in module_names]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(
            "Compiler implementation module is missing: "
            + ", ".join(str(path) for path in missing)
        )
    return paths


def init_state(profile_path: Path, output: Path, overwrite: bool = False) -> dict[str, Any]:
    profile = load_profile(profile_path)
    state = {
        "schema_version": 2,
        "profile": profile["_profile_path"],
        "status": "active",
        "created_at": now(),
        "updated_at": now(),
        "runs": [],
        "active_run_id": None,
        "stages": {name: {"status": "pending", "attempts": 0} for name in STAGES},
    }
    state["stages"]["intake"] = {"status": "completed", "attempts": 1, "completed_at": now()}
    write_json_atomic(output, state, overwrite=overwrite)
    return state


def begin_run(state_path: Path, command: str) -> str:
    """Append a stable invocation record without rewriting completed runs."""
    state = load_json(state_path)
    runs = state.setdefault("runs", [])
    run_id = f"run-{len(runs) + 1:06d}"
    runs.append(
        {
            "run_id": run_id,
            "command": command,
            "status": "running",
            "started_at": now(),
            "stage_attempt_ids": [],
        }
    )
    state["schema_version"] = max(int(state.get("schema_version", 1)), 2)
    state["active_run_id"] = run_id
    state["status"] = "active"
    state["updated_at"] = now()
    write_json_atomic(state_path, state, overwrite=True)
    return run_id


def finish_run(
    state_path: Path,
    run_id: str,
    status: str,
    result: dict[str, Any] | None = None,
) -> None:
    if status not in {"passed", "failed", "review_required"}:
        raise ConfigurationError("Invalid run status")
    state = load_json(state_path)
    record = next(
        (item for item in state.get("runs", []) if item.get("run_id") == run_id),
        None,
    )
    if record is None or record.get("status") != "running":
        raise ConfigurationError(f"Run is not active: {run_id}")
    record["status"] = status
    record["completed_at"] = now()
    try:
        started = datetime.fromisoformat(str(record["started_at"]))
        completed = datetime.fromisoformat(str(record["completed_at"]))
        record["duration_seconds"] = round((completed - started).total_seconds(), 3)
    except ValueError:
        pass
    if result:
        record["result"] = {
            key: result[key]
            for key in ("status", "next_stage", "graph_root", "pipeline_state")
            if key in result
        }
    history_root = state_path.resolve().parent / "run-history"
    run_manifest = history_root / f"{run_id}.json"
    if run_manifest.exists():
        raise ConfigurationError(f"Immutable run manifest already exists: {run_manifest}")
    manifest_value = {
        "schema_version": 1,
        "profile": state.get("profile"),
        **record,
    }
    write_json_atomic(run_manifest, manifest_value, overwrite=False)
    record["manifest"] = str(run_manifest.resolve())
    state["active_run_id"] = None
    state["status"] = "completed" if status == "passed" else status
    state["updated_at"] = now()
    write_json_atomic(state_path, state, overwrite=True)


def update_stage(
    state_path: Path,
    stage: str,
    status: str,
    artifacts: list[Path] | None = None,
    message: str | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    if stage not in STAGES or status not in {"running", "completed", "failed", "review_required", "skipped"}:
        raise ConfigurationError("Invalid runtime stage or status")
    state = load_json(state_path)
    load_profile(Path(state["profile"]))
    record = state["stages"].setdefault(stage, {"status": "pending", "attempts": 0})
    if status == "running":
        state["status"] = "active"
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["started_at"] = now()
        record.pop("completed_at", None)
        run_id = state.get("active_run_id") or "legacy-run"
        attempt_id = f"{run_id}:{stage}:{int(record['attempts']):03d}"
        record["active_attempt_id"] = attempt_id
        record.setdefault("attempt_history", []).append(
            {
                "attempt_id": attempt_id,
                "run_id": run_id,
                "status": "running",
                "started_at": record["started_at"],
                **({"input_fingerprint": fingerprint} if fingerprint is not None else {}),
            }
        )
        for run in state.get("runs", []):
            if run.get("run_id") == run_id:
                run.setdefault("stage_attempt_ids", []).append(attempt_id)
                break
    record["status"] = status
    if status in {"completed", "failed", "review_required", "skipped"}:
        record["completed_at"] = now()
        if record.get("started_at"):
            try:
                started = datetime.fromisoformat(str(record["started_at"]))
                completed = datetime.fromisoformat(str(record["completed_at"]))
                record["duration_seconds"] = round((completed - started).total_seconds(), 3)
            except ValueError:
                pass
        active_attempt_id = record.pop("active_attempt_id", None)
        attempt = next(
            (
                item
                for item in reversed(record.get("attempt_history", []))
                if item.get("attempt_id") == active_attempt_id
            ),
            None,
        )
        if attempt is not None:
            attempt["status"] = status
            attempt["completed_at"] = record["completed_at"]
            if "duration_seconds" in record:
                attempt["duration_seconds"] = record["duration_seconds"]
            if message:
                attempt["message"] = message
    if message:
        record["message"] = message
    elif status == "running":
        record.pop("message", None)
    if fingerprint is not None:
        record["input_fingerprint"] = fingerprint
    if artifacts is not None:
        recorded_artifacts = [
            {"path": str(path.resolve()), "sha256": sha256_file(path.resolve())}
            for path in artifacts
        ]
        record["artifacts"] = recorded_artifacts
        if status in {"completed", "failed", "review_required", "skipped"}:
            active_attempt_id = record.get("active_attempt_id")
            attempt = next(
                (
                    item
                    for item in reversed(record.get("attempt_history", []))
                    if item.get("attempt_id") == active_attempt_id
                    or (
                        active_attempt_id is None
                        and item.get("completed_at") == record.get("completed_at")
                    )
                ),
                None,
            )
            if attempt is not None:
                attempt["artifacts"] = recorded_artifacts
    if status in {"completed", "failed", "review_required", "skipped"}:
        terminal_attempt = next(
            (
                item
                for item in reversed(record.get("attempt_history", []))
                if item.get("completed_at") == record.get("completed_at")
            ),
            None,
        )
        if terminal_attempt is not None and not terminal_attempt.get("manifest"):
            attempt_id = str(terminal_attempt["attempt_id"])
            manifest_path = (
                state_path.resolve().parent
                / "run-history"
                / str(terminal_attempt.get("run_id", "legacy-run"))
                / f"{attempt_id.replace(':', '__')}.json"
            )
            if manifest_path.exists():
                raise ConfigurationError(
                    f"Immutable stage-attempt manifest already exists: {manifest_path}"
                )
            write_json_atomic(
                manifest_path,
                {
                    "schema_version": 1,
                    "profile": state.get("profile"),
                    "stage": stage,
                    **terminal_attempt,
                },
                overwrite=False,
            )
            terminal_attempt["manifest"] = str(manifest_path.resolve())
    state["updated_at"] = now()
    if status == "failed":
        state["status"] = "failed"
    if stage == "final-audit" and status == "completed":
        state["status"] = "completed"
    write_json_atomic(state_path, state, overwrite=True)
    return state


def artifacts_current(
    state_path: Path,
    stage: str,
    required: list[Path],
    fingerprint: str | None = None,
) -> bool:
    if not state_path.is_file():
        return False
    state = load_json(state_path)
    record = state.get("stages", {}).get(stage, {})
    if record.get("status") != "completed":
        return False
    if fingerprint is not None and record.get("input_fingerprint") != fingerprint:
        return False
    recorded = {str(Path(item["path"]).resolve()): item for item in record.get("artifacts", [])}
    for raw_path in required:
        path = raw_path.resolve()
        item = recorded.get(str(path))
        if item is None or not path.is_file() or sha256_file(path) != item.get("sha256"):
            return False
    return True


def status_state(state_path: Path) -> dict[str, Any]:
    state = load_json(state_path)
    load_profile(Path(state["profile"]))
    for record in state.get("stages", {}).values():
        for artifact in record.get("artifacts", []):
            path = Path(artifact["path"])
            if not path.is_file() or sha256_file(path) != artifact["sha256"]:
                artifact["drifted"] = True
                state["status"] = "drifted"
    return state

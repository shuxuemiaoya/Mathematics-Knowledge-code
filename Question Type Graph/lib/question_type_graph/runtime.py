from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import ConfigurationError, load_json, load_profile, sha256_file, write_json_atomic


STAGES = [
    "intake",
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


def init_state(profile_path: Path, output: Path, overwrite: bool = False) -> dict[str, Any]:
    profile = load_profile(profile_path)
    state = {
        "schema_version": 1,
        "profile": profile["_profile_path"],
        "status": "active",
        "created_at": now(),
        "updated_at": now(),
        "stages": {name: {"status": "pending", "attempts": 0} for name in STAGES},
    }
    state["stages"]["intake"] = {"status": "completed", "attempts": 1, "completed_at": now()}
    write_json_atomic(output, state, overwrite=overwrite)
    return state


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
    if message:
        record["message"] = message
    elif status == "running":
        record.pop("message", None)
    if fingerprint is not None:
        record["input_fingerprint"] = fingerprint
    if artifacts is not None:
        record["artifacts"] = [
            {"path": str(path.resolve()), "sha256": sha256_file(path.resolve())}
            for path in artifacts
        ]
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

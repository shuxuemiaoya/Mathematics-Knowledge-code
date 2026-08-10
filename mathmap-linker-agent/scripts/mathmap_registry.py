#!/usr/bin/env python3
"""Persistent identity and baseline helpers for the MathMap linker.

The registry deliberately stores paths relative to the vault so the vault can be
moved without invalidating provenance.  JSON is the portable source of truth for
the first migration phase; callers can replace the lookup layer with SQLite later
without changing the on-disk contract.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


REGISTRY_VERSION = 1
QID_REGISTRY_NAME = "question-qid-registry.json"
STATE_DIR_NAME = ".mathmap-linker"
PROVENANCE_NAME = "provenance-manifest.json"
UNLINKED_QUESTION_TYPES_DIR = "mathmap/习题/题型整理/未链接题型"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def file_hash(path: Path) -> str:
    return sha256_bytes(read_bytes(path))


def vault_relative(path: Path, vault_root: Path) -> str:
    return path.resolve().relative_to(vault_root.resolve()).as_posix()


def source_identity(book_short: str, source_root: Path, source_path: Path) -> str:
    rel = source_path.resolve().relative_to(source_root.resolve()).as_posix()
    return f"book:{book_short}:{source_root.name}/{rel}"


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取注册表 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"注册表根节点必须是 JSON object: {path}")
    return value


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    """Atomically replace one small state file without implementing a vault transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def default_qid_registry() -> Dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "updated_at": None,
        "questions": {},
        "normalized_stems": {},
    }


def default_provenance() -> Dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "updated_at": None,
        "files": {},
        "sources": {},
    }


class RegistryStore:
    """Load and update QID identity plus per-file manual-edit baselines."""

    def __init__(self, vault_root: Path):
        self.vault_root = vault_root.resolve()
        self.qid_path = self.vault_root / QID_REGISTRY_NAME
        self.state_dir = self.vault_root / STATE_DIR_NAME
        self.provenance_path = self.state_dir / PROVENANCE_NAME
        self.qids = load_json(self.qid_path, default_qid_registry())
        self.provenance = load_json(self.provenance_path, default_provenance())
        self.qids.setdefault("questions", {})
        self.qids.setdefault("normalized_stems", {})
        self.provenance.setdefault("files", {})
        self.provenance.setdefault("sources", {})

    @property
    def bootstrapped(self) -> bool:
        return self.qid_path.is_file() and self.provenance_path.is_file()

    def destination_for_source(self, identity: str) -> Optional[str]:
        record = self.provenance["sources"].get(identity)
        if isinstance(record, str):
            return record
        if isinstance(record, dict):
            destination = record.get("destination")
            return destination if isinstance(destination, str) else None
        return None

    def file_record(self, destination: str) -> Optional[Dict[str, Any]]:
        record = self.provenance["files"].get(destination)
        return record if isinstance(record, dict) else None

    def baseline_state(self, destination: str, current_hash: Optional[str]) -> str:
        """Return missing, unknown, unchanged, or manually_modified."""
        if current_hash is None:
            return "missing"
        record = self.file_record(destination)
        if not record:
            return "unknown"
        baseline = record.get("last_applied_hash") or record.get("content_hash")
        if baseline == current_hash:
            return "unchanged"
        return "manually_modified"

    def find_qid_by_stem_hash(self, normalized_stem_hash: str) -> Optional[str]:
        value = self.qids["normalized_stems"].get(normalized_stem_hash)
        if isinstance(value, str):
            return value
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
            return value[0]
        return None

    def register_question(
        self,
        qid: str,
        destination: str,
        normalized_stem_hash: str,
        content_hash: str,
        origin: str,
        answers: Optional[list[str]] = None,
        status: str = "adopted",
    ) -> None:
        questions = self.qids["questions"]
        questions[qid] = {
            "path": destination,
            "normalized_stem_hash": normalized_stem_hash,
            "content_hash": content_hash,
            "origin": origin,
            "answers": sorted(set(answers or [])),
            "status": status,
        }
        existing = self.qids["normalized_stems"].get(normalized_stem_hash)
        if existing is None:
            self.qids["normalized_stems"][normalized_stem_hash] = qid
        elif isinstance(existing, str) and existing != qid:
            self.qids["normalized_stems"][normalized_stem_hash] = sorted({existing, qid})
        elif isinstance(existing, list) and qid not in existing:
            existing.append(qid)
            existing.sort()

    def adopt_file(
        self,
        destination: str,
        identity: str,
        node_type: str,
        destination_hash: str,
        source_hash: Optional[str] = None,
        book_short: Optional[str] = None,
        origin: str = "linker",
        fingerprint: Optional[Dict[str, Any]] = None,
        knowledge_points: Optional[list[str]] = None,
    ) -> None:
        record: Dict[str, Any] = {
            "source_identity": identity,
            "source_hash": source_hash,
            "last_applied_hash": destination_hash,
            "node_type": node_type,
            "book_short": book_short,
            "origin": origin,
            "updated_at": utc_now(),
        }
        if fingerprint:
            record["fingerprint"] = fingerprint
        if knowledge_points:
            record["knowledge_points"] = sorted(set(knowledge_points))
        self.provenance["files"][destination] = record
        self.provenance["sources"][identity] = {"destination": destination}

    def save(self) -> None:
        now = utc_now()
        self.qids["version"] = REGISTRY_VERSION
        self.qids["updated_at"] = now
        self.provenance["version"] = REGISTRY_VERSION
        self.provenance["updated_at"] = now
        atomic_write_json(self.qid_path, self.qids)
        atomic_write_json(self.provenance_path, self.provenance)


def fingerprint(path: Path, known: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Use size/mtime as a fast path and SHA-256 as the authoritative identity."""
    stat = path.stat()
    size = stat.st_size
    mtime_ns = stat.st_mtime_ns
    if known and known.get("size") == size and known.get("mtime_ns") == mtime_ns and known.get("sha256"):
        digest = known["sha256"]
    else:
        digest = file_hash(path)
    return {"size": size, "mtime_ns": mtime_ns, "sha256": digest}

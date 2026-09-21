"""Identity-bound, roll-forward file transactions for one conversion run."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def publication_lock(journal: Path):
    """One publisher per journal; OS locks are released after process failure."""
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.with_suffix(journal.suffix + ".lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("publication already in progress") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("publication already in progress") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def current_digest(path: Path) -> str | None:
    if path.resolve() != path:
        raise ValueError(f"transaction path was redirected: {path}")
    return digest(path.read_bytes()) if path.exists() else None


def guarded_write_batch(writes: list[tuple[Path, str]], guards: dict[Path, str | None], *, writer=atomic_write) -> None:
    """Validate the original read set, then recheck each target before replacing it."""
    for path, expected in guards.items():
        if current_digest(path) != expected:
            raise ValueError(f"batch input drift: {path}")
    for path, text in writes:
        if path not in guards or current_digest(path) != guards[path]:
            raise ValueError(f"batch target drift: {path}")
        writer(path, text)


def _resume_transaction(journal: Path, identity: dict, *, writer=atomic_write) -> bool:
    if not journal.exists():
        return False
    plan = json.loads(journal.read_text(encoding="utf-8"))
    if plan.get("identity") != identity:
        raise ValueError("transaction identity changed; do not reuse another run's writes")
    outputs = {item["path"]: item for item in plan["writes"]}
    if len(outputs) != len(plan["writes"]):
        raise ValueError("duplicate transaction output")
    for raw, expected in plan.get("guards", {}).items():
        allowed = {expected}
        if raw in outputs:
            allowed.add(outputs[raw]["after"])
        if current_digest(Path(raw)) not in allowed:
            raise ValueError(f"transaction input drift: {raw}")
    # Validate the entire write set before making any further changes.
    for item in plan["writes"]:
        path = Path(item["path"])
        if digest(item["text"].encode()) != item["after"]:
            raise ValueError(f"corrupt transaction payload: {path}")
        current = current_digest(path)
        if current not in {item["before"], item["after"]}:
            raise ValueError(f"transaction target drift: {path}")
    for item in plan["writes"]:
        path = Path(item["path"])
        current = current_digest(path)
        if current not in {item["before"], item["after"]}:
            raise ValueError(f"transaction target drift: {path}")
        if current != item["after"]:
            writer(path, item["text"])
    plan["status"] = "committed"
    atomic_write(journal, json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    return True


def resume_transaction(journal: Path, identity: dict, *, writer=atomic_write) -> bool:
    if not journal.exists():
        return False
    with publication_lock(journal):
        return _resume_transaction(journal, identity, writer=writer)


def commit_transaction(journal: Path, identity: dict, writes: list[tuple[Path, str]], *,
                       guards: dict[Path, str | None] | None = None, writer=atomic_write) -> None:
    with publication_lock(journal):
        if _resume_transaction(journal, identity, writer=writer):
            return
        paths = [str(path.resolve()) for path, _ in writes]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate transaction output")
        frozen = {str(path): expected for path, expected in (guards or {}).items()}
        for raw, expected in frozen.items():
            if current_digest(Path(raw)) != expected:
                raise ValueError(f"transaction input drift before preparation: {raw}")
        plan = {"schema_version": 1, "status": "prepared", "identity": identity, "guards": frozen, "writes": [
            {"path": str(path.resolve()), "before": current_digest(path.resolve()),
             "after": digest(text.encode()), "text": text} for path, text in writes
        ]}
        atomic_write(journal, json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
        _resume_transaction(journal, identity, writer=writer)

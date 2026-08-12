from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .common import ConfigurationError


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def _ancestors(path: Path) -> Iterable[Path]:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    yield current
    yield from current.parents


def env_file_candidates(profile_path: Path) -> list[Path]:
    """Return deterministic credential-file candidates independent of launch cwd."""
    package_file = Path(__file__).resolve()
    roots = [profile_path.resolve().parent, package_file.parent]
    candidates: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        for parent in _ancestors(root):
            candidate = (parent / ".env").resolve()
            key = str(candidate)
            if key not in seen:
                candidates.append(candidate)
                seen.add(key)
    return candidates


def resolve_env_file(profile_path: Path, explicit: str | Path | None = None) -> Path | None:
    """Resolve an explicit/configured env file, then search stable project roots."""
    configured = explicit or os.environ.get("QUESTION_TYPE_GRAPH_ENV_FILE")
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise ConfigurationError(f"Configured environment file does not exist: {path}")
        return path
    return next((path for path in env_file_candidates(profile_path) if path.is_file()), None)

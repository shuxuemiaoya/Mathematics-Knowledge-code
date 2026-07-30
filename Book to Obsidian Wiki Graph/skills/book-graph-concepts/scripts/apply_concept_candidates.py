#!/usr/bin/env python3
"""Materialize reviewed formal concepts without re-discovering link mechanics."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def category_directory(profile: dict, role: str) -> str:
    for item in profile["categories"]:
        if item["role"] == role and item.get("enabled", True):
            return item["directory"]
    raise ValueError(f"profile has no enabled {role!r} category")


def note_target(profile: dict, path: Path) -> str:
    mode = profile["links"]["note_mode"]
    encode_spaces = profile["links"].get("encode_spaces", False)
    if mode == "vault-root":
        root = Path(profile["paths"]["vault_root"])
        target = "/" + path.resolve().relative_to(root.resolve()).as_posix()
    elif mode == "relative":
        raise ValueError("relative links require a source directory")
    else:
        raise ValueError(f"unsupported note mode: {mode}")
    return target.replace(" ", "%20") if encode_spaces else target


def source_key_by_target(coverage: dict) -> dict[str, str]:
    return {
        unit["target"].replace("\\", "/"): unit["source_key"]
        for unit in coverage["units"]
        if unit.get("target")
    }


DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)", re.DOTALL)


def math_spans(text: str) -> list[tuple[int, int]]:
    display = [(match.start(), match.end()) for match in DISPLAY_MATH_RE.finditer(text)]
    masked = list(text)
    for start, end in display:
        masked[start:end] = " " * (end - start)
    inline = [
        (match.start(), match.end())
        for match in INLINE_MATH_RE.finditer("".join(masked))
    ]
    return display + inline


def validate_candidate(candidate: dict, source_lines: list[str]) -> tuple[int, int, str]:
    start = int(candidate["definition_start_line"])
    end = int(candidate["definition_end_line"])
    if start < 1 or end < start or end > len(source_lines):
        raise ValueError(
            f"{candidate['name']}: invalid definition lines {start}-{end}"
        )
    definition = "\n".join(source_lines[start - 1 : end]).strip()
    anchor = candidate["anchor_text"]
    link_text = candidate.get("link_text", candidate["name"])
    if anchor not in definition:
        raise ValueError(f"{candidate['name']}: anchor not found in definition range")
    if link_text not in anchor:
        raise ValueError(f"{candidate['name']}: link text is not inside anchor")
    if any(line.startswith(("# ", "## ", "### ")) for line in source_lines[start - 1 : end]):
        raise ValueError(f"{candidate['name']}: definition range includes H1-H3")
    if candidate["name"].endswith("公式"):
        math_fragments = math_spans(definition)
        if not any(
            "=" in definition[left:right] or r"\equiv" in definition[left:right]
            for left, right in math_fragments
        ):
            raise ValueError(
                f"{candidate['name']}: formula definition has no equation"
            )
    full_source = "\n".join(source_lines)
    definition_offset = sum(len(line) + 1 for line in source_lines[: start - 1])
    term_start = definition_offset + definition.find(anchor) + anchor.find(link_text)
    term_end = term_start + len(link_text)
    if any(left <= term_start and term_end <= right for left, right in math_spans(full_source)):
        raise ValueError(
            f"{candidate['name']}: defining term is inside math and cannot host a Markdown link"
        )
    return start, end, definition


def detach_definition_from_source_callout(definition: str) -> str:
    """Render a definition copied from a source callout as standalone Markdown."""
    lines = definition.splitlines()
    substantive = [line for line in lines if line.strip()]
    quoted = [line for line in substantive if line.lstrip().startswith(">")]
    if not quoted:
        return definition
    if any("[!" in line for line in quoted):
        return definition
    detached: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            detached.append("")
            continue
        if stripped.startswith(">"):
            stripped = re.sub(r"^(?:>\s*)+", "", stripped)
        detached.append(stripped)
    return "\n".join(detached).strip()


def link_first_defining_occurrence(
    lines: list[str],
    start: int,
    end: int,
    *,
    anchor: str,
    link_text: str,
    target: str,
) -> None:
    segment = "\n".join(lines[start - 1 : end])
    anchor_offset = segment.find(anchor)
    if anchor_offset < 0:
        raise ValueError("anchor disappeared before source replacement")
    term_offset = anchor.find(link_text)
    absolute = anchor_offset + term_offset
    linked = f"[{link_text}]({target})"
    segment = segment[:absolute] + linked + segment[absolute + len(link_text) :]
    lines[start - 1 : end] = segment.split("\n")


def apply_candidates(
    profile_path: Path,
    coverage_path: Path,
    candidates_path: Path,
    manifest_path: Path,
) -> dict:
    profile = load_json(profile_path)
    coverage = load_json(coverage_path)
    payload = load_json(candidates_path)
    book_root = Path(profile["paths"]["book_root"])
    concept_dir = book_root / category_directory(profile, "concept")
    if concept_dir.exists() and any(concept_dir.iterdir()):
        raise ValueError(f"concept directory is not empty: {concept_dir}")

    candidates = payload.get("concepts", [])
    if candidates and payload.get("status") != "approved":
        raise ValueError(
            "concept candidates are not approved; review the planner output "
            "and set status to approved"
        )
    unreviewed = [
        candidate.get("name", "<unnamed>")
        for candidate in candidates
        if candidate.get("reviewed") is not True
    ]
    if unreviewed:
        raise ValueError(
            "concept candidates remain unreviewed: " + ", ".join(unreviewed)
        )
    names = [candidate["name"] for candidate in candidates]
    if len(names) != len(set(names)):
        raise ValueError("concept candidate names must be unique")

    sources: dict[str, list[str]] = {}
    validated: list[tuple[dict, int, int, str]] = []
    for candidate in candidates:
        source_rel = candidate["definition_source"].replace("\\", "/")
        source = book_root / Path(source_rel)
        if source_rel not in sources:
            sources[source_rel] = source.read_text(encoding="utf-8").splitlines()
        start, end, definition = validate_candidate(candidate, sources[source_rel])
        validated.append((candidate, start, end, definition))

    concept_targets: dict[str, Path] = {
        candidate["name"]: concept_dir / f"{candidate['name']}.md"
        for candidate in candidates
    }
    source_keys = source_key_by_target(coverage)
    manifest_concepts: list[dict] = []

    for candidate, start, end, definition in validated:
        name = candidate["name"]
        source_rel = candidate["definition_source"].replace("\\", "/")
        source_path = book_root / Path(source_rel)
        concept_path = concept_targets[name]
        source_link = note_target(profile, source_path)
        concept_link = note_target(profile, concept_path)
        link_first_defining_occurrence(
            sources[source_rel],
            start,
            end,
            anchor=candidate["anchor_text"],
            link_text=candidate.get("link_text", name),
            target=concept_link,
        )
        standalone_definition = detach_definition_from_source_callout(definition)
        body = (
            f"# {name}\n\n"
            f"来源：[{source_path.stem}]({source_link})\n\n"
            f"## 定义\n\n"
            f"{standalone_definition}\n"
        )
        atomic_write(concept_path, body)
        manifest_concepts.append(
            {
                "name": name,
                "definition_source": source_rel,
                "definition_unit": source_keys.get(source_rel, source_rel),
                "target": concept_path.relative_to(book_root).as_posix(),
                "linked_from": [source_rel],
                "confidence": candidate.get("confidence", "high"),
            }
        )

    for source_rel, lines in sources.items():
        atomic_write(book_root / Path(source_rel), "\n".join(lines) + "\n")

    manifest = {
        "schema_version": 1,
        "profile": str(profile_path),
        "source_sha256": profile["source"]["sha256"],
        "concepts": manifest_concepts,
        "rejected": payload.get("rejected", []),
    }
    atomic_write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return {
        "status": "passed",
        "concepts": len(manifest_concepts),
        "sources_modified": len(sources),
        "manifest": str(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    parser.add_argument("coverage", type=Path)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        result = apply_candidates(
            args.profile, args.coverage, args.candidates, args.manifest
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

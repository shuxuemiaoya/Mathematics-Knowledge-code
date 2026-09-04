#!/usr/bin/env python3
"""Deterministic contracts for two-pass, range-only semantic atomization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from validate_book_graph import artifact_digest, canonical_digest, load_json, sha256_file


ATOM_CATEGORY_NAMES = {"knowledge", "worked-example", "exercise", "scenario"}
DEFAULT_ATOMIZATION = {
    "mode": "llm-two-pass",
    "knowledge_granularity": "complete-teaching-unit",
    "scenario_policy": "substantial-only",
    "confidence_threshold": 0.90,
    "short_atom_confidence_threshold": 0.95,
}
FORMAL_STANDALONE_KINDS = {"formal-definition", "theorem", "law"}
FORBIDDEN_DECISION_FIELDS = {"body", "content", "markdown", "source_text", "rewritten_text"}
EXAMPLE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?【?例题?\s*(?:\d+|[一二三四五六七八九十]+)】?(?:\s|[.．、：:]|$)")
EXERCISE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?\d+[.．、]\s*\S+")
EXERCISE_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s*)?【?(?:练习|习题|复习题)[^】]*】?(?:\s|[.．、：:]|$)")


class AtomizationError(ValueError):
    pass


def seal_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["artifact_sha256"] = artifact_digest(result)
    return result


def verify_artifact(payload: dict[str, Any], kind: str | None = None) -> None:
    if kind is not None and payload.get("kind") != kind:
        raise AtomizationError(f"Expected {kind}, got {payload.get('kind')!r}")
    if payload.get("artifact_sha256") != artifact_digest(payload):
        raise AtomizationError(f"Stale or missing digest for {payload.get('kind', 'artifact')}")


def atomic_json(path: Path, payload: dict[str, Any], overwrite: bool = False) -> None:
    path = path.expanduser().resolve()
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_range(value: Any, field: str, line_count: int) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise AtomizationError(f"{field} must be [start, end]")
    start, end = value
    if start < 1 or end < start or end > line_count:
        raise AtomizationError(f"{field} is outside source Markdown")
    return start, end


def source_slice(lines: list[str], source_range: list[int] | tuple[int, int]) -> list[str]:
    start, end = int(source_range[0]), int(source_range[1])
    return lines[start - 1 : end]


def normalized_char_count(lines: Iterable[str]) -> int:
    text = "\n".join(lines)
    # Resource filenames are converter metadata, not teaching content.  A long
    # hashed image URL must not let a one-line knowledge fragment evade audit.
    text = re.sub(r"!\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)", "", text)
    text = re.sub(r"<img\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return len(re.sub(r"\s+", "", text))


def descendants(nodes: dict[str, dict[str, Any]], start: str) -> list[str]:
    ordered: list[str] = []

    def visit(key: str) -> None:
        if key in ordered or key not in nodes:
            return
        ordered.append(key)
        if nodes[key].get("layer") == "organizer":
            for child in nodes[key].get("children", []):
                visit(str(child))

    visit(start)
    return ordered


def config_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    supplied = profile.get("atomization", {})
    if not isinstance(supplied, dict):
        raise AtomizationError("profile.atomization must be an object")
    config = {**DEFAULT_ATOMIZATION, **supplied}
    if config.get("mode") != "llm-two-pass":
        raise AtomizationError("Two-pass preparation requires mode=llm-two-pass")
    for field in ("confidence_threshold", "short_atom_confidence_threshold"):
        value = config.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise AtomizationError(f"atomization.{field} must be between 0 and 1")
        config[field] = float(value)
    return config


def explicit_boundary(atom: dict[str, Any], lines: list[str]) -> dict[str, Any] | None:
    start, end = atom["source_range"]
    first: tuple[int, str] | None = None
    for number in range(int(start), min(int(end), int(start) + 4) + 1):
        if lines[number - 1].strip():
            first = number, lines[number - 1]
            break
    if first is None:
        return None
    number, text = first
    category = atom.get("category")
    if category == "worked-example" and EXAMPLE_RE.match(text):
        pass
    elif category == "exercise" and (EXERCISE_RE.match(text) or EXERCISE_HEADING_RE.match(text)):
        pass
    else:
        return None
    return {"line": number, "kind": "required-atom-start", "category": category, "evidence": text.strip()}


def split_run(atoms: list[dict[str, Any]], lines: list[str], max_chars: int) -> list[list[dict[str, Any]]]:
    if max_chars < 1000:
        raise AtomizationError("--max-chars must be at least 1000")
    result: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for atom in atoms:
        atom_size = sum(len(line) + 1 for line in source_slice(lines, atom["source_range"]))
        if current and size + atom_size > max_chars:
            result.append(current)
            current, size = [], 0
        current.append(atom)
        size += atom_size
    if current:
        result.append(current)
    return result


def prepare_jobs(manifest_path: Path, selected_roots: list[str] | None = None, max_chars: int = 12000) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_json(manifest_path)
    profile_path = Path(str(manifest.get("profile", ""))).expanduser().resolve()
    profile = load_json(profile_path)
    config = config_from_profile(profile)
    source_path = Path(str(manifest.get("source_markdown", ""))).expanduser().resolve()
    if not source_path.is_file() or sha256_file(source_path) != manifest.get("source_markdown_sha256"):
        raise AtomizationError("Source Markdown is missing or stale")
    lines = source_path.read_text(encoding="utf-8-sig").splitlines()
    raw_nodes = manifest.get("nodes")
    if not isinstance(raw_nodes, list):
        raise AtomizationError("Base manifest nodes must be an array")
    nodes = {str(node["key"]): node for node in raw_nodes if isinstance(node, dict) and isinstance(node.get("key"), str)}
    roots = [key for key, node in nodes.items() if node.get("layer") == "organizer" and node.get("parent_key") is None]
    if len(roots) != 1:
        raise AtomizationError("Base manifest must contain one root organizer")
    root = roots[0]
    available = [str(key) for key in nodes[root].get("children", []) if nodes.get(str(key), {}).get("layer") == "organizer"]
    scope = list(selected_roots or available)
    if not scope or any(key not in available for key in scope):
        raise AtomizationError("Every --root-key must be a direct organizer child of the root")
    selected: set[str] = set()
    for key in scope:
        selected.update(descendants(nodes, key))

    def top_level(key: str) -> str:
        current = key
        while nodes.get(current, {}).get("parent_key") not in {None, root}:
            current = str(nodes[current]["parent_key"])
        return current

    jobs: list[dict[str, Any]] = []
    run_number = 0
    for organizer in raw_nodes:
        if not isinstance(organizer, dict) or organizer.get("layer") != "organizer" or organizer.get("key") not in selected:
            continue
        owner = str(organizer["key"])
        children = [str(child) for child in organizer.get("children", [])]
        index = 0
        while index < len(children):
            if nodes.get(children[index], {}).get("layer") != "atom":
                index += 1
                continue
            run_atoms: list[dict[str, Any]] = []
            while index < len(children) and nodes.get(children[index], {}).get("layer") == "atom":
                atom = nodes[children[index]]
                parse_range(atom.get("source_range"), f"node {atom.get('key')}.source_range", len(lines))
                run_atoms.append(atom)
                index += 1
            run_number += 1
            run_id = f"run-{run_number:04d}-{hashlib.sha256(owner.encode()).hexdigest()[:8]}"
            packets = split_run(run_atoms, lines, max_chars)
            for part, packet_atoms in enumerate(packets, start=1):
                start, end = int(packet_atoms[0]["source_range"][0]), int(packet_atoms[-1]["source_range"][1])
                identity = hashlib.sha256(f"{owner}:{start}:{end}".encode()).hexdigest()[:8]
                job = {
                    "job_id": f"job-{len(jobs)+1:04d}-{identity}", "run_id": run_id,
                    "part_index": part, "part_count": len(packets), "owner_key": owner,
                    "owner_title": organizer.get("title"), "top_level_key": top_level(owner),
                    "source_range": [start, end],
                    "source_lines": [{"line": number, "text": lines[number-1]} for number in range(start, end+1)],
                    "baseline_atoms": [{"key": str(atom["key"]), "source_range": list(atom["source_range"]), "category": atom.get("category"), "title": atom.get("title")} for atom in packet_atoms],
                    "hard_boundaries": [marker for marker in (explicit_boundary(atom, lines) for atom in packet_atoms) if marker],
                    "instructions": {
                        "knowledge": "Keep definition, conditions, notation, explanation, derivation, and nearby conclusion in one complete teaching unit.",
                        "scenario": "Only substantial narrative, real-world context, experiment setup, or motivation may stand alone; merge short prompts into knowledge.",
                        "worked_example": "Keep complete stem, analysis, solution, and nearby conclusion.",
                        "exercise": "Keep a top-level question with all subparts, figures, tables, and materials.",
                        "source_fidelity": "Choose contiguous source ranges only; never rewrite source text."
                    },
                }
                job["packet_sha256"] = canonical_digest(job)
                jobs.append(job)
    if not jobs:
        raise AtomizationError("Selected roots contain no draft atoms")
    return seal_artifact({
        "schema_version": 1, "kind": "atomization-jobs",
        "base_manifest": str(manifest_path), "base_manifest_sha256": sha256_file(manifest_path),
        "profile": str(profile_path), "profile_sha256": sha256_file(profile_path),
        "source_markdown": str(source_path), "source_markdown_sha256": sha256_file(source_path),
        "source_line_count": len(lines), "root_key": root, "scope_root_keys": scope,
        "atomization": config, "jobs": jobs,
    })


def validate_atom(atom: Any, field: str, owner: str, lines: list[str], errors: list[dict[str, Any]]) -> tuple[int, int] | None:
    if not isinstance(atom, dict):
        errors.append({"code": "decision-atom-invalid", "field": field})
        return None
    forbidden = sorted(FORBIDDEN_DECISION_FIELDS.intersection(atom))
    if forbidden:
        errors.append({"code": "decision-rewrites-source", "field": field, "forbidden": forbidden})
    try:
        result = parse_range(atom.get("source_range"), f"{field}.source_range", len(lines))
    except Exception as exc:
        errors.append({"code": "decision-range-invalid", "field": field, "detail": str(exc)})
        return None
    if atom.get("owner_key") != owner:
        errors.append({"code": "decision-owner-invalid", "field": field})
    if atom.get("category") not in ATOM_CATEGORY_NAMES:
        errors.append({"code": "decision-category-invalid", "field": field})
    for name in ("title", "boundary_reason", "cohesion_reason", "atom_id"):
        if not isinstance(atom.get(name), str) or not atom[name].strip():
            errors.append({"code": "decision-field-missing", "field": field, "name": name})
    confidence = atom.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append({"code": "decision-confidence-invalid", "field": field})
    return result


def validate_partition(atoms: Any, expected: list[int], owner: str, lines: list[str], field: str, errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(atoms, list) or not atoms:
        errors.append({"code": "decision-atoms-missing", "field": field})
        return []
    parsed: list[tuple[int, int, dict[str, Any]]] = []
    ids: set[str] = set()
    for index, atom in enumerate(atoms):
        item_range = validate_atom(atom, f"{field}[{index}]", owner, lines, errors)
        if item_range is None or not isinstance(atom, dict):
            continue
        if atom.get("atom_id") in ids:
            errors.append({"code": "decision-atom-id-duplicate", "field": field, "atom_id": atom.get("atom_id")})
        ids.add(str(atom.get("atom_id")))
        parsed.append((item_range[0], item_range[1], atom))
    parsed.sort(key=lambda item: (item[0], item[1]))
    cursor = int(expected[0])
    for start, end, _ in parsed:
        if start != cursor:
            errors.append({"code": "decision-partition-gap-or-overlap", "field": field, "expected_line": cursor, "actual_line": start})
        cursor = end + 1
    if cursor != int(expected[1]) + 1:
        errors.append({"code": "decision-partition-incomplete", "field": field, "expected_end": expected[1], "actual_end": cursor-1})
    return [item[2] for item in parsed]


def hard_boundary_issues(atoms: list[dict[str, Any]], markers: list[dict[str, Any]], location: str) -> list[dict[str, Any]]:
    starts = {int(atom["source_range"][0]): atom for atom in atoms if isinstance(atom.get("source_range"), list)}
    return [{"code": "hard-boundary-violation", "location": location, "line": marker.get("line"), "required_category": marker.get("category"), "evidence": marker.get("evidence")} for marker in markers if starts.get(marker.get("line"), {}).get("category") != marker.get("category")]


def quality_issues(atom: dict[str, Any], lines: list[str], config: dict[str, Any], location: str, final: bool) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    confidence = atom.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and float(confidence) < float(config["confidence_threshold"]):
        issues.append({"code": "low-confidence", "location": location, "atom_id": atom.get("atom_id"), "confidence": confidence})
    if atom.get("category") != "knowledge":
        return issues
    body = source_slice(lines, atom["source_range"])
    short = normalized_char_count(body) < 150 or sum(bool(line.strip()) for line in body) <= 1
    if not short:
        return issues
    if not final:
        issues.append({"code": "short-knowledge-requires-round2-audit", "location": location, "atom_id": atom.get("atom_id"), "source_range": atom.get("source_range")})
    elif not (atom.get("standalone_kind") in FORMAL_STANDALONE_KINDS and isinstance(atom.get("standalone_reason"), str) and len(atom["standalone_reason"].strip()) >= 12 and isinstance(confidence, (int, float)) and float(confidence) >= float(config["short_atom_confidence_threshold"])):
        issues.append({"code": "short-knowledge-not-independent", "location": location, "atom_id": atom.get("atom_id"), "source_range": atom.get("source_range"), "required_confidence": config["short_atom_confidence_threshold"]})
    return issues


def validate_round1_payload(jobs: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    verify_artifact(jobs, "atomization-jobs")
    verify_artifact(decisions, "round-1-decisions")
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    if decisions.get("jobs_sha256") != jobs.get("artifact_sha256"):
        errors.append({"code": "round1-jobs-digest-mismatch"})
    source = Path(str(jobs.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != jobs.get("source_markdown_sha256"):
        lines: list[str] = []
        errors.append({"code": "source-markdown-digest-mismatch"})
    else:
        lines = source.read_text(encoding="utf-8-sig").splitlines()
    raw = decisions.get("decisions")
    if not isinstance(raw, list):
        raw = []
        errors.append({"code": "round1-decisions-missing"})
    by_job = {item.get("job_id"): item for item in raw if isinstance(item, dict)}
    expected = {job["job_id"] for job in jobs.get("jobs", [])}
    if len(by_job) != len(raw) or set(by_job) != expected:
        errors.append({"code": "round1-job-coverage-invalid", "missing": sorted(expected-set(by_job)), "extra": sorted(set(by_job)-expected)})
    normalized: dict[str, list[dict[str, Any]]] = {}
    for job in jobs.get("jobs", []):
        decision = by_job.get(job["job_id"])
        if not isinstance(decision, dict):
            continue
        if decision.get("packet_sha256") != job.get("packet_sha256"):
            errors.append({"code": "round1-packet-digest-mismatch", "job_id": job["job_id"]})
        atoms = validate_partition(decision.get("atoms"), job["source_range"], job["owner_key"], lines, f"job:{job['job_id']}", errors)
        normalized[job["job_id"]] = atoms
        review.extend(hard_boundary_issues(atoms, job.get("hard_boundaries", []), job["job_id"]))
        for atom in atoms:
            review.extend(quality_issues(atom, lines, jobs["atomization"], job["job_id"], False))
    return {"schema_version": 1, "status": "failed" if errors else ("review_required" if review else "passed"), "structural_errors": errors, "review_items": review, "counts": {"jobs": len(jobs.get("jobs", [])), "atoms": sum(len(value) for value in normalized.values()), "review_items": len(review)}, "normalized_atoms": normalized}


def prepare_audit_jobs(jobs: dict[str, Any], round1: dict[str, Any]) -> dict[str, Any]:
    report = validate_round1_payload(jobs, round1)
    if report["structural_errors"]:
        raise AtomizationError("Round one has structural errors")
    lines = Path(str(jobs["source_markdown"])).read_text(encoding="utf-8-sig").splitlines()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for job in jobs["jobs"]:
        grouped.setdefault(str(job["run_id"]), []).append(job)
    audits: list[dict[str, Any]] = []
    for run_id, run_jobs in grouped.items():
        run_jobs.sort(key=lambda item: int(item["part_index"]))
        atoms: list[dict[str, Any]] = []
        markers: list[dict[str, Any]] = []
        for job in run_jobs:
            atoms.extend(report["normalized_atoms"][job["job_id"]])
            markers.extend(job.get("hard_boundaries", []))
        atoms.sort(key=lambda atom: (int(atom["source_range"][0]), int(atom["source_range"][1])))
        boundaries: list[dict[str, Any]] = []
        for index, (left, right) in enumerate(zip(atoms, atoms[1:]), start=1):
            identity = hashlib.sha256(f"{left.get('atom_id')}:{right.get('atom_id')}".encode()).hexdigest()[:8]
            boundaries.append({"boundary_id": f"boundary-{index:04d}-{identity}", "line_after": int(left["source_range"][1]), "left_atom_id": left.get("atom_id"), "right_atom_id": right.get("atom_id"), "left_range": left.get("source_range"), "right_range": right.get("source_range")})
        audit_id = f"audit-{len(audits)+1:04d}-{hashlib.sha256(run_id.encode()).hexdigest()[:8]}"
        start, end = int(atoms[0]["source_range"][0]), int(atoms[-1]["source_range"][1])
        audit = {"audit_id": audit_id, "run_id": run_id, "owner_key": run_jobs[0]["owner_key"], "top_level_key": run_jobs[0]["top_level_key"], "source_range": [start, end], "source_lines": [{"line": number, "text": lines[number-1]} for number in range(start, end+1)], "round1_atoms": atoms, "boundaries": boundaries, "hard_boundaries": markers, "instructions": {"required": "Review every boundary and return the complete final partition.", "actions": ["keep", "merge", "resegment"], "fragment_gate": "Short knowledge must merge unless it is a formal independent definition, theorem, or law with confidence >= 0.95.", "source_fidelity": "Never rewrite source text."}}
        audit["packet_sha256"] = canonical_digest(audit)
        audits.append(audit)
    return seal_artifact({"schema_version": 1, "kind": "round-2-jobs", "jobs_sha256": jobs["artifact_sha256"], "round_1_decisions_sha256": round1["artifact_sha256"], "source_markdown": jobs["source_markdown"], "source_markdown_sha256": jobs["source_markdown_sha256"], "scope_root_keys": jobs["scope_root_keys"], "atomization": jobs["atomization"], "audits": audits})


def actual_boundary_action(final_atoms: list[dict[str, Any]], boundary: dict[str, Any]) -> str:
    line_after = int(boundary["line_after"])
    if any(int(atom["source_range"][1]) == line_after for atom in final_atoms):
        return "keep"
    left_start, right_end = int(boundary["left_range"][0]), int(boundary["right_range"][1])
    new_boundaries = [int(atom["source_range"][1]) for atom in final_atoms if left_start <= int(atom["source_range"][1]) < right_end and int(atom["source_range"][1]) != line_after]
    return "resegment" if new_boundaries else "merge"


def finalize_payload(jobs: dict[str, Any], round1: dict[str, Any], audit_jobs: dict[str, Any], round2: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    for payload, kind in ((jobs, "atomization-jobs"), (round1, "round-1-decisions"), (audit_jobs, "round-2-jobs"), (round2, "round-2-decisions")):
        verify_artifact(payload, kind)
    errors = list(validate_round1_payload(jobs, round1)["structural_errors"])
    review: list[dict[str, Any]] = []
    if audit_jobs.get("jobs_sha256") != jobs.get("artifact_sha256") or audit_jobs.get("round_1_decisions_sha256") != round1.get("artifact_sha256"):
        errors.append({"code": "round2-upstream-binding-invalid"})
    if round2.get("round_2_jobs_sha256") != audit_jobs.get("artifact_sha256"):
        errors.append({"code": "round2-decisions-binding-invalid"})
    source = Path(str(jobs["source_markdown"])).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != jobs.get("source_markdown_sha256"):
        lines: list[str] = []
        errors.append({"code": "source-markdown-digest-mismatch"})
    else:
        lines = source.read_text(encoding="utf-8-sig").splitlines()
    raw = round2.get("decisions")
    if not isinstance(raw, list):
        raw = []
        errors.append({"code": "round2-decisions-missing"})
    by_audit = {item.get("audit_id"): item for item in raw if isinstance(item, dict)}
    expected_audits = {audit["audit_id"] for audit in audit_jobs.get("audits", [])}
    if len(by_audit) != len(raw) or set(by_audit) != expected_audits:
        errors.append({"code": "round2-audit-coverage-invalid", "missing": sorted(expected_audits-set(by_audit)), "extra": sorted(set(by_audit)-expected_audits)})
    final_atoms: list[dict[str, Any]] = []
    for audit in audit_jobs.get("audits", []):
        decision = by_audit.get(audit["audit_id"])
        if not isinstance(decision, dict):
            continue
        if decision.get("packet_sha256") != audit.get("packet_sha256"):
            errors.append({"code": "round2-packet-digest-mismatch", "audit_id": audit["audit_id"]})
        atoms = validate_partition(decision.get("atoms"), audit["source_range"], audit["owner_key"], lines, f"audit:{audit['audit_id']}", errors)
        raw_reviews = decision.get("boundary_reviews")
        if not isinstance(raw_reviews, list):
            raw_reviews = []
            errors.append({"code": "boundary-reviews-missing", "audit_id": audit["audit_id"]})
        reviews = {item.get("boundary_id"): item for item in raw_reviews if isinstance(item, dict)}
        expected = {item["boundary_id"] for item in audit.get("boundaries", [])}
        if len(reviews) != len(raw_reviews) or set(reviews) != expected:
            errors.append({"code": "boundary-review-coverage-invalid", "audit_id": audit["audit_id"], "missing": sorted(expected-set(reviews)), "extra": sorted(set(reviews)-expected)})
        for boundary in audit.get("boundaries", []):
            item = reviews.get(boundary["boundary_id"])
            if not isinstance(item, dict):
                continue
            actual = actual_boundary_action(atoms, boundary)
            if item.get("action") not in {"keep", "merge", "resegment"} or item.get("action") != actual:
                errors.append({"code": "boundary-action-partition-mismatch", "audit_id": audit["audit_id"], "boundary_id": boundary["boundary_id"], "declared": item.get("action"), "actual": actual})
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                errors.append({"code": "boundary-reason-missing", "audit_id": audit["audit_id"], "boundary_id": boundary["boundary_id"]})
            confidence = item.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                errors.append({"code": "boundary-confidence-invalid", "audit_id": audit["audit_id"], "boundary_id": boundary["boundary_id"]})
            elif float(confidence) < float(jobs["atomization"]["confidence_threshold"]):
                review.append({"code": "low-confidence-boundary", "audit_id": audit["audit_id"], "boundary_id": boundary["boundary_id"], "confidence": confidence})
        review.extend(hard_boundary_issues(atoms, audit.get("hard_boundaries", []), audit["audit_id"]))
        for atom in atoms:
            review.extend(quality_issues(atom, lines, jobs["atomization"], audit["audit_id"], True))
            copied = {key: value for key, value in atom.items() if key not in FORBIDDEN_DECISION_FIELDS}
            copied["source_text_sha256"] = canonical_digest(source_slice(lines, atom["source_range"]))
            final_atoms.append(copied)
    final_atoms.sort(key=lambda atom: (int(atom["source_range"][0]), int(atom["source_range"][1]), str(atom.get("atom_id"))))
    ids = [atom.get("atom_id") for atom in final_atoms]
    if len(ids) != len(set(ids)):
        errors.append({"code": "final-atom-id-duplicate"})
    unresolved = [*errors, *review]
    bindings = {name: {"path": payload.get("_path"), "sha256": payload["artifact_sha256"]} for name, payload in (("jobs", jobs), ("round_1_decisions", round1), ("round_2_jobs", audit_jobs), ("round_2_decisions", round2))}
    final = seal_artifact({"schema_version": 1, "kind": "atomization-final", "status": "passed" if not unresolved else "review_required", "source_markdown": jobs["source_markdown"], "source_markdown_sha256": jobs["source_markdown_sha256"], "base_manifest": jobs["base_manifest"], "base_manifest_sha256": jobs["base_manifest_sha256"], "scope_root_keys": jobs["scope_root_keys"], "atomization": jobs["atomization"], "reviewer": {"round_1": round1.get("reviewer"), "round_2": round2.get("reviewer")}, "bindings": bindings, "unresolved_count": len(unresolved), "atoms": final_atoms})
    queue = seal_artifact({"schema_version": 1, "kind": "atomization-review-queue", "status": "passed" if not unresolved else "blocked", "atomization_final_sha256": final["artifact_sha256"], "unresolved_count": len(unresolved), "items": unresolved})
    return final, queue


def load_tagged(path: Path, kind: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    payload = load_json(resolved)
    verify_artifact(payload, kind)
    payload["_path"] = str(resolved)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("manifest", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--root-key", action="append", dest="root_keys")
    prepare.add_argument("--max-chars", type=int, default=12000)
    prepare.add_argument("--overwrite", action="store_true")
    validate = sub.add_parser("validate-round1")
    validate.add_argument("jobs", type=Path)
    validate.add_argument("decisions", type=Path)
    validate.add_argument("--output", type=Path)
    validate.add_argument("--overwrite", action="store_true")
    audit = sub.add_parser("prepare-audit")
    audit.add_argument("jobs", type=Path)
    audit.add_argument("decisions", type=Path)
    audit.add_argument("--output-dir", type=Path, required=True)
    audit.add_argument("--overwrite", action="store_true")
    finish = sub.add_parser("finalize")
    finish.add_argument("jobs", type=Path)
    finish.add_argument("round1", type=Path)
    finish.add_argument("round2_jobs", type=Path)
    finish.add_argument("round2", type=Path)
    finish.add_argument("--output-dir", type=Path, required=True)
    finish.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            payload = prepare_jobs(args.manifest, args.root_keys, args.max_chars)
            output = args.output_dir.expanduser().resolve() / "atomization-jobs.json"
            atomic_json(output, payload, args.overwrite)
            report, code = {"status": "created", "path": str(output), "jobs": len(payload["jobs"]), "sha256": payload["artifact_sha256"]}, 0
        elif args.command == "validate-round1":
            report = validate_round1_payload(load_tagged(args.jobs, "atomization-jobs"), load_tagged(args.decisions, "round-1-decisions"))
            if args.output:
                atomic_json(args.output, report, args.overwrite)
            code = 1 if report["status"] == "failed" else 0
        elif args.command == "prepare-audit":
            payload = prepare_audit_jobs(load_tagged(args.jobs, "atomization-jobs"), load_tagged(args.decisions, "round-1-decisions"))
            output = args.output_dir.expanduser().resolve() / "round-2-jobs.json"
            atomic_json(output, payload, args.overwrite)
            report, code = {"status": "created", "path": str(output), "audits": len(payload["audits"]), "sha256": payload["artifact_sha256"]}, 0
        else:
            final, queue = finalize_payload(load_tagged(args.jobs, "atomization-jobs"), load_tagged(args.round1, "round-1-decisions"), load_tagged(args.round2_jobs, "round-2-jobs"), load_tagged(args.round2, "round-2-decisions"))
            output_dir = args.output_dir.expanduser().resolve()
            final_path, queue_path = output_dir / "atomization-final.json", output_dir / "atomization-review-queue.json"
            atomic_json(final_path, final, args.overwrite)
            atomic_json(queue_path, queue, args.overwrite)
            report = {"status": final["status"], "atomization_final": str(final_path), "review_queue": str(queue_path), "atoms": len(final["atoms"]), "unresolved_count": final["unresolved_count"]}
            code = 0 if final["status"] == "passed" else 2
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Deterministic contracts for legacy and category-aware graph atomization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from validate_book_graph import (
    artifact_digest,
    canonical_digest,
    load_json,
    sha256_file,
    validate_organizer_review,
)


ATOM_CATEGORY_NAMES = {"knowledge", "worked-example", "exercise", "scenario"}
SCENARIO_ROLES = {
    "book-introduction", "chapter-introduction", "section-introduction",
    "knowledge-motivation", "reflection-question",
}
SCOPED_INTRO_ROLES = {
    "book-introduction", "chapter-introduction", "section-introduction",
}
DERIVED_CATEGORY_NAMES = {"concept", "formula"}
LOCAL_RELATION_TYPES = {
    "prerequisite", "develops", "derives", "motivates", "contrasts",
    "analogous", "synthesizes", "illustrates", "applies",
}
DEFAULT_ATOMIZATION = {
    "mode": "llm-category-aware-graph",
    "knowledge_granularity": "complete-teaching-unit",
    "scenario_policy": "preserve-and-role-classify-activities",
    "activity_prompt_policy": "preserve-marker-and-explicit-disposition",
    "confidence_threshold": 0.90,
    "short_atom_confidence_threshold": 0.95,
    "teaching_role_audit": "integrated",
    "relation_feedback_cycles": 2,
    "knowledge_boundary_authority": "llm-exclusive",
    "provisional_atom_policy": "coverage-context-only",
    "parallel_definition_policy": "split-when-independently-reusable",
    "scoped_introduction_policy": "one-source-complete-atom-per-owner",
    "knowledge_motivation_policy": "complete-problem-or-context",
}
FORMAL_STANDALONE_KINDS = {"formal-definition", "theorem", "law"}
FORBIDDEN_DECISION_FIELDS = {"body", "content", "markdown", "source_text", "rewritten_text"}
EXAMPLE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?【?例题?\s*(?:\d+|[一二三四五六七八九十]+)】?(?:\s|[.．、：:]|$)")
EXERCISE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?\d+[.．、]\s*\S+")
EXERCISE_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s*)?【?(?:练习|习题|复习题)[^】]*】?(?:\s|[.．、：:]|$)")
ACTIVITY_MARKER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?"
    r"(?:观察|思考|尝试|操作|交流|探究|探索|讨论|做一做|议一议)"
    r"(?:[·・、]\s*(?:观察|思考|尝试|操作|交流|探究|探索|讨论))?"
    r"(?:\*\*|__)?\s*(?:[：:].*)?$"
)
ACTIVITY_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(?:观察|思考|尝试|操作|交流|探究|探索|讨论|做一做|议一议)[·・、]?(?:\s|$)", re.MULTILINE)
TASK_LANGUAGE_RE = re.compile(r"(?:请你|请同伴|你能|你认为|怎样|如何|与同伴.*交流|[？?])")
REFLECTION_LANGUAGE_RE = re.compile(r"(?:举例说明|比较|概括|归纳|评价|探究|思考|说明.+特点|[？?])")
KNOWLEDGE_MOTIVATION_RE = re.compile(r"(?:从上面|由此想到|在此基础上|除此之外|还能|接下来|下面(?:先|来)|进一步|为了.+需要|如何|什么方式|为什么|[？?])")
INTRODUCTION_LANGUAGE_RE = re.compile(r"(?:本章(?:我们)?将|本节(?:我们)?将|我们将学习|学习目标|研究.+基础|为了.+需要|下面(?:先|来))")
SECTION_SCOPE_QUESTION_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:我们知道|我们已经知道|已经知道|此前|前面(?:已经)?.{0,24}(?:学习|研究|接触)|"
    r"在.{0,36}(?:已经)?(?:学习|研究|接触)).{0,180}?(?:是否|能否|可否|有没有|也有|又有).{0,100}?[？?]",
    re.DOTALL,
)
SOLUTION_LANGUAGE_RE = re.compile(r"(?:解法[一二三四五六七八九十\d]+|^\s*(?:解|证明|分析)\s*[：:]|因此|所以|可得|叫作|称为|法则)", re.MULTILINE)
CONTINUATION_TITLE_RE = re.compile(
    r"(?:^|[\s·・、_-])(?:续(?:\s*\d+)?|continued|continuation|part\s*\d+)(?:$|[\s·・、_-])",
    re.IGNORECASE,
)


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


def activity_markers(lines: list[str], source_range: list[int] | tuple[int, int]) -> list[dict[str, Any]]:
    """Return printed activity labels that must be dispositioned by the LLM.

    The marker is deliberately kept separate from the atom category: a
    ``思考`` heading may be a scenario, a reflection question, an exercise, or
    an inseparable scaffold for the following definition.  The model decides
    that role, but it may not silently drop the marker.
    """
    start, end = int(source_range[0]), int(source_range[1])
    result: list[dict[str, Any]] = []
    for number in range(start, end + 1):
        text = lines[number - 1].strip()
        if ACTIVITY_MARKER_RE.fullmatch(text):
            result.append({"line": number, "text": text})
    return result


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
    if config.get("mode") not in {"llm-two-pass", "llm-category-aware-graph"}:
        raise AtomizationError("atomization.mode must be llm-two-pass or llm-category-aware-graph")
    if config.get("mode") == "llm-two-pass" and "teaching_role_audit" not in supplied:
        config.pop("teaching_role_audit", None)
    for field in ("confidence_threshold", "short_atom_confidence_threshold"):
        value = config.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise AtomizationError(f"atomization.{field} must be between 0 and 1")
        config[field] = float(value)
    cycles = config.get("relation_feedback_cycles", 2)
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 0 <= cycles <= 2:
        raise AtomizationError("atomization.relation_feedback_cycles must be an integer from 0 to 2")
    if category_aware(config):
        for field, expected in {
            "knowledge_boundary_authority": "llm-exclusive",
            "provisional_atom_policy": "coverage-context-only",
            "parallel_definition_policy": "split-when-independently-reusable",
            "scoped_introduction_policy": "one-source-complete-atom-per-owner",
            "knowledge_motivation_policy": "complete-problem-or-context",
        }.items():
            if config.get(field) != expected:
                raise AtomizationError(f"atomization.{field} must be {expected}")
    return config


def category_aware(config: dict[str, Any]) -> bool:
    return config.get("mode") == "llm-category-aware-graph"


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
    if category_aware(config):
        organizer_errors = validate_organizer_review(
            manifest,
            manifest.get("source_markdown_sha256"),
            set(nodes),
            required=True,
        )
        if organizer_errors:
            raise AtomizationError(
                "Category-aware atomization requires a passed, digest-bound organizer review: "
                + json.dumps(organizer_errors, ensure_ascii=False)
            )
    available = [str(key) for key in nodes[root].get("children", []) if nodes.get(str(key), {}).get("layer") == "organizer"]
    scope = list(selected_roots or available)
    if not scope or any(key not in available for key in scope):
        raise AtomizationError("Every --root-key must be a direct organizer child of the root")
    selected: set[str] = set()
    for key in scope:
        selected.update(descendants(nodes, key))
    # Whole-book runs also review direct root prose such as a preface or reader
    # guide. A chapter-only experiment intentionally leaves it out of scope.
    if set(scope) == set(available):
        selected.add(root)

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
            # An existing printed organizer may legitimately own a motivation
            # immediately before its own heading and the teaching body after
            # that heading. Never send the retained heading through an atom
            # packet: split the owner's source runs at its heading boundary.
            heading_lines = sorted(
                int(value)
                for item in organizer.get("heading_ranges", [])
                if isinstance(item, list) and len(item) == 2
                for value in item
                if isinstance(value, int)
            )
            semantic_runs: list[list[dict[str, Any]]] = []
            current_run: list[dict[str, Any]] = []
            for atom in run_atoms:
                if current_run:
                    previous_end = int(current_run[-1]["source_range"][1])
                    current_start = int(atom["source_range"][0])
                    if any(previous_end < line < current_start for line in heading_lines):
                        semantic_runs.append(current_run)
                        current_run = []
                current_run.append(atom)
            if current_run:
                semantic_runs.append(current_run)
            for semantic_run in semantic_runs:
                run_number += 1
                run_identity = f"{owner}:{semantic_run[0]['source_range'][0]}"
                run_id = f"run-{run_number:04d}-{hashlib.sha256(run_identity.encode()).hexdigest()[:8]}"
                packets = split_run(semantic_run, lines, max_chars)
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
                        "activity_markers": activity_markers(lines, [start, end]),
                        "instructions": {
                            "boundary_authority": "LLM has exclusive authority over knowledge boundaries and atom count. Baseline atoms are non-binding coverage/context hints only; ignore their titles and internal boundaries unless an explicit hard boundary is independently proven.",
                            "parallel_definitions": "No transition word is required. If adjacent prose independently defines parallel reusable terms (for example 全称量词 and 存在量词), create separate knowledge atoms and topic assignments. Keep each prompt with the concept it scaffolds.",
                            "knowledge": "Keep definition, conditions, notation, explanation, derivation, and nearby conclusion in one complete teaching unit.",
                            "scenario": "Preserve every meaningful printed activity marker (观察、思考、尝试、交流、探究等) and its question/context. Classify a complete prompt as scenario, book-introduction, chapter-introduction, section-introduction, knowledge-motivation, or reflection-question; classify a complete top-level task as exercise. A book/chapter/section introduction is one discourse-level atom containing all contiguous introductory paragraphs, questions, figures, and captions up to the next structural heading; never split it into continuation or image-only atoms. A knowledge motivation preserves the complete problem or context, including its figure/caption and final question, and points to one target topic. Only merge an activity marker into knowledge when the prompt and the immediately following definition/explanation are one inseparable teaching unit, and return an explicit activity_disposition with that reason. A post-knowledge unanswered 思考 is normally a reflection-question, not a knowledge fragment.",
                            "reflection_question": "A complete post-knowledge comparison, synthesis, extension, or open inquiry may stand alone as category scenario with scenario_role reflection-question; it is not an exercise merely because it is phrased as a question.",
                            "worked_example": "Keep complete stem, analysis, solution, and nearby conclusion.",
                            "exercise": "Keep a top-level question with all subparts, figures, tables, and materials.",
                            "source_fidelity": "Choose contiguous source ranges only; never rewrite source text."
                        },
                    }
                    if category_aware(config):
                        job["instructions"].update({
                            "joint_output": "Return the partition, a teaches/assumes/outputs signature for every knowledge atom, local logical relations with two-sided evidence, and source-grounded concept/formula candidates in one decision. Do not copy the baseline partition: determine knowledge atom count and boundaries from teaching semantics alone.",
                            "boundary_relation_consistency": "Merge knowledge fragments that are one teaching process; split only independently reusable knowledge with different dependency signatures.",
                            "derived_cards": "Concept candidates come only from knowledge and must cite a definition-form source span only (formal definition/property/rule plus immediate conditions; exclude examples, prompts, and questions). Formula candidates require a reusable expression plus variables, conditions, or explanation and come only from knowledge or a bridge worked example.",
                            "activity_dispositions": "For every activity_markers line, return exactly one activity_disposition {line, atom_id, disposition: scenario|exercise|merged-with-knowledge, rationale}. A marker may not be omitted or hidden by deleting its heading.",
                        })
                    job["packet_sha256"] = canonical_digest(job)
                    jobs.append(job)
    if not jobs:
        raise AtomizationError("Selected roots contain no draft atoms")
    return seal_artifact({
        "schema_version": 2 if category_aware(config) else 1, "kind": "atomization-jobs",
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
    scenario_role = atom.get("scenario_role")
    if scenario_role is not None and (atom.get("category") != "scenario" or scenario_role not in SCENARIO_ROLES):
        errors.append({"code": "decision-scenario-role-invalid", "field": field, "scenario_role": scenario_role})
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


def _string_list(value: Any, field: str, errors: list[dict[str, Any]], allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.append({"code": "joint-string-list-invalid", "field": field})
        return []
    result = [item.strip() for item in value]
    if not allow_empty and not result:
        errors.append({"code": "joint-string-list-empty", "field": field})
    return result


def validate_joint_metadata(
    decision: dict[str, Any], atoms: list[dict[str, Any]], lines: list[str], location: str,
    config: dict[str, Any], errors: list[dict[str, Any]], review: list[dict[str, Any]], final: bool,
) -> dict[str, list[dict[str, Any]]]:
    """Validate semantics emitted with a category-aware partition.

    These records refer to temporary atom ids.  They deliberately contain no
    rewritten body text and are rebound to stable atom keys only after the
    boundary/relationship loop is frozen.
    """
    atom_by_id = {str(atom.get("atom_id")): atom for atom in atoms}
    # Activity headings are source content, not disposable Markdown chrome.
    # Every marker in the packet must be explicitly classified by the model so
    # a lost ``思考``/``观察`` cannot silently turn into a knowledge atom.
    marker_lines: dict[int, dict[str, Any]] = {}
    for atom in atoms:
        for marker in activity_markers(lines, atom["source_range"]):
            marker_lines[int(marker["line"])] = marker
    dispositions_raw = decision.get("activity_dispositions", [])
    if marker_lines and not isinstance(dispositions_raw, list):
        errors.append({"code": "activity-dispositions-missing", "location": location})
        dispositions_raw = []
    disposition_by_line: dict[int, dict[str, Any]] = {}
    if isinstance(dispositions_raw, list):
        for index, raw in enumerate(dispositions_raw):
            field = f"{location}.activity_dispositions[{index}]"
            if not isinstance(raw, dict):
                errors.append({"code": "activity-disposition-invalid", "field": field})
                continue
            try:
                line = int(raw.get("line"))
            except (TypeError, ValueError):
                errors.append({"code": "activity-disposition-line-invalid", "field": field})
                continue
            if line not in marker_lines or line in disposition_by_line:
                errors.append({"code": "activity-disposition-coverage-invalid", "field": field, "line": line})
                continue
            atom_id = str(raw.get("atom_id", ""))
            atom = next((item for item in atoms if int(item["source_range"][0]) <= line <= int(item["source_range"][1])), None)
            disposition = str(raw.get("disposition", ""))
            if atom is None or atom_id != str(atom.get("atom_id")):
                errors.append({"code": "activity-disposition-atom-invalid", "field": field, "line": line})
                continue
            if disposition not in {"scenario", "exercise", "merged-with-knowledge"}:
                errors.append({"code": "activity-disposition-kind-invalid", "field": field, "line": line})
                continue
            rationale = str(raw.get("rationale", "")).strip()
            if len(rationale) < 12:
                errors.append({"code": "activity-disposition-rationale-invalid", "field": field, "line": line})
            if disposition == "merged-with-knowledge" and atom.get("category") != "knowledge":
                errors.append({"code": "activity-disposition-merge-target-invalid", "field": field, "line": line})
            if disposition == "scenario" and atom.get("category") != "scenario":
                errors.append({"code": "activity-disposition-scenario-target-invalid", "field": field, "line": line})
            if disposition == "exercise" and atom.get("category") != "exercise":
                errors.append({"code": "activity-disposition-exercise-target-invalid", "field": field, "line": line})
            disposition_by_line[line] = {"line": line, "atom_id": atom_id, "disposition": disposition, "rationale": rationale}
    if marker_lines:
        missing = sorted(set(marker_lines) - set(disposition_by_line))
        if missing:
            errors.append({"code": "activity-disposition-coverage-invalid", "location": location, "missing_lines": missing})
    for disposition in disposition_by_line.values():
        target = next((item for item in atoms if str(item.get("atom_id")) == str(disposition["atom_id"])), None)
        if target is not None:
            target.setdefault("activity_dispositions", []).append(dict(disposition))
    knowledge_ids = {key for key, atom in atom_by_id.items() if atom.get("category") == "knowledge"}
    signatures_raw = decision.get("knowledge_signatures")
    if not isinstance(signatures_raw, list):
        errors.append({"code": "knowledge-signatures-missing", "location": location})
        signatures_raw = []
    signatures: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for index, raw in enumerate(signatures_raw):
        field = f"{location}.knowledge_signatures[{index}]"
        if not isinstance(raw, dict):
            errors.append({"code": "knowledge-signature-invalid", "field": field})
            continue
        atom_id = str(raw.get("atom_id", ""))
        if atom_id not in knowledge_ids or atom_id in seen_signatures:
            errors.append({"code": "knowledge-signature-atom-invalid", "field": field, "atom_id": atom_id})
            continue
        seen_signatures.add(atom_id)
        teaches = _string_list(raw.get("teaches"), f"{field}.teaches", errors, allow_empty=False)
        assumes = _string_list(raw.get("assumes"), f"{field}.assumes", errors)
        outputs = _string_list(raw.get("outputs"), f"{field}.outputs", errors)
        global_needed = raw.get("global_relation_needed", False)
        if not isinstance(global_needed, bool):
            errors.append({"code": "knowledge-signature-global-flag-invalid", "field": field})
            global_needed = False
        independent_reason = str(raw.get("independent_reason", "")).strip()
        if independent_reason and len(independent_reason) < 12:
            review.append({"code": "knowledge-independent-reason-too-short", "location": location, "atom_id": atom_id})
        signatures.append({
            "atom_id": atom_id, "teaches": teaches, "assumes": assumes, "outputs": outputs,
            "global_relation_needed": global_needed, "independent_reason": independent_reason,
        })
    if seen_signatures != knowledge_ids:
        errors.append({"code": "knowledge-signature-coverage-invalid", "location": location, "missing": sorted(knowledge_ids - seen_signatures), "extra": sorted(seen_signatures - knowledge_ids)})

    relations_raw = decision.get("local_relations")
    if not isinstance(relations_raw, list):
        errors.append({"code": "local-relations-missing", "location": location})
        relations_raw = []
    relations: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    incident: set[str] = set()
    for index, raw in enumerate(relations_raw):
        field = f"{location}.local_relations[{index}]"
        if not isinstance(raw, dict):
            errors.append({"code": "local-relation-invalid", "field": field})
            continue
        left, right, relation_type = str(raw.get("from_atom_id", "")), str(raw.get("to_atom_id", "")), str(raw.get("type", ""))
        identity = (left, right, relation_type)
        if left not in atom_by_id or right not in atom_by_id or left == right or relation_type not in LOCAL_RELATION_TYPES or identity in identities:
            errors.append({"code": "local-relation-endpoint-or-type-invalid", "field": field})
            continue
        identities.add(identity)
        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            errors.append({"code": "local-relation-confidence-invalid", "field": field})
            confidence = 0.0
        elif float(confidence) < float(config["confidence_threshold"]):
            review.append({"code": "local-relation-low-confidence", "field": field, "confidence": confidence})
        rationale = str(raw.get("rationale", "")).strip()
        if len(rationale) < 12:
            errors.append({"code": "local-relation-rationale-invalid", "field": field})
        evidence_raw = raw.get("evidence")
        evidence: list[dict[str, Any]] = []
        evidence_atoms: set[str] = set()
        if not isinstance(evidence_raw, list):
            errors.append({"code": "local-relation-evidence-missing", "field": field})
            evidence_raw = []
        for evidence_index, item in enumerate(evidence_raw):
            if not isinstance(item, dict) or str(item.get("atom_id", "")) not in {left, right}:
                errors.append({"code": "local-relation-evidence-invalid", "field": f"{field}.evidence[{evidence_index}]"})
                continue
            atom_id = str(item["atom_id"])
            try:
                start, end = parse_range(item.get("source_range"), f"{field}.evidence[{evidence_index}].source_range", len(lines))
            except Exception as exc:
                errors.append({"code": "local-relation-evidence-range-invalid", "field": field, "detail": str(exc)})
                continue
            owner_start, owner_end = atom_by_id[atom_id]["source_range"]
            if start < int(owner_start) or end > int(owner_end):
                errors.append({"code": "local-relation-evidence-outside-atom", "field": field, "atom_id": atom_id})
                continue
            evidence_atoms.add(atom_id)
            evidence.append({"atom_id": atom_id, "source_range": [start, end]})
        if evidence_atoms != {left, right}:
            errors.append({"code": "local-relation-two-sided-evidence-missing", "field": field})
        recall_source = _string_list(raw.get("recall_source"), f"{field}.recall_source", errors, allow_empty=False)
        incident.update({left, right})
        relations.append({
            "from_atom_id": left, "to_atom_id": right, "type": relation_type,
            "tier": str(raw.get("tier", "supporting")), "evidence_kind": str(raw.get("evidence_kind", "pedagogical-inference")),
            "evidence": evidence, "rationale": rationale, "confidence": float(confidence), "recall_source": recall_source,
        })
    for signature in signatures:
        atom_id = signature["atom_id"]
        if atom_id not in incident and not signature["global_relation_needed"] and not signature["independent_reason"]:
            review.append({"code": "knowledge-local-relation-missing", "location": location, "atom_id": atom_id})

    candidates_raw = decision.get("derived_card_candidates")
    if not isinstance(candidates_raw, list):
        errors.append({"code": "derived-card-candidates-missing", "location": location})
        candidates_raw = []
    candidates: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for index, raw in enumerate(candidates_raw):
        field = f"{location}.derived_card_candidates[{index}]"
        if not isinstance(raw, dict):
            errors.append({"code": "derived-card-candidate-invalid", "field": field})
            continue
        candidate_id, atom_id, derived_category = str(raw.get("candidate_id", "")), str(raw.get("from_atom_id", "")), str(raw.get("category", ""))
        source_atom_value = atom_by_id.get(atom_id)
        allowed_source = source_atom_value and (source_atom_value.get("category") == "knowledge" or (derived_category == "formula" and source_atom_value.get("category") == "worked-example" and raw.get("example_role") == "bridge"))
        if not candidate_id or candidate_id in seen_candidates or derived_category not in DERIVED_CATEGORY_NAMES or not allowed_source:
            errors.append({"code": "derived-card-source-or-category-invalid", "field": field})
            continue
        seen_candidates.add(candidate_id)
        try:
            start, end = parse_range(raw.get("source_range"), f"{field}.source_range", len(lines))
        except Exception as exc:
            errors.append({"code": "derived-card-range-invalid", "field": field, "detail": str(exc)})
            continue
        owner_start, owner_end = source_atom_value["source_range"]
        if start < int(owner_start) or end > int(owner_end):
            errors.append({"code": "derived-card-range-outside-source", "field": field})
        title, reason = str(raw.get("title", "")).strip(), str(raw.get("selection_reason", "")).strip()
        if not title or len(reason) < 12:
            errors.append({"code": "derived-card-description-invalid", "field": field})
        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            errors.append({"code": "derived-card-confidence-invalid", "field": field})
            confidence = 0.0
        if derived_category == "formula" and not str(raw.get("expression", "")).strip():
            errors.append({"code": "derived-formula-expression-missing", "field": field})
        candidates.append({
            "candidate_id": candidate_id, "from_atom_id": atom_id, "category": derived_category,
            "title": title, "source_range": [start, end], "selection_reason": reason,
            "confidence": float(confidence), "expression": str(raw.get("expression", "")).strip(),
            "variables": list(raw.get("variables", [])) if isinstance(raw.get("variables"), list) else [],
            "conditions": list(raw.get("conditions", [])) if isinstance(raw.get("conditions"), list) else [],
        })
    return {
        "knowledge_signatures": signatures,
        "local_relations": relations,
        "derived_card_candidates": candidates,
        "activity_dispositions": list(disposition_by_line.values()),
    }


def hard_boundary_issues(atoms: list[dict[str, Any]], markers: list[dict[str, Any]], location: str) -> list[dict[str, Any]]:
    starts = {int(atom["source_range"][0]): atom for atom in atoms if isinstance(atom.get("source_range"), list)}
    return [{"code": "hard-boundary-violation", "location": location, "line": marker.get("line"), "required_category": marker.get("category"), "evidence": marker.get("evidence")} for marker in markers if starts.get(marker.get("line"), {}).get("category") != marker.get("category")]


def quality_issues(atom: dict[str, Any], lines: list[str], config: dict[str, Any], location: str, final: bool) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    confidence = atom.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and float(confidence) < float(config["confidence_threshold"]):
        issues.append({"code": "low-confidence", "location": location, "atom_id": atom.get("atom_id"), "confidence": confidence})
    if category_aware(config) and final:
        body_text = "\n".join(source_slice(lines, atom["source_range"]))
        markers = activity_markers(lines, atom["source_range"])
        if atom.get("category") == "knowledge" and markers:
            dispositions = {
                int(item.get("line")): str(item.get("disposition"))
                for item in atom.get("activity_dispositions", []) if isinstance(item, dict)
            }
            if any(dispositions.get(int(item["line"])) != "merged-with-knowledge" for item in markers):
                issues.append({"code": "knowledge-activity-marker-requires-scenario-or-explicit-merge", "location": location, "atom_id": atom.get("atom_id"), "lines": [item["line"] for item in markers]})
        if atom.get("category") == "worked-example" and (not EXAMPLE_RE.search(body_text) or not SOLUTION_LANGUAGE_RE.search(body_text)):
            issues.append({"code": "worked-example-incomplete", "location": location, "atom_id": atom.get("atom_id")})
        if atom.get("category") == "exercise" and not (EXERCISE_RE.search(body_text) or EXERCISE_HEADING_RE.search(body_text)):
            issues.append({"code": "exercise-top-level-boundary-unproven", "location": location, "atom_id": atom.get("atom_id")})
        if atom.get("category") == "scenario":
            role = atom.get("scenario_role")
            length = normalized_char_count(source_slice(lines, atom["source_range"]))
            if role not in SCENARIO_ROLES:
                issues.append({"code": "scenario-role-missing-or-invalid", "location": location, "atom_id": atom.get("atom_id")})
            elif role == "reflection-question":
                if not REFLECTION_LANGUAGE_RE.search(body_text):
                    issues.append({"code": "reflection-question-not-actionable", "location": location, "atom_id": atom.get("atom_id")})
            elif role == "knowledge-motivation":
                if length < 150 and not KNOWLEDGE_MOTIVATION_RE.search(body_text):
                    issues.append({"code": "knowledge-motivation-not-a-bridge", "location": location, "atom_id": atom.get("atom_id")})
            elif length < 150 and not (
                INTRODUCTION_LANGUAGE_RE.search(body_text)
                or (role == "section-introduction" and SECTION_SCOPE_QUESTION_RE.search(body_text))
            ):
                issues.append({"code": "scenario-not-substantial", "location": location, "atom_id": atom.get("atom_id")})
    if atom.get("category") != "knowledge":
        return issues
    if category_aware(config) and final:
        body_text = "\n".join(source_slice(lines, atom["source_range"]))
        section_scope_match = SECTION_SCOPE_QUESTION_RE.search(body_text)
        if section_scope_match and len(body_text[section_scope_match.end():].strip()) >= 20:
            issues.append({
                "code": "section-introduction-absorbed-into-knowledge",
                "location": location,
                "atom_id": atom.get("atom_id"),
                "source_range": atom.get("source_range"),
            })
    body = source_slice(lines, atom["source_range"])
    short = normalized_char_count(body) < 150 or sum(bool(line.strip()) for line in body) <= 1
    if not short:
        return issues
    if not final:
        issues.append({"code": "short-knowledge-requires-round2-audit", "location": location, "atom_id": atom.get("atom_id"), "source_range": atom.get("source_range")})
    elif not (atom.get("standalone_kind") in FORMAL_STANDALONE_KINDS and isinstance(atom.get("standalone_reason"), str) and len(atom["standalone_reason"].strip()) >= 12 and isinstance(confidence, (int, float)) and float(confidence) >= float(config["short_atom_confidence_threshold"])):
        issues.append({"code": "short-knowledge-not-independent", "location": location, "atom_id": atom.get("atom_id"), "source_range": atom.get("source_range"), "required_confidence": config["short_atom_confidence_threshold"]})
    return issues


def scoped_scenario_issues(
    atoms: list[dict[str, Any]],
    lines: list[str],
    location: str = "final",
) -> list[dict[str, Any]]:
    """Reject paragraph-level fragmentation of book/chapter/section introductions.

    These introductions are discourse units, not a bag of paragraphs.  A
    figure-only continuation, a title such as ``续 2``, or several atoms with
    the same scoped role and owner means the final partition is not stable.
    """
    issues: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    scoped_by_owner: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        if atom.get("category") != "scenario" or atom.get("scenario_role") not in SCOPED_INTRO_ROLES:
            continue
        role = str(atom["scenario_role"])
        owner = str(atom.get("owner_key", ""))
        grouped.setdefault((owner, role), []).append(atom)
        scoped_by_owner.setdefault(owner, []).append(atom)
        title = str(atom.get("title", "")).strip()
        if CONTINUATION_TITLE_RE.search(title):
            issues.append({
                "code": "scoped-introduction-continuation-title",
                "location": location,
                "owner_key": owner,
                "scenario_role": role,
                "atom_id": atom.get("atom_id"),
                "title": title,
            })
        body = "\n".join(source_slice(lines, atom["source_range"]))
        without_media = re.sub(r"!\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)", "", body)
        without_media = re.sub(r"<img\b[^>]*>", "", without_media, flags=re.IGNORECASE)
        without_media = re.sub(r"^\s{0,3}#{1,6}\s*", "", without_media, flags=re.MULTILINE)
        if not re.sub(r"\s+", "", without_media):
            issues.append({
                "code": "scoped-introduction-media-only-fragment",
                "location": location,
                "owner_key": owner,
                "scenario_role": role,
                "atom_id": atom.get("atom_id"),
            })
    for (owner, role), members in grouped.items():
        if len(members) > 1:
            issues.append({
                "code": "scoped-introduction-fragmented",
                "location": location,
                "owner_key": owner,
                "scenario_role": role,
                "atom_ids": [item.get("atom_id") for item in members],
                "source_ranges": [item.get("source_range") for item in members],
            })
    for owner, members in scoped_by_owner.items():
        roles = sorted({str(item.get("scenario_role")) for item in members})
        if len(roles) > 1:
            issues.append({
                "code": "scoped-introduction-role-conflict",
                "location": location,
                "owner_key": owner,
                "scenario_roles": roles,
                "atom_ids": [item.get("atom_id") for item in members],
            })
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
    normalized_semantics: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for job in jobs.get("jobs", []):
        decision = by_job.get(job["job_id"])
        if not isinstance(decision, dict):
            continue
        if decision.get("packet_sha256") != job.get("packet_sha256"):
            errors.append({"code": "round1-packet-digest-mismatch", "job_id": job["job_id"]})
        atoms = validate_partition(decision.get("atoms"), job["source_range"], job["owner_key"], lines, f"job:{job['job_id']}", errors)
        normalized[job["job_id"]] = atoms
        if category_aware(jobs["atomization"]):
            normalized_semantics[job["job_id"]] = validate_joint_metadata(
                decision, atoms, lines, f"job:{job['job_id']}", jobs["atomization"], errors, review, False,
            )
        review.extend(hard_boundary_issues(atoms, job.get("hard_boundaries", []), job["job_id"]))
        for atom in atoms:
            review.extend(quality_issues(atom, lines, jobs["atomization"], job["job_id"], False))
    return {"schema_version": 2 if category_aware(jobs["atomization"]) else 1, "status": "failed" if errors else ("review_required" if review else "passed"), "structural_errors": errors, "review_items": review, "counts": {"jobs": len(jobs.get("jobs", [])), "atoms": sum(len(value) for value in normalized.values()), "review_items": len(review)}, "normalized_atoms": normalized, "normalized_semantics": normalized_semantics}


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
        round1_semantics = {
            key: [item for job in run_jobs for item in report["normalized_semantics"].get(job["job_id"], {}).get(key, [])]
            for key in ("knowledge_signatures", "local_relations", "derived_card_candidates", "activity_dispositions")
        }
        audit = {"audit_id": audit_id, "run_id": run_id, "owner_key": run_jobs[0]["owner_key"], "top_level_key": run_jobs[0]["top_level_key"], "source_range": [start, end], "source_lines": [{"line": number, "text": lines[number-1]} for number in range(start, end+1)], "round1_atoms": atoms, "round1_semantics": round1_semantics, "boundaries": boundaries, "hard_boundaries": markers, "instructions": {"required": "Review every boundary and return the complete final partition plus signatures, local relations, and derived candidates for that final partition.", "actions": ["keep", "merge", "resegment"], "fragment_gate": "Short knowledge must merge unless it is a formal independent definition, theorem, or law with confidence >= 0.95.", "category_rules": "Knowledge follows complete teaching semantics; worked examples preserve stem-analysis-solution-conclusion; each top-level exercise preserves every subpart and resource; every printed activity marker must be preserved and dispositioned as scenario, exercise, or an explicitly justified merged scaffold.", "scoped_introductions": "Merge every contiguous book, chapter, or section introduction into one complete scenario atom per owner and role, including all introductory paragraphs, questions, figures, and captions. Reject continuation and media-only fragments.", "knowledge_motivations": "Keep a complete problem/context, figure or caption, and final motivating question together and bind it to the one knowledge topic it introduces.", "relation_boundary_consistency": "Merge knowledge atoms that are one teaching process; resegment an atom that teaches independently reusable concepts with different dependency structures.", "source_fidelity": "Never rewrite source text."}}
        audit["packet_sha256"] = canonical_digest(audit)
        audits.append(audit)
    return seal_artifact({"schema_version": 2 if category_aware(jobs["atomization"]) else 1, "kind": "round-2-jobs", "jobs_sha256": jobs["artifact_sha256"], "round_1_decisions_sha256": round1["artifact_sha256"], "source_markdown": jobs["source_markdown"], "source_markdown_sha256": jobs["source_markdown_sha256"], "scope_root_keys": jobs["scope_root_keys"], "atomization": jobs["atomization"], "audits": audits})


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
    final_signatures: list[dict[str, Any]] = []
    final_local_relations: list[dict[str, Any]] = []
    final_derived_candidates: list[dict[str, Any]] = []
    final_activity_dispositions: list[dict[str, Any]] = []
    for audit in audit_jobs.get("audits", []):
        decision = by_audit.get(audit["audit_id"])
        if not isinstance(decision, dict):
            continue
        if decision.get("packet_sha256") != audit.get("packet_sha256"):
            errors.append({"code": "round2-packet-digest-mismatch", "audit_id": audit["audit_id"]})
        atoms = validate_partition(decision.get("atoms"), audit["source_range"], audit["owner_key"], lines, f"audit:{audit['audit_id']}", errors)
        if category_aware(jobs["atomization"]):
            semantics = validate_joint_metadata(
                decision, atoms, lines, f"audit:{audit['audit_id']}", jobs["atomization"], errors, review, True,
            )
            final_signatures.extend(semantics["knowledge_signatures"])
            final_local_relations.extend(semantics["local_relations"])
            final_derived_candidates.extend(semantics["derived_card_candidates"])
            final_activity_dispositions.extend(semantics.get("activity_dispositions", []))
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
    if category_aware(jobs["atomization"]):
        review.extend(scoped_scenario_issues(final_atoms, lines))
    unresolved = [*errors, *review]
    bindings = {name: {"path": payload.get("_path"), "sha256": payload["artifact_sha256"]} for name, payload in (("jobs", jobs), ("round_1_decisions", round1), ("round_2_jobs", audit_jobs), ("round_2_decisions", round2))}
    final = seal_artifact({"schema_version": 2 if category_aware(jobs["atomization"]) else 1, "kind": "atomization-final", "status": "passed" if not unresolved else "review_required", "source_markdown": jobs["source_markdown"], "source_markdown_sha256": jobs["source_markdown_sha256"], "base_manifest": jobs["base_manifest"], "base_manifest_sha256": jobs["base_manifest_sha256"], "scope_root_keys": jobs["scope_root_keys"], "atomization": jobs["atomization"], "reviewer": {"round_1": round1.get("reviewer"), "round_2": round2.get("reviewer")}, "bindings": bindings, "unresolved_count": len(unresolved), "atoms": final_atoms, "knowledge_signatures": final_signatures, "local_relations": final_local_relations, "derived_card_candidates": final_derived_candidates, "activity_dispositions": final_activity_dispositions, "feedback_cycle": {"cycle": 0, "max_cycles": int(jobs["atomization"].get("relation_feedback_cycles", 2)), "history": []}})
    queue = seal_artifact({"schema_version": 1, "kind": "atomization-review-queue", "status": "passed" if not unresolved else "blocked", "atomization_final_sha256": final["artifact_sha256"], "unresolved_count": len(unresolved), "items": unresolved})
    return final, queue


def teaching_role_flags(atom: dict[str, Any], lines: list[str]) -> list[str]:
    """Recall suspicious atoms for a focused post-partition role audit.

    These signals never reclassify source automatically. They deliberately
    favour recall so an Agent can distinguish a prompt that belongs inside a
    complete teaching arc from a genuinely misclassified task or scenario.
    """
    body = "\n".join(source_slice(lines, atom["source_range"]))
    compact_title = "".join(str(atom.get("title", "")).split())
    category = str(atom.get("category"))
    flags: list[str] = []
    if len(compact_title) > 48:
        flags.append("title-too-long-for-reusable-atom")
    if category == "knowledge" and TASK_LANGUAGE_RE.search(str(atom.get("title", ""))):
        flags.append("knowledge-title-looks-like-question-or-task")
    if category == "knowledge" and ACTIVITY_HEADING_RE.search(body):
        flags.append("knowledge-contains-activity-heading")
    if category == "knowledge" and TASK_LANGUAGE_RE.search(body) and not SOLUTION_LANGUAGE_RE.search(body):
        flags.append("knowledge-looks-like-unsolved-task")
    if category == "knowledge" and normalized_char_count(source_slice(lines, atom["source_range"])) > 1200:
        flags.append("knowledge-may-contain-multiple-teaching-roles")
    if category == "knowledge" and re.search(r"解法[一二三四五六七八九十\d]+", body):
        flags.append("knowledge-looks-like-worked-example")
    return sorted(set(flags))


def prepare_feedback_jobs(final_path: Path, relation_final_path: Path) -> dict[str, Any]:
    """Turn graph-audit boundary feedback into bounded re-atomization jobs."""
    final_path, relation_final_path = final_path.expanduser().resolve(), relation_final_path.expanduser().resolve()
    final, relation_final = load_json(final_path), load_json(relation_final_path)
    verify_artifact(final, "atomization-final")
    verify_artifact(relation_final, "relation-final-v2")
    if final.get("status") != "passed" or final.get("unresolved_count") != 0:
        raise AtomizationError("Boundary feedback requires a passed atomization-final")
    if relation_final.get("atomization_final_sha256") != final.get("artifact_sha256"):
        raise AtomizationError("Relation final is not bound to this atomization-final")
    feedback = relation_final.get("boundary_feedback")
    if not isinstance(feedback, list) or not feedback:
        raise AtomizationError("Relation final contains no boundary feedback")
    cycle = int(final.get("feedback_cycle", {}).get("cycle", 0))
    maximum = int(final.get("feedback_cycle", {}).get("max_cycles", final.get("atomization", {}).get("relation_feedback_cycles", 2)))
    if cycle >= maximum:
        raise AtomizationError("Automatic boundary feedback cycle limit reached")
    source = Path(str(final.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != final.get("source_markdown_sha256"):
        raise AtomizationError("Atomization source is missing or stale")
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    atoms = {str(item.get("atom_id")): item for item in final.get("atoms", []) if isinstance(item, dict)}
    jobs: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for index, item in enumerate(feedback, start=1):
        if not isinstance(item, dict) or item.get("action") not in {"merge", "split", "resegment"}:
            raise AtomizationError(f"Invalid boundary feedback item {index}")
        atom_ids = [str(value) for value in item.get("atom_ids", [])]
        selected = [atoms[value] for value in atom_ids if value in atoms]
        if len(selected) != len(atom_ids) or not selected:
            raise AtomizationError(f"Boundary feedback item {index} has unknown atoms")
        owners = {str(atom.get("owner_key")) for atom in selected}
        if len(owners) != 1:
            raise AtomizationError("Automatic feedback cannot cross organizer ownership")
        start = min(int(atom["source_range"][0]) for atom in selected)
        end = max(int(atom["source_range"][1]) for atom in selected)
        if any(not (end < left or start > right) for left, right in occupied):
            raise AtomizationError("Boundary feedback items overlap")
        occupied.append((start, end))
        job = {
            "feedback_id": str(item.get("feedback_id") or f"feedback-{index:04d}"),
            "action": str(item["action"]), "atom_ids": atom_ids, "owner_key": next(iter(owners)),
            "source_range": [start, end],
            "source_lines": [{"line": number, "text": lines[number - 1]} for number in range(start, end + 1)],
            "current_atoms": selected, "graph_evidence": item.get("evidence", []),
            "rationale": str(item.get("rationale", "")),
            "instructions": "Return a complete category-aware partition and its signatures, local relations, and derived candidates. Do not rewrite source.",
        }
        job["packet_sha256"] = canonical_digest(job)
        jobs.append(job)
    return seal_artifact({
        "schema_version": 2, "kind": "atomization-feedback-jobs",
        "atomization_final": str(final_path), "atomization_final_sha256": final["artifact_sha256"],
        "relation_final": str(relation_final_path), "relation_final_sha256": relation_final["artifact_sha256"],
        "source_markdown": str(source), "source_markdown_sha256": final["source_markdown_sha256"],
        "feedback_cycle": cycle + 1, "max_cycles": maximum, "atomization": final["atomization"], "jobs": jobs,
    })


def finalize_feedback(final: dict[str, Any], jobs: dict[str, Any], decisions: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    for payload, kind in ((final, "atomization-final"), (jobs, "atomization-feedback-jobs"), (decisions, "atomization-feedback-decisions")):
        verify_artifact(payload, kind)
    if jobs.get("atomization_final_sha256") != final.get("artifact_sha256") or decisions.get("feedback_jobs_sha256") != jobs.get("artifact_sha256"):
        raise AtomizationError("Boundary feedback artifact chain is stale")
    source = Path(str(jobs["source_markdown"])).expanduser().resolve()
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    raw = decisions.get("decisions")
    if not isinstance(raw, list):
        raw = []
    by_id = {str(item.get("feedback_id")): item for item in raw if isinstance(item, dict)}
    expected = {str(item["feedback_id"]) for item in jobs["jobs"]}
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    if set(by_id) != expected or len(by_id) != len(raw):
        errors.append({"code": "feedback-decision-coverage-invalid", "missing": sorted(expected - set(by_id)), "extra": sorted(set(by_id) - expected)})
    replacement_ids: set[str] = set()
    replacement_atoms: list[dict[str, Any]] = []
    signatures: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for job in jobs["jobs"]:
        decision = by_id.get(str(job["feedback_id"]))
        if not isinstance(decision, dict):
            continue
        if decision.get("packet_sha256") != job.get("packet_sha256"):
            errors.append({"code": "feedback-packet-digest-mismatch", "feedback_id": job["feedback_id"]})
        atoms = validate_partition(decision.get("atoms"), job["source_range"], job["owner_key"], lines, f"feedback:{job['feedback_id']}", errors)
        metadata = validate_joint_metadata(decision, atoms, lines, f"feedback:{job['feedback_id']}", jobs["atomization"], errors, review, True)
        replacement_ids.update(map(str, job["atom_ids"]))
        for atom in atoms:
            copied = {key: value for key, value in atom.items() if key not in FORBIDDEN_DECISION_FIELDS}
            copied["source_text_sha256"] = canonical_digest(source_slice(lines, atom["source_range"]))
            replacement_atoms.append(copied)
        signatures.extend(metadata["knowledge_signatures"])
        relations.extend(metadata["local_relations"])
        candidates.extend(metadata["derived_card_candidates"])
    retained = [dict(atom) for atom in final.get("atoms", []) if str(atom.get("atom_id")) not in replacement_ids]
    retained_ids = {str(atom.get("atom_id")) for atom in retained}
    merged_atoms = sorted([*retained, *replacement_atoms], key=lambda atom: (int(atom["source_range"][0]), int(atom["source_range"][1]), str(atom["atom_id"])))
    signatures = [item for item in final.get("knowledge_signatures", []) if str(item.get("atom_id")) in retained_ids] + signatures
    relations = [item for item in final.get("local_relations", []) if str(item.get("from_atom_id")) in retained_ids and str(item.get("to_atom_id")) in retained_ids] + relations
    candidates = [item for item in final.get("derived_card_candidates", []) if str(item.get("from_atom_id")) in retained_ids] + candidates
    unresolved = [*errors, *review]
    history = list(final.get("feedback_cycle", {}).get("history", []))
    history.append({"cycle": jobs["feedback_cycle"], "relation_final_sha256": jobs["relation_final_sha256"], "feedback_jobs_sha256": jobs["artifact_sha256"], "decisions_sha256": decisions["artifact_sha256"], "replaced_atom_ids": sorted(replacement_ids)})
    result = seal_artifact({
        **{key: value for key, value in final.items() if key not in {"artifact_sha256", "status", "unresolved_count", "atoms", "knowledge_signatures", "local_relations", "derived_card_candidates", "feedback_cycle"}},
        "status": "passed" if not unresolved else "review_required", "unresolved_count": len(unresolved),
        "atoms": merged_atoms, "knowledge_signatures": signatures, "local_relations": relations,
        "derived_card_candidates": candidates,
        "feedback_cycle": {"cycle": jobs["feedback_cycle"], "max_cycles": jobs["max_cycles"], "history": history},
    })
    queue = seal_artifact({"schema_version": 2, "kind": "atomization-review-queue", "status": "passed" if not unresolved else "blocked", "atomization_final_sha256": result["artifact_sha256"], "unresolved_count": len(unresolved), "items": unresolved})
    return result, queue


def prepare_role_review(final_path: Path) -> dict[str, Any]:
    final_path = final_path.expanduser().resolve()
    final = load_json(final_path)
    verify_artifact(final, "atomization-final")
    if category_aware({**DEFAULT_ATOMIZATION, **dict(final.get("atomization", {}))}):
        raise AtomizationError("Category-aware mode integrates teaching-role review into both atomization rounds")
    if final.get("status") != "passed" or final.get("unresolved_count") != 0:
        raise AtomizationError("Role review requires a passed atomization-final artifact")
    source = Path(str(final.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != final.get("source_markdown_sha256"):
        raise AtomizationError("Role review source Markdown is missing or stale")
    base_path = Path(str(final.get("base_manifest", ""))).expanduser().resolve()
    if not base_path.is_file() or sha256_file(base_path) != final.get("base_manifest_sha256"):
        raise AtomizationError("Role review base manifest is missing or stale")
    base = load_json(base_path)
    nodes = {str(item["key"]): item for item in base.get("nodes", []) if isinstance(item, dict) and item.get("key")}
    organizers = {key for key, node in nodes.items() if node.get("layer") == "organizer"}
    root = next((key for key in organizers if nodes[key].get("parent_key") is None), None)
    if root is None:
        raise AtomizationError("Role review base manifest has no root organizer")
    scope_roots = set(map(str, final.get("scope_root_keys", [])))

    def scope_for(owner: str) -> str:
        cursor = owner
        while nodes.get(cursor, {}).get("parent_key") not in {None, root}:
            cursor = str(nodes[cursor]["parent_key"])
        return cursor

    owners_by_scope: dict[str, list[str]] = {}
    for scope in scope_roots:
        owners_by_scope[scope] = [key for key in descendants(nodes, scope) if key in organizers]
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    review_atoms: list[dict[str, Any]] = []
    for atom in final.get("atoms", []):
        if not isinstance(atom, dict):
            continue
        flags = teaching_role_flags(atom, lines)
        owner = str(atom.get("owner_key"))
        scope = scope_for(owner)
        if str(atom.get("category")) == "exercise" and owner in scope_roots:
            flags = sorted({*flags, "chapter-opening-exercise-may-be-scenario"})
        item = {
            "atom_id": str(atom.get("atom_id")), "owner_key": owner,
            "source_range": list(atom.get("source_range", [])),
            "category": str(atom.get("category")), "title": str(atom.get("title", "")),
            "source_text": "\n".join(source_slice(lines, atom["source_range"])),
            "flags": flags, "requires_decision": bool(flags),
            "allowed_owner_keys": owners_by_scope.get(scope, [owner]),
        }
        review_atoms.append(item)
    return seal_artifact({
        "schema_version": 1, "kind": "atom-role-jobs",
        "atomization_final": str(final_path), "atomization_final_sha256": final["artifact_sha256"],
        "source_markdown": str(source), "source_markdown_sha256": final["source_markdown_sha256"],
        "base_manifest": str(base_path), "base_manifest_sha256": final["base_manifest_sha256"],
        "atomization": {**DEFAULT_ATOMIZATION, **dict(final.get("atomization", {}))},
        "confidence_threshold": float(final.get("atomization", {}).get("role_correction_confidence_threshold", 0.95)),
        "instructions": {
            "goal": "Ensure each atom has one accurate teaching role and a concise reusable title.",
            "actions": ["keep", "replace"],
            "replace": "Return a complete contiguous partition of the flagged atom. Reclassification, splitting, concise retitling, and evidence-backed reassignment inside the same scope are allowed; source text may not be rewritten.",
            "categories": sorted(ATOM_CATEGORY_NAMES),
        },
        "atoms": review_atoms,
    })


def validate_role_review(jobs: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    verify_artifact(jobs, "atom-role-jobs")
    verify_artifact(decisions, "atom-role-decisions")
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    if decisions.get("atom_role_jobs_sha256") != jobs.get("artifact_sha256"):
        errors.append({"code": "atom-role-binding-invalid"})
    required = {str(item["atom_id"]): item for item in jobs.get("atoms", []) if item.get("requires_decision")}
    raw = decisions.get("decisions")
    if not isinstance(raw, list):
        raw = []
        errors.append({"code": "atom-role-decisions-missing"})
    by_id = {str(item.get("atom_id")): item for item in raw if isinstance(item, dict)}
    if len(by_id) != len(raw) or set(by_id) != set(required):
        errors.append({"code": "atom-role-decision-coverage-invalid", "missing": sorted(set(required) - set(by_id)), "extra": sorted(set(by_id) - set(required))})
    normalized: dict[str, list[dict[str, Any]]] = {}
    threshold = float(jobs.get("confidence_threshold", 0.95))
    source = Path(str(jobs.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != jobs.get("source_markdown_sha256"):
        errors.append({"code": "atom-role-source-stale"})
        lines: list[str] = []
    else:
        lines = source.read_text(encoding="utf-8-sig").splitlines()
    seen_new_ids: set[str] = set()
    for atom_id, original in required.items():
        decision = by_id.get(atom_id)
        if decision is None:
            continue
        action = decision.get("action")
        rationale = decision.get("rationale")
        confidence = decision.get("confidence")
        if action not in {"keep", "replace"}:
            errors.append({"code": "atom-role-action-invalid", "atom_id": atom_id})
        if not isinstance(rationale, str) or len(rationale.strip()) < 12:
            errors.append({"code": "atom-role-rationale-invalid", "atom_id": atom_id})
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            errors.append({"code": "atom-role-confidence-invalid", "atom_id": atom_id})
            confidence = 0.0
        elif float(confidence) < threshold:
            review.append({"code": "atom-role-low-confidence", "atom_id": atom_id, "confidence": confidence, "required": threshold})
        if action == "keep":
            if decision.get("replacement_atoms") not in (None, []):
                errors.append({"code": "atom-role-keep-has-replacements", "atom_id": atom_id})
            if "title-too-long-for-reusable-atom" in set(map(str, original.get("flags", []))):
                review.append({
                    "code": "atom-role-title-not-corrected", "atom_id": atom_id,
                    "detail": "A keep decision cannot leave a title that is too long for reusable Markdown and Canvas labels.",
                })
            normalized[atom_id] = []
            continue
        replacements = decision.get("replacement_atoms")
        if not isinstance(replacements, list) or not replacements:
            errors.append({"code": "atom-role-replacements-missing", "atom_id": atom_id})
            continue
        parsed: list[tuple[int, int, dict[str, Any]]] = []
        for index, replacement in enumerate(replacements):
            context = f"{atom_id}:replacement:{index}"
            if not isinstance(replacement, dict):
                errors.append({"code": "atom-role-replacement-invalid", "context": context})
                continue
            forbidden = sorted(FORBIDDEN_DECISION_FIELDS.intersection(replacement))
            if forbidden:
                errors.append({"code": "decision-rewrites-source", "context": context, "forbidden": forbidden})
            try:
                start, end = parse_range(replacement.get("source_range"), f"{context}.source_range", len(lines))
            except Exception as exc:
                errors.append({"code": "atom-role-range-invalid", "context": context, "detail": str(exc)})
                continue
            new_id = str(replacement.get("atom_id", ""))
            title = str(replacement.get("title", "")).strip()
            owner = str(replacement.get("owner_key", ""))
            category = replacement.get("category")
            item_confidence = replacement.get("confidence")
            if not new_id or new_id in seen_new_ids:
                errors.append({"code": "atom-role-id-invalid", "context": context})
            seen_new_ids.add(new_id)
            if owner not in set(map(str, original.get("allowed_owner_keys", []))):
                errors.append({"code": "atom-role-owner-invalid", "context": context, "owner_key": owner})
            if category not in ATOM_CATEGORY_NAMES:
                errors.append({"code": "atom-role-category-invalid", "context": context})
            if not title or "\n" in title or len("".join(title.split())) > 48:
                errors.append({"code": "atom-role-title-invalid", "context": context})
            if isinstance(item_confidence, bool) or not isinstance(item_confidence, (int, float)) or float(item_confidence) < threshold or float(item_confidence) > 1:
                review.append({"code": "atom-role-replacement-confidence-low", "context": context, "confidence": item_confidence, "required": threshold})
            copied = {key: value for key, value in replacement.items() if key not in FORBIDDEN_DECISION_FIELDS}
            copied["source_range"] = [start, end]
            copied["source_text_sha256"] = canonical_digest(source_slice(lines, [start, end]))
            for field in ("boundary_reason", "cohesion_reason"):
                if not isinstance(copied.get(field), str) or len(str(copied[field]).strip()) < 12:
                    errors.append({"code": "atom-role-replacement-reason-invalid", "context": context, "field": field})
            role_config = {**DEFAULT_ATOMIZATION, **dict(jobs.get("atomization", {}))}
            review.extend(quality_issues(copied, lines, role_config, context, final=True))
            parsed.append((start, end, copied))
        parsed.sort(key=lambda item: (item[0], item[1]))
        cursor = int(original["source_range"][0])
        for start, end, _ in parsed:
            if start != cursor:
                errors.append({"code": "atom-role-partition-gap-or-overlap", "atom_id": atom_id, "expected": cursor, "actual": start})
            cursor = end + 1
        if cursor != int(original["source_range"][1]) + 1:
            errors.append({"code": "atom-role-partition-incomplete", "atom_id": atom_id})
        normalized[atom_id] = [item[2] for item in parsed]
    return {
        "schema_version": 1,
        "status": "failed" if errors else ("review_required" if review else "passed"),
        "errors": errors, "review_items": review,
        "required_decisions": len(required), "normalized_replacements": normalized,
    }


def finalize_role_review(final: dict[str, Any], jobs: dict[str, Any], decisions: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    verify_artifact(final, "atomization-final")
    report = validate_role_review(jobs, decisions)
    if jobs.get("atomization_final_sha256") != final.get("artifact_sha256"):
        report["errors"].append({"code": "atom-role-final-binding-invalid"})
        report["status"] = "failed"
    if report["status"] != "passed":
        raise AtomizationError(f"Atom role review is unresolved: {report['errors'] + report['review_items']}")
    required = report["normalized_replacements"]
    atoms: list[dict[str, Any]] = []
    changed = 0
    for atom in final.get("atoms", []):
        atom_id = str(atom.get("atom_id"))
        if atom_id not in required or required[atom_id] == []:
            atoms.append(dict(atom))
            continue
        atoms.extend(required[atom_id])
        changed += 1
    atoms.sort(key=lambda item: (int(item["source_range"][0]), int(item["source_range"][1]), str(item["atom_id"])))
    bindings = dict(final.get("bindings", {}))
    bindings["atom_role_jobs"] = {"path": jobs.get("_path"), "sha256": jobs["artifact_sha256"]}
    bindings["atom_role_decisions"] = {"path": decisions.get("_path"), "sha256": decisions["artifact_sha256"]}
    reviewer = dict(final.get("reviewer", {}))
    reviewer["role_review"] = decisions.get("reviewer", {})
    atomization = dict(final.get("atomization", {}))
    atomization["teaching_role_audit"] = "required-before-materialization"
    atomization["role_correction_confidence_threshold"] = float(jobs.get("confidence_threshold", 0.95))
    result = seal_artifact({
        **{key: value for key, value in final.items() if key not in {"artifact_sha256", "atoms", "bindings", "reviewer", "atomization"}},
        "atoms": atoms, "bindings": bindings, "reviewer": reviewer,
        "atomization": atomization,
        "role_review": {
            "status": "passed", "reviewed_flagged_atoms": report["required_decisions"],
            "replaced_atoms": changed, "result_atoms": len(atoms), "unresolved_count": 0,
        },
    })
    queue = seal_artifact({
        "schema_version": 1, "kind": "atom-role-review-queue", "status": "passed",
        "atomization_final_sha256": result["artifact_sha256"], "unresolved_count": 0, "items": [],
    })
    return result, queue


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
    feedback_prepare = sub.add_parser("prepare-feedback")
    feedback_prepare.add_argument("atomization_final", type=Path)
    feedback_prepare.add_argument("relation_final", type=Path)
    feedback_prepare.add_argument("--output-dir", type=Path, required=True)
    feedback_prepare.add_argument("--overwrite", action="store_true")
    feedback_finish = sub.add_parser("finalize-feedback")
    feedback_finish.add_argument("atomization_final", type=Path)
    feedback_finish.add_argument("feedback_jobs", type=Path)
    feedback_finish.add_argument("feedback_decisions", type=Path)
    feedback_finish.add_argument("--output-dir", type=Path, required=True)
    feedback_finish.add_argument("--overwrite", action="store_true")
    role_prepare = sub.add_parser("prepare-role-review")
    role_prepare.add_argument("atomization_final", type=Path)
    role_prepare.add_argument("--output-dir", type=Path, required=True)
    role_prepare.add_argument("--overwrite", action="store_true")
    role_validate = sub.add_parser("validate-role-review")
    role_validate.add_argument("jobs", type=Path)
    role_validate.add_argument("decisions", type=Path)
    role_validate.add_argument("--output", type=Path)
    role_validate.add_argument("--overwrite", action="store_true")
    role_finish = sub.add_parser("finalize-role-review")
    role_finish.add_argument("atomization_final", type=Path)
    role_finish.add_argument("jobs", type=Path)
    role_finish.add_argument("decisions", type=Path)
    role_finish.add_argument("--output-dir", type=Path, required=True)
    role_finish.add_argument("--overwrite", action="store_true")
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
        elif args.command == "finalize":
            final, queue = finalize_payload(load_tagged(args.jobs, "atomization-jobs"), load_tagged(args.round1, "round-1-decisions"), load_tagged(args.round2_jobs, "round-2-jobs"), load_tagged(args.round2, "round-2-decisions"))
            output_dir = args.output_dir.expanduser().resolve()
            final_path, queue_path = output_dir / "atomization-final.json", output_dir / "atomization-review-queue.json"
            atomic_json(final_path, final, args.overwrite)
            atomic_json(queue_path, queue, args.overwrite)
            report = {"status": final["status"], "atomization_final": str(final_path), "review_queue": str(queue_path), "atoms": len(final["atoms"]), "unresolved_count": final["unresolved_count"]}
            code = 0 if final["status"] == "passed" else 2
        elif args.command == "prepare-feedback":
            payload = prepare_feedback_jobs(args.atomization_final, args.relation_final)
            output = args.output_dir.expanduser().resolve() / "atomization-feedback-jobs.json"
            atomic_json(output, payload, args.overwrite)
            report, code = {"status": "created", "path": str(output), "jobs": len(payload["jobs"]), "cycle": payload["feedback_cycle"]}, 0
        elif args.command == "finalize-feedback":
            original = load_tagged(args.atomization_final, "atomization-final")
            jobs = load_tagged(args.feedback_jobs, "atomization-feedback-jobs")
            decisions = load_tagged(args.feedback_decisions, "atomization-feedback-decisions")
            final, queue = finalize_feedback(original, jobs, decisions)
            output_dir = args.output_dir.expanduser().resolve()
            final_path, queue_path = output_dir / "atomization-final.json", output_dir / "atomization-review-queue.json"
            atomic_json(final_path, final, args.overwrite)
            atomic_json(queue_path, queue, args.overwrite)
            report, code = {"status": final["status"], "atomization_final": str(final_path), "review_queue": str(queue_path), "feedback_cycle": final["feedback_cycle"]["cycle"], "unresolved_count": final["unresolved_count"]}, (0 if final["status"] == "passed" else 2)
        elif args.command == "prepare-role-review":
            payload = prepare_role_review(args.atomization_final)
            output = args.output_dir.expanduser().resolve() / "atom-role-jobs.json"
            atomic_json(output, payload, args.overwrite)
            report = {"status": "created", "path": str(output), "atoms": len(payload["atoms"]), "flagged_atoms": sum(item["requires_decision"] for item in payload["atoms"])}
            code = 0
        elif args.command == "validate-role-review":
            report = validate_role_review(load_tagged(args.jobs, "atom-role-jobs"), load_tagged(args.decisions, "atom-role-decisions"))
            if args.output:
                atomic_json(args.output, report, args.overwrite)
            code = 0 if report["status"] == "passed" else 2
        else:
            original = load_tagged(args.atomization_final, "atomization-final")
            jobs = load_tagged(args.jobs, "atom-role-jobs")
            decisions = load_tagged(args.decisions, "atom-role-decisions")
            final, queue = finalize_role_review(original, jobs, decisions)
            output_dir = args.output_dir.expanduser().resolve()
            final_path = output_dir / "atomization-final.role-reviewed.json"
            queue_path = output_dir / "atom-role-review-queue.json"
            atomic_json(final_path, final, args.overwrite)
            atomic_json(queue_path, queue, args.overwrite)
            report = {"status": "passed", "atomization_final": str(final_path), "review_queue": str(queue_path), "atoms": len(final["atoms"]), "reviewed_flagged_atoms": final["role_review"]["reviewed_flagged_atoms"], "replaced_atoms": final["role_review"]["replaced_atoms"]}
            code = 0
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

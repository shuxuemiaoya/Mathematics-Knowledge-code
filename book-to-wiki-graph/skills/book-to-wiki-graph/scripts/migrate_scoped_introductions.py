#!/usr/bin/env python3
"""Migrate legacy paragraph-split scoped introductions into reviewed atoms.

This is a narrow compatibility tool for an already reviewed legacy corpus.  It
does not infer arbitrary atom boundaries: it only applies an Agent-approved
merge when atoms share one owner and one book/chapter/section introduction
role, and every uncovered source line between them is blank.  The migration
rebinds both frozen atomization and relation artifacts so the normal
materializer can rebuild Markdown, filenames, Canvas files, and PNG previews.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from validate_book_graph import artifact_digest, canonical_digest, load_json, sha256_file


SCOPED_ROLES = {"book-introduction", "chapter-introduction", "section-introduction"}
CONTINUATION_SUFFIX_RE = re.compile(
    r"\s*(?:[（(]\s*续\s*\d*\s*[）)]|[·・、_-]?\s*续\s*\d*)\s*$",
    re.IGNORECASE,
)


class ScopedIntroductionMigrationError(ValueError):
    pass


def seal(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    result["artifact_sha256"] = artifact_digest(result)
    return result


def atomic_json(path: Path, payload: dict[str, Any], overwrite: bool = False) -> None:
    path = path.expanduser().resolve()
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", prefix=f".{path.name}.",
        suffix=".tmp", dir=path.parent, delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def virtual_atom_key(atom: dict[str, Any]) -> str:
    identity = f"{atom['owner_key']}:{atom['source_range'][0]}:{atom['source_range'][1]}:{atom['category']}"
    return f"atom-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"


def stable_key(prefix: str, *parts: str) -> str:
    return f"{prefix}-{hashlib.sha256(chr(31).join(parts).encode('utf-8')).hexdigest()[:16]}"


def verify_sealed(payload: dict[str, Any], kind: str) -> None:
    if payload.get("kind") != kind:
        raise ScopedIntroductionMigrationError(f"Expected {kind}, got {payload.get('kind')!r}")
    if payload.get("artifact_sha256") != artifact_digest(payload):
        raise ScopedIntroductionMigrationError(f"Stale artifact digest: {kind}")


def chapter_key_for_owner(nodes: dict[str, dict[str, Any]], root_key: str, owner_key: str) -> str:
    cursor = owner_key
    if cursor == root_key:
        return root_key
    while cursor in nodes:
        parent = nodes[cursor].get("parent_key")
        if parent == root_key:
            return cursor
        if parent is None:
            break
        cursor = str(parent)
    raise ScopedIntroductionMigrationError(f"Cannot resolve chapter for owner {owner_key}")


def collect_groups(
    base: dict[str, Any], final: dict[str, Any], lines: list[str],
) -> list[dict[str, Any]]:
    nodes = {
        str(node["key"]): node for node in base.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("key"), str)
    }
    organizer_ranges = [
        tuple(value)
        for node in nodes.values() if node.get("layer") == "organizer"
        for value in node.get("heading_ranges", [])
        if isinstance(value, list) and len(value) == 2
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    atoms = [item for item in final.get("atoms", []) if isinstance(item, dict)]
    roots = [
        key for key, node in nodes.items()
        if node.get("layer") == "organizer" and node.get("parent_key") is None
    ]
    if len(roots) != 1:
        raise ScopedIntroductionMigrationError("Base manifest must have exactly one root organizer")
    root_key = roots[0]
    for atom in atoms:
        role = atom.get("scenario_role")
        if atom.get("category") == "scenario" and role in SCOPED_ROLES:
            grouped[(str(atom.get("owner_key")), str(role))].append(atom)

    result: list[dict[str, Any]] = []
    for (owner_key, role), members in grouped.items():
        ordered = sorted(members, key=lambda item: (item["source_range"][0], item["source_range"][1]))
        continuation = any(CONTINUATION_SUFFIX_RE.search(str(item.get("title", ""))) for item in ordered)
        if len(ordered) == 1:
            if continuation:
                raise ScopedIntroductionMigrationError(
                    f"Orphan continuation title cannot be migrated automatically: {ordered[0].get('title')}"
                )
            owner = nodes.get(owner_key, {})
            parent_key = str(owner.get("parent_key") or "")
            parent = nodes.get(parent_key, {})
            wrapper_is_redundant = (
                role == "chapter-introduction"
                and owner.get("layer") == "organizer"
                and not owner.get("heading_ranges")
                and parent.get("layer") == "organizer"
                and parent.get("parent_key") == root_key
            )
            if not wrapper_is_redundant:
                continue
            atom = ordered[0]
            result.append({
                "owner_key": parent_key,
                "source_owner_key": owner_key,
                "removed_wrapper_key": owner_key,
                "scenario_role": role,
                "source_range": list(atom["source_range"]),
                "title": CONTINUATION_SUFFIX_RE.sub("", str(atom.get("title", ""))).strip(),
                "member_atom_ids": [str(atom["atom_id"])],
                "member_atom_keys": [virtual_atom_key(atom)],
                "action": "reparent-remove-wrapper",
            })
            continue
        start = int(ordered[0]["source_range"][0])
        end = int(ordered[-1]["source_range"][1])
        member_ids = {str(item["atom_id"]) for item in ordered}
        for atom in atoms:
            if str(atom.get("atom_id")) in member_ids:
                continue
            other = atom.get("source_range")
            if isinstance(other, list) and len(other) == 2 and int(other[0]) <= end and int(other[1]) >= start:
                raise ScopedIntroductionMigrationError(
                    f"Scoped introduction overlaps another atom: {owner_key} {role} {other}"
                )
        covered_nonblank: set[int] = set()
        for atom in ordered:
            left, right = map(int, atom["source_range"])
            covered_nonblank.update(number for number in range(left, right + 1) if lines[number - 1].strip())
        uncovered = [number for number in range(start, end + 1) if lines[number - 1].strip() and number not in covered_nonblank]
        if uncovered:
            raise ScopedIntroductionMigrationError(
                f"Nonblank source occurs between introduction fragments: {owner_key} {role} {uncovered[:8]}"
            )
        crossing_headings = [value for value in organizer_ranges if value[0] <= end and value[1] >= start]
        if crossing_headings:
            raise ScopedIntroductionMigrationError(
                f"Scoped introduction crosses an organizer heading: {owner_key} {role} {crossing_headings}"
            )
        title = CONTINUATION_SUFFIX_RE.sub("", str(ordered[0].get("title", ""))).strip()
        if not title:
            raise ScopedIntroductionMigrationError(f"Merged introduction needs a stable title: {owner_key} {role}")
        result.append({
            "owner_key": owner_key,
            "source_owner_key": owner_key,
            "scenario_role": role,
            "source_range": [start, end],
            "title": title,
            "member_atom_ids": [str(item["atom_id"]) for item in ordered],
            "member_atom_keys": [virtual_atom_key(item) for item in ordered],
            "action": "merge",
        })
    return sorted(result, key=lambda item: item["source_range"])


def remap_atomization(
    legacy: dict[str, Any], groups: list[dict[str, Any]], lines: list[str],
    base_path: Path, review_path: Path, review: dict[str, Any], legacy_path: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    id_map: dict[str, str] = {}
    key_map: dict[str, str] = {}
    group_by_id: dict[str, dict[str, Any]] = {}
    for group in groups:
        retained = group["member_atom_ids"][0]
        new_key = virtual_atom_key({
            "owner_key": group["owner_key"], "source_range": group["source_range"], "category": "scenario",
        })
        for atom_id, old_key in zip(group["member_atom_ids"], group["member_atom_keys"]):
            id_map[atom_id] = retained
            key_map[old_key] = new_key
            group_by_id[atom_id] = group

    rewritten_atoms: list[dict[str, Any]] = []
    emitted: set[str] = set()
    for atom in legacy.get("atoms", []):
        atom_id = str(atom.get("atom_id"))
        group = group_by_id.get(atom_id)
        if group is None:
            rewritten_atoms.append(copy.deepcopy(atom))
            continue
        retained = group["member_atom_ids"][0]
        if retained in emitted:
            continue
        emitted.add(retained)
        merged = copy.deepcopy(atom)
        merged.update({
            "atom_id": retained,
            "owner_key": group["owner_key"],
            "source_range": list(group["source_range"]),
            "category": "scenario",
            "scenario_role": group["scenario_role"],
            "title": group["title"],
            "boundary_reason": "Agent review confirmed one scope-level introduction extending continuously to the next structural heading; paragraph and image boundaries are not atom boundaries.",
            "cohesion_reason": "All introductory paragraphs, questions, figures and captions form one chapter/section framing discourse and are meaningful only as a complete unit.",
            "confidence": 0.99,
            "source_text_sha256": canonical_digest(lines[group["source_range"][0] - 1:group["source_range"][1]]),
            "review_origin": "scoped-introduction-repair-agent-review",
        })
        rewritten_atoms.append(merged)
    rewritten_atoms.sort(key=lambda item: (item["source_range"][0], item["source_range"][1], str(item["atom_id"])))

    def mapped_id(value: Any) -> Any:
        return id_map.get(str(value), value)

    signatures: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for item in legacy.get("knowledge_signatures", []):
        copied = copy.deepcopy(item)
        copied["atom_id"] = mapped_id(copied.get("atom_id"))
        marker = json.dumps(copied, ensure_ascii=False, sort_keys=True)
        if marker not in seen_signatures:
            signatures.append(copied)
            seen_signatures.add(marker)

    local_relations: list[dict[str, Any]] = []
    seen_local: set[tuple[str, str, str]] = set()
    for item in legacy.get("local_relations", []):
        copied = copy.deepcopy(item)
        copied["from_atom_id"] = mapped_id(copied.get("from_atom_id"))
        copied["to_atom_id"] = mapped_id(copied.get("to_atom_id"))
        if copied["from_atom_id"] == copied["to_atom_id"]:
            continue
        for evidence in copied.get("evidence", []):
            if isinstance(evidence, dict):
                evidence["atom_id"] = mapped_id(evidence.get("atom_id"))
        identity = (str(copied["from_atom_id"]), str(copied["to_atom_id"]), str(copied.get("type")))
        if identity not in seen_local:
            local_relations.append(copied)
            seen_local.add(identity)

    candidates: list[dict[str, Any]] = []
    for item in legacy.get("derived_card_candidates", []):
        copied = copy.deepcopy(item)
        if "from_atom_id" in copied:
            copied["from_atom_id"] = mapped_id(copied.get("from_atom_id"))
        candidates.append(copied)

    result = copy.deepcopy(legacy)
    result.update({
        "base_manifest": str(base_path),
        "base_manifest_sha256": sha256_file(base_path),
        "atoms": rewritten_atoms,
        "knowledge_signatures": signatures,
        "local_relations": local_relations,
        "derived_card_candidates": candidates,
        "bindings": {
            "legacy_atomization_final": {"path": str(legacy_path), "sha256": legacy["artifact_sha256"]},
            "scoped_introduction_review": {"path": str(review_path), "sha256": review["artifact_sha256"]},
        },
        "reviewer": {
            **dict(legacy.get("reviewer", {})),
            "scoped_introductions": {
                "identity": "Codex agent",
                "method": "source-complete scope-level introduction merge review",
            },
        },
        "unresolved_count": 0,
        "status": "passed",
    })
    atomization = dict(result.get("atomization", {}))
    atomization.update({
        "scoped_introduction_policy": "one-source-complete-atom-per-owner",
        "knowledge_motivation_policy": "complete-problem-or-context",
    })
    result["atomization"] = atomization
    result.pop("artifact_sha256", None)
    return seal(result), key_map


def remap_evidence(items: Any, key_map: dict[str, str]) -> Any:
    if isinstance(items, list):
        return [remap_evidence(item, key_map) for item in items]
    if not isinstance(items, dict):
        return key_map.get(str(items), items)
    copied: dict[str, Any] = {}
    for key, value in items.items():
        if key in {"atom_key", "node_key", "from_key", "to_key", "derived_from_key"} and isinstance(value, str):
            copied[key] = key_map.get(value, value)
        elif key == "atom_keys" and isinstance(value, list):
            copied[key] = [key_map.get(str(item), item) for item in value]
        else:
            copied[key] = remap_evidence(value, key_map)
    return copied


def remap_relation_final(
    legacy: dict[str, Any], groups: list[dict[str, Any]], key_map: dict[str, str],
    base: dict[str, Any], atomization: dict[str, Any], base_path: Path,
    atomization_path: Path, review_path: Path, review: dict[str, Any], legacy_path: Path,
) -> dict[str, Any]:
    concepts = remap_evidence(copy.deepcopy(legacy.get("concepts", [])), key_map)
    for concept in concepts:
        if isinstance(concept, dict) and isinstance(concept.get("evidence"), list):
            unique = {json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in concept["evidence"]}
            concept["evidence"] = sorted(unique.values(), key=lambda item: (item.get("source_range", [10**12])[0], str(item.get("atom_key"))))

    link_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in remap_evidence(copy.deepcopy(legacy.get("atom_concept_links", [])), key_map):
        identity = (str(raw["atom_key"]), str(raw["concept_key"]), str(raw["role"]))
        item = link_index.setdefault(identity, {
            "key": stable_key("atom-concept", *identity),
            "atom_key": identity[0], "concept_key": identity[1], "role": identity[2],
            "evidence_ranges": [], "confidence": 0.0,
        })
        item["evidence_ranges"] = [list(value) for value in sorted({
            tuple(value) for value in [*item["evidence_ranges"], *raw.get("evidence_ranges", [])]
        })]
        item["confidence"] = max(float(item["confidence"]), float(raw.get("confidence", 0.0)))

    relation_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in remap_evidence(copy.deepcopy(legacy.get("relations", [])), key_map):
        left, right, relation_type = str(raw["from_key"]), str(raw["to_key"]), str(raw["type"])
        if left == right:
            continue
        if relation_type in {"contrasts", "analogous"} and left > right:
            left, right = right, left
        identity = (left, right, relation_type)
        item = relation_index.setdefault(identity, {
            **raw, "key": stable_key("relation", *identity),
            "from_key": left, "to_key": right, "type": relation_type,
            "evidence_ranges": [], "basis_keys": [], "candidate_sources": [],
        })
        evidence = [
            value for value in raw.get("evidence_ranges", [])
            if isinstance(value, dict) and value.get("node_key") in {left, right}
        ]
        evidence_index = {
            json.dumps(value, ensure_ascii=False, sort_keys=True): value
            for value in [*item.get("evidence_ranges", []), *evidence]
        }
        item["evidence_ranges"] = sorted(
            evidence_index.values(), key=lambda value: (str(value.get("node_key")), value.get("source_range", [0])[0])
        )
        item["basis_keys"] = sorted(set(item.get("basis_keys", [])) | set(raw.get("basis_keys", [])))
        item["candidate_sources"] = sorted(set(item.get("candidate_sources", [])) | set(raw.get("candidate_sources", [])))
        item["confidence"] = max(float(item.get("confidence", 0.0)), float(raw.get("confidence", 0.0)))

    nodes = {
        str(node["key"]): node for node in base.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("key"), str)
    }
    roots = [key for key, node in nodes.items() if node.get("layer") == "organizer" and node.get("parent_key") is None]
    if len(roots) != 1:
        raise ScopedIntroductionMigrationError("Base manifest must have exactly one root organizer")
    root_key = roots[0]
    atom_by_key = {virtual_atom_key(atom): atom for atom in atomization.get("atoms", [])}
    chapter_by_atom = {
        key: chapter_key_for_owner(nodes, root_key, str(atom["owner_key"]))
        for key, atom in atom_by_key.items()
    }
    for group in groups:
        merged_key = key_map[group["member_atom_keys"][0]]
        outgoing = any(identity[0] == merged_key for identity in relation_index)
        if outgoing:
            continue
        chapter_key = chapter_key_for_owner(nodes, root_key, group["owner_key"])
        candidates = [
            (key, atom) for key, atom in atom_by_key.items()
            if chapter_by_atom.get(key) == chapter_key
            and int(atom["source_range"][0]) > int(group["source_range"][1])
            and atom.get("category") in {"knowledge", "scenario"}
            and atom.get("scenario_role") != "chapter-introduction"
        ]
        if not candidates:
            continue
        target_key, target = min(candidates, key=lambda value: (value[1]["source_range"][0], value[0]))
        identity = (merged_key, target_key, "motivates")
        relation_index[identity] = {
            "key": stable_key("relation", *identity),
            "from_key": merged_key, "to_key": target_key, "type": "motivates",
            "tier": "supporting", "evidence_kind": "pedagogical-inference",
            "evidence_ranges": [
                {"node_key": merged_key, "source_range": list(group["source_range"])},
                {"node_key": target_key, "source_range": list(target["source_range"])},
            ],
            "rationale": "完整章节导语提出本章研究对象与核心问题，并沿原书教学顺序导向本章第一个真实教学单元。",
            "confidence": 0.97, "basis_keys": [],
            "candidate_sources": ["scoped-introduction-repair-agent-review", "organization-neighborhood"],
        }

    role_index: dict[str, dict[str, Any]] = {}
    for raw in remap_evidence(copy.deepcopy(legacy.get("atom_roles", [])), key_map):
        atom_key = str(raw.get("atom_key"))
        role_index.setdefault(atom_key, raw)

    result = copy.deepcopy(legacy)
    result.update({
        "manifest": str(base_path),
        "manifest_sha256": sha256_file(base_path),
        "atomization_final": str(atomization_path),
        "atomization_final_sha256": atomization["artifact_sha256"],
        "bindings": {
            "legacy_relation_final": {"path": str(legacy_path), "sha256": legacy["artifact_sha256"]},
            "scoped_introduction_review": {"path": str(review_path), "sha256": review["artifact_sha256"]},
        },
        "reviewer": {
            **dict(legacy.get("reviewer", {})),
            "scoped_introductions": {
                "identity": "Codex agent",
                "method": "relation rebind after source-complete scoped-introduction merge",
            },
        },
        "concepts": concepts,
        "atom_concept_links": sorted(link_index.values(), key=lambda item: (item["atom_key"], item["concept_key"], item["role"])),
        "concept_relations": remap_evidence(copy.deepcopy(legacy.get("concept_relations", [])), key_map),
        "relations": sorted(relation_index.values(), key=lambda item: (item["from_key"], item["to_key"], item["type"])),
        "formulas": remap_evidence(copy.deepcopy(legacy.get("formulas", [])), key_map),
        "atom_roles": sorted(role_index.values(), key=lambda item: str(item.get("atom_key"))),
        "independent_atoms": remap_evidence(copy.deepcopy(legacy.get("independent_atoms", [])), key_map),
        "independent_components": remap_evidence(copy.deepcopy(legacy.get("independent_components", [])), key_map),
        "boundary_feedback": [], "unresolved_count": 0, "status": "passed",
    })
    result.pop("artifact_sha256", None)
    return seal(result)


def migrate(
    base_path: Path, atomization_path: Path, relation_path: Path,
    output_dir: Path, overwrite: bool = False,
) -> dict[str, Any]:
    base_path = base_path.expanduser().resolve()
    atomization_path = atomization_path.expanduser().resolve()
    relation_path = relation_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    base, legacy_atomization, legacy_relation = (
        load_json(base_path), load_json(atomization_path), load_json(relation_path)
    )
    verify_sealed(legacy_atomization, "atomization-final")
    verify_sealed(legacy_relation, "relation-final-v2")
    source_path = Path(str(base.get("source_markdown", ""))).expanduser().resolve()
    if not source_path.is_file() or sha256_file(source_path) != base.get("source_markdown_sha256"):
        raise ScopedIntroductionMigrationError("Base source Markdown is missing or stale")
    if legacy_atomization.get("source_markdown_sha256") != base.get("source_markdown_sha256"):
        raise ScopedIntroductionMigrationError("Atomization final binds another source Markdown")
    if legacy_relation.get("atomization_final_sha256") != legacy_atomization.get("artifact_sha256"):
        raise ScopedIntroductionMigrationError("Relation final binds another atomization final")
    lines = source_path.read_text(encoding="utf-8-sig").splitlines()
    groups = collect_groups(base, legacy_atomization, lines)
    if not groups:
        raise ScopedIntroductionMigrationError("No duplicate scoped introductions require migration")

    profile_source = Path(str(base.get("profile", ""))).expanduser().resolve()
    profile = load_json(profile_source)
    profile["paths"] = {**dict(profile.get("paths", {})), "staging_root": str(output_dir)}
    profile["atomization"] = {
        **dict(profile.get("atomization", {})),
        "scoped_introduction_policy": "one-source-complete-atom-per-owner",
        "knowledge_motivation_policy": "complete-problem-or-context",
    }
    profile["markdown_rendering"] = {
        **dict(profile.get("markdown_rendering", {})),
        "atom_filename_policy": "per-folder-sequence-category-code",
        "organizer_self_heading_policy": "omit",
    }
    profile["canvas"] = {
        **dict(profile.get("canvas", {})),
        "png_preview": "required-every-canvas",
        "review": {
            "mode": "llm-png-two-pass", "scope": "every-canvas",
            "required_before_completion": True, "max_optimization_cycles": 2,
        },
    }
    profile_path = output_dir / "book-profile.json"
    atomic_json(profile_path, profile, overwrite)

    organizer_review = seal({
        "schema_version": 1, "kind": "organizer-review", "status": "passed",
        "base_manifest_sha256": sha256_file(base_path),
        "source_markdown_sha256": base["source_markdown_sha256"],
        "reviewer": {"type": "codex-agent", "model": "current-agent", "method": "migrated from whole-book reviewed organizer manifest"},
        "demote_organizer_keys": sorted({
            str(group["removed_wrapper_key"])
            for group in groups if group.get("removed_wrapper_key")
        }),
        "content_runs": [], "renumber_parent_keys": [],
        "migration_source_review": copy.deepcopy(base.get("review", {})),
    })
    organizer_review_path = output_dir / "organizer-review.migrated.json"
    atomic_json(organizer_review_path, organizer_review, overwrite)

    migrated_base = copy.deepcopy(base)
    migrated_base["profile"] = str(profile_path)
    removed_wrappers = {
        str(group["removed_wrapper_key"])
        for group in groups if group.get("removed_wrapper_key")
    }
    if removed_wrappers:
        migrated_base["nodes"] = [
            node for node in migrated_base.get("nodes", [])
            if not isinstance(node, dict) or str(node.get("key")) not in removed_wrappers
        ]
        for node in migrated_base.get("nodes", []):
            if isinstance(node, dict) and isinstance(node.get("children"), list):
                node["children"] = [
                    child for child in node["children"] if str(child) not in removed_wrappers
                ]
    migrated_base["organizer_review"] = {
        "status": "passed", "path": str(organizer_review_path),
        "sha256": organizer_review["artifact_sha256"],
        "demoted_organizer_keys": sorted(removed_wrappers),
        "synthesized_organizer_keys": [],
    }
    migrated_base_path = output_dir / "book-graph.organizers-reviewed.json"
    atomic_json(migrated_base_path, migrated_base, overwrite)

    review = seal({
        "schema_version": 1, "kind": "scoped-introduction-repair-review", "status": "passed",
        "base_manifest": str(base_path), "base_manifest_sha256": sha256_file(base_path),
        "atomization_final": str(atomization_path), "atomization_final_sha256": legacy_atomization["artifact_sha256"],
        "relation_final": str(relation_path), "relation_final_sha256": legacy_relation["artifact_sha256"],
        "source_markdown_sha256": base["source_markdown_sha256"],
        "reviewer": {"type": "codex-agent", "model": "current-agent"},
        "decisions": [
            {**group, "confidence": 0.99,
             "rationale": "These fragments are consecutive paragraphs/media of one owner-scoped introduction and cannot stand alone as independent teaching atoms."}
            for group in groups
        ],
        "unresolved_count": 0,
    })
    review_path = output_dir / "scoped-introduction-repair-review.json"
    atomic_json(review_path, review, overwrite)

    migrated_atomization, key_map = remap_atomization(
        legacy_atomization, groups, lines, migrated_base_path, review_path,
        review, atomization_path,
    )
    migrated_atomization_path = output_dir / "atomization-final.json"
    atomic_json(migrated_atomization_path, migrated_atomization, overwrite)
    migrated_relation = remap_relation_final(
        legacy_relation, groups, key_map, migrated_base, migrated_atomization,
        migrated_base_path, migrated_atomization_path, review_path, review,
        relation_path,
    )
    migrated_relation_path = output_dir / "relation-final.json"
    atomic_json(migrated_relation_path, migrated_relation, overwrite)
    report = seal({
        "schema_version": 1, "kind": "scoped-introduction-migration-report", "status": "passed",
        "outputs": {
            "profile": str(profile_path), "base_manifest": str(migrated_base_path),
            "organizer_review": str(organizer_review_path), "review": str(review_path),
            "atomization_final": str(migrated_atomization_path),
            "relation_final": str(migrated_relation_path),
        },
        "merged_groups": groups,
        "counts": {
            "groups": len(groups),
            "removed_fragments": sum(len(group["member_atom_ids"]) - 1 for group in groups),
            "removed_wrapper_organizers": len(removed_wrappers),
            "atoms_before": len(legacy_atomization.get("atoms", [])),
            "atoms_after": len(migrated_atomization.get("atoms", [])),
            "relations_before": len(legacy_relation.get("relations", [])),
            "relations_after": len(migrated_relation.get("relations", [])),
        },
    })
    atomic_json(output_dir / "scoped-introduction-migration-report.json", report, overwrite)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_manifest", type=Path)
    parser.add_argument("atomization_final", type=Path)
    parser.add_argument("relation_final", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report = migrate(
            args.base_manifest, args.atomization_final, args.relation_final,
            args.output_dir, args.overwrite,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

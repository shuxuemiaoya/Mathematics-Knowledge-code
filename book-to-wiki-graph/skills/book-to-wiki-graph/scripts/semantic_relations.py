#!/usr/bin/env python3
"""Prepare, audit, finalize, and apply evidence-bound teaching relations."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from semantic_atomization import atomic_json, seal_artifact, verify_artifact
from validate_book_graph import artifact_digest, canonical_digest, load_json, sha256_file


RELATION_TYPES = {
    "prerequisite",
    "develops",
    "derives",
    "motivates",
    "illustrates",
    "applies",
    "practices",
    "contrasts",
    "analogous",
}
SYMMETRIC_RELATION_TYPES = {"contrasts", "analogous"}
BACKBONE_RELATION_TYPES = {"prerequisite", "develops", "derives", "motivates"}
SEMANTIC_ROLES = {"core", "bridge", "satellite"}
DEFAULT_RELATION_ANALYSIS = {
    "mode": "llm-two-pass",
    "explicit_confidence_threshold": 0.90,
    "inferred_confidence_threshold": 0.95,
    "mainline": "directed-acyclic-backbone",
    "cross_chapter": True,
}
DEFAULT_CANVAS = {
    "enabled": True,
    "mode": "two-level-constellation",
    "theme": "adaptive",
    "overview_granularity": "chapter",
    "chapter_granularity": "atom",
}


class RelationError(ValueError):
    pass


def relation_key(relation: dict[str, Any]) -> str:
    identity = ":".join(
        (
            str(relation.get("from_key", "")),
            str(relation.get("to_key", "")),
            str(relation.get("type", "")),
        )
    )
    return f"relation-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]}"


def packet_digest(payload: dict[str, Any]) -> str:
    return canonical_digest({key: value for key, value in payload.items() if key != "packet_sha256"})


def descendants(nodes: dict[str, dict[str, Any]], root_key: str) -> list[str]:
    ordered: list[str] = []

    def visit(key: str) -> None:
        ordered.append(key)
        node = nodes[key]
        if node.get("layer") == "organizer":
            for child in node.get("children", []):
                visit(str(child))

    visit(root_key)
    return ordered


def organizer_path(nodes: dict[str, dict[str, Any]], key: str) -> list[str]:
    result: list[str] = []
    cursor: str | None = key
    while cursor is not None:
        node = nodes[cursor]
        if node.get("layer") == "organizer":
            result.append(str(node.get("title", cursor)))
        parent = node.get("parent_key")
        cursor = str(parent) if parent is not None else None
    return list(reversed(result))


def chapter_for(nodes: dict[str, dict[str, Any]], root_key: str, key: str) -> str:
    cursor = key
    parent = nodes[cursor].get("parent_key")
    while parent is not None and str(parent) != root_key:
        cursor = str(parent)
        parent = nodes[cursor].get("parent_key")
    if parent is None:
        raise RelationError(f"Node is not below a chapter: {key}")
    return cursor


def source_atom(node: dict[str, Any], nodes: dict[str, dict[str, Any]], lines: list[str]) -> dict[str, Any]:
    start, end = [int(value) for value in node["source_range"]]
    text = "\n".join(lines[start - 1 : end])
    return {
        "atom_key": str(node["key"]),
        "title": str(node["title"]),
        "category": str(node["category"]),
        "owner_key": str(node["parent_key"]),
        "organizer_path": organizer_path(nodes, str(node["parent_key"])),
        "source_range": [start, end],
        "source_text": text,
        "source_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def load_relation_context(manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path, list[str]]:
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_json(manifest_path)
    profile_path = Path(str(manifest.get("profile", ""))).expanduser().resolve()
    if not profile_path.is_file():
        raise RelationError(f"Profile is missing: {profile_path}")
    profile = load_json(profile_path)
    source = Path(str(manifest.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != manifest.get("source_markdown_sha256"):
        raise RelationError("Source Markdown is missing or stale")
    return manifest, profile, source, source.read_text(encoding="utf-8-sig").splitlines()


def relation_config(profile: dict[str, Any]) -> dict[str, Any]:
    raw = profile.get("relation_analysis")
    if raw is None:
        return dict(DEFAULT_RELATION_ANALYSIS)
    if not isinstance(raw, dict):
        raise RelationError("relation_analysis must be an object")
    config = {**DEFAULT_RELATION_ANALYSIS, **raw}
    if config.get("mode") != "llm-two-pass":
        raise RelationError("relation_analysis.mode must be llm-two-pass")
    for field in ("explicit_confidence_threshold", "inferred_confidence_threshold"):
        value = config.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise RelationError(f"Invalid {field}")
    return config


def prepare_relation_jobs(manifest_path: Path, max_chars: int = 50000) -> dict[str, Any]:
    if max_chars < 1000:
        raise RelationError("max_chars must be at least 1000")
    manifest_path = manifest_path.expanduser().resolve()
    manifest, profile, source, lines = load_relation_context(manifest_path)
    nodes = {str(node["key"]): node for node in manifest.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("key"), str)}
    roots = [key for key, node in nodes.items() if node.get("layer") == "organizer" and node.get("parent_key") is None]
    if len(roots) != 1:
        raise RelationError("Manifest must have one root organizer")
    root_key = roots[0]
    chapter_order = [str(key) for key in nodes[root_key].get("children", []) if nodes.get(str(key), {}).get("layer") == "organizer"]
    if not chapter_order:
        raise RelationError("Manifest has no chapter organizers")
    atoms = {key: node for key, node in nodes.items() if node.get("layer") == "atom"}
    atom_to_chapter = {key: chapter_for(nodes, root_key, key) for key in atoms}
    jobs: list[dict[str, Any]] = []
    for chapter_key in chapter_order:
        chapter_atoms = sorted(
            (source_atom(atoms[key], nodes, lines) for key in atoms if atom_to_chapter[key] == chapter_key),
            key=lambda item: (int(item["source_range"][0]), int(item["source_range"][1]), str(item["atom_key"])),
        )
        packets: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_chars = 0
        for atom in chapter_atoms:
            size = len(str(atom["source_text"]))
            if current and current_chars + size > max_chars:
                packets.append(current)
                current, current_chars = [], 0
            current.append(atom)
            current_chars += size
        if current:
            packets.append(current)
        for index, packet_atoms in enumerate(packets, start=1):
            payload = {
                "job_id": f"relation-job-{chapter_order.index(chapter_key)+1:03d}-{index:03d}",
                "chapter_key": chapter_key,
                "chapter_title": str(nodes[chapter_key]["title"]),
                "packet_index": index,
                "packet_count": len(packets),
                "atoms": packet_atoms,
                "adjacent_pairs": [
                    [str(packet_atoms[p]["atom_key"]), str(packet_atoms[p + 1]["atom_key"])]
                    for p in range(len(packet_atoms) - 1)
                ],
            }
            payload["packet_sha256"] = packet_digest(payload)
            jobs.append(payload)
    return seal_artifact(
        {
            "schema_version": 1,
            "kind": "relation-jobs",
            "manifest": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "source_markdown": str(source),
            "source_markdown_sha256": sha256_file(source),
            "root_key": root_key,
            "chapter_order": chapter_order,
            "atom_to_chapter": atom_to_chapter,
            "relation_analysis": relation_config(profile),
            "jobs": jobs,
        }
    )


def decision_map(payload: dict[str, Any], id_field: str) -> dict[str, dict[str, Any]]:
    raw = payload.get("decisions")
    if not isinstance(raw, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get(id_field), str):
            key = str(item[id_field])
            if key not in result:
                result[key] = item
    return result


def validate_signature(raw: Any, atom_keys: set[str], context: str, errors: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        errors.append({"code": "relation-concept-signature-invalid", "context": context})
        return None
    atom_key = raw.get("atom_key")
    if atom_key not in atom_keys or raw.get("role") not in SEMANTIC_ROLES:
        errors.append({"code": "relation-concept-signature-invalid", "context": context, "atom": atom_key})
        return None
    for field in ("teaches", "assumes"):
        values = raw.get(field)
        if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
            errors.append({"code": "relation-concept-signature-invalid", "context": context, "atom": atom_key, "field": field})
            return None
    return {
        "atom_key": str(atom_key),
        "role": str(raw["role"]),
        "teaches": [str(value).strip() for value in raw["teaches"]],
        "assumes": [str(value).strip() for value in raw["assumes"]],
    }


def validate_relation(
    raw: Any,
    atoms: dict[str, dict[str, Any]],
    config: dict[str, Any],
    context: str,
    errors: list[dict[str, Any]],
    review: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        errors.append({"code": "relation-invalid", "context": context})
        return None
    from_key, to_key = raw.get("from_key"), raw.get("to_key")
    relation_type = raw.get("type")
    tier = raw.get("tier")
    evidence_kind = raw.get("evidence_kind")
    if from_key not in atoms or to_key not in atoms or from_key == to_key:
        errors.append({"code": "relation-endpoint-invalid", "context": context, "from": from_key, "to": to_key})
        return None
    if relation_type not in RELATION_TYPES or tier not in {"backbone", "supporting"} or evidence_kind not in {"explicit", "pedagogical-inference"}:
        errors.append({"code": "relation-classification-invalid", "context": context})
        return None
    if relation_type in SYMMETRIC_RELATION_TYPES and str(from_key) > str(to_key):
        errors.append({"code": "relation-symmetric-order-invalid", "context": context})
        return None
    if tier == "backbone":
        if relation_type not in BACKBONE_RELATION_TYPES:
            errors.append({"code": "relation-backbone-type-invalid", "context": context})
        if atoms[str(from_key)].get("category") not in {"knowledge", "scenario"} or atoms[str(to_key)].get("category") not in {"knowledge", "scenario"}:
            errors.append({"code": "relation-backbone-category-invalid", "context": context})
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or len(rationale.strip()) < 12:
        errors.append({"code": "relation-rationale-invalid", "context": context})
    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append({"code": "relation-confidence-invalid", "context": context})
        confidence_value = 0.0
    else:
        confidence_value = float(confidence)
        threshold = float(config["explicit_confidence_threshold"] if evidence_kind == "explicit" else config["inferred_confidence_threshold"])
        if confidence_value < threshold:
            review.append({"code": "relation-confidence-below-threshold", "context": context, "confidence": confidence_value, "threshold": threshold})
    evidence = raw.get("evidence_ranges")
    valid_evidence: list[dict[str, Any]] = []
    if not isinstance(evidence, list):
        errors.append({"code": "relation-evidence-invalid", "context": context})
        evidence = []
    covered: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict) or item.get("node_key") not in {from_key, to_key}:
            errors.append({"code": "relation-evidence-invalid", "context": context})
            continue
        source_range = item.get("source_range")
        node_range = atoms[str(item["node_key"])].get("source_range")
        if not isinstance(source_range, list) or len(source_range) != 2 or not all(isinstance(value, int) for value in source_range):
            errors.append({"code": "relation-evidence-invalid", "context": context})
            continue
        if not isinstance(node_range, list) or int(source_range[0]) < int(node_range[0]) or int(source_range[1]) > int(node_range[1]) or int(source_range[0]) > int(source_range[1]):
            errors.append({"code": "relation-evidence-outside-atom", "context": context, "node": item.get("node_key")})
            continue
        covered.add(str(item["node_key"]))
        valid_evidence.append({"node_key": str(item["node_key"]), "source_range": [int(source_range[0]), int(source_range[1])]})
    if evidence_kind == "pedagogical-inference" and covered != {str(from_key), str(to_key)}:
        errors.append({"code": "relation-inference-needs-both-endpoints", "context": context})
    if not valid_evidence:
        errors.append({"code": "relation-evidence-empty", "context": context})
    normalized = {
        "from_key": str(from_key),
        "to_key": str(to_key),
        "type": str(relation_type),
        "tier": str(tier),
        "evidence_kind": str(evidence_kind),
        "evidence_ranges": valid_evidence,
        "rationale": str(rationale).strip() if isinstance(rationale, str) else "",
        "confidence": confidence_value,
    }
    normalized["key"] = relation_key(normalized)
    return normalized


def validate_round1_payload(jobs: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    if decisions.get("kind") != "round-1-relations" or decisions.get("jobs_sha256") != jobs.get("artifact_sha256"):
        errors.append({"code": "round1-binding-invalid"})
    by_id = decision_map(decisions, "job_id")
    expected_ids = [str(job["job_id"]) for job in jobs.get("jobs", [])]
    if set(by_id) != set(expected_ids):
        errors.append({"code": "round1-job-coverage-invalid", "missing": sorted(set(expected_ids)-set(by_id)), "extra": sorted(set(by_id)-set(expected_ids))})
    all_signatures: dict[str, dict[str, Any]] = {}
    normalized_relations: list[dict[str, Any]] = []
    for job in jobs.get("jobs", []):
        job_id = str(job["job_id"])
        decision = by_id.get(job_id)
        if decision is None:
            continue
        if decision.get("packet_sha256") != job.get("packet_sha256"):
            errors.append({"code": "round1-packet-digest-mismatch", "job_id": job_id})
        atom_map = {str(atom["atom_key"]): atom for atom in job.get("atoms", [])}
        signatures: dict[str, dict[str, Any]] = {}
        for raw in decision.get("concept_signatures", []) if isinstance(decision.get("concept_signatures"), list) else []:
            signature = validate_signature(raw, set(atom_map), job_id, errors)
            if signature is not None and signature["atom_key"] not in signatures:
                category = atom_map[signature["atom_key"]].get("category")
                if signature["role"] == "bridge" and category != "worked-example":
                    errors.append({"code": "relation-bridge-role-category-invalid", "job_id": job_id, "atom": signature["atom_key"]})
                if signature["role"] == "core" and category not in {"knowledge", "scenario"}:
                    errors.append({"code": "relation-core-role-category-invalid", "job_id": job_id, "atom": signature["atom_key"]})
                signatures[signature["atom_key"]] = signature
        if set(signatures) != set(atom_map):
            errors.append({"code": "relation-concept-coverage-invalid", "job_id": job_id, "missing": sorted(set(atom_map)-set(signatures))})
        all_signatures.update(signatures)
        for index, raw in enumerate(decision.get("relations", []) if isinstance(decision.get("relations"), list) else []):
            relation = validate_relation(raw, atom_map, jobs["relation_analysis"], f"{job_id}:relation:{index}", errors, review)
            if relation is not None:
                normalized_relations.append(relation)
    return {
        "schema_version": 1,
        "status": "failed" if errors else ("review_required" if review else "passed"),
        "errors": errors,
        "review_items": review,
        "concept_signatures": list(all_signatures.values()),
        "relations": normalized_relations,
    }


def normalized_terms(values: Iterable[str]) -> set[str]:
    return {"".join(value.casefold().split()) for value in values if len("".join(value.split())) >= 2}


def candidate_id(from_key: str, to_key: str) -> str:
    return f"candidate-{hashlib.sha256(f'{from_key}:{to_key}'.encode()).hexdigest()[:16]}"


def prepare_audit_jobs(jobs: dict[str, Any], round1: dict[str, Any]) -> dict[str, Any]:
    report = validate_round1_payload(jobs, round1)
    if report["errors"]:
        raise RelationError(f"Round one is structurally invalid: {report['errors'][:5]}")
    atoms: dict[str, dict[str, Any]] = {}
    for job in jobs.get("jobs", []):
        for atom in job.get("atoms", []):
            atoms[str(atom["atom_key"])] = atom
    signatures = {str(item["atom_key"]): item for item in report["concept_signatures"]}
    relation_by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    for relation in report["relations"]:
        relation_by_pair[(str(relation["from_key"]), str(relation["to_key"]))].append(str(relation["key"]))
    atom_to_chapter = {str(key): str(value) for key, value in jobs["atom_to_chapter"].items()}
    chapter_atoms: dict[str, list[str]] = defaultdict(list)
    for key, chapter in atom_to_chapter.items():
        chapter_atoms[chapter].append(key)
    for keys in chapter_atoms.values():
        keys.sort(key=lambda key: (int(atoms[key]["source_range"][0]), key))

    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for chapter, keys in chapter_atoms.items():
        for left, right in zip(keys, keys[1:]):
            pairs[(left, right)].add("source-adjacent")
        knowledge = [key for key in keys if atoms[key]["category"] == "knowledge"]
        for key in keys:
            if atoms[key]["category"] not in {"worked-example", "exercise", "scenario"} or not knowledge:
                continue
            nearest = min(knowledge, key=lambda candidate: abs(int(atoms[candidate]["source_range"][0])-int(atoms[key]["source_range"][0])))
            pair = (nearest, key) if int(atoms[nearest]["source_range"][0]) <= int(atoms[key]["source_range"][0]) else (key, nearest)
            pairs[pair].add("nearest-knowledge")
        for target in keys:
            assumptions = normalized_terms(signatures.get(target, {}).get("assumes", []))
            if not assumptions:
                continue
            scored: list[tuple[int, int, str]] = []
            for source in keys:
                if source == target:
                    continue
                overlap = assumptions.intersection(normalized_terms(signatures.get(source, {}).get("teaches", [])))
                if overlap:
                    scored.append((-len(overlap), abs(int(atoms[source]["source_range"][0])-int(atoms[target]["source_range"][0])), source))
            for _, _, source in sorted(scored)[:3]:
                pairs[(source, target)].add("concept-dependency")
    for from_key, to_key in relation_by_pair:
        pairs[(from_key, to_key)].add("round-one-relation")

    if jobs["relation_analysis"].get("cross_chapter"):
        keys = sorted(atoms, key=lambda key: (int(atoms[key]["source_range"][0]), key))
        for target in keys:
            assumptions = normalized_terms(signatures.get(target, {}).get("assumes", []))
            if not assumptions:
                continue
            scored: list[tuple[int, int, str]] = []
            for source in keys:
                if atom_to_chapter[source] == atom_to_chapter[target]:
                    continue
                overlap = assumptions.intersection(normalized_terms(signatures.get(source, {}).get("teaches", [])))
                if overlap:
                    scored.append((-len(overlap), abs(int(atoms[source]["source_range"][0])-int(atoms[target]["source_range"][0])), source))
            for _, _, source in sorted(scored)[:3]:
                pairs[(source, target)].add("cross-chapter-concept-dependency")

    audits: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(jobs["chapter_order"], start=1):
        keys = chapter_atoms.get(str(chapter), [])
        candidates = []
        for (from_key, to_key), reasons in sorted(pairs.items(), key=lambda item: (int(atoms[item[0][0]]["source_range"][0]), int(atoms[item[0][1]]["source_range"][0]), item[0])):
            if atom_to_chapter[from_key] != chapter or atom_to_chapter[to_key] != chapter:
                continue
            candidates.append({"candidate_id": candidate_id(from_key, to_key), "from_key": from_key, "to_key": to_key, "reasons": sorted(reasons), "round_1_relation_keys": relation_by_pair.get((from_key, to_key), [])})
        payload = {
            "audit_id": f"relation-audit-chapter-{chapter_index:03d}",
            "scope": "chapter",
            "scope_key": chapter,
            "atoms": [atoms[atom_key] for atom_key in keys],
            "concept_signatures": [signatures[key] for key in keys],
            "candidate_pairs": candidates,
            "round_1_relations": [relation for relation in report["relations"] if atom_to_chapter[relation["from_key"]] == chapter and atom_to_chapter[relation["to_key"]] == chapter],
        }
        payload["packet_sha256"] = packet_digest(payload)
        audits.append(payload)
    cross_candidates = []
    for (from_key, to_key), reasons in pairs.items():
        if atom_to_chapter[from_key] == atom_to_chapter[to_key]:
            continue
        cross_candidates.append({"candidate_id": candidate_id(from_key, to_key), "from_key": from_key, "to_key": to_key, "reasons": sorted(reasons), "round_1_relation_keys": relation_by_pair.get((from_key, to_key), [])})
    cross_payload = {
        "audit_id": "relation-audit-cross-chapter",
        "scope": "cross-chapter",
        "scope_key": None,
        "atoms": [atoms[atom_key] for atom_key in sorted({key for candidate in cross_candidates for key in (candidate["from_key"], candidate["to_key"])})],
        "concept_signatures": [signatures[key] for key in sorted({key for candidate in cross_candidates for key in (candidate["from_key"], candidate["to_key"])})],
        "candidate_pairs": sorted(cross_candidates, key=lambda item: (item["from_key"], item["to_key"])),
        "round_1_relations": [],
    }
    cross_payload["packet_sha256"] = packet_digest(cross_payload)
    audits.append(cross_payload)
    return seal_artifact(
        {
            "schema_version": 1,
            "kind": "round-2-relation-jobs",
            "relation_jobs_sha256": jobs["artifact_sha256"],
            "round_1_relations_sha256": round1["artifact_sha256"],
            "manifest": jobs["manifest"],
            "manifest_sha256": jobs["manifest_sha256"],
            "source_markdown_sha256": jobs["source_markdown_sha256"],
            "chapter_order": jobs["chapter_order"],
            "atom_to_chapter": atom_to_chapter,
            "relation_analysis": jobs["relation_analysis"],
            "concept_signatures": list(signatures.values()),
            "audits": audits,
        }
    )


def cycle_nodes(relations: list[dict[str, Any]]) -> list[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for relation in relations:
        if relation.get("tier") == "backbone":
            graph[str(relation["from_key"])].append(str(relation["to_key"]))
    visiting: set[str] = set()
    visited: set[str] = set()
    found: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            found.add(key)
            return
        if key in visited:
            return
        visiting.add(key)
        for child in graph.get(key, []):
            if child in visiting:
                found.update({key, child})
            else:
                visit(child)
        visiting.remove(key)
        visited.add(key)

    for key in list(graph):
        visit(key)
    return sorted(found)


def finalize_relations(jobs: dict[str, Any], round1: dict[str, Any], audits: dict[str, Any], round2: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    round1_report = validate_round1_payload(jobs, round1)
    errors.extend(round1_report["errors"])
    if audits.get("relation_jobs_sha256") != jobs.get("artifact_sha256") or audits.get("round_1_relations_sha256") != round1.get("artifact_sha256"):
        errors.append({"code": "relation-audit-binding-invalid"})
    if round2.get("kind") != "round-2-relations" or round2.get("round_2_jobs_sha256") != audits.get("artifact_sha256"):
        errors.append({"code": "round2-relation-binding-invalid"})
    atom_records = {str(atom["atom_key"]): atom for job in jobs.get("jobs", []) for atom in job.get("atoms", [])}
    by_id = decision_map(round2, "audit_id")
    expected_ids = [str(audit["audit_id"]) for audit in audits.get("audits", [])]
    if set(by_id) != set(expected_ids):
        errors.append({"code": "round2-relation-coverage-invalid", "missing": sorted(set(expected_ids)-set(by_id)), "extra": sorted(set(by_id)-set(expected_ids))})
    final_relations: list[dict[str, Any]] = []
    independent: dict[str, str] = {}
    atom_to_chapter = {str(key): str(value) for key, value in jobs["atom_to_chapter"].items()}
    for audit in audits.get("audits", []):
        audit_id = str(audit["audit_id"])
        decision = by_id.get(audit_id)
        if decision is None:
            continue
        if decision.get("packet_sha256") != audit.get("packet_sha256"):
            errors.append({"code": "round2-relation-packet-digest-mismatch", "audit_id": audit_id})
        expected_candidates = {str(item["candidate_id"]) for item in audit.get("candidate_pairs", [])}
        reviewed = decision.get("reviewed_candidate_ids")
        if not isinstance(reviewed, list) or set(reviewed) != expected_candidates or len(reviewed) != len(set(reviewed)):
            errors.append({"code": "relation-candidate-review-coverage-invalid", "audit_id": audit_id})
        raw_independent = decision.get("independent_atoms", [])
        if not isinstance(raw_independent, list):
            errors.append({"code": "relation-independent-atoms-invalid", "audit_id": audit_id})
            raw_independent = []
        for item in raw_independent:
            if not isinstance(item, dict) or item.get("atom_key") not in atom_records or not isinstance(item.get("reason"), str) or len(item["reason"].strip()) < 12:
                errors.append({"code": "relation-independent-atom-invalid", "audit_id": audit_id})
            else:
                independent[str(item["atom_key"])] = str(item["reason"]).strip()
        for index, raw in enumerate(decision.get("relations", []) if isinstance(decision.get("relations"), list) else []):
            relation = validate_relation(raw, atom_records, jobs["relation_analysis"], f"{audit_id}:relation:{index}", errors, review)
            if relation is None:
                continue
            same_chapter = atom_to_chapter[relation["from_key"]] == atom_to_chapter[relation["to_key"]]
            if (audit.get("scope") == "chapter") != same_chapter:
                errors.append({"code": "relation-audit-scope-invalid", "audit_id": audit_id, "relation": relation["key"]})
            final_relations.append(relation)
    identities: set[tuple[str, str, str]] = set()
    for relation in final_relations:
        identity = (relation["from_key"], relation["to_key"], relation["type"])
        if identity in identities:
            errors.append({"code": "relation-duplicate", "relation": relation["key"]})
        identities.add(identity)
        reverse = (relation["to_key"], relation["from_key"], relation["type"])
        if relation["type"] not in SYMMETRIC_RELATION_TYPES and reverse in identities:
            review.append({"code": "relation-direction-conflict", "relation": relation["key"]})
    cycles = cycle_nodes(final_relations)
    if cycles:
        review.append({"code": "relation-backbone-cycle", "nodes": cycles})
    incident_with_knowledge: dict[str, bool] = defaultdict(bool)
    backbone_incident: dict[str, bool] = defaultdict(bool)
    for relation in final_relations:
        left, right = atom_records[relation["from_key"]], atom_records[relation["to_key"]]
        if left["category"] == "knowledge" or right["category"] == "knowledge":
            incident_with_knowledge[relation["from_key"]] = True
            incident_with_knowledge[relation["to_key"]] = True
        if relation["tier"] == "backbone":
            backbone_incident[relation["from_key"]] = True
            backbone_incident[relation["to_key"]] = True
    for atom_key, atom in atom_records.items():
        category = atom["category"]
        if category in {"worked-example", "exercise", "scenario"} and not incident_with_knowledge[atom_key] and atom_key not in independent:
            review.append({"code": "relation-orphan-teaching-atom", "atom": atom_key, "category": category})
    for chapter in jobs["chapter_order"]:
        core = [key for key, atom in atom_records.items() if atom_to_chapter[key] == chapter and atom["category"] in {"knowledge", "scenario"}]
        if len(core) > 1:
            for atom_key in core:
                if not backbone_incident[atom_key] and atom_key not in independent:
                    review.append({"code": "relation-orphan-backbone-atom", "atom": atom_key, "chapter": chapter})
    unresolved = [*errors, *review]
    bindings = {
        "jobs": {"path": jobs.get("_path"), "sha256": jobs.get("artifact_sha256")},
        "round_1_relations": {"path": round1.get("_path"), "sha256": round1.get("artifact_sha256")},
        "round_2_jobs": {"path": audits.get("_path"), "sha256": audits.get("artifact_sha256")},
        "round_2_relations": {"path": round2.get("_path"), "sha256": round2.get("artifact_sha256")},
    }
    final = seal_artifact(
        {
            "schema_version": 1,
            "kind": "relation-final",
            "status": "passed" if not unresolved else "review_required",
            "manifest": jobs["manifest"],
            "manifest_sha256": jobs["manifest_sha256"],
            "source_markdown_sha256": jobs["source_markdown_sha256"],
            "relation_analysis": jobs["relation_analysis"],
            "chapter_order": jobs["chapter_order"],
            "concept_signatures": audits.get("concept_signatures", []),
            "reviewer": {"round_1": round1.get("reviewer"), "round_2": round2.get("reviewer")},
            "bindings": bindings,
            "independent_atoms": [{"atom_key": key, "reason": independent[key]} for key in sorted(independent)],
            "unresolved_count": len(unresolved),
            "relations": sorted(final_relations, key=lambda item: (item["from_key"], item["to_key"], item["type"])),
        }
    )
    queue = seal_artifact(
        {
            "schema_version": 1,
            "kind": "relation-review-queue",
            "status": "passed" if not unresolved else "blocked",
            "relation_final_sha256": final["artifact_sha256"],
            "unresolved_count": len(unresolved),
            "items": unresolved,
        }
    )
    return final, queue


def load_tagged(path: Path, kind: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    payload = load_json(resolved)
    verify_artifact(payload, kind)
    payload["_path"] = str(resolved)
    return payload


def apply_relation_final(
    manifest_path: Path,
    final_path: Path,
    output_path: Path,
    profile_output: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    manifest_path, final_path, output_path = (path.expanduser().resolve() for path in (manifest_path, final_path, output_path))
    manifest = load_json(manifest_path)
    final = load_tagged(final_path, "relation-final")
    if final.get("status") != "passed" or final.get("unresolved_count") != 0:
        raise RelationError("Relation analysis is not passed")
    if final.get("manifest_sha256") != sha256_file(manifest_path) or final.get("source_markdown_sha256") != manifest.get("source_markdown_sha256"):
        raise RelationError("Relation analysis binds a different or stale manifest")
    result = {key: value for key, value in manifest.items()}
    result["relations"] = final["relations"]
    atom_categories = {
        str(node["key"]): str(node.get("category"))
        for node in manifest.get("nodes", [])
        if isinstance(node, dict) and node.get("layer") == "atom"
    }
    featured_examples = sorted(
        str(signature["atom_key"])
        for signature in final.get("concept_signatures", [])
        if isinstance(signature, dict)
        and signature.get("role") == "bridge"
        and atom_categories.get(str(signature.get("atom_key"))) == "worked-example"
    )
    result["relation_review"] = {
        "status": "passed",
        "mode": "llm-two-pass",
        "final_artifact": {"path": str(final_path), "sha256": final["artifact_sha256"]},
        "bindings": final.get("bindings", {}),
        "reviewer": final.get("reviewer"),
        "featured_example_keys": featured_examples,
        "unresolved_count": 0,
    }
    if profile_output is not None:
        profile_output = profile_output.expanduser().resolve()
        profile = load_json(Path(str(manifest["profile"])).expanduser().resolve())
        profile["relation_analysis"] = dict(final["relation_analysis"])
        profile["canvas"] = dict(DEFAULT_CANVAS)
        atomic_json(profile_output, profile, overwrite)
        result["profile"] = str(profile_output)
    atomic_json(output_path, result, overwrite)
    return {"status": "passed", "manifest": str(output_path), "profile": result["profile"], "relations": len(result["relations"]), "relation_final_sha256": artifact_digest(final)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("manifest", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--max-chars", type=int, default=50000)
    prepare.add_argument("--overwrite", action="store_true")
    validate = sub.add_parser("validate-round1")
    validate.add_argument("jobs", type=Path)
    validate.add_argument("decisions", type=Path)
    validate.add_argument("--output", type=Path)
    validate.add_argument("--overwrite", action="store_true")
    audit = sub.add_parser("prepare-audit")
    audit.add_argument("jobs", type=Path)
    audit.add_argument("round1", type=Path)
    audit.add_argument("--output-dir", type=Path, required=True)
    audit.add_argument("--overwrite", action="store_true")
    finish = sub.add_parser("finalize")
    finish.add_argument("jobs", type=Path)
    finish.add_argument("round1", type=Path)
    finish.add_argument("round2_jobs", type=Path)
    finish.add_argument("round2", type=Path)
    finish.add_argument("--output-dir", type=Path, required=True)
    finish.add_argument("--overwrite", action="store_true")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("manifest", type=Path)
    apply_parser.add_argument("relation_final", type=Path)
    apply_parser.add_argument("--output", type=Path, required=True)
    apply_parser.add_argument("--profile-output", type=Path)
    apply_parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            payload = prepare_relation_jobs(args.manifest, args.max_chars)
            output = args.output_dir.expanduser().resolve() / "relation-jobs.json"
            atomic_json(output, payload, args.overwrite)
            report, code = {"status": "created", "path": str(output), "jobs": len(payload["jobs"]), "sha256": payload["artifact_sha256"]}, 0
        elif args.command == "validate-round1":
            report = validate_round1_payload(load_tagged(args.jobs, "relation-jobs"), load_tagged(args.decisions, "round-1-relations"))
            if args.output:
                atomic_json(args.output, report, args.overwrite)
            code = 1 if report["status"] == "failed" else (2 if report["status"] == "review_required" else 0)
        elif args.command == "prepare-audit":
            payload = prepare_audit_jobs(load_tagged(args.jobs, "relation-jobs"), load_tagged(args.round1, "round-1-relations"))
            output = args.output_dir.expanduser().resolve() / "round-2-jobs.json"
            atomic_json(output, payload, args.overwrite)
            report, code = {"status": "created", "path": str(output), "audits": len(payload["audits"]), "sha256": payload["artifact_sha256"]}, 0
        elif args.command == "finalize":
            final, queue = finalize_relations(load_tagged(args.jobs, "relation-jobs"), load_tagged(args.round1, "round-1-relations"), load_tagged(args.round2_jobs, "round-2-relation-jobs"), load_tagged(args.round2, "round-2-relations"))
            output_dir = args.output_dir.expanduser().resolve()
            final_path, queue_path = output_dir / "relation-final.json", output_dir / "relation-review-queue.json"
            atomic_json(final_path, final, args.overwrite)
            atomic_json(queue_path, queue, args.overwrite)
            report = {"status": final["status"], "relation_final": str(final_path), "review_queue": str(queue_path), "relations": len(final["relations"]), "unresolved_count": final["unresolved_count"]}
            code = 0 if final["status"] == "passed" else 2
        else:
            report = apply_relation_final(args.manifest, args.relation_final, args.output, args.profile_output, args.overwrite)
            code = 0
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

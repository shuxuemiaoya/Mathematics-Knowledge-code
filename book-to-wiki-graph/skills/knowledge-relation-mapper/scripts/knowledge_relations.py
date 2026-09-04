#!/usr/bin/env python3
"""Three-pass, evidence-bound atom/concept teaching-graph construction."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable


CONCEPT_KINDS = {
    "concept", "definition", "property", "theorem", "rule", "procedure",
    "representation", "method",
}
ATOM_CONCEPT_ROLES = {
    "introduces", "explains", "derives", "triggered_by", "motivates",
    "illustrates", "applies", "practices", "assumes",
}
CONCEPT_RELATION_TYPES = {
    "prerequisite", "develops", "derives", "broader", "part_of",
    "contrasts", "analogous",
}
ATOM_RELATION_TYPES = {
    "prerequisite", "develops", "derives", "motivates", "illustrates",
    "applies", "practices", "contrasts", "analogous",
}
SYMMETRIC_CONCEPT_RELATIONS = {"contrasts", "analogous"}
SYMMETRIC_ATOM_RELATIONS = {"contrasts", "analogous"}
PRODUCER_ROLES = {"introduces", "explains", "derives"}
DEPENDENT_ROLES = {"assumes", "triggered_by", "motivates", "illustrates", "applies", "practices"}
CORE_ATOM_CATEGORIES = {"knowledge", "scenario"}
DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "llm-three-pass",
    "graph_model": "atom-concept-dual-layer",
    "concept_scope": "book",
    "explicit_confidence_threshold": 0.90,
    "inferred_confidence_threshold": 0.95,
    "concept_merge_threshold": 0.97,
    "cross_chapter": True,
    "candidate_retrieval": {
        "source_window": 2,
        "lexical_top_k": 8,
        "embedding": "optional",
        "embedding_top_k": 8,
        "graph_hops": 2,
        "max_ranked_candidates_per_atom": 12,
    },
    "community_analysis": "wcc-required-leiden-optional",
}
ACTIVITY_LABEL_RE = re.compile(r"^(观察|思考|尝试|交流|探索|做一做|议一议)(?:[·・、].*)?$", re.I)
QUESTION_LABEL_RE = re.compile(r"^(?:第\s*\d+\s*题|\(?\d+\)?[.、．])|[？?]$")


class RelationV2Error(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RelationV2Error(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_digest(payload: dict[str, Any]) -> str:
    clean = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
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


def atomic_text(path: Path, text: str, overwrite: bool = False) -> None:
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
            handle.write(text)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def load_tagged(path: Path, kind: str) -> dict[str, Any]:
    path = path.expanduser().resolve()
    payload = load_json(path)
    if payload.get("kind") != kind or payload.get("artifact_sha256") != artifact_digest(payload):
        raise RelationV2Error(f"Invalid or stale {kind}: {path}")
    payload["_path"] = str(path)
    return payload


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in folded if character.isalnum())


def ngrams(value: str, width: int = 2) -> set[str]:
    text = normalized(value)
    if not text:
        return set()
    if len(text) <= width:
        return {text}
    return {text[index:index + width] for index in range(len(text) - width + 1)}


def lexical_similarity(left: str, right: str) -> float:
    a, b = ngrams(left), ngrams(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


def packet_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def stable_key(prefix: str, *parts: str) -> str:
    return f"{prefix}-{hashlib.sha256(chr(31).join(parts).encode('utf-8')).hexdigest()[:16]}"


def descendants(nodes: dict[str, dict[str, Any]], root_key: str) -> list[str]:
    result: list[str] = []

    def visit(key: str) -> None:
        result.append(key)
        for child in nodes[key].get("children", []):
            visit(str(child))

    visit(root_key)
    return result


def chapter_for(nodes: dict[str, dict[str, Any]], root_key: str, key: str) -> str:
    cursor = key
    parent = nodes[cursor].get("parent_key")
    while parent is not None and str(parent) != root_key:
        cursor = str(parent)
        parent = nodes[cursor].get("parent_key")
    if parent is None:
        raise RelationV2Error(f"Atom is outside the root organizer: {key}")
    return cursor


def organizer_path(nodes: dict[str, dict[str, Any]], key: str) -> list[str]:
    result: list[str] = []
    cursor = nodes[key].get("parent_key")
    while cursor is not None:
        result.append(str(cursor))
        cursor = nodes[str(cursor)].get("parent_key")
    return list(reversed(result))


def relation_config(profile: dict[str, Any]) -> dict[str, Any]:
    raw = profile.get("relation_analysis")
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key == "candidate_retrieval" and isinstance(value, dict):
                config[key].update(value)
            elif key != "mode" or value == "llm-three-pass":
                config[key] = value
        if raw.get("mode") == "llm-two-pass":
            config["upgraded_from"] = "llm-two-pass"
    for field in ("explicit_confidence_threshold", "inferred_confidence_threshold", "concept_merge_threshold"):
        value = config.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise RelationV2Error(f"Invalid relation_analysis.{field}")
    retrieval = config.get("candidate_retrieval")
    if not isinstance(retrieval, dict):
        raise RelationV2Error("relation_analysis.candidate_retrieval must be an object")
    for field in ("source_window", "lexical_top_k", "embedding_top_k", "graph_hops", "max_ranked_candidates_per_atom"):
        if not isinstance(retrieval.get(field), int) or int(retrieval[field]) < 0:
            raise RelationV2Error(f"Invalid candidate_retrieval.{field}")
    return config


def load_manifest_context(manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], Path, list[str], str, list[str]]:
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_json(manifest_path)
    profile_path = Path(str(manifest.get("profile", ""))).expanduser().resolve()
    source_path = Path(str(manifest.get("source_markdown", ""))).expanduser().resolve()
    if not profile_path.is_file() or not source_path.is_file():
        raise RelationV2Error("Manifest profile or source Markdown is missing")
    profile = load_json(profile_path)
    if manifest.get("source_markdown_sha256") != sha256_file(source_path):
        raise RelationV2Error("Source Markdown digest is stale")
    nodes = {
        str(node["key"]): node for node in manifest.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("key"), str)
    }
    roots = [key for key, node in nodes.items() if node.get("layer") == "organizer" and node.get("parent_key") is None]
    if len(roots) != 1:
        raise RelationV2Error("Manifest must contain exactly one root organizer")
    root_key = roots[0]
    chapters = [str(key) for key in nodes[root_key].get("children", []) if nodes.get(str(key), {}).get("layer") == "organizer"]
    if not chapters:
        raise RelationV2Error("Manifest must contain chapter organizers")
    return manifest, profile, nodes, source_path, source_path.read_text(encoding="utf-8-sig").splitlines(), root_key, chapters


def source_atom(node: dict[str, Any], nodes: dict[str, dict[str, Any]], lines: list[str], root_key: str) -> dict[str, Any]:
    start, end = (int(value) for value in node["source_range"])
    key = str(node["key"])
    path = organizer_path(nodes, key)
    return {
        "atom_key": key,
        "title": str(node["title"]),
        "category": str(node["category"]),
        "source_range": [start, end],
        "source_text": "\n".join(lines[start - 1:end]),
        "organizer_path": path,
        "organizer_titles": [str(nodes[item]["title"]) for item in path],
        "chapter_key": chapter_for(nodes, root_key, key),
    }


def registry_binding(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    payload = load_json(resolved)
    concepts = payload.get("concepts")
    if not isinstance(concepts, list):
        raise RelationV2Error("Concept registry must contain a concepts array")
    return {"path": str(resolved), "sha256": sha256_file(resolved), "concept_count": len(concepts), "mode": "read-only"}


def prepare_concept_jobs(manifest_path: Path, max_chars: int = 80000, registry: Path | None = None) -> dict[str, Any]:
    if max_chars < 4000:
        raise RelationV2Error("max_chars must be at least 4000")
    manifest, profile, nodes, source, lines, root_key, chapters = load_manifest_context(manifest_path)
    atoms = {
        key: source_atom(node, nodes, lines, root_key)
        for key, node in nodes.items() if node.get("layer") == "atom"
    }
    jobs: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(chapters, start=1):
        ordered = sorted(
            (atom for atom in atoms.values() if atom["chapter_key"] == chapter),
            key=lambda item: (item["source_range"][0], item["atom_key"]),
        )
        packets: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_chars = 0
        for atom in ordered:
            atom_chars = len(atom["source_text"])
            section = atom["organizer_path"][1] if len(atom["organizer_path"]) > 1 else chapter
            current_section = current[-1]["organizer_path"][1] if current and len(current[-1]["organizer_path"]) > 1 else chapter
            if current and current_chars + atom_chars > max_chars and section != current_section:
                packets.append(current)
                current, current_chars = [], 0
            if current and current_chars + atom_chars > max_chars:
                packets.append(current)
                current, current_chars = [], 0
            current.append(atom)
            current_chars += atom_chars
        if current:
            packets.append(current)
        for packet_index, packet in enumerate(packets, start=1):
            first = ordered.index(packet[0])
            last = ordered.index(packet[-1])
            context = ordered[max(0, first - 1):first] + ordered[last + 1:min(len(ordered), last + 2)]
            job = {
                "job_id": f"concept-job-{chapter_index:03d}-{packet_index:03d}",
                "chapter_key": chapter,
                "chapter_title": str(nodes[chapter]["title"]),
                "packet_index": packet_index,
                "packet_count": len(packets),
                "atoms": packet,
                "context_atoms": context,
            }
            job["packet_sha256"] = packet_digest(job)
            jobs.append(job)
    return seal_artifact({
        "schema_version": 2,
        "kind": "concept-jobs",
        "manifest": str(manifest_path.expanduser().resolve()),
        "manifest_sha256": sha256_file(manifest_path.expanduser().resolve()),
        "source_markdown": str(source),
        "source_markdown_sha256": sha256_file(source),
        "root_key": root_key,
        "chapter_order": chapters,
        "relation_analysis": relation_config(profile),
        "concept_registry": registry_binding(registry),
        "existing_relations": list(manifest.get("relations", [])),
        "jobs": jobs,
    })


def decision_map(payload: dict[str, Any], field: str) -> dict[str, dict[str, Any]]:
    values = payload.get("decisions")
    if not isinstance(values, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        if isinstance(value, dict) and isinstance(value.get(field), str) and value[field] not in result:
            result[str(value[field])] = value
    return result


def label_issue(label: str) -> str | None:
    compact = "".join(label.split())
    if not compact:
        return "concept-label-empty"
    if len(compact) > 60:
        return "concept-label-too-long"
    if ACTIVITY_LABEL_RE.match(label.strip()):
        return "concept-label-is-activity"
    if QUESTION_LABEL_RE.search(label.strip()):
        return "concept-label-is-question"
    return None


def valid_range(raw: Any, atom: dict[str, Any]) -> bool:
    return (
        isinstance(raw, list) and len(raw) == 2 and all(isinstance(value, int) for value in raw)
        and int(atom["source_range"][0]) <= raw[0] <= raw[1] <= int(atom["source_range"][1])
    )


def validate_concept_payload(jobs: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    if decisions.get("kind") != "round-1-concepts" or decisions.get("concept_jobs_sha256") != jobs.get("artifact_sha256"):
        errors.append({"code": "concept-round1-binding-invalid"})
    by_id = decision_map(decisions, "job_id")
    expected = {str(job["job_id"]) for job in jobs.get("jobs", [])}
    if set(by_id) != expected:
        errors.append({"code": "concept-job-coverage-invalid", "missing": sorted(expected - set(by_id)), "extra": sorted(set(by_id) - expected)})
    concepts: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    atom_roles: dict[str, dict[str, Any]] = {}
    seen_proposals: set[str] = set()
    all_primary_atoms: set[str] = set()
    for job in jobs.get("jobs", []):
        job_id = str(job["job_id"])
        decision = by_id.get(job_id)
        if decision is None:
            continue
        if decision.get("packet_sha256") != job.get("packet_sha256"):
            errors.append({"code": "concept-packet-digest-mismatch", "job_id": job_id})
        atom_map = {str(atom["atom_key"]): atom for atom in [*job.get("atoms", []), *job.get("context_atoms", [])]}
        primary_atoms = {str(atom["atom_key"]) for atom in job.get("atoms", [])}
        all_primary_atoms.update(primary_atoms)
        local_proposals: set[str] = set()
        for index, raw in enumerate(decision.get("concepts", []) if isinstance(decision.get("concepts"), list) else []):
            context = f"{job_id}:concept:{index}"
            if not isinstance(raw, dict):
                errors.append({"code": "concept-invalid", "context": context})
                continue
            proposal = str(raw.get("proposal_id", ""))
            label = str(raw.get("preferred_label", "")).strip()
            if not proposal or proposal in seen_proposals:
                errors.append({"code": "concept-proposal-id-invalid", "context": context, "proposal_id": proposal})
                continue
            seen_proposals.add(proposal)
            local_proposals.add(proposal)
            issue = label_issue(label)
            if issue:
                review.append({"code": issue, "context": context, "proposal_id": proposal, "label": label})
            aliases = raw.get("aliases")
            definition = raw.get("definition")
            kind = raw.get("kind")
            evidence = raw.get("evidence")
            if not isinstance(aliases, list) or not all(isinstance(value, str) and value.strip() for value in aliases):
                errors.append({"code": "concept-aliases-invalid", "context": context})
                aliases = []
            if not isinstance(definition, str) or len(definition.strip()) < 8 or kind not in CONCEPT_KINDS:
                errors.append({"code": "concept-description-invalid", "context": context})
            valid_evidence: list[dict[str, Any]] = []
            evidence_categories: set[str] = set()
            if not isinstance(evidence, list) or not evidence:
                errors.append({"code": "concept-evidence-missing", "context": context})
                evidence = []
            for item in evidence:
                atom_key = item.get("atom_key") if isinstance(item, dict) else None
                if atom_key not in atom_map or not valid_range(item.get("source_range"), atom_map[str(atom_key)]):
                    errors.append({"code": "concept-evidence-invalid", "context": context})
                    continue
                evidence_categories.add(str(atom_map[str(atom_key)]["category"]))
                valid_evidence.append({"atom_key": str(atom_key), "source_range": list(item["source_range"])})
            if evidence_categories and evidence_categories <= {"exercise"}:
                review.append({"code": "exercise-only-concept-proposal", "context": context, "proposal_id": proposal})
            concepts.append({
                "proposal_id": proposal, "preferred_label": label,
                "aliases": sorted(set(str(value).strip() for value in aliases if str(value).strip() and normalized(str(value)) != normalized(label))),
                "definition": definition.strip() if isinstance(definition, str) else "",
                "kind": str(kind), "evidence": valid_evidence,
                "chapter_key": str(job["chapter_key"]), "job_id": job_id,
            })
        for index, raw in enumerate(decision.get("atom_concept_links", []) if isinstance(decision.get("atom_concept_links"), list) else []):
            context = f"{job_id}:link:{index}"
            if not isinstance(raw, dict):
                errors.append({"code": "atom-concept-link-invalid", "context": context})
                continue
            atom_key, concept_ref, role = raw.get("atom_key"), raw.get("concept_ref"), raw.get("role")
            if atom_key not in atom_map or concept_ref not in local_proposals or role not in ATOM_CONCEPT_ROLES:
                errors.append({"code": "atom-concept-link-invalid", "context": context})
                continue
            confidence = raw.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                errors.append({"code": "atom-concept-confidence-invalid", "context": context})
                confidence = 0.0
            evidence_ranges = raw.get("evidence_ranges")
            if not isinstance(evidence_ranges, list) or not evidence_ranges or not all(valid_range(value, atom_map[str(atom_key)]) for value in evidence_ranges):
                errors.append({"code": "atom-concept-evidence-invalid", "context": context})
                evidence_ranges = []
            links.append({
                "atom_key": str(atom_key), "concept_ref": str(concept_ref), "role": str(role),
                "evidence_ranges": [list(value) for value in evidence_ranges], "confidence": float(confidence),
            })
        for raw in decision.get("atom_roles", []) if isinstance(decision.get("atom_roles"), list) else []:
            if not isinstance(raw, dict) or raw.get("atom_key") not in primary_atoms or raw.get("role") not in {"core", "bridge", "satellite"}:
                errors.append({"code": "atom-semantic-role-invalid", "job_id": job_id})
                continue
            atom_key = str(raw["atom_key"])
            category = atom_map[atom_key]["category"]
            if raw["role"] == "bridge" and category != "worked-example":
                errors.append({"code": "bridge-role-category-invalid", "atom_key": atom_key})
            if raw["role"] == "core" and category not in CORE_ATOM_CATEGORIES:
                errors.append({"code": "core-role-category-invalid", "atom_key": atom_key})
            rationale = raw.get("rationale")
            if not isinstance(rationale, str) or len(rationale.strip()) < 8:
                errors.append({"code": "atom-semantic-role-rationale-invalid", "atom_key": atom_key})
            atom_roles[atom_key] = {"atom_key": atom_key, "role": str(raw["role"]), "rationale": str(rationale).strip() if isinstance(rationale, str) else ""}
        linked_primary = {link["atom_key"] for link in links if link["atom_key"] in primary_atoms}
        if linked_primary != primary_atoms:
            errors.append({"code": "atom-concept-coverage-invalid", "job_id": job_id, "missing": sorted(primary_atoms - linked_primary)})
        if set(atom_roles).intersection(primary_atoms) != primary_atoms:
            errors.append({"code": "atom-semantic-role-coverage-invalid", "job_id": job_id, "missing": sorted(primary_atoms - set(atom_roles))})
    return {
        "schema_version": 2,
        "status": "failed" if errors else ("review_required" if review else "passed"),
        "errors": errors, "review_items": review,
        "concepts": concepts, "atom_concept_links": links,
        "atom_roles": [atom_roles[key] for key in sorted(atom_roles)],
        "atom_count": len(all_primary_atoms),
    }


def concept_text(concept: dict[str, Any]) -> str:
    return " ".join([str(concept["preferred_label"]), *concept.get("aliases", []), str(concept.get("definition", ""))])


def candidate_id(kind: str, left: str, right: str) -> str:
    a, b = sorted((left, right))
    return stable_key("candidate", kind, a, b)


def add_candidate(
    target: dict[tuple[str, str, str], dict[str, Any]], kind: str, left: str, right: str,
    channel: str, score: float = 1.0, hard: bool = False,
) -> None:
    if left == right:
        return
    a, b = sorted((left, right))
    identity = kind, a, b
    item = target.setdefault(identity, {
        "candidate_id": candidate_id(kind, a, b), "kind": kind,
        "left_key": a, "right_key": b, "channels": [], "scores": {}, "hard": False,
    })
    if channel not in item["channels"]:
        item["channels"].append(channel)
    item["scores"][channel] = round(max(float(score), float(item["scores"].get(channel, 0.0))), 6)
    item["hard"] = bool(item["hard"] or hard)


def load_embeddings(path: Path | None, jobs_digest: str, round1_digest: str) -> tuple[dict[str, list[float]], dict[str, Any]]:
    if path is None:
        return {}, {"status": "not-configured"}
    resolved = path.expanduser().resolve()
    payload = load_json(resolved)
    if (
        payload.get("kind") != "relation-embeddings"
        or payload.get("artifact_sha256") != artifact_digest(payload)
        or payload.get("concept_jobs_sha256") != jobs_digest
        or payload.get("round_1_concepts_sha256") != round1_digest
    ):
        raise RelationV2Error("Embedding artifact is stale or bound to other concept jobs")
    vectors = payload.get("vectors")
    if not isinstance(vectors, dict):
        raise RelationV2Error("Embedding artifact vectors must be an object")
    normalized_vectors: dict[str, list[float]] = {}
    for key, value in vectors.items():
        if isinstance(value, list) and value and all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in value):
            normalized_vectors[str(key)] = [float(number) for number in value]
    return normalized_vectors, {"status": "used", "path": str(resolved), "sha256": sha256_file(resolved), "model": payload.get("model")}


def atom_records(jobs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(atom["atom_key"]): atom
        for job in jobs.get("jobs", []) for atom in job.get("atoms", [])
    }


def prepare_relation_jobs(
    concept_jobs: dict[str, Any], round1: dict[str, Any], embeddings_path: Path | None = None,
) -> dict[str, Any]:
    report = validate_concept_payload(concept_jobs, round1)
    if report["errors"]:
        raise RelationV2Error(f"Round-one concepts are structurally invalid: {report['errors'][:5]}")
    config = concept_jobs["relation_analysis"]
    retrieval = config["candidate_retrieval"]
    atoms = atom_records(concept_jobs)
    concepts = {str(item["proposal_id"]): item for item in report["concepts"]}
    links = report["atom_concept_links"]
    by_atom: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        by_atom[link["atom_key"]].append(link)
        by_concept[link["concept_ref"]].append(link)
    vectors, embedding_binding = load_embeddings(
        embeddings_path, str(concept_jobs["artifact_sha256"]), str(round1["artifact_sha256"]),
    )
    candidates: dict[tuple[str, str, str], dict[str, Any]] = {}

    concept_keys = sorted(concepts)
    for index, left in enumerate(concept_keys):
        left_terms = {normalized(concepts[left]["preferred_label"]), *(normalized(value) for value in concepts[left].get("aliases", []))}
        for right in concept_keys[index + 1:]:
            right_terms = {normalized(concepts[right]["preferred_label"]), *(normalized(value) for value in concepts[right].get("aliases", []))}
            if (left_terms - {""}) & (right_terms - {""}):
                add_candidate(candidates, "concept-merge", left, right, "exact-alias", 1.0, True)
            similarity = lexical_similarity(concept_text(concepts[left]), concept_text(concepts[right]))
            if similarity >= 0.45:
                add_candidate(candidates, "concept-merge", left, right, "lexical-concept", similarity)
            if left in vectors and right in vectors:
                vector_score = cosine(vectors[left], vectors[right])
                if vector_score >= 0.75:
                    add_candidate(candidates, "concept-merge", left, right, "embedding-concept", vector_score)

    ordered = sorted(atoms, key=lambda key: (atoms[key]["source_range"][0], key))
    source_window = int(retrieval["source_window"])
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:index + source_window + 1]:
            if atoms[left]["chapter_key"] == atoms[right]["chapter_key"]:
                add_candidate(candidates, "atom-relation", left, right, "source-window", 1.0, True)
    same_owner: dict[str, list[str]] = defaultdict(list)
    for atom_key, atom in atoms.items():
        owner = atom["organizer_path"][-1] if atom["organizer_path"] else atom["chapter_key"]
        same_owner[owner].append(atom_key)
    for keys in same_owner.values():
        keys.sort(key=lambda key: (atoms[key]["source_range"][0], key))
        for index, left in enumerate(keys):
            for right in keys[index + 1:index + 5]:
                add_candidate(candidates, "atom-relation", left, right, "organizer-neighborhood", 0.9, True)

    for concept_ref, concept_links in by_concept.items():
        producers = [item["atom_key"] for item in concept_links if item["role"] in PRODUCER_ROLES]
        dependents = [item["atom_key"] for item in concept_links if item["role"] in DEPENDENT_ROLES]
        for left in producers:
            for right in dependents:
                add_candidate(candidates, "atom-relation", left, right, "teaches-assumes", 1.0, True)
        occurrence_atoms = sorted({item["atom_key"] for item in concept_links})
        for index, left in enumerate(occurrence_atoms):
            for right in occurrence_atoms[index + 1:]:
                add_candidate(candidates, "atom-relation", left, right, "shared-concept", 0.95, True)

    aliases_to_producers: dict[str, set[str]] = defaultdict(set)
    for concept_ref, concept in concepts.items():
        producer_atoms = {item["atom_key"] for item in by_concept[concept_ref] if item["role"] in PRODUCER_ROLES}
        for label in [concept["preferred_label"], *concept.get("aliases", [])]:
            if len(normalized(label)) >= 2:
                aliases_to_producers[str(label)].update(producer_atoms)
    for target, atom in atoms.items():
        compact_text = normalized(atom["source_text"])
        for alias, producers in aliases_to_producers.items():
            if normalized(alias) and normalized(alias) in compact_text:
                for source in producers:
                    if source != target:
                        add_candidate(candidates, "atom-relation", source, target, "explicit-mention", 1.0, True)

    lexical_top_k = int(retrieval["lexical_top_k"])
    for left in ordered:
        scores = []
        for right in ordered:
            if left == right:
                continue
            score = lexical_similarity(atoms[left]["source_text"], atoms[right]["source_text"])
            if score > 0:
                scores.append((score, right))
        for score, right in sorted(scores, key=lambda value: (-value[0], value[1]))[:lexical_top_k]:
            add_candidate(candidates, "atom-relation", left, right, "lexical-atom", score)

    embedding_top_k = int(retrieval["embedding_top_k"])
    for left in ordered:
        if left not in vectors:
            continue
        scores = [(cosine(vectors[left], vectors[right]), right) for right in ordered if right != left and right in vectors]
        for score, right in sorted(scores, key=lambda value: (-value[0], value[1]))[:embedding_top_k]:
            if score > 0:
                add_candidate(candidates, "atom-relation", left, right, "embedding-atom", score)

    existing = [item for item in concept_jobs.get("existing_relations", []) if isinstance(item, dict)]
    adjacency: dict[str, set[str]] = defaultdict(set)
    for relation in existing:
        left, right = str(relation.get("from_key", "")), str(relation.get("to_key", ""))
        if left in atoms and right in atoms and left != right:
            add_candidate(candidates, "atom-relation", left, right, "existing-reviewed-relation", 1.0, True)
            adjacency[left].add(right)
            adjacency[right].add(left)
    if int(retrieval["graph_hops"]) >= 2:
        for left in adjacency:
            for middle in adjacency[left]:
                for right in adjacency[middle]:
                    if right != left:
                        add_candidate(candidates, "atom-relation", left, right, "existing-two-hop", 0.8)

    atom_candidates = [item for item in candidates.values() if item["kind"] == "atom-relation"]
    kept_atom_ids: set[str] = {item["candidate_id"] for item in atom_candidates if item["hard"]}
    ranked_by_atom: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for item in atom_candidates:
        if item["hard"]:
            continue
        rank = max(item["scores"].values(), default=0.0) + 0.02 * len(item["channels"])
        ranked_by_atom[item["left_key"]].append((rank, item["candidate_id"]))
        ranked_by_atom[item["right_key"]].append((rank, item["candidate_id"]))
    cap = int(retrieval["max_ranked_candidates_per_atom"])
    for values in ranked_by_atom.values():
        kept_atom_ids.update(candidate for _, candidate in sorted(values, key=lambda value: (-value[0], value[1]))[:cap])
    for identity, item in list(candidates.items()):
        if item["kind"] == "atom-relation" and item["candidate_id"] not in kept_atom_ids:
            del candidates[identity]

    for item in list(candidates.values()):
        if item["kind"] != "atom-relation":
            continue
        left_concepts = {link["concept_ref"] for link in by_atom.get(item["left_key"], [])}
        right_concepts = {link["concept_ref"] for link in by_atom.get(item["right_key"], [])}
        for left_concept in left_concepts:
            for right_concept in right_concepts:
                if left_concept != right_concept:
                    add_candidate(candidates, "concept-relation", left_concept, right_concept, "atom-candidate-projection", max(item["scores"].values(), default=0.5), item["hard"])

    all_candidates = sorted(candidates.values(), key=lambda item: (item["kind"], item["left_key"], item["right_key"]))
    atom_chapter = {key: str(atom["chapter_key"]) for key, atom in atoms.items()}
    concept_chapters = {
        key: {atom_chapter[link["atom_key"]] for link in by_concept.get(key, [])}
        for key in concepts
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in all_candidates:
        if item["kind"] == "atom-relation":
            scopes = {atom_chapter[item["left_key"]], atom_chapter[item["right_key"]]}
        else:
            scopes = concept_chapters[item["left_key"]] | concept_chapters[item["right_key"]]
        scope = next(iter(scopes)) if len(scopes) == 1 else "__cross_chapter__"
        grouped[scope].append(item)
    relation_jobs: list[dict[str, Any]] = []
    for index, scope in enumerate([*concept_jobs["chapter_order"], "__cross_chapter__"], start=1):
        scoped = grouped.get(str(scope), [])
        involved_atoms = sorted({key for item in scoped if item["kind"] == "atom-relation" for key in (item["left_key"], item["right_key"])})
        involved_concepts = sorted({key for item in scoped if item["kind"] != "atom-relation" for key in (item["left_key"], item["right_key"])})
        job = {
            "job_id": f"relation-job-{index:03d}",
            "scope": "cross-chapter" if scope == "__cross_chapter__" else "chapter",
            "scope_key": None if scope == "__cross_chapter__" else str(scope),
            "atoms": [atoms[key] for key in involved_atoms],
            "concepts": [concepts[key] for key in involved_concepts],
            "atom_concept_links": [link for link in links if link["atom_key"] in involved_atoms or link["concept_ref"] in involved_concepts],
            "candidates": scoped,
        }
        job["packet_sha256"] = packet_digest(job)
        relation_jobs.append(job)
    return seal_artifact({
        "schema_version": 2, "kind": "relation-jobs-v2",
        "concept_jobs_sha256": concept_jobs["artifact_sha256"],
        "round_1_concepts_sha256": round1["artifact_sha256"],
        "manifest": concept_jobs["manifest"], "manifest_sha256": concept_jobs["manifest_sha256"],
        "source_markdown_sha256": concept_jobs["source_markdown_sha256"],
        "relation_analysis": config, "chapter_order": concept_jobs["chapter_order"],
        "embedding": embedding_binding, "concepts": report["concepts"],
        "atoms": sorted(atoms.values(), key=lambda item: (item["source_range"][0], item["atom_key"])),
        "atom_concept_links": report["atom_concept_links"], "atom_roles": report["atom_roles"],
        "jobs": relation_jobs,
    })


def validate_confidence(raw: Any, evidence_kind: str, config: dict[str, Any], context: str, errors: list[dict[str, Any]], review: list[dict[str, Any]]) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 <= float(raw) <= 1:
        errors.append({"code": "relation-confidence-invalid", "context": context})
        return 0.0
    value = float(raw)
    threshold = float(config["explicit_confidence_threshold"] if evidence_kind == "explicit" else config["inferred_confidence_threshold"])
    if value < threshold:
        review.append({"code": "relation-confidence-below-threshold", "context": context, "confidence": value, "threshold": threshold})
    return value


def validate_relation_evidence(raw: Any, atoms: dict[str, dict[str, Any]], endpoints: set[str], context: str, errors: list[dict[str, Any]], require_both: bool) -> list[dict[str, Any]]:
    values = raw if isinstance(raw, list) else []
    valid: list[dict[str, Any]] = []
    covered: set[str] = set()
    for item in values:
        atom_key = item.get("atom_key") if isinstance(item, dict) else None
        if atom_key not in atoms or not valid_range(item.get("source_range"), atoms[str(atom_key)]):
            errors.append({"code": "relation-evidence-invalid", "context": context})
            continue
        if endpoints and str(atom_key) not in endpoints and len(endpoints) <= 2:
            errors.append({"code": "relation-evidence-endpoint-invalid", "context": context})
            continue
        covered.add(str(atom_key))
        valid.append({"atom_key": str(atom_key), "source_range": list(item["source_range"])})
    if not valid or (require_both and not endpoints.issubset(covered)):
        errors.append({"code": "relation-evidence-coverage-invalid", "context": context})
    return valid


def validate_round2_payload(jobs: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    if decisions.get("kind") != "round-2-relations-v2" or decisions.get("relation_jobs_sha256") != jobs.get("artifact_sha256"):
        errors.append({"code": "relation-round2-binding-invalid"})
    by_id = decision_map(decisions, "job_id")
    expected_jobs = {str(job["job_id"]) for job in jobs.get("jobs", [])}
    if set(by_id) != expected_jobs:
        errors.append({"code": "relation-round2-job-coverage-invalid", "missing": sorted(expected_jobs - set(by_id)), "extra": sorted(set(by_id) - expected_jobs)})
    atoms = {
        str(atom["atom_key"]): atom for atom in jobs.get("atoms", [])
        if isinstance(atom, dict) and isinstance(atom.get("atom_key"), str)
    }
    concepts = {str(item["proposal_id"]): item for item in jobs.get("concepts", [])}
    all_candidates = {str(item["candidate_id"]): item for job in jobs.get("jobs", []) for item in job.get("candidates", [])}
    merges: list[dict[str, Any]] = []
    concept_relations: list[dict[str, Any]] = []
    atom_relations: list[dict[str, Any]] = []
    reviewed_global: set[str] = set()
    for job in jobs.get("jobs", []):
        job_id = str(job["job_id"])
        decision = by_id.get(job_id)
        if decision is None:
            continue
        if decision.get("packet_sha256") != job.get("packet_sha256"):
            errors.append({"code": "relation-round2-packet-digest-mismatch", "job_id": job_id})
        expected_candidates = {str(item["candidate_id"]) for item in job.get("candidates", [])}
        reviewed = decision.get("reviewed_candidate_ids")
        if not isinstance(reviewed, list) or set(reviewed) != expected_candidates or len(reviewed) != len(set(reviewed)):
            errors.append({"code": "relation-candidate-review-coverage-invalid", "job_id": job_id})
        else:
            reviewed_global.update(str(value) for value in reviewed)
        for raw in decision.get("merge_decisions", []) if isinstance(decision.get("merge_decisions"), list) else []:
            candidate = all_candidates.get(str(raw.get("candidate_id"))) if isinstance(raw, dict) else None
            if candidate is None or candidate["kind"] != "concept-merge" or raw.get("action") not in {"merge", "keep-separate"}:
                errors.append({"code": "concept-merge-decision-invalid", "job_id": job_id})
                continue
            confidence = raw.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                errors.append({"code": "concept-merge-confidence-invalid", "candidate_id": candidate["candidate_id"]})
                confidence = 0.0
            rationale = raw.get("rationale")
            if not isinstance(rationale, str) or len(rationale.strip()) < 8:
                errors.append({"code": "concept-merge-rationale-invalid", "candidate_id": candidate["candidate_id"]})
            if raw.get("action") == "merge" and float(confidence) < float(jobs["relation_analysis"]["concept_merge_threshold"]):
                review.append({"code": "concept-merge-below-threshold", "candidate_id": candidate["candidate_id"]})
            merges.append({
                "candidate_id": candidate["candidate_id"], "left_ref": candidate["left_key"], "right_ref": candidate["right_key"],
                "action": str(raw["action"]), "confidence": float(confidence),
                "rationale": str(rationale).strip() if isinstance(rationale, str) else "",
            })
        for index, raw in enumerate(decision.get("concept_relations", []) if isinstance(decision.get("concept_relations"), list) else []):
            context = f"{job_id}:concept-relation:{index}"
            if not isinstance(raw, dict):
                errors.append({"code": "concept-relation-invalid", "context": context})
                continue
            candidate = all_candidates.get(str(raw.get("candidate_id")))
            left, right = str(raw.get("from_ref", "")), str(raw.get("to_ref", ""))
            relation_type, tier, evidence_kind = raw.get("type"), raw.get("tier"), raw.get("evidence_kind")
            if candidate is None or candidate["kind"] != "concept-relation" or {left, right} != {candidate["left_key"], candidate["right_key"]}:
                errors.append({"code": "concept-relation-candidate-invalid", "context": context})
            if left not in concepts or right not in concepts or left == right or relation_type not in CONCEPT_RELATION_TYPES or tier not in {"backbone", "supporting"} or evidence_kind not in {"explicit", "pedagogical-inference"}:
                errors.append({"code": "concept-relation-invalid", "context": context})
                continue
            if relation_type in SYMMETRIC_CONCEPT_RELATIONS and left > right:
                errors.append({"code": "concept-relation-symmetric-order-invalid", "context": context})
            rationale = raw.get("rationale")
            if not isinstance(rationale, str) or len(rationale.strip()) < 12:
                errors.append({"code": "relation-rationale-invalid", "context": context})
            confidence = validate_confidence(raw.get("confidence"), str(evidence_kind), jobs["relation_analysis"], context, errors, review)
            endpoint_atoms = {
                str(item["atom_key"])
                for concept_ref in (left, right)
                for item in jobs.get("atom_concept_links", [])
                if item.get("concept_ref") == concept_ref
            }
            evidence = validate_relation_evidence(raw.get("evidence"), atoms, endpoint_atoms, context, errors, False)
            if str(evidence_kind) == "pedagogical-inference":
                covered = {item["atom_key"] for item in evidence}
                left_atoms = {
                    str(item["atom_key"]) for item in jobs.get("atom_concept_links", [])
                    if item.get("concept_ref") == left
                }
                right_atoms = {
                    str(item["atom_key"]) for item in jobs.get("atom_concept_links", [])
                    if item.get("concept_ref") == right
                }
                if not (covered & left_atoms and covered & right_atoms):
                    errors.append({"code": "concept-relation-two-sided-evidence-missing", "context": context})
            concept_relations.append({
                "candidate_id": str(raw.get("candidate_id")), "from_ref": left, "to_ref": right,
                "type": str(relation_type), "tier": str(tier), "evidence_kind": str(evidence_kind),
                "evidence": evidence, "rationale": str(rationale).strip() if isinstance(rationale, str) else "", "confidence": confidence,
            })
        for index, raw in enumerate(decision.get("relations", []) if isinstance(decision.get("relations"), list) else []):
            context = f"{job_id}:atom-relation:{index}"
            if not isinstance(raw, dict):
                errors.append({"code": "atom-relation-invalid", "context": context})
                continue
            candidate = all_candidates.get(str(raw.get("candidate_id")))
            left, right = str(raw.get("from_key", "")), str(raw.get("to_key", ""))
            relation_type, tier, evidence_kind = raw.get("type"), raw.get("tier"), raw.get("evidence_kind")
            if candidate is None or candidate["kind"] != "atom-relation" or {left, right} != {candidate["left_key"], candidate["right_key"]}:
                errors.append({"code": "atom-relation-candidate-invalid", "context": context})
            if left not in atoms or right not in atoms or left == right or relation_type not in ATOM_RELATION_TYPES or tier not in {"backbone", "supporting"} or evidence_kind not in {"explicit", "pedagogical-inference"}:
                errors.append({"code": "atom-relation-invalid", "context": context})
                continue
            if relation_type in SYMMETRIC_ATOM_RELATIONS and left > right:
                errors.append({"code": "atom-relation-symmetric-order-invalid", "context": context})
            if tier == "backbone" and (relation_type not in {"prerequisite", "develops", "derives", "motivates"} or atoms[left]["category"] not in CORE_ATOM_CATEGORIES or atoms[right]["category"] not in CORE_ATOM_CATEGORIES):
                errors.append({"code": "atom-relation-backbone-invalid", "context": context})
            rationale = raw.get("rationale")
            if not isinstance(rationale, str) or len(rationale.strip()) < 12:
                errors.append({"code": "relation-rationale-invalid", "context": context})
            confidence = validate_confidence(raw.get("confidence"), str(evidence_kind), jobs["relation_analysis"], context, errors, review)
            evidence = validate_relation_evidence(raw.get("evidence"), atoms, {left, right}, context, errors, str(evidence_kind) == "pedagogical-inference")
            atom_relations.append({
                "candidate_id": str(raw.get("candidate_id")), "from_key": left, "to_key": right,
                "type": str(relation_type), "tier": str(tier), "evidence_kind": str(evidence_kind),
                "evidence": evidence, "rationale": str(rationale).strip() if isinstance(rationale, str) else "", "confidence": confidence,
                "basis_candidate_ids": [str(value) for value in raw.get("basis_candidate_ids", []) if isinstance(value, str)],
            })
    merge_candidate_ids = {key for key, item in all_candidates.items() if item["kind"] == "concept-merge"}
    decided_merge_ids = {item["candidate_id"] for item in merges}
    if decided_merge_ids != merge_candidate_ids:
        errors.append({"code": "concept-merge-review-coverage-invalid", "missing": sorted(merge_candidate_ids - decided_merge_ids), "extra": sorted(decided_merge_ids - merge_candidate_ids)})
    return {
        "schema_version": 2,
        "status": "failed" if errors else ("review_required" if review else "passed"),
        "errors": errors, "review_items": review, "reviewed_candidate_ids": sorted(reviewed_global),
        "merge_decisions": merges, "concept_relations": concept_relations, "relations": atom_relations,
    }


class UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def normalize_graph(
    concepts: list[dict[str, Any]], links: list[dict[str, Any]], merge_decisions: list[dict[str, Any]],
    concept_relations: list[dict[str, Any]], atom_relations: list[dict[str, Any]], atom_roles: list[dict[str, Any]],
    config: dict[str, Any], final_concepts: list[dict[str, Any]] | None = None,
    final_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    proposals = {str(item["proposal_id"]): item for item in concepts}
    if final_concepts is None:
        union = UnionFind(proposals)
        for decision in merge_decisions:
            if decision["action"] == "merge" and decision["confidence"] >= float(config["concept_merge_threshold"]):
                union.union(decision["left_ref"], decision["right_ref"])
        grouped: dict[str, list[str]] = defaultdict(list)
        for proposal in proposals:
            grouped[union.find(proposal)].append(proposal)
        concept_specs = []
        for members in grouped.values():
            ordered = sorted(members, key=lambda key: (min((item["source_range"][0] for item in proposals[key]["evidence"]), default=10**12), key))
            labels = [proposals[key]["preferred_label"] for key in ordered]
            preferred = min(labels, key=lambda value: (len(normalized(value)), labels.index(value)))
            kinds = [proposals[key]["kind"] for key in ordered]
            concept_specs.append({
                "member_proposal_ids": ordered, "preferred_label": preferred,
                "aliases": sorted({alias for key in ordered for alias in [proposals[key]["preferred_label"], *proposals[key].get("aliases", [])] if normalized(alias) != normalized(preferred)}),
                "definition": proposals[ordered[0]]["definition"], "kind": kinds[0],
            })
    else:
        concept_specs = final_concepts
    proposal_to_concept: dict[str, str] = {}
    canonical: list[dict[str, Any]] = []
    for raw in concept_specs:
        members = sorted({str(value) for value in raw.get("member_proposal_ids", [])})
        key = stable_key("concept", *members)
        evidence = sorted(
            {json.dumps(item, sort_keys=True): item for member in members for item in proposals[member].get("evidence", [])}.values(),
            key=lambda item: (item["source_range"][0], item["atom_key"]),
        )
        source_chapters = sorted({proposals[member]["chapter_key"] for member in members})
        first_order = min((item["source_range"][0] for item in evidence), default=0)
        canonical.append({
            "key": key, "preferred_label": str(raw["preferred_label"]).strip(),
            "aliases": sorted(set(str(value).strip() for value in raw.get("aliases", []) if str(value).strip() and normalized(str(value)) != normalized(str(raw["preferred_label"])))),
            "definition": str(raw["definition"]).strip(), "kind": str(raw["kind"]),
            "member_proposal_ids": members, "evidence": evidence,
            "source_chapters": source_chapters, "first_source_order": first_order,
        })
        for member in members:
            proposal_to_concept[member] = key
    canonical.sort(key=lambda item: (item["first_source_order"], item["key"]))
    normalized_links: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in final_links if final_links is not None else links:
        concept_ref = str(raw.get("concept_ref", ""))
        concept_key = proposal_to_concept.get(concept_ref, concept_ref if any(item["key"] == concept_ref for item in canonical) else "")
        if not concept_key:
            continue
        identity = str(raw["atom_key"]), concept_key, str(raw["role"])
        item = normalized_links.setdefault(identity, {
            "key": stable_key("atom-concept", *identity), "atom_key": identity[0], "concept_key": identity[1], "role": identity[2],
            "evidence_ranges": [], "confidence": float(raw.get("confidence", 0.0)),
        })
        item["confidence"] = max(item["confidence"], float(raw.get("confidence", 0.0)))
        item["evidence_ranges"] = sorted({tuple(value) for value in [*item["evidence_ranges"], *raw.get("evidence_ranges", [])]})
        item["evidence_ranges"] = [list(value) for value in item["evidence_ranges"]]
    normalized_concept_relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    candidate_to_key: dict[str, str] = {}
    for raw in concept_relations:
        left = proposal_to_concept.get(str(raw.get("from_ref", "")), str(raw.get("from_key", "")))
        right = proposal_to_concept.get(str(raw.get("to_ref", "")), str(raw.get("to_key", "")))
        relation_type = str(raw.get("type"))
        if not left or not right or left == right:
            continue
        if relation_type in SYMMETRIC_CONCEPT_RELATIONS and left > right:
            left, right = right, left
        identity = left, right, relation_type
        key = stable_key("concept-relation", *identity)
        candidate_to_key[str(raw.get("candidate_id", ""))] = key
        normalized_concept_relations[identity] = {
            "key": key, "from_key": left, "to_key": right, "type": relation_type,
            "tier": str(raw.get("tier")), "evidence_kind": str(raw.get("evidence_kind")),
            "evidence": list(raw.get("evidence", [])), "rationale": str(raw.get("rationale", "")),
            "confidence": float(raw.get("confidence", 0.0)),
            "candidate_sources": [str(raw.get("candidate_id"))] if raw.get("candidate_id") else [],
        }
    normalized_atom_relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in atom_relations:
        left, right, relation_type = str(raw["from_key"]), str(raw["to_key"]), str(raw["type"])
        if relation_type in SYMMETRIC_ATOM_RELATIONS and left > right:
            left, right = right, left
        identity = left, right, relation_type
        normalized_atom_relations[identity] = {
            "key": stable_key("relation", *identity), "from_key": left, "to_key": right,
            "type": relation_type, "tier": str(raw["tier"]), "evidence_kind": str(raw["evidence_kind"]),
            "evidence_ranges": [{"node_key": item["atom_key"], "source_range": item["source_range"]} for item in raw.get("evidence", [])],
            "rationale": str(raw["rationale"]), "confidence": float(raw["confidence"]),
            "basis_keys": sorted({candidate_to_key[value] for value in raw.get("basis_candidate_ids", []) if value in candidate_to_key}),
            "candidate_sources": [str(raw.get("candidate_id"))] if raw.get("candidate_id") else ["audit-added"],
        }
    return {
        "concepts": canonical,
        "atom_concept_links": sorted(normalized_links.values(), key=lambda item: (item["atom_key"], item["concept_key"], item["role"])),
        "concept_relations": sorted(normalized_concept_relations.values(), key=lambda item: (item["from_key"], item["to_key"], item["type"])),
        "relations": sorted(normalized_atom_relations.values(), key=lambda item: (item["from_key"], item["to_key"], item["type"])),
        "atom_roles": atom_roles,
        "proposal_to_concept": proposal_to_concept,
    }


def cycle_members(edges: Iterable[tuple[str, str]]) -> list[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for left, right in edges:
        graph[left].append(right)
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
            visit(child)
            if child in found:
                found.add(key)
        visiting.remove(key)
        visited.add(key)

    for key in list(graph):
        visit(key)
    return sorted(found)


def components(keys: Iterable[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = {key: set() for key in keys}
    for left, right in edges:
        if left in adjacency and right in adjacency:
            adjacency[left].add(right)
            adjacency[right].add(left)
    result: list[list[str]] = []
    remaining = set(adjacency)
    while remaining:
        start = min(remaining)
        queue = deque([start])
        found: set[str] = set()
        while queue:
            key = queue.popleft()
            if key in found:
                continue
            found.add(key)
            queue.extend(adjacency[key] - found)
        remaining -= found
        result.append(sorted(found))
    return sorted(result, key=lambda item: (-len(item), item))


def has_alternate_path(edges: list[tuple[str, str]], source: str, target: str, skipped: tuple[str, str]) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge != skipped:
            graph[edge[0]].append(edge[1])
    queue = deque([source])
    visited: set[str] = set()
    while queue:
        key = queue.popleft()
        if key == target:
            return True
        if key in visited:
            continue
        visited.add(key)
        queue.extend(graph.get(key, []))
    return False


def graph_issues(graph: dict[str, Any], atoms: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[list[str]]]:
    issues: list[dict[str, Any]] = []
    concept_keys = {item["key"] for item in graph["concepts"]}
    links_by_atom: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in graph["atom_concept_links"]:
        links_by_atom[link["atom_key"]].append(link)
    for atom_key, atom in atoms.items():
        roles = {item["role"] for item in links_by_atom.get(atom_key, [])}
        category = atom["category"]
        allowed = {
            "knowledge": PRODUCER_ROLES,
            "scenario": {"triggered_by", "motivates", "introduces", "explains"},
            "worked-example": {"illustrates", "applies", "derives", "assumes"},
            "exercise": {"practices", "applies", "assumes"},
        }[category]
        if not roles.intersection(allowed):
            issues.append({"code": "atom-concept-role-orphan", "atom_key": atom_key, "category": category})
    grounded = {link["concept_key"] for link in graph["atom_concept_links"]}
    for concept in concept_keys - grounded:
        issues.append({"code": "ungrounded-concept", "concept_key": concept})
    concept_edges = [(item["from_key"], item["to_key"]) for item in graph["concept_relations"]]
    backbone_edges = [(item["from_key"], item["to_key"]) for item in graph["concept_relations"] if item["tier"] == "backbone" and item["type"] in {"prerequisite", "develops", "derives"}]
    cycle = cycle_members(backbone_edges)
    if cycle:
        issues.append({"code": "concept-backbone-cycle", "concept_keys": cycle})
    structural_cycle = cycle_members((item["from_key"], item["to_key"]) for item in graph["concept_relations"] if item["type"] in {"broader", "part_of"})
    if structural_cycle:
        issues.append({"code": "concept-structure-cycle", "concept_keys": structural_cycle})
    for relation in graph["concept_relations"]:
        edge = relation["from_key"], relation["to_key"]
        if relation["type"] in {"prerequisite", "develops", "derives"} and has_alternate_path(backbone_edges, edge[0], edge[1], edge):
            issues.append({"code": "concept-transitive-redundancy", "relation_key": relation["key"], "evidence_kind": relation["evidence_kind"]})
    orders = {item["key"]: int(item["first_source_order"]) for item in graph["concepts"]}
    for relation in graph["concept_relations"]:
        if relation["tier"] == "backbone" and relation["type"] in {"prerequisite", "develops", "derives"} and orders[relation["from_key"]] > orders[relation["to_key"]]:
            issues.append({"code": "backward-learning-relation", "relation_key": relation["key"]})
    atom_backbone = [(item["from_key"], item["to_key"]) for item in graph["relations"] if item["tier"] == "backbone"]
    atom_cycle = cycle_members(atom_backbone)
    if atom_cycle:
        issues.append({"code": "atom-backbone-cycle", "atom_keys": atom_cycle})
    wcc = components(concept_keys, concept_edges)
    for component in wcc[1:]:
        issues.append({"code": "non-main-concept-component", "concept_keys": component})
    for index, issue in enumerate(issues, start=1):
        issue["issue_id"] = f"issue-{index:04d}-{stable_key('i', json.dumps(issue, sort_keys=True))[-8:]}"
    return issues, wcc


def prepare_audit_jobs(relation_jobs: dict[str, Any], round2: dict[str, Any]) -> dict[str, Any]:
    report = validate_round2_payload(relation_jobs, round2)
    if report["errors"]:
        raise RelationV2Error(f"Round-two relations are structurally invalid: {report['errors'][:5]}")
    graph = normalize_graph(
        relation_jobs["concepts"], relation_jobs["atom_concept_links"], report["merge_decisions"],
        report["concept_relations"], report["relations"], relation_jobs["atom_roles"], relation_jobs["relation_analysis"],
    )
    atoms = {str(atom["atom_key"]): atom for atom in relation_jobs.get("atoms", [])}
    issues, wcc = graph_issues(graph, atoms)
    audit = {
        "audit_id": "graph-audit-global",
        "atoms": sorted(atoms.values(), key=lambda item: (item["source_range"][0], item["atom_key"])),
        "proposal_concepts": relation_jobs["concepts"],
        "draft_concepts": graph["concepts"],
        "draft_atom_concept_links": graph["atom_concept_links"],
        "draft_concept_relations": graph["concept_relations"],
        "draft_relations": graph["relations"],
        "atom_roles": relation_jobs["atom_roles"],
        "merge_decisions": report["merge_decisions"],
        "issues": issues,
        "wcc": wcc,
    }
    audit["packet_sha256"] = packet_digest(audit)
    return seal_artifact({
        "schema_version": 2, "kind": "graph-audit-jobs",
        "relation_jobs_sha256": relation_jobs["artifact_sha256"],
        "round_2_relations_sha256": round2["artifact_sha256"],
        "manifest": relation_jobs["manifest"], "manifest_sha256": relation_jobs["manifest_sha256"],
        "source_markdown_sha256": relation_jobs["source_markdown_sha256"],
        "relation_analysis": relation_jobs["relation_analysis"],
        "audits": [audit],
    })


def validate_final_concepts(raw: Any, proposal_keys: set[str], errors: list[dict[str, Any]], review: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = raw if isinstance(raw, list) else []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        context = f"final-concept:{index}"
        if not isinstance(item, dict):
            errors.append({"code": "final-concept-invalid", "context": context})
            continue
        members = item.get("member_proposal_ids")
        label = str(item.get("preferred_label", "")).strip()
        if not isinstance(members, list) or not members or not set(members).issubset(proposal_keys) or seen.intersection(members):
            errors.append({"code": "final-concept-members-invalid", "context": context})
            continue
        seen.update(str(value) for value in members)
        issue = label_issue(label)
        if issue:
            review.append({"code": issue, "context": context, "label": label})
        if item.get("kind") not in CONCEPT_KINDS or not isinstance(item.get("definition"), str) or len(item["definition"].strip()) < 8:
            errors.append({"code": "final-concept-description-invalid", "context": context})
        aliases = item.get("aliases")
        if not isinstance(aliases, list) or not all(isinstance(value, str) and value.strip() for value in aliases):
            errors.append({"code": "final-concept-aliases-invalid", "context": context})
            aliases = []
        result.append({
            "member_proposal_ids": [str(value) for value in members], "preferred_label": label,
            "aliases": [str(value).strip() for value in aliases], "definition": str(item.get("definition", "")).strip(),
            "kind": str(item.get("kind")),
        })
    if seen != proposal_keys:
        errors.append({"code": "final-concept-proposal-coverage-invalid", "missing": sorted(proposal_keys - seen), "extra": sorted(seen - proposal_keys)})
    return result


def validate_final_links(raw: Any, atoms: dict[str, dict[str, Any]], proposal_to_group: dict[str, int], config: dict[str, Any], errors: list[dict[str, Any]], review: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = raw if isinstance(raw, list) else []
    result = []
    for index, item in enumerate(values):
        context = f"final-link:{index}"
        if not isinstance(item, dict) or item.get("atom_key") not in atoms or item.get("concept_ref") not in proposal_to_group or item.get("role") not in ATOM_CONCEPT_ROLES:
            errors.append({"code": "final-atom-concept-link-invalid", "context": context})
            continue
        atom = atoms[str(item["atom_key"])]
        ranges = item.get("evidence_ranges")
        if not isinstance(ranges, list) or not ranges or not all(valid_range(value, atom) for value in ranges):
            errors.append({"code": "final-atom-concept-evidence-invalid", "context": context})
            ranges = []
        confidence = validate_confidence(item.get("confidence"), "pedagogical-inference", config, context, errors, review)
        result.append({"atom_key": str(item["atom_key"]), "concept_ref": str(item["concept_ref"]), "role": str(item["role"]), "evidence_ranges": [list(value) for value in ranges], "confidence": confidence})
    return result


def validate_final_relation(raw: Any, index: int, atoms: dict[str, dict[str, Any]], proposal_keys: set[str], config: dict[str, Any], concept: bool, errors: list[dict[str, Any]], review: list[dict[str, Any]]) -> dict[str, Any] | None:
    context = f"final-{'concept' if concept else 'atom'}-relation:{index}"
    if not isinstance(raw, dict):
        errors.append({"code": "final-relation-invalid", "context": context})
        return None
    left_field, right_field = ("from_ref", "to_ref") if concept else ("from_key", "to_key")
    left, right = str(raw.get(left_field, "")), str(raw.get(right_field, ""))
    keys = proposal_keys if concept else set(atoms)
    relation_types = CONCEPT_RELATION_TYPES if concept else ATOM_RELATION_TYPES
    symmetric = SYMMETRIC_CONCEPT_RELATIONS if concept else SYMMETRIC_ATOM_RELATIONS
    if left not in keys or right not in keys or left == right or raw.get("type") not in relation_types or raw.get("tier") not in {"backbone", "supporting"} or raw.get("evidence_kind") not in {"explicit", "pedagogical-inference"}:
        errors.append({"code": "final-relation-invalid", "context": context})
        return None
    if raw["type"] in symmetric and left > right:
        errors.append({"code": "final-relation-symmetric-order-invalid", "context": context})
    if not concept and raw["tier"] == "backbone" and (raw["type"] not in {"prerequisite", "develops", "derives", "motivates"} or atoms[left]["category"] not in CORE_ATOM_CATEGORIES or atoms[right]["category"] not in CORE_ATOM_CATEGORIES):
        errors.append({"code": "final-atom-backbone-invalid", "context": context})
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or len(rationale.strip()) < 12:
        errors.append({"code": "relation-rationale-invalid", "context": context})
    evidence_kind = str(raw["evidence_kind"])
    confidence = validate_confidence(raw.get("confidence"), evidence_kind, config, context, errors, review)
    endpoints = set() if concept else {left, right}
    evidence = validate_relation_evidence(raw.get("evidence"), atoms, endpoints, context, errors, evidence_kind == "pedagogical-inference")
    result = {
        left_field: left, right_field: right, "type": str(raw["type"]), "tier": str(raw["tier"]),
        "evidence_kind": evidence_kind, "evidence": evidence,
        "rationale": str(rationale).strip() if isinstance(rationale, str) else "", "confidence": confidence,
        "candidate_id": str(raw.get("candidate_id", "")),
    }
    if not concept:
        result["basis_candidate_ids"] = [str(value) for value in raw.get("basis_candidate_ids", []) if isinstance(value, str)]
    return result


def quality_report(graph: dict[str, Any], atoms: dict[str, dict[str, Any]], candidates: list[dict[str, Any]], reviewed_ids: set[str], wcc: list[list[str]], queue: list[dict[str, Any]]) -> dict[str, Any]:
    channels: dict[str, int] = defaultdict(int)
    hard = 0
    for candidate in candidates:
        hard += int(bool(candidate.get("hard")))
        for channel in candidate.get("channels", []):
            channels[str(channel)] += 1
    relation_types: dict[str, int] = defaultdict(int)
    for relation in [*graph["concept_relations"], *graph["relations"]]:
        relation_types[str(relation["type"])] += 1
    return {
        "schema_version": 1, "kind": "relation-quality-report",
        "status": "passed" if not queue else "review_required",
        "counts": {
            "atoms": len(atoms), "concepts": len(graph["concepts"]),
            "atom_concept_links": len(graph["atom_concept_links"]),
            "concept_relations": len(graph["concept_relations"]), "relations": len(graph["relations"]),
            "candidates": len(candidates), "hard_candidates": hard,
            "reviewed_candidates": len(reviewed_ids), "components": len(wcc),
            "isolated_concepts": sum(len(item) == 1 for item in wcc), "unresolved": len(queue),
        },
        "candidate_channels": dict(sorted(channels.items())),
        "relation_types": dict(sorted(relation_types.items())),
        "component_sizes": [len(item) for item in wcc],
    }


def review_markdown(final: dict[str, Any], quality: dict[str, Any], queue: dict[str, Any]) -> str:
    counts = quality["counts"]
    lines = [
        "# 知识关系审核报告", "",
        f"- 状态：`{final['status']}`",
        f"- 规范概念：{counts['concepts']}",
        f"- 原子—概念映射：{counts['atom_concept_links']}",
        f"- 概念关系：{counts['concept_relations']}",
        f"- 原子投影关系：{counts['relations']}",
        f"- 连通分量：{counts['components']}",
        f"- 未解决项：{counts['unresolved']}", "",
        "## 候选召回渠道", "",
    ]
    lines.extend(f"- `{key}`：{value}" for key, value in quality["candidate_channels"].items())
    lines.extend(["", "## 复核队列", ""])
    if queue["items"]:
        for item in queue["items"]:
            lines.append(f"- `{item.get('code')}`：`{item.get('issue_id', item.get('context', ''))}`")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def finalize_relations(
    concept_jobs: dict[str, Any], round1: dict[str, Any], relation_jobs: dict[str, Any], round2: dict[str, Any],
    audit_jobs: dict[str, Any], round3: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    concept_report = validate_concept_payload(concept_jobs, round1)
    round2_report = validate_round2_payload(relation_jobs, round2)
    errors.extend(concept_report["errors"])
    errors.extend(round2_report["errors"])
    review.extend(concept_report["review_items"])
    review.extend(round2_report["review_items"])
    if relation_jobs.get("concept_jobs_sha256") != concept_jobs.get("artifact_sha256") or relation_jobs.get("round_1_concepts_sha256") != round1.get("artifact_sha256"):
        errors.append({"code": "relation-artifact-chain-invalid"})
    if audit_jobs.get("relation_jobs_sha256") != relation_jobs.get("artifact_sha256") or audit_jobs.get("round_2_relations_sha256") != round2.get("artifact_sha256"):
        errors.append({"code": "audit-artifact-chain-invalid"})
    if round3.get("kind") != "round-3-audit" or round3.get("graph_audit_jobs_sha256") != audit_jobs.get("artifact_sha256"):
        errors.append({"code": "round3-binding-invalid"})
    audit = audit_jobs.get("audits", [{}])[0]
    decisions = decision_map(round3, "audit_id")
    decision = decisions.get(str(audit.get("audit_id")))
    if decision is None or set(decisions) != {str(audit.get("audit_id"))}:
        errors.append({"code": "round3-audit-coverage-invalid"})
        decision = {}
    if decision.get("packet_sha256") != audit.get("packet_sha256"):
        errors.append({"code": "round3-packet-digest-mismatch"})
    expected_issue_ids = {str(item["issue_id"]) for item in audit.get("issues", [])}
    reviewed_issue_ids = decision.get("reviewed_issue_ids")
    if not isinstance(reviewed_issue_ids, list) or set(reviewed_issue_ids) != expected_issue_ids or len(reviewed_issue_ids) != len(set(reviewed_issue_ids)):
        errors.append({"code": "round3-issue-review-coverage-invalid"})
    atoms = atom_records(concept_jobs)
    proposal_keys = {str(item["proposal_id"]) for item in concept_report["concepts"]}
    final_concepts = validate_final_concepts(decision.get("concepts"), proposal_keys, errors, review)
    proposal_to_group = {proposal: index for index, concept in enumerate(final_concepts) for proposal in concept["member_proposal_ids"]}
    final_links = validate_final_links(decision.get("atom_concept_links"), atoms, proposal_to_group, concept_jobs["relation_analysis"], errors, review)
    final_concept_relations = [
        value for index, raw in enumerate(decision.get("concept_relations", []) if isinstance(decision.get("concept_relations"), list) else [])
        if (value := validate_final_relation(raw, index, atoms, proposal_keys, concept_jobs["relation_analysis"], True, errors, review)) is not None
    ]
    evidence_atoms_by_proposal = {
        str(item["proposal_id"]): {str(evidence["atom_key"]) for evidence in item.get("evidence", [])}
        for item in concept_report["concepts"]
    }
    for index, relation in enumerate(final_concept_relations):
        if relation["evidence_kind"] != "pedagogical-inference":
            continue
        covered = {str(item["atom_key"]) for item in relation["evidence"]}
        if not (
            covered & evidence_atoms_by_proposal.get(relation["from_ref"], set())
            and covered & evidence_atoms_by_proposal.get(relation["to_ref"], set())
        ):
            errors.append({"code": "final-concept-relation-two-sided-evidence-missing", "context": f"final-concept-relation:{index}"})
    final_atom_relations = [
        value for index, raw in enumerate(decision.get("relations", []) if isinstance(decision.get("relations"), list) else [])
        if (value := validate_final_relation(raw, index, atoms, proposal_keys, concept_jobs["relation_analysis"], False, errors, review)) is not None
    ]
    graph = normalize_graph(
        concept_report["concepts"], concept_report["atom_concept_links"], round2_report["merge_decisions"],
        final_concept_relations, final_atom_relations, concept_report["atom_roles"], concept_jobs["relation_analysis"],
        final_concepts=final_concepts, final_links=final_links,
    )
    issues, wcc = graph_issues(graph, atoms)
    independent_atoms = {
        str(item.get("atom_key")): str(item.get("reason", "")).strip()
        for item in decision.get("independent_atoms", []) if isinstance(item, dict) and item.get("atom_key") in atoms and len(str(item.get("reason", "")).strip()) >= 12
    }
    independent_components = [
        {"concept_keys": sorted(str(value) for value in item.get("concept_keys", [])), "reason": str(item.get("reason", "")).strip()}
        for item in decision.get("independent_components", []) if isinstance(item, dict) and len(str(item.get("reason", "")).strip()) >= 12
    ]
    explained_component_sets = {tuple(item["concept_keys"]) for item in independent_components}
    for issue in issues:
        if issue["code"] == "atom-concept-role-orphan" and issue.get("atom_key") in independent_atoms:
            continue
        if issue["code"] == "non-main-concept-component" and tuple(issue["concept_keys"]) in explained_component_sets:
            continue
        if issue["code"] == "concept-transitive-redundancy" and issue.get("evidence_kind") == "explicit":
            continue
        review.append(issue)
    unresolved = [*errors, *review]
    candidates = [item for job in relation_jobs.get("jobs", []) for item in job.get("candidates", [])]
    quality = quality_report(graph, atoms, candidates, set(round2_report["reviewed_candidate_ids"]), wcc, unresolved)
    final = seal_artifact({
        "schema_version": 2, "kind": "relation-final-v2",
        "status": "failed" if errors else ("review_required" if review else "passed"),
        "manifest": concept_jobs["manifest"], "manifest_sha256": concept_jobs["manifest_sha256"],
        "source_markdown_sha256": concept_jobs["source_markdown_sha256"],
        "relation_analysis": concept_jobs["relation_analysis"],
        "bindings": {
            "concept_jobs": {"path": concept_jobs.get("_path"), "sha256": concept_jobs["artifact_sha256"]},
            "round_1_concepts": {"path": round1.get("_path"), "sha256": round1["artifact_sha256"]},
            "relation_jobs": {"path": relation_jobs.get("_path"), "sha256": relation_jobs["artifact_sha256"]},
            "round_2_relations": {"path": round2.get("_path"), "sha256": round2["artifact_sha256"]},
            "graph_audit_jobs": {"path": audit_jobs.get("_path"), "sha256": audit_jobs["artifact_sha256"]},
            "round_3_audit": {"path": round3.get("_path"), "sha256": round3["artifact_sha256"]},
        },
        "reviewer": {
            "concepts": round1.get("reviewer", {}), "relations": round2.get("reviewer", {}), "audit": round3.get("reviewer", {}),
        },
        "concepts": graph["concepts"], "atom_concept_links": graph["atom_concept_links"],
        "concept_relations": graph["concept_relations"], "relations": graph["relations"],
        "atom_roles": graph["atom_roles"],
        "independent_atoms": [{"atom_key": key, "reason": independent_atoms[key]} for key in sorted(independent_atoms)],
        "independent_components": independent_components,
        "unresolved_count": len(unresolved),
    })
    queue = seal_artifact({
        "schema_version": 2, "kind": "relation-review-queue-v2",
        "status": "passed" if not unresolved else "review_required",
        "relation_final_sha256": final["artifact_sha256"], "items": unresolved,
        "unresolved_count": len(unresolved),
    })
    quality["relation_final_sha256"] = final["artifact_sha256"]
    quality = seal_artifact(quality)
    return final, queue, quality, review_markdown(final, quality, queue)


def apply_relation_final(manifest_path: Path, final_path: Path, output_path: Path, profile_output: Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    manifest_path, final_path, output_path = (path.expanduser().resolve() for path in (manifest_path, final_path, output_path))
    manifest = load_json(manifest_path)
    final = load_tagged(final_path, "relation-final-v2")
    if final.get("status") != "passed" or final.get("unresolved_count") != 0:
        raise RelationV2Error("Only a passed v2 relation final can be applied")
    if final.get("manifest_sha256") != sha256_file(manifest_path) or final.get("source_markdown_sha256") != manifest.get("source_markdown_sha256"):
        raise RelationV2Error("Relation final is stale for this manifest")
    result = dict(manifest)
    result["concepts"] = final["concepts"]
    result["atom_concept_links"] = final["atom_concept_links"]
    result["concept_relations"] = final["concept_relations"]
    result["relations"] = final["relations"]
    featured = sorted(
        item["atom_key"] for item in final.get("atom_roles", []) if item.get("role") == "bridge"
    )
    result["relation_review"] = {
        "status": "passed", "mode": "llm-three-pass", "graph_model": "atom-concept-dual-layer",
        "final_artifact": {"path": str(final_path), "sha256": final["artifact_sha256"]},
        "bindings": final["bindings"], "reviewer": final["reviewer"],
        "featured_example_keys": featured, "unresolved_count": 0,
    }
    profile_path = Path(str(manifest["profile"])).expanduser().resolve()
    profile = load_json(profile_path)
    profile["relation_analysis"] = dict(final["relation_analysis"])
    if profile_output is not None:
        profile_output = profile_output.expanduser().resolve()
        atomic_json(profile_output, profile, overwrite=overwrite)
        result["profile"] = str(profile_output)
        result["source_sha256"] = profile.get("source", {}).get("sha256")
    atomic_json(output_path, result, overwrite=overwrite)
    return {
        "status": "passed", "manifest": str(output_path), "profile": result["profile"],
        "concepts": len(result["concepts"]), "atom_concept_links": len(result["atom_concept_links"]),
        "concept_relations": len(result["concept_relations"]), "relations": len(result["relations"]),
        "relation_final_sha256": final["artifact_sha256"],
    }

#!/usr/bin/env python3
"""Run one knowledge-relation phase through Responses Structured Outputs."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from knowledge_relations import (
    ATOM_CONCEPT_ROLES,
    ATOM_RELATION_TYPES,
    CONCEPT_KINDS,
    CONCEPT_RELATION_TYPES,
    atomic_json,
    load_json,
    load_tagged,
    seal_artifact,
)


RESPONSES_URL = "https://api.openai.com/v1/responses"


class RelationModelError(RuntimeError):
    pass


RANGE = {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 2, "maxItems": 2}
EVIDENCE = {
    "type": "object", "additionalProperties": False,
    "properties": {"atom_key": {"type": "string"}, "source_range": RANGE},
    "required": ["atom_key", "source_range"],
}
CONCEPT_SPEC = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "proposal_id": {"type": "string"}, "preferred_label": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "definition": {"type": "string"}, "kind": {"type": "string", "enum": sorted(CONCEPT_KINDS)},
        "evidence": {"type": "array", "minItems": 1, "items": EVIDENCE},
    },
    "required": ["proposal_id", "preferred_label", "aliases", "definition", "kind", "evidence"],
}
ATOM_CONCEPT_LINK = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "atom_key": {"type": "string"}, "concept_ref": {"type": "string"},
        "role": {"type": "string", "enum": sorted(ATOM_CONCEPT_ROLES)},
        "evidence_ranges": {"type": "array", "minItems": 1, "items": RANGE},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["atom_key", "concept_ref", "role", "evidence_ranges", "confidence"],
}
ATOM_ROLE = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "atom_key": {"type": "string"}, "role": {"type": "string", "enum": ["core", "bridge", "satellite"]},
        "rationale": {"type": "string"},
    },
    "required": ["atom_key", "role", "rationale"],
}
MERGE_DECISION = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "candidate_id": {"type": "string"}, "action": {"type": "string", "enum": ["merge", "keep-separate"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "rationale": {"type": "string"},
    },
    "required": ["candidate_id", "action", "confidence", "rationale"],
}
CONCEPT_RELATION = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "candidate_id": {"type": "string"}, "from_ref": {"type": "string"}, "to_ref": {"type": "string"},
        "type": {"type": "string", "enum": sorted(CONCEPT_RELATION_TYPES)},
        "tier": {"type": "string", "enum": ["backbone", "supporting"]},
        "evidence_kind": {"type": "string", "enum": ["explicit", "pedagogical-inference"]},
        "evidence": {"type": "array", "minItems": 1, "items": EVIDENCE},
        "rationale": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["candidate_id", "from_ref", "to_ref", "type", "tier", "evidence_kind", "evidence", "rationale", "confidence"],
}
ATOM_RELATION = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "candidate_id": {"type": "string"}, "from_key": {"type": "string"}, "to_key": {"type": "string"},
        "type": {"type": "string", "enum": sorted(ATOM_RELATION_TYPES)},
        "tier": {"type": "string", "enum": ["backbone", "supporting"]},
        "evidence_kind": {"type": "string", "enum": ["explicit", "pedagogical-inference"]},
        "evidence": {"type": "array", "minItems": 1, "items": EVIDENCE},
        "rationale": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "basis_candidate_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["candidate_id", "from_key", "to_key", "type", "tier", "evidence_kind", "evidence", "rationale", "confidence", "basis_candidate_ids"],
}
FINAL_CONCEPT = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "member_proposal_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "preferred_label": {"type": "string"}, "aliases": {"type": "array", "items": {"type": "string"}},
        "definition": {"type": "string"}, "kind": {"type": "string", "enum": sorted(CONCEPT_KINDS)},
    },
    "required": ["member_proposal_ids", "preferred_label", "aliases", "definition", "kind"],
}
INDEPENDENT_ATOM = {
    "type": "object", "additionalProperties": False,
    "properties": {"atom_key": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["atom_key", "reason"],
}
INDEPENDENT_COMPONENT = {
    "type": "object", "additionalProperties": False,
    "properties": {"concept_keys": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
    "required": ["concept_keys", "reason"],
}


def schema(phase: str) -> dict[str, Any]:
    common: dict[str, Any] = {"type": "object", "additionalProperties": False}
    if phase == "concepts":
        return {**common, "properties": {
            "job_id": {"type": "string"}, "packet_sha256": {"type": "string"},
            "concepts": {"type": "array", "items": CONCEPT_SPEC},
            "atom_concept_links": {"type": "array", "items": ATOM_CONCEPT_LINK},
            "atom_roles": {"type": "array", "items": ATOM_ROLE},
        }, "required": ["job_id", "packet_sha256", "concepts", "atom_concept_links", "atom_roles"]}
    if phase == "relations":
        return {**common, "properties": {
            "job_id": {"type": "string"}, "packet_sha256": {"type": "string"},
            "reviewed_candidate_ids": {"type": "array", "items": {"type": "string"}},
            "merge_decisions": {"type": "array", "items": MERGE_DECISION},
            "concept_relations": {"type": "array", "items": CONCEPT_RELATION},
            "relations": {"type": "array", "items": ATOM_RELATION},
        }, "required": ["job_id", "packet_sha256", "reviewed_candidate_ids", "merge_decisions", "concept_relations", "relations"]}
    return {**common, "properties": {
        "audit_id": {"type": "string"}, "packet_sha256": {"type": "string"},
        "reviewed_issue_ids": {"type": "array", "items": {"type": "string"}},
        "concepts": {"type": "array", "items": FINAL_CONCEPT},
        "atom_concept_links": {"type": "array", "items": ATOM_CONCEPT_LINK},
        "concept_relations": {"type": "array", "items": CONCEPT_RELATION},
        "relations": {"type": "array", "items": ATOM_RELATION},
        "independent_atoms": {"type": "array", "items": INDEPENDENT_ATOM},
        "independent_components": {"type": "array", "items": INDEPENDENT_COMPONENT},
    }, "required": ["audit_id", "packet_sha256", "reviewed_issue_ids", "concepts", "atom_concept_links", "concept_relations", "relations", "independent_atoms", "independent_components"]}


def instructions(phase: str) -> str:
    shared = (
        "You are constructing an evidence-bound educational knowledge graph. Never rewrite source text. "
        "Every inference must cite exact source ranges. Prefer no relation over a vague relation. "
        "Learning relations point from prerequisite/trigger to the developed knowledge. "
    )
    if phase == "concepts":
        return shared + (
            "Extract reusable canonical concept proposals from each TextUnit-like atom. Do not use a whole problem, "
            "activity heading, truncated sentence, or exercise number as a concept name. Exercises may only map to "
            "concepts evidenced elsewhere in the packet/context. Classify every atom as core, bridge, or satellite; "
            "bridge is reserved for worked examples with a substantial reusable mathematical method."
        )
    if phase == "relations":
        return shared + (
            "Review every candidate ID. For atom and concept candidates decide relation, reverse relation, or no relation; "
            "absence from relation arrays means no relation. Return one merge decision for every concept-merge candidate. "
            "Pedagogical inferences require evidence from both endpoints. Keep the backbone acyclic."
        )
    return shared + (
        "Audit the complete graph. Review every issue ID, then return a complete replacement graph: correct merges, "
        "add/delete/reverse/retype edges, remove transitive inferred prerequisites, and connect unjustified components. "
        "Independent atoms/components require a concrete mathematical reason; 'unclear relation' is not sufficient."
    )


def default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise RelationModelError(f"Responses API returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RelationModelError(f"Responses API request failed: {error.reason}") from error


def extract_output(response: dict[str, Any]) -> dict[str, Any]:
    texts: list[str] = []
    if isinstance(response.get("output_text"), str):
        texts.append(response["output_text"])
    for item in response.get("output", []):
        if isinstance(item, dict):
            texts.extend(
                str(content["text"]) for content in item.get("content", [])
                if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str)
            )
    if not texts:
        raise RelationModelError("Responses API returned no output text")
    try:
        payload = json.loads("".join(texts))
    except json.JSONDecodeError as error:
        raise RelationModelError("Responses API output was not valid JSON") from error
    if not isinstance(payload, dict):
        raise RelationModelError("Structured output must be an object")
    return payload


def request_packet(packet: dict[str, Any], phase: str, model: str, api_key: str, timeout: float, transport: Callable[[urllib.request.Request, float], bytes] = default_transport) -> dict[str, Any]:
    body = {
        "model": model, "store": False, "instructions": instructions(phase),
        "input": json.dumps(packet, ensure_ascii=False, separators=(",", ":")),
        "text": {"format": {"type": "json_schema", "name": f"knowledge_relations_{phase}", "strict": True, "schema": schema(phase)}},
    }
    request = urllib.request.Request(
        RESPONSES_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        response = json.loads(transport(request, timeout).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RelationModelError("Responses API returned invalid JSON") from error
    if not isinstance(response, dict) or response.get("status") not in {None, "completed"}:
        raise RelationModelError("Responses API did not complete")
    return extract_output(response)


PHASES = {
    "concepts": ("concept-jobs", "jobs", "job_id", "round-1-concepts", "concept_jobs_sha256"),
    "relations": ("relation-jobs-v2", "jobs", "job_id", "round-2-relations-v2", "relation_jobs_sha256"),
    "audit": ("graph-audit-jobs", "audits", "audit_id", "round-3-audit", "graph_audit_jobs_sha256"),
}


def run_packets(input_path: Path, output_path: Path, phase: str, model: str, api_key: str, execute: bool, timeout: float = 120.0, transport: Callable[[urllib.request.Request, float], bytes] = default_transport) -> dict[str, Any]:
    if not execute:
        raise RelationModelError("External model calls require explicit --execute")
    if not model.strip():
        raise RelationModelError("--model is required and has no implicit default")
    if not api_key:
        raise RelationModelError("API key is missing")
    input_kind, packets_field, id_field, output_kind, binding = PHASES[phase]
    source = load_tagged(input_path, input_kind)
    packets = source[packets_field]
    completed: dict[str, dict[str, Any]] = {}
    output_path = output_path.expanduser().resolve()
    if output_path.exists():
        existing = load_json(output_path)
        if existing.get("kind") != output_kind or existing.get(binding) != source["artifact_sha256"] or existing.get("reviewer", {}).get("model") != model:
            raise RelationModelError("Existing output binds a different phase input or model")
        completed = {str(item.get(id_field)): item for item in existing.get("decisions", []) if isinstance(item, dict)}
    for packet in packets:
        packet_id = str(packet[id_field])
        if packet_id in completed:
            continue
        decision = request_packet(packet, phase, model, api_key, timeout, transport)
        if decision.get(id_field) != packet_id or decision.get("packet_sha256") != packet.get("packet_sha256"):
            raise RelationModelError(f"Model returned a wrong ID or stale digest for {packet_id}")
        completed[packet_id] = decision
        partial = seal_artifact({
            "schema_version": 2, "kind": output_kind, binding: source["artifact_sha256"],
            "reviewer": {"type": "openai-responses-api", "model": model}, "status": "incomplete",
            "decisions": [completed[str(item[id_field])] for item in packets if str(item[id_field]) in completed],
        })
        atomic_json(output_path, partial, overwrite=True)
    final = seal_artifact({
        "schema_version": 2, "kind": output_kind, binding: source["artifact_sha256"],
        "reviewer": {"type": "openai-responses-api", "model": model}, "status": "complete",
        "decisions": [completed[str(item[id_field])] for item in packets],
    })
    atomic_json(output_path, final, overwrite=True)
    return {"status": "complete", "output": str(output_path), "model": model, "packets": len(packets), "artifact_sha256": final["artifact_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    try:
        report, code = run_packets(args.input, args.output, args.phase, args.model, os.environ.get(args.api_key_env, ""), args.execute, args.timeout), 0
    except Exception as error:
        report, code = {"status": "failed", "error": f"{type(error).__name__}: {error}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

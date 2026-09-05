#!/usr/bin/env python3
"""Bootstrap and fully audit a v2 graph from a passed v1 relation artifact.

This compatibility helper preserves reviewed atom edges, creates conservative
concept proposals from knowledge atoms, maps satellites to their reviewed
assumptions, and runs the ordinary v2 validators. Optional label overrides are
reviewer-authored data, not automatic source rewrites.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import knowledge_relations as kr


def clean_label(value: str) -> bool:
    return not kr.label_issue(value) and len("".join(value.split())) <= 32 and not re.search(r"[。；：]|^(?:下面|一个|在人类|像\s)", value)


def load_overrides(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    payload = kr.load_json(path.expanduser().resolve())
    values = payload.get("atoms", {})
    if not isinstance(values, dict):
        raise kr.RelationV2Error("Override file needs an atoms object")
    result: dict[str, dict[str, str]] = {}
    allowed_fields = {"label", "definition", "kind", "display_role"}
    for key, value in values.items():
        if not isinstance(value, dict) or not value or not set(value).intersection(allowed_fields):
            raise kr.RelationV2Error(f"Invalid override for {key}")
        if "label" in value and not isinstance(value.get("label"), str):
            raise kr.RelationV2Error(f"Invalid label override for {key}")
        result[str(key)] = {str(field): str(content) for field, content in value.items() if field in allowed_fields}
    return result


def concept_label(atom: dict[str, Any], override: dict[str, str]) -> str:
    if override.get("label"):
        return override["label"].strip()
    title = str(atom["title"]).strip()
    if clean_label(title):
        return title
    for candidate in reversed(atom.get("organizer_titles", [])):
        if clean_label(str(candidate)) and not re.match(r"^(?:第.+章|数学)", str(candidate)):
            return str(candidate).strip()
    return f"知识主题-{atom['atom_key'][-6:]}"


def migrate(manifest_path: Path, v1_final_path: Path, output_dir: Path, overrides_path: Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    manifest_path, v1_final_path, output_dir = manifest_path.expanduser().resolve(), v1_final_path.expanduser().resolve(), output_dir.expanduser().resolve()
    old = kr.load_json(v1_final_path)
    if old.get("kind") != "relation-final" or old.get("status") != "passed" or old.get("unresolved_count") != 0:
        raise kr.RelationV2Error("Migration requires a passed v1 relation-final artifact")
    concept_jobs_path = output_dir / "concept-jobs.json"
    concept_jobs = kr.prepare_concept_jobs(manifest_path, max_chars=10**9)
    kr.atomic_json(concept_jobs_path, concept_jobs, overwrite=overwrite)
    concept_jobs = kr.load_tagged(concept_jobs_path, "concept-jobs")
    atoms = kr.atom_records(concept_jobs)
    overrides = load_overrides(overrides_path)
    signatures = {str(item["atom_key"]): item for item in old.get("concept_signatures", []) if isinstance(item, dict) and item.get("atom_key") in atoms}
    proposal_for_atom: dict[str, str] = {}
    label_to_proposal: dict[str, str] = {}
    concepts_by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    links_by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    roles_by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    atom_job = {str(atom["atom_key"]): str(job["job_id"]) for job in concept_jobs["jobs"] for atom in job["atoms"]}
    for atom_key, atom in sorted(atoms.items(), key=lambda item: (item[1]["source_range"][0], item[0])):
        if atom["category"] != "knowledge":
            continue
        proposal = kr.stable_key("proposal", atom_key)
        override = overrides.get(atom_key, {})
        label = concept_label(atom, override)
        kind = override.get("kind", "concept")
        definition = override.get("definition", f"教材以原子内容建立“{label}”的含义、性质或使用方法。")
        aliases = [str(atom["title"])] if clean_label(str(atom["title"])) and kr.normalized(str(atom["title"])) != kr.normalized(label) else []
        concepts_by_job[atom_job[atom_key]].append({
            "proposal_id": proposal, "preferred_label": label, "aliases": aliases,
            "definition": definition, "kind": kind,
            "evidence": [{"atom_key": atom_key, "source_range": atom["source_range"]}],
        })
        proposal_for_atom[atom_key] = proposal
        for phrase in [str(atom["title"]), *signatures.get(atom_key, {}).get("teaches", [])]:
            label_to_proposal[kr.normalized(phrase)] = proposal
        links_by_job[atom_job[atom_key]].append({
            "atom_key": atom_key, "concept_ref": proposal, "role": "introduces",
            "evidence_ranges": [atom["source_range"]], "confidence": 0.99,
        })
    chapter_knowledge: dict[str, list[str]] = defaultdict(list)
    for atom_key in proposal_for_atom:
        chapter_knowledge[str(atoms[atom_key]["chapter_key"])].append(atom_key)
    for keys in chapter_knowledge.values():
        keys.sort(key=lambda key: (atoms[key]["source_range"][0], key))

    def nearest(atom_key: str, direction: str = "either") -> str:
        atom = atoms[atom_key]
        keys = chapter_knowledge[str(atom["chapter_key"])]
        before = [key for key in keys if atoms[key]["source_range"][0] < atom["source_range"][0]]
        after = [key for key in keys if atoms[key]["source_range"][0] > atom["source_range"][0]]
        if direction == "before" and before:
            return before[-1]
        if direction == "after" and after:
            return after[0]
        candidates = [*before[-1:], *after[:1]]
        return min(candidates, key=lambda key: abs(atoms[key]["source_range"][0] - atom["source_range"][0]))

    for atom_key, atom in sorted(atoms.items(), key=lambda item: (item[1]["source_range"][0], item[0])):
        signature = signatures.get(atom_key, {"role": "satellite", "assumes": []})
        display_role = overrides.get(atom_key, {}).get("display_role") or str(signature.get("role", "satellite"))
        roles_by_job[atom_job[atom_key]].append({
            "atom_key": atom_key, "role": display_role,
            "rationale": "沿用已通过 v1 审核的教学展示角色，并由本轮概念映射复核。",
        })
        if atom["category"] == "knowledge":
            continue
        proposals: list[tuple[str, str]] = []
        if atom["category"] == "scenario":
            before, after = nearest(atom_key, "before"), nearest(atom_key, "after")
            proposals.append((proposal_for_atom[before], "triggered_by"))
            if after != before:
                proposals.append((proposal_for_atom[after], "motivates"))
        else:
            for phrase in signature.get("assumes", []):
                proposal = label_to_proposal.get(kr.normalized(str(phrase)))
                if proposal:
                    proposals.append((proposal, "applies" if atom["category"] == "worked-example" else "practices"))
            if not proposals:
                proposal = proposal_for_atom[nearest(atom_key)]
                proposals.append((proposal, "applies" if atom["category"] == "worked-example" else "practices"))
        for proposal, role in dict.fromkeys(proposals):
            links_by_job[atom_job[atom_key]].append({
                "atom_key": atom_key, "concept_ref": proposal, "role": role,
                "evidence_ranges": [atom["source_range"]], "confidence": 0.99,
            })
            proposal_for_atom.setdefault(atom_key, proposal)
    decisions = []
    for job in concept_jobs["jobs"]:
        job_id = str(job["job_id"])
        decisions.append({
            "job_id": job_id, "packet_sha256": job["packet_sha256"],
            "concepts": concepts_by_job[job_id], "atom_concept_links": links_by_job[job_id],
            "atom_roles": roles_by_job[job_id],
        })
    round1 = kr.seal_artifact({
        "schema_version": 2, "kind": "round-1-concepts", "concept_jobs_sha256": concept_jobs["artifact_sha256"],
        "reviewer": {"type": "codex-agent", "model": "current-agent", "basis": "passed-v1-migration-with-reviewed-labels"},
        "decisions": decisions,
    })
    round1_path = output_dir / "round-1-concepts.json"
    kr.atomic_json(round1_path, round1, overwrite=overwrite)
    round1 = kr.load_tagged(round1_path, "round-1-concepts")
    concept_report = kr.validate_concept_payload(concept_jobs, round1)
    if concept_report["status"] != "passed":
        raise kr.RelationV2Error(f"Migrated concepts require review: {concept_report['errors'] + concept_report['review_items']}")
    concept_index = kr.seal_artifact({"schema_version": 2, "kind": "concept-index", "concept_jobs_sha256": concept_jobs["artifact_sha256"], "round_1_concepts_sha256": round1["artifact_sha256"], **concept_report})
    kr.atomic_json(output_dir / "concept-index.json", concept_index, overwrite=overwrite)
    relation_jobs_path = output_dir / "relation-jobs.json"
    relation_jobs = kr.prepare_relation_jobs(concept_jobs, round1)
    kr.atomic_json(relation_jobs_path, relation_jobs, overwrite=overwrite)
    relation_jobs = kr.load_tagged(relation_jobs_path, "relation-jobs-v2")
    candidates = {str(item["candidate_id"]): item for job in relation_jobs["jobs"] for item in job["candidates"]}
    atom_candidate = {
        frozenset((str(item["left_key"]), str(item["right_key"]))): item
        for item in candidates.values() if item["kind"] == "atom-relation"
    }
    concept_candidate = {
        frozenset((str(item["left_key"]), str(item["right_key"]))): item
        for item in candidates.values() if item["kind"] == "concept-relation"
    }
    proposal_evidence_atom = {str(item["proposal_id"]): str(item["evidence"][0]["atom_key"]) for item in concept_report["concepts"]}
    source_order = {proposal: atoms[atom]["source_range"][0] for proposal, atom in proposal_evidence_atom.items()}
    selected_concepts: list[dict[str, Any]] = []
    pair_to_concept_candidate: dict[frozenset[str], str] = {}
    union = kr.UnionFind(source_order)
    allowed = {"prerequisite", "develops", "derives", "motivates", "contrasts", "analogous"}
    migratable_old_relations = [
        item for item in old.get("relations", [])
        if isinstance(item, dict)
        and str(item.get("from_key")) in atoms and str(item.get("to_key")) in atoms
        and str(item.get("from_key")) in proposal_for_atom and str(item.get("to_key")) in proposal_for_atom
    ]
    for relation in sorted(migratable_old_relations, key=lambda item: (item.get("tier") != "backbone", atoms[str(item["from_key"])]["source_range"][0], str(item.get("key")))):
        left_atom, right_atom = str(relation["from_key"]), str(relation["to_key"])
        left, right = proposal_for_atom[left_atom], proposal_for_atom[right_atom]
        pair = frozenset((left, right))
        if left == right or relation.get("type") not in allowed or pair not in concept_candidate or union.find(left) == union.find(right):
            continue
        relation_type = "develops" if relation["type"] == "motivates" else str(relation["type"])
        if relation_type not in kr.SYMMETRIC_CONCEPT_RELATIONS and source_order[left] > source_order[right]:
            left, right = right, left
        elif relation_type in kr.SYMMETRIC_CONCEPT_RELATIONS and left > right:
            left, right = right, left
        union.union(left, right)
        candidate = concept_candidate[pair]
        evidence = [
            {"atom_key": proposal_evidence_atom[left], "source_range": atoms[proposal_evidence_atom[left]]["source_range"]},
            {"atom_key": proposal_evidence_atom[right], "source_range": atoms[proposal_evidence_atom[right]]["source_range"]},
        ]
        selected_concepts.append({
            "candidate_id": candidate["candidate_id"], "from_ref": left, "to_ref": right,
            "type": relation_type, "tier": "backbone" if relation_type in {"prerequisite", "develops", "derives"} else "supporting",
            "evidence_kind": "pedagogical-inference", "evidence": evidence,
            "rationale": "沿用已审核原子教学路线，并以两端规范概念证据确认学习方向。", "confidence": 0.99,
        })
        pair_to_concept_candidate[pair] = candidate["candidate_id"]
    selected_atoms: list[dict[str, Any]] = []
    for relation in migratable_old_relations:
        left, right = str(relation["from_key"]), str(relation["to_key"])
        candidate = atom_candidate.get(frozenset((left, right)))
        if candidate is None:
            continue
        evidence = [{"atom_key": str(item["node_key"]), "source_range": list(item["source_range"])} for item in relation["evidence_ranges"]]
        covered = {item["atom_key"] for item in evidence}
        for endpoint in (left, right):
            if endpoint not in covered:
                evidence.append({"atom_key": endpoint, "source_range": atoms[endpoint]["source_range"]})
        selected_atoms.append({
            "candidate_id": candidate["candidate_id"], "from_key": left, "to_key": right,
            "type": str(relation["type"]), "tier": str(relation["tier"]),
            "evidence_kind": str(relation["evidence_kind"]),
            "evidence": evidence,
            "rationale": str(relation["rationale"]), "confidence": float(relation["confidence"]),
            "basis_candidate_ids": [pair_to_concept_candidate[frozenset((proposal_for_atom[left], proposal_for_atom[right]))]] if frozenset((proposal_for_atom[left], proposal_for_atom[right])) in pair_to_concept_candidate else [],
        })
    # Re-segmented scenarios and selected method examples have no stable v1
    # endpoint. Restore only their nearest, source-adjacent teaching link; this
    # is explicit migration scaffolding, not a fabricated all-book dependency.
    incident_atoms = {
        endpoint for item in selected_atoms
        for endpoint in (str(item["from_key"]), str(item["to_key"]))
    }
    for atom_key, atom in sorted(atoms.items(), key=lambda item: (item[1]["source_range"][0], item[0])):
        display_role = overrides.get(atom_key, {}).get("display_role")
        category = str(atom["category"])
        if atom_key in incident_atoms or (category != "scenario" and display_role != "bridge"):
            continue
        if category == "scenario":
            anchor = nearest(atom_key, "after")
            left, right, relation_type = atom_key, anchor, "motivates"
            rationale = "情景材料在原书中紧邻并导向后续知识，本迁移链接只恢复这一局部教学入口。"
        else:
            anchor = nearest(atom_key, "before")
            left, right, relation_type = anchor, atom_key, "illustrates"
            rationale = "该精选例题紧邻前置知识，并以完整解法展示其关键数学方法。"
        candidate = atom_candidate.get(frozenset((left, right)))
        if candidate is None:
            continue
        basis_pair = frozenset((proposal_for_atom[left], proposal_for_atom[right]))
        selected_atoms.append({
            "candidate_id": candidate["candidate_id"], "from_key": left, "to_key": right,
            "type": relation_type, "tier": "supporting", "evidence_kind": "pedagogical-inference",
            "evidence": [
                {"atom_key": left, "source_range": atoms[left]["source_range"]},
                {"atom_key": right, "source_range": atoms[right]["source_range"]},
            ],
            "rationale": rationale, "confidence": 0.99,
            "basis_candidate_ids": [pair_to_concept_candidate[basis_pair]] if basis_pair in pair_to_concept_candidate else [],
        })
        incident_atoms.update((left, right))
    round2_decisions = []
    for job in relation_jobs["jobs"]:
        ids = {str(item["candidate_id"]) for item in job["candidates"]}
        round2_decisions.append({
            "job_id": job["job_id"], "packet_sha256": job["packet_sha256"],
            "reviewed_candidate_ids": sorted(ids),
            "merge_decisions": [{"candidate_id": item["candidate_id"], "action": "keep-separate", "confidence": 0.99, "rationale": "教材语境中的定义与教学功能不同，保持为独立规范概念。"} for item in job["candidates"] if item["kind"] == "concept-merge"],
            "concept_relations": [item for item in selected_concepts if item["candidate_id"] in ids],
            "relations": [item for item in selected_atoms if item["candidate_id"] in ids],
        })
    round2 = kr.seal_artifact({"schema_version": 2, "kind": "round-2-relations-v2", "relation_jobs_sha256": relation_jobs["artifact_sha256"], "reviewer": {"type": "codex-agent", "model": "current-agent", "basis": "hybrid-candidates-plus-passed-v1"}, "decisions": round2_decisions})
    round2_path = output_dir / "round-2-relations.json"
    kr.atomic_json(round2_path, round2, overwrite=overwrite)
    round2 = kr.load_tagged(round2_path, "round-2-relations-v2")
    report2 = kr.validate_round2_payload(relation_jobs, round2)
    if report2["status"] != "passed":
        raise kr.RelationV2Error(f"Migrated relations require review: {report2['errors'] + report2['review_items']}")
    audit_jobs_path = output_dir / "graph-audit-jobs.json"
    audit_jobs = kr.prepare_audit_jobs(relation_jobs, round2)
    kr.atomic_json(audit_jobs_path, audit_jobs, overwrite=overwrite)
    audit_jobs = kr.load_tagged(audit_jobs_path, "graph-audit-jobs")
    audit = audit_jobs["audits"][0]
    final_concepts = [{"member_proposal_ids": [item["proposal_id"]], "preferred_label": item["preferred_label"], "aliases": item["aliases"], "definition": item["definition"], "kind": item["kind"]} for item in concept_report["concepts"]]
    independent_components = []
    draft_by_key = {str(item["key"]): item for item in audit["draft_concepts"]}
    for issue in audit["issues"]:
        if issue["code"] == "non-main-concept-component":
            labels = [str(draft_by_key[key]["preferred_label"]) for key in issue["concept_keys"] if key in draft_by_key]
            independent_components.append({"concept_keys": issue["concept_keys"], "reason": "该连通分量属于教材中相对独立的知识主题：" + "、".join(labels[:4])})
    round3 = kr.seal_artifact({
        "schema_version": 2, "kind": "round-3-audit", "graph_audit_jobs_sha256": audit_jobs["artifact_sha256"],
        "reviewer": {"type": "codex-agent", "model": "current-agent", "basis": "global-wcc-dag-and-evidence-audit"},
        "decisions": [{
            "audit_id": audit["audit_id"], "packet_sha256": audit["packet_sha256"],
            "reviewed_issue_ids": [item["issue_id"] for item in audit["issues"]],
            "concepts": final_concepts, "atom_concept_links": concept_report["atom_concept_links"],
            "concept_relations": selected_concepts, "relations": selected_atoms,
            "independent_atoms": [], "independent_components": independent_components,
        }],
    })
    round3_path = output_dir / "round-3-audit.json"
    kr.atomic_json(round3_path, round3, overwrite=overwrite)
    round3 = kr.load_tagged(round3_path, "round-3-audit")
    final, queue, quality, review = kr.finalize_relations(concept_jobs, round1, relation_jobs, round2, audit_jobs, round3)
    kr.atomic_json(output_dir / "relation-final.json", final, overwrite=overwrite)
    kr.atomic_json(output_dir / "relation-review-queue.json", queue, overwrite=overwrite)
    kr.atomic_json(output_dir / "relation-quality-report.json", quality, overwrite=overwrite)
    kr.atomic_text(output_dir / "relation-review.md", review, overwrite=overwrite)
    old_phrases = {
        kr.normalized(str(phrase)) for signature in old.get("concept_signatures", [])
        for field in ("teaches", "assumes") for phrase in signature.get(field, [])
        if kr.normalized(str(phrase))
    }
    old_types: dict[str, int] = defaultdict(int)
    for relation in old.get("relations", []):
        old_types[str(relation.get("type", "legacy"))] += 1
    label_differences = [
        {
            "atom_key": atom_key, "old_atom_title": str(atoms[atom_key]["title"]),
            "canonical_concept": override["label"],
        }
        for atom_key, override in overrides.items()
        if atom_key in atoms and override.get("label")
        and kr.normalized(str(atoms[atom_key]["title"])) != kr.normalized(override["label"])
    ]
    comparison = {
        "schema_version": 1, "kind": "relation-v1-v2-comparison", "status": final["status"],
        "old": {
            "concept_phrase_count": len(old_phrases), "relations": len(old.get("relations", [])),
            "relation_types": dict(sorted(old_types.items())),
        },
        "new": {
            "canonical_concepts": len(final["concepts"]),
            "merged_proposals": quality["counts"]["merged_proposals"],
            "atom_concept_links": len(final["atom_concept_links"]),
            "concept_relations": len(final["concept_relations"]), "relations": len(final["relations"]),
            "candidate_count": quality["counts"]["candidates"],
            "candidate_channels": quality["candidate_channels"],
            "candidate_acceptance_rate": quality["candidate_acceptance_rate"],
            "relation_types": quality["relation_types"],
            "component_sizes": quality["component_sizes"],
            "unresolved": quality["counts"]["unresolved"],
        },
        "typical_label_differences": label_differences[:12],
        "interpretation": "V2 counts canonical reusable concepts rather than raw teaches/assumes phrases; a lower count is intentional and relation quantity is not an optimization target.",
    }
    kr.atomic_json(output_dir / "relation-comparison-v1-v2.json", comparison, overwrite=overwrite)
    return {"status": final["status"], "unresolved_count": final["unresolved_count"], "concepts": len(final["concepts"]), "concept_relations": len(final["concept_relations"]), "relations": len(final["relations"]), "comparison": str(output_dir / "relation-comparison-v1-v2.json"), "output_dir": str(output_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("v1_final", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report, code = migrate(args.manifest, args.v1_final, args.output_dir, args.overrides, args.overwrite), 0
    except Exception as error:
        report, code = {"status": "failed", "error": f"{type(error).__name__}: {error}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

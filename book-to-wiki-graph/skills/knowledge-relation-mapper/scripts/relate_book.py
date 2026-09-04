#!/usr/bin/env python3
"""CLI for the three-pass atom/concept knowledge-relation workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from knowledge_relations import (
    RelationV2Error,
    apply_relation_final,
    atomic_json,
    atomic_text,
    finalize_relations,
    load_tagged,
    prepare_audit_jobs,
    prepare_concept_jobs,
    prepare_relation_jobs,
    validate_concept_payload,
    validate_round2_payload,
)


def write_json(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    atomic_json(path.expanduser().resolve(), payload, overwrite=overwrite)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    concepts = commands.add_parser("prepare-concepts", help="Create round-one concept extraction jobs")
    concepts.add_argument("manifest", type=Path)
    concepts.add_argument("--output-dir", type=Path, required=True)
    concepts.add_argument("--max-chars", type=int, default=80000)
    concepts.add_argument("--concept-registry", type=Path)
    concepts.add_argument("--overwrite", action="store_true")

    check_concepts = commands.add_parser("validate-concepts", help="Validate round-one concept decisions")
    check_concepts.add_argument("jobs", type=Path)
    check_concepts.add_argument("decisions", type=Path)
    check_concepts.add_argument("--output", type=Path)
    check_concepts.add_argument("--overwrite", action="store_true")

    relations = commands.add_parser("prepare-relations", help="Create hybrid round-two relation candidates")
    relations.add_argument("concept_jobs", type=Path)
    relations.add_argument("round_1_concepts", type=Path)
    relations.add_argument("--output-dir", type=Path, required=True)
    relations.add_argument("--embeddings", type=Path)
    relations.add_argument("--overwrite", action="store_true")

    check_relations = commands.add_parser("validate-relations", help="Validate round-two relation decisions")
    check_relations.add_argument("jobs", type=Path)
    check_relations.add_argument("decisions", type=Path)
    check_relations.add_argument("--output", type=Path)
    check_relations.add_argument("--overwrite", action="store_true")

    audit = commands.add_parser("prepare-audit", help="Create the global round-three graph audit")
    audit.add_argument("relation_jobs", type=Path)
    audit.add_argument("round_2_relations", type=Path)
    audit.add_argument("--output-dir", type=Path, required=True)
    audit.add_argument("--overwrite", action="store_true")

    finalize = commands.add_parser("finalize", help="Finalize reviewed concepts, relations, and graph audit")
    finalize.add_argument("concept_jobs", type=Path)
    finalize.add_argument("round_1_concepts", type=Path)
    finalize.add_argument("relation_jobs", type=Path)
    finalize.add_argument("round_2_relations", type=Path)
    finalize.add_argument("graph_audit_jobs", type=Path)
    finalize.add_argument("round_3_audit", type=Path)
    finalize.add_argument("--output-dir", type=Path, required=True)
    finalize.add_argument("--overwrite", action="store_true")

    apply = commands.add_parser("apply", help="Apply a passed final graph to book-graph.json")
    apply.add_argument("manifest", type=Path)
    apply.add_argument("relation_final", type=Path)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--profile-output", type=Path)
    apply.add_argument("--overwrite", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "prepare-concepts":
            payload = prepare_concept_jobs(args.manifest, max_chars=args.max_chars, registry=args.concept_registry)
            path = args.output_dir.expanduser().resolve() / "concept-jobs.json"
            write_json(path, payload, args.overwrite)
            print(json.dumps({"status": "prepared", "path": str(path), "jobs": len(payload["jobs"])}, ensure_ascii=False))
            return 0
        if args.command == "validate-concepts":
            jobs = load_tagged(args.jobs, "concept-jobs")
            decisions = load_tagged(args.decisions, "round-1-concepts")
            report = validate_concept_payload(jobs, decisions)
            if args.output:
                write_json(args.output, report, args.overwrite)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["status"] == "passed" else 1
        if args.command == "prepare-relations":
            jobs = load_tagged(args.concept_jobs, "concept-jobs")
            decisions = load_tagged(args.round_1_concepts, "round-1-concepts")
            payload = prepare_relation_jobs(jobs, decisions, embeddings_path=args.embeddings)
            path = args.output_dir.expanduser().resolve() / "relation-jobs.json"
            write_json(path, payload, args.overwrite)
            print(json.dumps({"status": "prepared", "path": str(path), "jobs": len(payload["jobs"])}, ensure_ascii=False))
            return 0
        if args.command == "validate-relations":
            jobs = load_tagged(args.jobs, "relation-jobs-v2")
            decisions = load_tagged(args.decisions, "round-2-relations-v2")
            report = validate_round2_payload(jobs, decisions)
            if args.output:
                write_json(args.output, report, args.overwrite)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["status"] == "passed" else 1
        if args.command == "prepare-audit":
            jobs = load_tagged(args.relation_jobs, "relation-jobs-v2")
            decisions = load_tagged(args.round_2_relations, "round-2-relations-v2")
            payload = prepare_audit_jobs(jobs, decisions)
            path = args.output_dir.expanduser().resolve() / "graph-audit-jobs.json"
            write_json(path, payload, args.overwrite)
            print(json.dumps({"status": "prepared", "path": str(path), "issues": len(payload["audits"][0]["issues"])}, ensure_ascii=False))
            return 0
        if args.command == "finalize":
            concept_jobs = load_tagged(args.concept_jobs, "concept-jobs")
            round1 = load_tagged(args.round_1_concepts, "round-1-concepts")
            relation_jobs = load_tagged(args.relation_jobs, "relation-jobs-v2")
            round2 = load_tagged(args.round_2_relations, "round-2-relations-v2")
            audit_jobs = load_tagged(args.graph_audit_jobs, "graph-audit-jobs")
            round3 = load_tagged(args.round_3_audit, "round-3-audit")
            final, queue, quality, review = finalize_relations(concept_jobs, round1, relation_jobs, round2, audit_jobs, round3)
            output_dir = args.output_dir.expanduser().resolve()
            write_json(output_dir / "relation-final.json", final, args.overwrite)
            write_json(output_dir / "relation-review-queue.json", queue, args.overwrite)
            write_json(output_dir / "relation-quality-report.json", quality, args.overwrite)
            atomic_text(output_dir / "relation-review.md", review, overwrite=args.overwrite)
            print(json.dumps({"status": final["status"], "unresolved_count": final["unresolved_count"], "output_dir": str(output_dir)}, ensure_ascii=False))
            return 0 if final["status"] == "passed" else 1
        report = apply_relation_final(
            args.manifest, args.relation_final, args.output,
            profile_output=args.profile_output, overwrite=args.overwrite,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (RelationV2Error, FileExistsError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

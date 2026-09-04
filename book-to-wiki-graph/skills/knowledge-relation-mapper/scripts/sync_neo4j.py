#!/usr/bin/env python3
"""Explicitly synchronize a deterministic export bundle to Neo4j."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from knowledge_relations import atomic_json, load_json


ALLOWED_LABELS = {"Book", "Organizer", "Atom", "Concept"}
ALLOWED_TYPES = {
    "CONTAINS", "INTRODUCES", "EXPLAINS", "DERIVES", "TRIGGERED_BY", "MOTIVATES",
    "ILLUSTRATES", "APPLIES", "PRACTICES", "ASSUMES", "PREREQUISITE", "DEVELOPS",
    "BROADER", "PART_OF", "CONTRASTS", "ANALOGOUS",
}


class Neo4jSyncError(RuntimeError):
    pass


def default_driver_factory(uri: str, auth: tuple[str, str]) -> Any:
    try:
        from neo4j import GraphDatabase
    except ImportError as error:
        raise Neo4jSyncError("Install the optional neo4j Python driver before using --execute") from error
    return GraphDatabase.driver(uri, auth=auth)


def sync_bundle(bundle_path: Path, uri: str, user: str, password: str, database: str, execute: bool, run_gds: bool = False, analysis_output: Path | None = None, driver_factory: Callable[[str, tuple[str, str]], Any] = default_driver_factory) -> dict[str, Any]:
    if not execute:
        raise Neo4jSyncError("Database writes require explicit --execute")
    if not uri or not user or not password:
        raise Neo4jSyncError("Neo4j URI, user, and password are required")
    bundle = load_json(bundle_path.expanduser().resolve())
    if bundle.get("kind") != "neo4j-export":
        raise Neo4jSyncError("Input is not a Neo4j export bundle")
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in bundle.get("nodes", []):
        label = str(node.get("label"))
        if label not in ALLOWED_LABELS:
            raise Neo4jSyncError(f"Unsupported node label: {label}")
        by_label[label].append(node)
    for relation in bundle.get("relationships", []):
        relation_type = str(relation.get("type"))
        if relation_type not in ALLOWED_TYPES:
            raise Neo4jSyncError(f"Unsupported relationship type: {relation_type}")
        by_type[relation_type].append(relation)
    driver = driver_factory(uri, (user, password))
    analysis: dict[str, Any] = {"wcc": [], "leiden": [], "status": "not-requested"}
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            for label in sorted(ALLOWED_LABELS):
                session.run(f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS FOR (n:{label}) REQUIRE n.key IS UNIQUE").consume()
            for label, rows in sorted(by_label.items()):
                session.run(
                    f"UNWIND $rows AS row MERGE (n:{label} {{key: row.key}}) SET n += row.properties",
                    rows=rows,
                ).consume()
            for relation_type, rows in sorted(by_type.items()):
                session.run(
                    f"UNWIND $rows AS row MATCH (a {{key: row.from_key}}), (b {{key: row.to_key}}) "
                    f"MERGE (a)-[r:{relation_type} {{key: row.merge_key}}]->(b) SET r += row.properties",
                    rows=rows,
                ).consume()
            if run_gds:
                session.run("CALL gds.graph.drop('bookKnowledgeGraph', false) YIELD graphName").consume()
                session.run("CALL gds.graph.project('bookKnowledgeGraph', ['Atom','Concept'], '*')").consume()
                analysis["wcc"] = [dict(record) for record in session.run(
                    "CALL gds.wcc.stream('bookKnowledgeGraph') YIELD nodeId, componentId RETURN gds.util.asNode(nodeId).key AS key, componentId ORDER BY componentId, key"
                )]
                try:
                    analysis["leiden"] = [dict(record) for record in session.run(
                        "CALL gds.leiden.stream('bookKnowledgeGraph') YIELD nodeId, communityId RETURN gds.util.asNode(nodeId).key AS key, communityId ORDER BY communityId, key"
                    )]
                    analysis["status"] = "wcc-and-leiden"
                except Exception as error:
                    analysis["status"] = "wcc-only"
                    analysis["leiden_error"] = type(error).__name__
                session.run("CALL gds.graph.drop('bookKnowledgeGraph') YIELD graphName").consume()
    finally:
        driver.close()
    report = {
        "status": "synced", "source": str(bundle_path.expanduser().resolve()),
        "nodes": sum(map(len, by_label.values())), "relationships": sum(map(len, by_type.values())),
        "database": database, "analysis": analysis,
    }
    if analysis_output is not None:
        atomic_json(analysis_output.expanduser().resolve(), report, overwrite=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="graph-export.json from export_neo4j.py")
    parser.add_argument("--uri", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--database", default="neo4j")
    parser.add_argument("--password-env", default="NEO4J_PASSWORD")
    parser.add_argument("--run-gds", action="store_true")
    parser.add_argument("--analysis-output", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        report, code = sync_bundle(
            args.bundle, args.uri, args.user, os.environ.get(args.password_env, ""), args.database,
            args.execute, args.run_gds, args.analysis_output,
        ), 0
    except Exception as error:
        report, code = {"status": "failed", "error": f"{type(error).__name__}: {error}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

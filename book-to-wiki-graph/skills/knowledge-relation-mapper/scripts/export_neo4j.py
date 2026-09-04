#!/usr/bin/env python3
"""Export the authoritative JSON graph as a deterministic Neo4j import bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from knowledge_relations import atomic_json, atomic_text, load_json, sha256_file, stable_key


def descendants(nodes: dict[str, dict[str, Any]], root_key: str) -> list[str]:
    result: list[str] = []
    def visit(key: str) -> None:
        result.append(key)
        for child in nodes[key].get("children", []):
            visit(str(child))
    visit(root_key)
    return result


def export_bundle(manifest_path: Path, output_dir: Path, overwrite: bool = False) -> dict[str, Any]:
    manifest_path, output_dir = manifest_path.expanduser().resolve(), output_dir.expanduser().resolve()
    graph = load_json(manifest_path)
    review = graph.get("relation_review", {})
    if review.get("status") != "passed" or review.get("graph_model") != "atom-concept-dual-layer":
        raise ValueError("Neo4j export requires a passed dual-layer knowledge graph")
    source_nodes = {str(item["key"]): item for item in graph.get("nodes", []) if isinstance(item, dict) and item.get("key")}
    roots = [key for key, item in source_nodes.items() if item.get("parent_key") is None]
    if len(roots) != 1:
        raise ValueError("Graph must contain exactly one root organizer")
    book_key = stable_key("book", str(graph.get("book_title", source_nodes[roots[0]].get("title", "book"))), str(graph.get("source_markdown_sha256", "")))
    nodes: list[dict[str, Any]] = [{
        "label": "Book", "key": book_key,
        "properties": {"title": str(graph.get("book_title", source_nodes[roots[0]].get("title", ""))), "source_sha256": str(graph.get("source_markdown_sha256", ""))},
    }]
    for key in descendants(source_nodes, roots[0]):
        item = source_nodes[key]
        label = "Organizer" if item.get("layer") == "organizer" else "Atom"
        properties = {"title": str(item.get("title", "")), "filename": str(item.get("filename", ""))}
        if label == "Atom":
            properties.update({"category": str(item.get("category", "")), "source_start": int(item["source_range"][0]), "source_end": int(item["source_range"][1])})
        nodes.append({"label": label, "key": key, "properties": properties})
    for concept in graph.get("concepts", []):
        nodes.append({"label": "Concept", "key": str(concept["key"]), "properties": {
            "preferred_label": str(concept["preferred_label"]), "aliases": list(concept.get("aliases", [])),
            "definition": str(concept["definition"]), "kind": str(concept["kind"]),
            "first_source_order": int(concept.get("first_source_order", 0)),
        }})
    relations: list[dict[str, Any]] = [{"type": "CONTAINS", "from_key": book_key, "to_key": roots[0], "properties": {}}]
    for key, item in source_nodes.items():
        parent = item.get("parent_key")
        if parent is not None:
            relations.append({"type": "CONTAINS", "from_key": str(parent), "to_key": key, "properties": {}})
    for link in graph.get("atom_concept_links", []):
        relations.append({
            "type": str(link["role"]).upper(), "from_key": str(link["atom_key"]), "to_key": str(link["concept_key"]),
            "properties": {"key": str(link.get("key", "")), "confidence": float(link.get("confidence", 0)), "evidence_ranges": json.dumps(link.get("evidence_ranges", []), ensure_ascii=False, sort_keys=True)},
        })
    for relation in graph.get("concept_relations", []):
        relations.append({
            "type": str(relation["type"]).upper(), "from_key": str(relation["from_key"]), "to_key": str(relation["to_key"]),
            "properties": {"key": str(relation.get("key", "")), "tier": str(relation.get("tier", "")), "evidence_kind": str(relation.get("evidence_kind", "")), "confidence": float(relation.get("confidence", 0)), "rationale": str(relation.get("rationale", ""))},
        })
    for relation in relations:
        relation["merge_key"] = str(
            relation["properties"].get("key")
            or stable_key("neo4j-edge", relation["type"], relation["from_key"], relation["to_key"])
        )
    nodes.sort(key=lambda item: (item["label"], item["key"]))
    relations.sort(key=lambda item: (item["type"], item["from_key"], item["to_key"], str(item["properties"].get("key", ""))))
    export = {"schema_version": 1, "kind": "neo4j-export", "source": str(manifest_path), "source_sha256": sha256_file(manifest_path), "nodes": nodes, "relationships": relations}
    node_lines = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in nodes)
    relation_lines = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in relations)
    constraints = "\n".join([
        "CREATE CONSTRAINT book_key IF NOT EXISTS FOR (n:Book) REQUIRE n.key IS UNIQUE;",
        "CREATE CONSTRAINT organizer_key IF NOT EXISTS FOR (n:Organizer) REQUIRE n.key IS UNIQUE;",
        "CREATE CONSTRAINT atom_key IF NOT EXISTS FOR (n:Atom) REQUIRE n.key IS UNIQUE;",
        "CREATE CONSTRAINT concept_key IF NOT EXISTS FOR (n:Concept) REQUIRE n.key IS UNIQUE;",
        "",
    ])
    import_notes = """// Execute with sync_neo4j.py. JSON is authoritative; this file documents idempotent semantics.\n// Nodes: MERGE (n:<Label> {key: row.key}) SET n += row.properties\n// Edges: MATCH endpoints by key, then MERGE (a)-[r:<TYPE> {key: row.merge_key}]->(b) SET r += row.properties\n"""
    atomic_json(output_dir / "graph-export.json", export, overwrite=overwrite)
    atomic_text(output_dir / "nodes.jsonl", node_lines, overwrite=overwrite)
    atomic_text(output_dir / "relationships.jsonl", relation_lines, overwrite=overwrite)
    atomic_text(output_dir / "constraints.cypher", constraints, overwrite=overwrite)
    atomic_text(output_dir / "import.cypher", import_notes, overwrite=overwrite)
    return {"status": "exported", "output_dir": str(output_dir), "nodes": len(nodes), "relationships": len(relations), "source_sha256": export["source_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report, code = export_bundle(args.manifest, args.output_dir, args.overwrite), 0
    except Exception as error:
        report, code = {"status": "failed", "error": f"{type(error).__name__}: {error}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

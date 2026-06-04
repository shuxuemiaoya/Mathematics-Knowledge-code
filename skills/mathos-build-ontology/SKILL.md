---
name: mathos-build-ontology
description: Use when merging scattered extracted JSON ontologies into a single global graph and exporting to Neo4j CSVs for GraphRAG.
---

# Merging Ontology to GraphRAG (Phase 3C Track 1)

## Overview
Use this skill when transitioning from scattered LLM extractions (Phase 3B) into a unified backend database for AI logic and GraphRAG. It involves a Map-Reduce style merge to prevent Token limits, followed by CSV exporting.

## When to Use
- When you need to build the `global_ontology.json`.
- When you need to deploy the knowledge graph to a Neo4j database.

## Core Process
1. **Global Merge**: The script reads thousands of `*.candidates.json` files and uses exact-match deduplication to merge identical concepts into a single `global_ontology.json`.
2. **Neo4j Export**: Translates the global JSON into `nodes.csv` and `edges.csv` standard formats.

## Command Reference
There is no dedicated CLI for this module yet. Use `mathos.ontology.global_merger.GlobalMerger` and `mathos.ontology.neo4j_exporter.Neo4jExporter` from Python, or add a small CLI before documenting commands.

## Common Mistakes / Red Flags
- ❌ **LLM Merge**: NEVER try to pass the thousands of JSONs to an LLM to "summarize or merge" them. You will exceed the context window and hallucinate data. Always use the deterministic python `merge` command.

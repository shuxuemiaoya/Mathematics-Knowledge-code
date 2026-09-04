# Optional Neo4j projection

Neo4j is a derived query and graph-algorithm backend, never the source of truth.

1. Run `export_neo4j.py <enriched-book-graph.json> --output-dir <dir>`.
   It writes deterministic `graph-export.json`, JSONL node/edge files,
   constraints, and import notes.
2. Inspect the bundle. Node labels are exactly `Book`, `Organizer`, `Atom`, and
   `Concept`; all nodes and edges have stable merge keys.
3. Only with explicit authorization, install the optional Neo4j driver and run:

   ```bash
   NEO4J_PASSWORD=... python scripts/sync_neo4j.py \
     <dir>/graph-export.json --uri <uri> --user <user> --execute
   ```

4. Add `--run-gds --analysis-output <report.json>` to run WCC and, when
   available, Leiden. The resulting report is independent and is never written
   back to `book-graph.json` automatically.

Without `--execute`, the sync command stops before importing the driver or
opening a connection. Passwords are read from the named environment variable
and never printed or stored in the export bundle.

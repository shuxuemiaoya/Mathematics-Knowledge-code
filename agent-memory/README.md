# Agent Memory

This directory stores operational memory for the MathOS Knowledge-Graph Implementation Operator.

The agent records execution facts:

- What stage ran.
- What command or workflow ran.
- What outputs were produced.
- What failures occurred.
- Where logs and artifacts were saved.

The agent does not record judgments about mathematical correctness or content quality unless a future human-approved skill explicitly changes that responsibility.

## Templates

- `templates/run-summary.md`: stage-level run summary.
- `templates/failure-ledger.json`: structured failure categories and counts.
- `templates/artifact-index.md`: generated files, folders, logs, and manifests.
- `templates/human-notes.md`: user-approved notes and future work.

Create dated run records from these templates when executing implemented stages.

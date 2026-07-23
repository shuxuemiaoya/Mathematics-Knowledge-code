# Operator Lifecycle

The Knowledge-Graph Implementation Operator follows the same lifecycle for every implemented stage.

## 1. Select Stage

Choose the repo-local skill or workflow that matches the user's requested task.

If no implemented skill exists for the requested task, stop and report that the skill slot is not active yet.

## 2. Execute Task

Run the command or Python workflow defined by the active skill.

Only run broad operations against explicit user-provided targets.

## 3. Monitor Health

Monitor operational health signals:

- Process crash.
- Non-zero command exit.
- Repeated failed files.
- Missing dependency.
- Missing API key.
- Stalled polling or no progress.
- Missing output folder.

Do not inspect generated content for mathematical correctness.

## 4. Summarize Output

Every completed or stopped stage must produce an output summary.

The summary includes:

- Stage name.
- Command or workflow used.
- Completion status.
- Output paths.
- Processed, generated, failed, skipped, and warning counts when available.
- Failure categories and log locations.

## 5. Save Operational Memory

Save run facts in `agent-memory/` using the templates in `agent-memory/templates/`.

Records must be human-readable Markdown or simple JSON.

## 6. Stop Or Continue

Stop when the active skill's operational stop conditions are met.

Continue only when the current implemented stage completed and the next requested stage is also implemented.

# Prompt Testing Environment with JSON Edit Interpreter

This document details the design for an independent prompt-testing environment and iterative refinement workflow. The environment is designed to optimize prompts for Markdown and mathematical formula formatting using DeepSeek, applying changes via structured JSON edit commands.

## Goals
- Provide a safe, file-driven workflow to test and iteratively refine system prompts.
- Ensure text transformations are applied using a strict, approved JSON edit schema rather than arbitrary code execution.
- Prevent destructive or ambiguous edits through strict interpreter validation rules.

## File Structure
All prompt-testing assets will be located under:
`c:\Mathematics-Knowledge\Mathematics-Knowledge-code\prompt-test-env\`

- **`prompt.md`**: The system instructions/prompt undergoing refinement.
- **`input.md`**: A markdown file containing input text/fragments (such as mathematics formulas) to format.
- **`output.md`**: The resulting markdown output after applying the edits.
- **`edits.json`**: The raw JSON array of edits received from DeepSeek.
- **`run_tester.py`**: The python script executing the pipeline.

## JSON Edit Schema
The interpreter only accepts a JSON array of search-and-replace edit commands. DeepSeek is instructed to output exactly this schema:

```json
[
  {
    "find": "exact substring to locate in input.md",
    "replace": "replacement content"
  }
]
```

### Safe Execution & Validation Rules
1. **Uniqueness check**: Before applying any edit, the interpreter checks that the `find` string occurs exactly *once* in the current text.
   - If the find string is missing, fail with `ValidationError("Edit target not found: ...")`.
   - If the find string matches multiple times, fail with `ValidationError("Ambiguous edit target: ... matches N times")`.
2. **Sequential execution**: Edits are applied in the exact order they are listed in the JSON array.
3. **Rollback**: If any edit command in the array fails validation, no edits are committed, and `output.md` is not written.

## DeepSeek API Integration
- The script imports environment variables from `c:\Mathematics-Knowledge\.env`.
- Uses the existing client/connection adapter to query DeepSeek (defaulting to the configuration in `.env`, falling back to standard API endpoints if necessary).
- Sends `prompt.md` as the system instructions and `input.md` as the user text payload.
- Requests the model to reply in JSON format with the edit array.

## Iterative Refinement Workflow
1. **User/Agent Setup**: Create the initial `prompt.md` and `input.md`.
2. **Execute**: The user runs `python prompt-test-env/run_tester.py`.
3. **Inspect**: The user reviews the generated `output.md` and `edits.json`.
4. **Feedback**: The user provides feedback in the chat.
5. **Update**: The agent edits `prompt.md` to incorporate the feedback.
6. **Repeat**: Steps 2–5 are repeated until the prompt behaves as desired.

## Verification Plan
1. **Dry Run (Mock Test)**: Write a quick internal test run inside `run_tester.py` that processes a dummy input string with dummy JSON edits to verify the uniqueness check, missing target checks, and clean replacement.
2. **API and Parser Test**: Run the script with a live call to DeepSeek using a sample mathematical fragment to verify that the API returns correctly formatted JSON and the edits are successfully applied.

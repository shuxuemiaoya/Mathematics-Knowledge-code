#!/usr/bin/env python3
"""
Collect training data from successful mathos-formatting runs.

Auto-discovers work directories under a search root, filters for
result-summary.json with status=passed, and extracts input/output pairs
for the two highest-value provider-generation stages:

  Step 1: toc_detection_sample.md (input) → toc.md (output)
  Step 3: toc_and_headings.md (input) → heading_processor.py (output)

Usage:
  python collect_training_data.py
  python collect_training_data.py --search-root "C:\\path\\to\\root" --output data.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Default search root
DEFAULT_SEARCH_ROOT = Path(
    r"C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map"
)
DEFAULT_OUTPUT = Path(__file__).parent / "training_data.json"


def find_work_dirs(search_root: Path) -> list[Path]:
    """Recursively find directories that contain result-summary.json."""
    results: list[Path] = []
    for summary_path in search_root.rglob("result-summary.json"):
        results.append(summary_path.parent)
    return sorted(results)


def is_passed(work_dir: Path) -> bool:
    """Check whether a work directory's result-summary has status=passed."""
    summary_path = work_dir / "result-summary.json"
    if not summary_path.exists():
        return False
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        return data.get("status") == "passed"
    except (json.JSONDecodeError, OSError):
        return False


def read_text_safe(path: Path) -> str | None:
    """Read a text file, returning None if missing or unreadable."""
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def extract_examples(work_dir: Path) -> dict:
    """
    Extract training examples from a single successful work directory.

    Returns a dict with metadata and step-specific input/output pairs.
    Missing files result in None values for their respective fields.
    """
    dir_name = work_dir.name
    result: dict = {
        "work_dir": str(work_dir),
        "dir_name": dir_name,
        "steps": {},
    }

    # Step 1: TOC Detection
    # Use toc_detection_response.md (raw LLM output with line numbers)
    # as ground truth, since DSPy optimizes the LLM call itself.
    # Fall back to toc.md if the response file is missing.
    step1_input = read_text_safe(work_dir / "toc_detection_sample.md")
    step1_output = read_text_safe(work_dir / "toc_detection_response.md")
    if not step1_output:
        step1_output = read_text_safe(work_dir / "toc.md")
    if step1_input and step1_output:
        result["steps"]["step1_toc_detection"] = {
            "input": step1_input,
            "output": step1_output,
        }

    # Step 3: Heading Processor Generation
    step3_input = read_text_safe(work_dir / "toc_and_headings.md")
    step3_output = read_text_safe(work_dir / "heading_processor.py")
    if step3_input and step3_output:
        result["steps"]["step3_heading_processor"] = {
            "input": step3_input,
            "output": step3_output,
        }

    return result


def collect(search_root: Path) -> list[dict]:
    """
    Discover all passed work directories and extract training examples.

    Returns a list of example dicts, one per work directory, that have
    at least one valid step.
    """
    work_dirs = find_work_dirs(search_root)
    examples: list[dict] = []

    for wd in work_dirs:
        if not is_passed(wd):
            continue
        example = extract_examples(wd)
        # Keep only if at least one step was successfully extracted
        if example["steps"]:
            examples.append(example)

    return examples


def print_summary(examples: list[dict]) -> None:
    """Print a human-readable summary of collected training data."""
    print(f"\n{'='*60}")
    print(f"  Training Data Collection Summary")
    print(f"{'='*60}")
    print(f"  Total examples collected: {len(examples)}")
    print()

    step_counts = {
        "step1_toc_detection": 0,
        "step3_heading_processor": 0,
    }

    for ex in examples:
        for step_name in step_counts:
            if step_name in ex["steps"]:
                step_counts[step_name] += 1

    print("  Per-step counts:")
    step_labels = {
        "step1_toc_detection": "Step 1 (TOC Detection)",
        "step3_heading_processor": "Step 3 (Heading Processor)",
    }
    for key, label in step_labels.items():
        count = step_counts[key]
        print(f"    {label}: {count} examples")

    print()
    print("  Work directories:")
    for ex in examples:
        steps = ", ".join(sorted(ex["steps"].keys()))
        print(f"    {ex['dir_name']}")
        print(f"      Steps: {steps}")

        # Show input/output sizes
        for step_name, step_data in sorted(ex["steps"].items()):
            in_len = len(step_data["input"])
            out_len = len(step_data["output"])
            print(
                f"      {step_name}: "
                f"input={in_len:,} chars, output={out_len:,} chars"
            )

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect training data from successful mathos-formatting runs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--search-root",
        type=Path,
        default=DEFAULT_SEARCH_ROOT,
        help=(
            "Root directory to search for mathos-formatting work dirs. "
            f"Default: {DEFAULT_SEARCH_ROOT}"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON file path. Default: {DEFAULT_OUTPUT}",
    )
    args = parser.parse_args()

    search_root: Path = args.search_root.resolve()
    output_path: Path = args.output.resolve()

    if not search_root.is_dir():
        print(f"ERROR: Search root does not exist: {search_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Searching for training data in: {search_root}")
    examples = collect(search_root)

    if not examples:
        print("WARNING: No successful runs found.", file=sys.stderr)
        sys.exit(0)

    print_summary(examples)

    # Save to JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(examples, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(examples)} examples to: {output_path}")


if __name__ == "__main__":
    main()

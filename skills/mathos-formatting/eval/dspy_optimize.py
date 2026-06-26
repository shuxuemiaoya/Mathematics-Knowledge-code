#!/usr/bin/env python3
"""
DSPy prompt optimization for the mathos-formatting pipeline.

Optimizes the three highest-value prompts in the pipeline:
  - step1: TOC extraction from numbered Markdown
  - step3: Heading processor Python script generation
  - step6: Content processor Python script generation

Uses DeepSeek API via litellm and supports BootstrapFewShot or MIPROv2
optimizers with domain-specific structural metrics.

Usage:
  python dspy_optimize.py --step step1 --trainset training_data.json
  python dspy_optimize.py --step step3 --optimizer mipro --dry-run
  python dspy_optimize.py --step step6 --output ./optimized
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

try:
    import dspy
except ImportError:
    print(
        "ERROR: dspy is not installed. Install with: pip install dspy",
        file=sys.stderr,
    )
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

ENV_FILE = Path(r"C:\Mathematics-Knowledge\.env")
DEFAULT_OUTPUT = Path(__file__).parent / "optimized"
DEFAULT_TRAINSET = Path(__file__).parent / "training_data.json"
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek/deepseek-chat"


def load_api_key() -> str:
    """Load DEEPSEEK_API_KEY from environment or .env file."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key

    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key

    print(
        "ERROR: DEEPSEEK_API_KEY not found in environment or .env file.",
        file=sys.stderr,
    )
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────
# DSPy Signatures
# ──────────────────────────────────────────────────────────────────────


class TOCExtraction(dspy.Signature):
    """Extract the complete table of contents from a numbered Markdown sample.

    The input is the first 20 pages of a Markdown file, with each line
    prepended with its 1-indexed line number in the format '<N>: <content>'.
    Return only the complete contiguous TOC span, preserving every numbered
    input line exactly, including line-number prefixes, text, whitespace,
    punctuation, OCR output, blank lines, and ordering.
    """

    markdown_sample: str = dspy.InputField(
        desc="First 20 pages of Markdown with line number prefixes"
    )
    toc_text: str = dspy.OutputField(
        desc="Complete contiguous TOC span with preserved line numbers"
    )


class HeadingProcessorGeneration(dspy.Signature):
    """Generate a Python script to normalize Markdown heading levels according to TOC.

    The input contains the immutable TOC wrapped in HTML comments and all
    body headings extracted from the full Markdown file. The output must be a
    complete, directly-runnable Python script containing a TOC_HEADINGS dict
    mapping each TOC title (with section prefixes preserved, page references
    stripped) to its target heading level (1=H1, 2=H2, 3=H3). The script must
    define: get_target_root, protect_blocks, restore_blocks, replace_in_file,
    and main functions.
    """

    toc_and_headings: str = dspy.InputField(
        desc="Combined TOC and body headings payload"
    )
    python_script: str = dspy.OutputField(
        desc="Complete Python heading processor script with TOC_HEADINGS dict"
    )


class ContentProcessorGeneration(dspy.Signature):
    """Generate a Python script to clean up Markdown content formatting.

    The input is a sample H1 chapter from the Markdown file. The output must
    be a complete, directly-runnable Python script using the protect-process-restore
    pipeline pattern. It must import os, pathlib.Path, and re, and define:
    get_target_root, protect_blocks, restore_blocks, replace_in_file, and main.
    """

    chapter_sample: str = dspy.InputField(
        desc="Sample H1 chapter content from the Markdown file"
    )
    python_script: str = dspy.OutputField(
        desc="Complete Python content processor script"
    )


# ──────────────────────────────────────────────────────────────────────
# Domain-Specific Metrics
# ──────────────────────────────────────────────────────────────────────


def toc_metric(example: dspy.Example, prediction, trace=None) -> float:
    """
    Evaluate TOC extraction quality.

    Scoring (0.0 – 1.0):
      0.25 — output contains line number prefixes (e.g. "42: ")
      0.25 — line numbers are contiguous (no gaps)
      0.25 — contains at least one TOC page header (目录/CONTENTS/## heading)
      0.25 — page references present (e.g. /2, /18, P1)
    """
    pred_text = getattr(prediction, "toc_text", "") or ""
    if not pred_text.strip():
        return 0.0

    score = 0.0
    lines = pred_text.strip().splitlines()

    # Check 1: Line number prefixes present
    line_num_pattern = re.compile(r"^\d+:\s")
    prefixed_lines = [l for l in lines if line_num_pattern.match(l)]
    if len(prefixed_lines) >= len(lines) * 0.5:
        score += 0.25

    # Check 2: Contiguous line numbers
    nums: list[int] = []
    for line in lines:
        m = re.match(r"^(\d+):", line)
        if m:
            nums.append(int(m.group(1)))
    if len(nums) >= 2:
        # Check if they form a contiguous (or near-contiguous) sequence
        expected_range = nums[-1] - nums[0] + 1
        # Allow for blank lines that might be skipped
        if len(nums) >= expected_range * 0.7:
            score += 0.25

    # Check 3: TOC headers present
    toc_headers = ["目录", "CONTENTS", "contents"]
    has_header = any(h in pred_text for h in toc_headers)
    # Also count ## headings as TOC structure indicators
    has_chapter_headings = bool(re.search(r"^##\s+第.+章", pred_text, re.MULTILINE))
    if has_header or has_chapter_headings:
        score += 0.25

    # Check 4: Page references present
    page_ref_pattern = re.compile(r"[/／]\s*\d+|P\d+|p\.\s*\d+|…+\s*\d+")
    page_refs = page_ref_pattern.findall(pred_text)
    if len(page_refs) >= 3:
        score += 0.25

    return score


def _check_python_syntax(code: str) -> bool:
    """Check if a string is valid Python syntax."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


REQUIRED_FUNCTIONS = [
    "get_target_root",
    "protect_blocks",
    "restore_blocks",
    "replace_in_file",
    "main",
]

DANGEROUS_IMPORTS = {
    "subprocess",
    "shutil",
    "socket",
    "http",
    "urllib",
    "requests",
    "ftplib",
    "smtplib",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
}


def _check_no_dangerous_imports(code: str) -> bool:
    """Check that code does not import dangerous modules."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in DANGEROUS_IMPORTS:
                    return False
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in DANGEROUS_IMPORTS:
                    return False
    return True


def _check_required_functions(code: str) -> tuple[int, int]:
    """
    Count how many of the required functions are defined in the code.

    Returns (found, total).
    """
    found = 0
    for fn_name in REQUIRED_FUNCTIONS:
        if re.search(rf"def\s+{fn_name}\s*\(", code):
            found += 1
    return found, len(REQUIRED_FUNCTIONS)


def heading_processor_metric(
    example: dspy.Example, prediction, trace=None
) -> float:
    """
    Evaluate heading processor script quality.

    Scoring (0.0 – 1.0):
      0.25 — valid Python syntax
      0.30 — all required functions present (partial credit)
      0.25 — TOC_HEADINGS dict present and non-empty
      0.20 — no dangerous imports
    """
    pred_text = getattr(prediction, "python_script", "") or ""
    if not pred_text.strip():
        return 0.0

    # Strip markdown code fences if present
    code = _strip_code_fences(pred_text)
    score = 0.0

    # Check 1: Valid Python syntax
    if _check_python_syntax(code):
        score += 0.25

    # Check 2: Required functions
    found, total = _check_required_functions(code)
    score += 0.30 * (found / total)

    # Check 3: TOC_HEADINGS dict present
    if re.search(r"TOC_HEADINGS\s*[:{]", code) or re.search(
        r"TOC_HEADINGS\s*=\s*\{", code
    ):
        # Check it's non-empty (has at least one key-value pair)
        if re.search(r"TOC_HEADINGS\s*.*=\s*\{[^}]+\}", code, re.DOTALL):
            score += 0.25
        else:
            score += 0.10  # Present but possibly empty

    # Check 4: No dangerous imports
    if _check_no_dangerous_imports(code):
        score += 0.20

    return min(score, 1.0)


def content_processor_metric(
    example: dspy.Example, prediction, trace=None
) -> float:
    """
    Evaluate content processor script quality.

    Scoring (0.0 – 1.0):
      0.25 — valid Python syntax
      0.30 — all required functions present (partial credit)
      0.25 — protect-process-restore pipeline structure
      0.20 — no dangerous imports
    """
    pred_text = getattr(prediction, "python_script", "") or ""
    if not pred_text.strip():
        return 0.0

    code = _strip_code_fences(pred_text)
    score = 0.0

    # Check 1: Valid Python syntax
    if _check_python_syntax(code):
        score += 0.25

    # Check 2: Required functions
    found, total = _check_required_functions(code)
    score += 0.30 * (found / total)

    # Check 3: Pipeline structure (protect → process → restore)
    has_protect_call = "protect_blocks" in code
    has_restore_call = "restore_blocks" in code
    # Check that replace_in_file calls both protect and restore
    replace_in_file_match = re.search(
        r"def\s+replace_in_file\s*\([^)]*\)[\s\S]*?(?=\ndef\s|\Z)",
        code,
    )
    if replace_in_file_match:
        fn_body = replace_in_file_match.group()
        if "protect_blocks" in fn_body and "restore_blocks" in fn_body:
            score += 0.25
        elif has_protect_call and has_restore_call:
            score += 0.15
    elif has_protect_call and has_restore_call:
        score += 0.10

    # Check 4: No dangerous imports
    if _check_no_dangerous_imports(code):
        score += 0.20

    return min(score, 1.0)


def _strip_code_fences(text: str) -> str:
    """Strip Markdown code fences from Python code output."""
    text = text.strip()
    # Remove ```python ... ``` wrapper
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


# ──────────────────────────────────────────────────────────────────────
# Training Data Loading
# ──────────────────────────────────────────────────────────────────────


def load_training_data(
    trainset_path: Path, step: str
) -> list[dspy.Example]:
    """
    Load training data from JSON and convert to dspy.Example objects
    for the specified step.

    Args:
        trainset_path: Path to training_data.json
        step: One of 'step1', 'step3', 'step6'

    Returns:
        List of dspy.Example with correct input/output field names.
    """
    raw = json.loads(trainset_path.read_text(encoding="utf-8"))
    examples: list[dspy.Example] = []

    step_key_map = {
        "step1": "step1_toc_detection",
        "step3": "step3_heading_processor",
        "step6": "step6_content_processor",
    }
    field_map = {
        "step1": ("markdown_sample", "toc_text"),
        "step3": ("toc_and_headings", "python_script"),
        "step6": ("chapter_sample", "python_script"),
    }

    step_key = step_key_map[step]
    input_field, output_field = field_map[step]

    for entry in raw:
        if step_key not in entry.get("steps", {}):
            continue
        step_data = entry["steps"][step_key]
        ex = dspy.Example(
            **{
                input_field: step_data["input"],
                output_field: step_data["output"],
            }
        ).with_inputs(input_field)
        examples.append(ex)

    return examples


# ──────────────────────────────────────────────────────────────────────
# Optimization
# ──────────────────────────────────────────────────────────────────────


STEP_CONFIG = {
    "step1": {
        "signature": TOCExtraction,
        "metric": toc_metric,
        "module_class": "TOCExtractor",
    },
    "step3": {
        "signature": HeadingProcessorGeneration,
        "metric": heading_processor_metric,
        "module_class": "HeadingProcessorGenerator",
    },
    "step6": {
        "signature": ContentProcessorGeneration,
        "metric": content_processor_metric,
        "module_class": "ContentProcessorGenerator",
    },
}


class FormattingModule(dspy.Module):
    """Generic DSPy module wrapping a single pipeline stage."""

    def __init__(self, signature_cls):
        super().__init__()
        self.predictor = dspy.ChainOfThought(signature_cls)

    def forward(self, **kwargs):
        return self.predictor(**kwargs)


def evaluate_baseline(
    module: dspy.Module,
    examples: list[dspy.Example],
    metric,
    step: str,
) -> float:
    """Evaluate current module on examples and return average score."""
    scores: list[float] = []
    field_map = {
        "step1": "markdown_sample",
        "step3": "toc_and_headings",
        "step6": "chapter_sample",
    }
    input_field = field_map[step]

    for ex in examples:
        try:
            pred = module(**{input_field: getattr(ex, input_field)})
            s = metric(ex, pred)
            scores.append(s)
        except Exception as e:
            print(f"  WARNING: Prediction failed: {e}")
            scores.append(0.0)

    return sum(scores) / len(scores) if scores else 0.0


def run_optimization(
    step: str,
    trainset_path: Path,
    output_dir: Path,
    optimizer_name: str,
    dry_run: bool = False,
) -> None:
    """
    Run the full optimization pipeline for a given step.

    Args:
        step: One of 'step1', 'step3', 'step6'
        trainset_path: Path to training_data.json
        output_dir: Directory to write optimized prompts and reports
        optimizer_name: 'bootstrap' or 'mipro'
        dry_run: If True, load data and validate metrics without API calls
    """
    config = STEP_CONFIG[step]
    signature_cls = config["signature"]
    metric = config["metric"]

    print(f"\n{'='*60}")
    print(f"  DSPy Optimization: {step}")
    print(f"{'='*60}")

    # Load training data
    print(f"\nLoading training data from: {trainset_path}")
    examples = load_training_data(trainset_path, step)
    print(f"  Loaded {len(examples)} examples for {step}")

    if not examples:
        print(f"ERROR: No training examples found for {step}", file=sys.stderr)
        return

    # Dry-run mode: validate metrics on ground truth
    if dry_run:
        print("\n[DRY RUN] Validating metrics on ground truth data...")
        _run_dry_validation(examples, metric, step)
        return

    # Configure LM
    api_key = load_api_key()
    lm = dspy.LM(
        DEEPSEEK_MODEL,
        api_key=api_key,
        api_base=DEEPSEEK_API_BASE,
    )
    dspy.configure(lm=lm)

    # Create module
    module = FormattingModule(signature_cls)

    # Split data: use all for training (small dataset), reserve last for dev
    if len(examples) >= 3:
        trainset = examples[:-1]
        devset = examples[-1:]
    else:
        trainset = examples
        devset = examples

    print(f"  Train: {len(trainset)}, Dev: {len(devset)}")

    # Run optimizer
    print(f"\nRunning {optimizer_name} optimizer...")
    if optimizer_name == "bootstrap":
        optimizer = dspy.BootstrapFewShot(
            metric=metric,
            max_bootstrapped_demos=2,
            max_labeled_demos=2,
            max_rounds=1,
        )
        optimized_module = optimizer.compile(
            module,
            trainset=trainset,
        )
    elif optimizer_name == "mipro":
        optimizer = dspy.MIPROv2(
            metric=metric,
            num_candidates=4,
            init_temperature=0.7,
        )
        optimized_module = optimizer.compile(
            module,
            trainset=trainset,
            max_bootstrapped_demos=2,
            max_labeled_demos=2,
            num_trials=8,
        )
    else:
        print(f"ERROR: Unknown optimizer: {optimizer_name}", file=sys.stderr)
        return

    # Evaluate optimized module
    print("\nEvaluating optimized module on dev set...")
    after_score = evaluate_baseline(optimized_module, devset, metric, step)
    print(f"  Optimized dev score: {after_score:.3f}")

    # Save results
    _save_results(optimized_module, step, output_dir, after_score, optimizer_name)

    print(f"\nOptimization complete for {step}.")


def _run_dry_validation(
    examples: list[dspy.Example],
    metric,
    step: str,
) -> None:
    """Run metrics on ground-truth outputs to validate metric functions."""
    field_map = {
        "step1": ("markdown_sample", "toc_text"),
        "step3": ("toc_and_headings", "python_script"),
        "step6": ("chapter_sample", "python_script"),
    }
    _, output_field = field_map[step]

    scores: list[float] = []
    for i, ex in enumerate(examples):
        # Create a mock prediction from the ground truth output
        ground_truth_output = getattr(ex, output_field)

        class MockPrediction:
            pass

        mock = MockPrediction()
        setattr(mock, output_field, ground_truth_output)

        score = metric(ex, mock)
        scores.append(score)

        # Show truncated output
        gt_preview = ground_truth_output[:100].replace("\n", "\\n")
        print(f"\n  Example {i+1}:")
        print(f"    Output preview: {gt_preview}...")
        print(f"    Metric score:   {score:.3f}")

    avg = sum(scores) / len(scores) if scores else 0.0
    print(f"\n  Average ground-truth score: {avg:.3f}")

    if avg < 0.5:
        print(
            "\n  WARNING: Ground-truth scores are low. "
            "Metric may need calibration.",
            file=sys.stderr,
        )
    else:
        print("\n  Metrics look healthy — ground truth scores well.")

    print("\n[DRY RUN] Complete. No API calls were made.")


def _save_results(
    optimized_module: dspy.Module,
    step: str,
    output_dir: Path,
    score: float,
    optimizer_name: str,
) -> None:
    """Save optimized prompt and report to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the optimized module state
    module_path = output_dir / f"{step}_optimized_module.json"
    try:
        optimized_module.save(str(module_path))
        print(f"\n  Saved optimized module: {module_path}")
    except Exception as e:
        print(f"  WARNING: Could not save module state: {e}")

    # Extract and save the optimized prompt
    prompt_path = output_dir / f"{step}_optimized_prompt.md"
    prompt_text = _extract_prompt(optimized_module, step)
    prompt_path.write_text(prompt_text, encoding="utf-8")
    print(f"  Saved optimized prompt: {prompt_path}")

    # Save optimization report
    report_path = output_dir / f"{step}_optimization_report.json"
    report = {
        "step": step,
        "optimizer": optimizer_name,
        "dev_score": score,
        "module_path": str(module_path),
        "prompt_path": str(prompt_path),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Saved optimization report: {report_path}")


def _extract_prompt(module: dspy.Module, step: str) -> str:
    """Extract the effective prompt text from an optimized module."""
    parts: list[str] = []
    parts.append(f"# Optimized Prompt: {step}\n")
    parts.append(f"Extracted from DSPy-optimized module.\n")

    # Try to get the predictor's demos and instructions
    predictor = getattr(module, "predictor", None)
    if predictor is None:
        parts.append("\n(Could not extract predictor details.)\n")
        return "\n".join(parts)

    # Extract signature docstring (instruction)
    sig = getattr(predictor, "signature", None)
    if sig:
        doc = getattr(sig, "__doc__", "") or ""
        if doc.strip():
            parts.append(f"\n## Instructions\n\n{doc.strip()}\n")

        # Extract field descriptions
        parts.append("\n## Input Fields\n")
        for name, field in sig.input_fields.items():
            desc = getattr(field, "json_schema_extra", {}).get("desc", "")
            parts.append(f"- **{name}**: {desc}")

        parts.append("\n## Output Fields\n")
        for name, field in sig.output_fields.items():
            desc = getattr(field, "json_schema_extra", {}).get("desc", "")
            parts.append(f"- **{name}**: {desc}")

    # Extract bootstrapped demos
    demos = getattr(predictor, "demos", [])
    if demos:
        parts.append(f"\n## Bootstrapped Demos ({len(demos)} examples)\n")
        for i, demo in enumerate(demos):
            parts.append(f"\n### Demo {i+1}\n")
            if hasattr(demo, "items"):
                for k, v in demo.items():
                    preview = str(v)[:200]
                    parts.append(f"**{k}**: {preview}{'...' if len(str(v)) > 200 else ''}\n")
            else:
                parts.append(f"{str(demo)[:500]}\n")

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DSPy prompt optimization for mathos-formatting pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to validate metrics without API calls
  python dspy_optimize.py --step step1 --dry-run

  # Optimize step1 with BootstrapFewShot
  python dspy_optimize.py --step step1 --optimizer bootstrap

  # Optimize step3 with MIPROv2
  python dspy_optimize.py --step step3 --optimizer mipro

  # Custom trainset and output directory
  python dspy_optimize.py --step step6 --trainset my_data.json --output ./results
""",
    )
    parser.add_argument(
        "--step",
        choices=["step1", "step3", "step6"],
        required=True,
        help="Which pipeline step to optimize.",
    )
    parser.add_argument(
        "--trainset",
        type=Path,
        default=DEFAULT_TRAINSET,
        help=f"Path to training data JSON. Default: {DEFAULT_TRAINSET}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output directory for optimized prompts. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--optimizer",
        choices=["bootstrap", "mipro"],
        default="bootstrap",
        help="Optimizer to use. Default: bootstrap",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load data and validate metrics without calling the API.",
    )
    args = parser.parse_args()

    run_optimization(
        step=args.step,
        trainset_path=args.trainset.resolve(),
        output_dir=args.output.resolve(),
        optimizer_name=args.optimizer,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

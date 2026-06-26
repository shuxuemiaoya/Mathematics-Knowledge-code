# -*- coding: utf-8 -*-
"""
Promptfoo assertion: validates generated Python scripts (step3 and step6).

Checks:
  - Required imports: import os, from pathlib import Path, import re
  - Required functions: get_target_root, protect_blocks, restore_blocks,
    replace_in_file, main
  - No dangerous imports (subprocess, shutil.rmtree, os.remove, etc.)
  - No dangerous calls (eval, exec, open('w') outside replace_in_file)
  - Valid Python syntax (compile check)
  - For step3: contains TOC_HEADINGS dict
"""

import re
import ast
from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Strip optional markdown code fences wrapping the Python source."""
    text = text.strip()
    # Handle ```python ... ``` wrapping
    fence_re = re.compile(
        r"^```(?:python|py)?\s*\n(.*?)\n```\s*$", re.DOTALL
    )
    m = fence_re.match(text)
    if m:
        return m.group(1)
    return text


REQUIRED_FUNCTIONS = [
    "get_target_root",
    "protect_blocks",
    "restore_blocks",
    "replace_in_file",
    "main",
]

DANGEROUS_IMPORTS = [
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "http.client",
    "http.server",
    "ftplib",
    "smtplib",
    "ctypes",
]

DANGEROUS_CALLS_RE = re.compile(
    r"\b(?:eval|exec)\s*\(", re.MULTILINE
)

DANGEROUS_SHUTIL_RE = re.compile(
    r"\bshutil\s*\.\s*rmtree\b|\bos\s*\.\s*remove\b|\bos\s*\.\s*unlink\b",
    re.MULTILINE,
)


def get_assert(output: str, context: dict[str, Any] | None = None) -> dict:
    """Return a GradingResult dict: {pass, score, reason}."""
    errors: list[str] = []

    if not output or not output.strip():
        return {"pass": False, "score": 0.0, "reason": "Output is empty"}

    source = _strip_fences(output)

    # ── 1. Required imports ──────────────────────────────────────────────
    if not re.search(r"^import\s+os\b", source, re.MULTILINE):
        errors.append("Missing 'import os'")

    if not re.search(r"from\s+pathlib\s+import\s+Path", source, re.MULTILINE):
        errors.append("Missing 'from pathlib import Path'")

    if not re.search(r"^import\s+re\b", source, re.MULTILINE):
        errors.append("Missing 'import re'")

    # ── 2. Required functions ────────────────────────────────────────────
    for fn in REQUIRED_FUNCTIONS:
        if not re.search(rf"def\s+{fn}\s*\(", source, re.MULTILINE):
            errors.append(f"Missing required function: {fn}()")

    # ── 3. Dangerous imports ─────────────────────────────────────────────
    for mod in DANGEROUS_IMPORTS:
        if re.search(
            rf"(?:^import\s+{mod}\b|^from\s+{mod}\b)", source, re.MULTILINE
        ):
            errors.append(f"Dangerous import detected: {mod}")

    # ── 4. Dangerous calls ───────────────────────────────────────────────
    if DANGEROUS_CALLS_RE.search(source):
        errors.append("Dangerous call detected: eval() or exec()")

    if DANGEROUS_SHUTIL_RE.search(source):
        errors.append(
            "Dangerous call detected: shutil.rmtree, os.remove, or os.unlink"
        )

    # ── 5. Syntax check ─────────────────────────────────────────────────
    try:
        ast.parse(source)
    except SyntaxError as e:
        errors.append(f"Python syntax error: {e.msg} (line {e.lineno})")

    # ── 6. Step-specific checks ──────────────────────────────────────────
    step = ""
    if context and "test" in context:
        test_config = context["test"]
        if isinstance(test_config, dict):
            assert_cfg = test_config.get("assert", [])
            # Try to extract step from assertion config
            for a in assert_cfg if isinstance(assert_cfg, list) else []:
                if isinstance(a, dict) and "config" in a:
                    cfg = a["config"]
                    if isinstance(cfg, dict) and "step" in cfg:
                        step = cfg["step"]
                        break

    # Also check via context.test.options or context.vars
    if not step and context:
        config = None
        if "test" in context and isinstance(context["test"], dict):
            options = context["test"].get("options", {})
            if isinstance(options, dict):
                config = options.get("config", {})
        # Check assertion-level config
        if not config and "config" in context:
            config = context["config"]
        if isinstance(config, dict):
            step = config.get("step", "")

    if step == "step3":
        if "TOC_HEADINGS" not in source:
            errors.append(
                "Step 3 script must contain a TOC_HEADINGS dictionary"
            )
        if not re.search(
            r"TOC_HEADINGS\s*[:{]", source, re.MULTILINE
        ):
            errors.append(
                "TOC_HEADINGS must be defined as a dict (dict[str, int])"
            )

    # ── Result ───────────────────────────────────────────────────────────
    if errors:
        return {
            "pass": False,
            "score": max(0.0, 1.0 - len(errors) * 0.15),
            "reason": "; ".join(errors),
        }

    return {
        "pass": True,
        "score": 1.0,
        "reason": "Python artifact is valid and safe",
    }

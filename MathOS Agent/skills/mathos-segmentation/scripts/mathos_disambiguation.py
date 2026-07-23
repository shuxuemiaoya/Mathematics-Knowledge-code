"""LLM-based heading disambiguation preprocessor for MathOS."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add mathos-formatting/scripts to sys.path to reuse mathos_provider
_script_dir = Path(__file__).resolve().parent
_formatting_dir = _script_dir.parents[1] / "mathos-formatting" / "scripts"
if str(_formatting_dir) not in sys.path:
    sys.path.insert(0, str(_formatting_dir))
import mathos_provider as provider


STAGE_NAME = "disambiguation"
SKILL_NAME = "skills/mathos-segmentation"
SCRIPT_COMMAND = r".\skills\mathos-segmentation\scripts\mathos_disambiguation.py"
ALL_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_TITLE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
SYSTEM_PROMPT = """You are a precise AI editor for textbook Markdown content.
Your task is to identify headings at level 2 (H2) or level 3 (H3) that are semantically generic, ambiguous, or likely to be repeated across different chapters.
Examples of generic headings: "小结", "本章小结", "复习参考题", "复习参考题 1", "练习", "习题", "阅读与思考", "数学探究", "探究与发现".
Any specific heading containing concrete mathematical topics (e.g., "1.1.1 集合的概念", "6.2.2 向量的数乘运算") is already specific and must NOT be rewritten.

For each generic heading, you must rewrite its title by prefixing it with the core semantic topic of its parent H1 heading.
To extract the core semantic topic from parent H1, strip chapter numbering prefixes such as "第一章 ", "第1章 ", "第 1 章 ", "Chapter 1 ", etc.
For example:
- Parent H1: "第一章 集合与常用逻辑用语" -> Core topic: "集合与常用逻辑用语"
- Generic H2: "小结" -> Rewritten title: "集合与常用逻辑用语 小结"
- Generic H2: "复习参考题 1" -> Rewritten title: "集合与常用逻辑用语 复习参考题"
- Generic H2: "阅读与思考" -> Rewritten title: "集合与常用逻辑用语 阅读与思考"

Rules:
1. Do not rewrite specific headings. Only rewrite generic/ambiguous ones.
2. The rewritten title must NOT contain heading markers like "##" or "###". It should only contain the plain text title.
3. Keep any suffix or number if it belongs to the generic heading (e.g., "复习参考题 1" -> "集合与常用逻辑用语 复习参考题" or "集合与常用逻辑用语 复习参考题1" - keep the suffix, but clean it if it is generic).
4. Return a JSON object with a key "rewrites" containing a list of objects. Each object must have:
   - "line_index": (integer) the exact line index of the heading provided in the input.
   - "original_text": (string) the original heading title text.
   - "new_text": (string) the new rewritten heading title text.
If no headings need to be rewritten, return {"rewrites": []}."""


class SegmentationError(Exception):
    """Raised when stage-one segmentation cannot continue safely."""


@dataclass(frozen=True)
class Heading:
    marker: str
    markdown_depth: int
    number: str
    number_depth: int
    title: str
    full_title: str
    line_index: int
    char_start: int
    char_end: int


def find_env_file(source_path: Path, vault_root: Path) -> Path | None:
    # 1. Check current working directory
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env
    # 2. Check vault_root parent
    parent_env = vault_root.parent / ".env"
    if parent_env.is_file():
        return parent_env
    # 3. Check vault_root itself
    vault_env = vault_root / ".env"
    if vault_env.is_file():
        return vault_env
    # 4. Search upward from source_path
    curr = source_path.resolve().parent
    while curr != curr.parent:
        candidate = curr / ".env"
        if candidate.is_file():
            return candidate
        curr = curr.parent
    return None


def extract_all_headings(markdown: str) -> list[Heading]:
    headings: list[Heading] = []
    char_offset = 0
    for line_index, line in enumerate(markdown.splitlines(keepends=True)):
        line_text = line.rstrip("\r\n")
        match = ALL_HEADING_RE.match(line_text)
        if match:
            marker = match.group(1)
            full_title = match.group(2).strip()
            number_match = NUMBERED_TITLE_RE.match(full_title)
            number = number_match.group(1) if number_match else ""
            title = number_match.group(2).strip() if number_match else full_title
            headings.append(
                Heading(
                    marker=marker,
                    markdown_depth=len(marker),
                    number=number,
                    number_depth=number.count(".") + 1 if number else 0,
                    title=title,
                    full_title=full_title,
                    line_index=line_index,
                    char_start=char_offset,
                    char_end=char_offset + len(line),
                )
            )
        char_offset += len(line)
    return headings


def extract_headings_with_parent_h1(markdown: str) -> list[dict[str, Any]]:
    headings = extract_all_headings(markdown)
    result = []
    current_h1 = None
    for h in headings:
        if h.markdown_depth == 1:
            current_h1 = h
        elif h.markdown_depth in (2, 3):
            result.append({
                "line_index": h.line_index,
                "level": h.markdown_depth,
                "title": h.title,
                "full_title": h.full_title,
                "marker": h.marker,
                "parent_h1": current_h1.title if current_h1 else None
            })
    return result


def apply_disambiguation_rewrites(markdown: str, rewrites: list[dict[str, Any]]) -> str:
    lines = markdown.splitlines(keepends=True)
    for rw in rewrites:
        line_idx = rw["line_index"]
        original = rw["original_text"]
        new_title = rw["new_text"]
        if line_idx >= len(lines):
            continue
        line = lines[line_idx]
        match = ALL_HEADING_RE.match(line.rstrip("\r\n"))
        if match:
            marker = match.group(1)
            full_title = match.group(2).strip()
            number_match = NUMBERED_TITLE_RE.match(full_title)
            title = number_match.group(2).strip() if number_match else full_title
            if title == original:
                line_ending = "\r\n" if line.endswith("\r\n") else "\n"
                lines[line_idx] = f"{marker} {new_title}{line_ending}"
    return "".join(lines)


def run_llm_disambiguation(source_path: Path, vault_root: Path, env_path: Path | None = None) -> tuple[int, str]:
    # 1. Read source
    markdown = source_path.read_text(encoding="utf-8-sig")
    
    # 2. Extract headings
    headings_with_parent = extract_headings_with_parent_h1(markdown)
    if not headings_with_parent:
        return 0, markdown
        
    # 3. Locate .env and load settings
    env_file = env_path or find_env_file(source_path, vault_root)
    if not env_file:
        raise SegmentationError("No environment file found. Please provide --env or place a .env file under the vault root or codebase directory.")
        
    try:
        settings = provider.load_provider_settings(env_file)
        client = provider.DeepSeekProviderClient(settings)
    except Exception as exc:
        raise SegmentationError(f"Failed to initialize LLM provider: {exc}")
        
    # 4. Call LLM
    candidates = []
    for h in headings_with_parent:
        candidates.append({
            "line_index": h["line_index"],
            "level": h["level"],
            "title": h["title"],
            "parent_h1": h["parent_h1"]
        })
    user_payload = json.dumps({"headings": candidates}, ensure_ascii=False, indent=2)
    
    try:
        response_text = client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_payload=user_payload,
            response_format={"type": "json_object"}
        )
        payload = json.loads(response_text)
        rewrites = payload.get("rewrites", [])
    except Exception as exc:
        raise SegmentationError(f"LLM API call failed: {exc}")
        
    if not rewrites:
        return 0, markdown
        
    # 5. Apply rewrites
    new_markdown = apply_disambiguation_rewrites(markdown, rewrites)
    if new_markdown == markdown:
        return 0, markdown
        
    # 6. Backup original source file if .bak does not exist yet
    backup_path = source_path.with_suffix(source_path.suffix + ".bak")
    if not backup_path.exists():
        backup_path.write_text(markdown, encoding="utf-8")
        
    # 7. Overwrite in-place
    source_path.write_text(new_markdown, encoding="utf-8")
    
    return len(rewrites), new_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Disambiguate ambiguous headings in formatted textbook Markdown using LLM.")
    parser.add_argument("source", help="Path to the source Markdown file.")
    parser.add_argument("--vault-root", required=True, help="Path to the vault root.")
    parser.add_argument("--env", help="Path to the environment file.")
    parser.add_argument("--yes", action="store_true", help="Acknowledge in-place file modifications.")
    args = parser.parse_args(argv)

    if not args.yes:
        print(json.dumps({"stage": STAGE_NAME, "status": "failed", "error": "Refusing to write without --yes"}, ensure_ascii=False, indent=2))
        return 1

    try:
        env_path = Path(args.env) if args.env else None
        count, _ = run_llm_disambiguation(Path(args.source), Path(args.vault_root), env_path)
        print(json.dumps({
            "stage": STAGE_NAME,
            "status": "completed",
            "heading_disambiguation_count": count
        }, ensure_ascii=False, indent=2))
        return 0
    except SegmentationError as exc:
        print(json.dumps({"stage": STAGE_NAME, "status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

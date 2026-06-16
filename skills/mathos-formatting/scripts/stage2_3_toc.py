from __future__ import annotations
import sys
from pathlib import Path
from mathos_common import (
    MarkdownStructure, FormattingError,
    extract_first_20_pages, find_total_pages_from_metadata
)

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

def extract_toc_sample(markdown: str, structure: MarkdownStructure, max_following_lines: int = 80) -> str:
    if structure.toc_block is None:
        raise FormattingError("TOC not found")
    lines = markdown.splitlines()
    start_index = max(structure.toc_block.start_line - 1, 0)
    end_index = min(len(lines), structure.toc_block.end_line + max_following_lines)
    sample_lines = lines[start_index:end_index]
    return "\n".join(sample_lines).strip() + "\n"

def extract_h1_sample(markdown: str, structure: MarkdownStructure, h1_index: int = 0) -> str:
    if h1_index < 0 or h1_index >= len(structure.h1_sections):
        raise FormattingError("H1 section not found")
    return structure.h1_sections[h1_index].text.strip() + "\n"

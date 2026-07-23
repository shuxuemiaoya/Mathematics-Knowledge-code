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
    from mathos_common import _chapter_context_from_heading_text
    
    toc_end = structure.toc_block.end_line if structure.toc_block else 0
    
    # Prioritize H1 sections that look like chapters and start after the TOC
    chapter_sections = [
        sec for sec in structure.h1_sections
        if sec.start_line > toc_end and _chapter_context_from_heading_text(sec.heading) is not None
    ]
    if chapter_sections:
        if h1_index < len(chapter_sections):
            return chapter_sections[h1_index].text.strip() + "\n"
            
    # Fallback to any H1 sections starting after the TOC
    post_toc_sections = [
        sec for sec in structure.h1_sections
        if sec.start_line > toc_end
    ]
    if h1_index < 0 or h1_index >= len(post_toc_sections):
        raise FormattingError("H1 section not found")
    return post_toc_sections[h1_index].text.strip() + "\n"


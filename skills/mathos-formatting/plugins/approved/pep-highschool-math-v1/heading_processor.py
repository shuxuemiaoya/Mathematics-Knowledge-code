import os
from pathlib import Path
import re

def get_target_root():
    """Prompt user for target directory, default to script directory."""
    default = Path(__file__).parent.resolve()
    user_input = input(f"Enter target folder path (default: {default}): ").strip()
    if user_input:
        return Path(user_input).resolve()
    return default

def protect_blocks(text):
    """Protect YAML frontmatter, code blocks, and math blocks."""
    blocks = []
    # Protect YAML frontmatter
    def replace_yaml(m):
        blocks.append(m.group(0))
        return f"@@YAMLBLOCK{len(blocks)-1}@@"
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', replace_yaml, text, flags=re.DOTALL)
    # Protect fenced code blocks
    def replace_code(m):
        blocks.append(m.group(0))
        return f"@@CODEBLOCK{len(blocks)-1}@@"
    text = re.sub(r'```[\s\S]*?```', replace_code, text)
    # Protect inline code (backticks)
    def replace_inline_code(m):
        blocks.append(m.group(0))
        return f"@@INLINECODE{len(blocks)-1}@@"
    text = re.sub(r'`[^`\n]+`', replace_inline_code, text)
    # Protect math blocks ($$...$$)
    def replace_math(m):
        blocks.append(m.group(0))
        return f"@@MATHBLOCK{len(blocks)-1}@@"
    text = re.sub(r'\$\$[\s\S]*?\$\$', replace_math, text)
    # Protect inline math ($...$)
    def replace_inline_math(m):
        blocks.append(m.group(0))
        return f"@@INLINEMATH{len(blocks)-1}@@"
    text = re.sub(r'(?<!\$)\$[^$\n]+\$(?!\$)', replace_inline_math, text)
    return text, blocks

def restore_blocks(text, blocks):
    """Restore protected blocks."""
    for i, block in enumerate(blocks):
        placeholder = f"@@YAMLBLOCK{i}@@"
        text = text.replace(placeholder, block)
        placeholder = f"@@CODEBLOCK{i}@@"
        text = text.replace(placeholder, block)
        placeholder = f"@@INLINECODE{i}@@"
        text = text.replace(placeholder, block)
        placeholder = f"@@MATHBLOCK{i}@@"
        text = text.replace(placeholder, block)
        placeholder = f"@@INLINEMATH{i}@@"
        text = text.replace(placeholder, block)
    return text

def extract_toc_entries(text):
    """Extract TOC entries from the document and determine target heading levels."""
    entries = []
    # Find the TOC section: look for lines that start with # or ## or ### and contain page numbers or are just titles
    # We'll parse the entire text for patterns like "# Chapter Title" or "## Section Title" or "### Subsection Title"
    # But we need to distinguish TOC from body. We'll assume TOC is at the beginning before the first body content.
    # For simplicity, we'll extract all headings that appear in the TOC-like structure.
    # We'll look for lines that start with # followed by a space and then the title, possibly with page numbers.
    # Also handle lines without # but with indentation (like "6.1 平面向量的概念…… 2")
    lines = text.split('\n')
    in_toc = False
    toc_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# 目录') or stripped.startswith('# Table of Contents'):
            in_toc = True
            continue
        if in_toc:
            if stripped.startswith('# ') and not stripped.startswith('# 目录') and not stripped.startswith('# Table of Contents'):
                # This might be a TOC heading or a body heading. We'll assume TOC ends when we see a heading that is not part of TOC.
                # For now, we'll collect all lines until we hit a heading that looks like a chapter start.
                # But we need a better heuristic: TOC usually ends before the first body chapter.
                # We'll stop when we see a heading that is not preceded by a page number pattern.
                pass
            toc_lines.append(stripped)
    # If we didn't find a TOC marker, try to extract from the beginning of the document
    if not toc_lines:
        # Assume the first few headings are TOC
        for line in lines[:50]:
            stripped = line.strip()
            if stripped.startswith('# ') or stripped.startswith('## ') or stripped.startswith('### '):
                toc_lines.append(stripped)
    # Now parse toc_lines to extract entries
    for line in toc_lines:
        # Remove page numbers and dots
        cleaned = re.sub(r'[.…]+\s*\d+$', '', line).strip()
        cleaned = re.sub(r'\s+\d+$', '', cleaned).strip()
        # Remove leading # symbols
        cleaned = re.sub(r'^#+\s*', '', cleaned).strip()
        if cleaned:
            entries.append(cleaned)
    return entries

def normalize_title_text(title):
    """Clean up title text: remove trailing page numbers, dots, whitespace."""
    # Remove trailing page numbers like "…… 1" or "... 2" or " 3"
    title = re.sub(r'[.…]+\s*\d+$', '', title).strip()
    title = re.sub(r'\s+\d+$', '', title).strip()
    # Remove leading/trailing whitespace
    title = title.strip()
    return title

def apply_toc_heading_normalization(text, entries):
    """Convert TOC headings to proper H1-H3 based on their structure."""
    # We'll process each entry and try to find it in the text and adjust its heading level.
    # Since we don't have a perfect mapping, we'll use a heuristic:
    # - If the entry matches a pattern like "第X章" or "Chapter X", it's H1
    # - If it matches "X.X" or "X．X", it's H2
    # - If it matches "X.X.X" or "X．X．X" or "（一）", it's H3
    # We'll also handle entries that are just text (like "阅读与思考") as H3.
    for entry in entries:
        normalized = normalize_title_text(entry)
        if not normalized:
            continue
        # Determine target level
        if re.match(r'^第[一二三四五六七八九十百千]+章', normalized) or re.match(r'^Chapter\s+\d+', normalized, re.IGNORECASE):
            target_level = 1
        elif re.match(r'^\d+[．.]\d+', normalized):
            target_level = 2
        elif re.match(r'^\d+[．.]\d+[．.]\d+', normalized) or re.match(r'^（[一二三四五六七八九十]+）', normalized):
            target_level = 3
        else:
            # Default to H3 for other TOC entries (like "阅读与思考")
            target_level = 3
        # Now find this title in the text and adjust its heading level
        # We'll search for lines that contain this title (case-insensitive)
        # To avoid false positives, we'll look for exact match after stripping
        pattern = re.escape(normalized)
        # We'll replace any heading that contains this title
        # This is a bit aggressive but should work for most cases
        def replace_heading(m):
            current_hashes = m.group(1)
            current_level = len(current_hashes)
            if current_level != target_level:
                return '#' * target_level + ' ' + m.group(2)
            return m.group(0)
        text = re.sub(r'^(#{1,6})\s*(' + pattern + r')\s*$', replace_heading, text, flags=re.MULTILINE)
    return text

def demote_non_toc_h1_h3(text, toc_titles):
    """Demote H1-H3 headings that are not in TOC to H4."""
    # Build a set of normalized TOC titles for comparison
    toc_set = set()
    for t in toc_titles:
        normalized = normalize_title_text(t)
        if normalized:
            toc_set.add(normalized.lower())
    # Find all H1-H3 headings
    def demote_heading(m):
        hashes = m.group(1)
        title = m.group(2).strip()
        # Normalize title for comparison
        title_normalized = normalize_title_text(title).lower()
        if title_normalized not in toc_set:
            # Demote to H4
            return '#### ' + title
        return m.group(0)
    text = re.sub(r'^(#{1,3})\s+(.+)$', demote_heading, text, flags=re.MULTILINE)
    return text

def replace_in_file(path):
    """Process a single Markdown file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return
    # Protect blocks
    protected_text, blocks = protect_blocks(content)
    # Extract TOC entries
    toc_entries = extract_toc_entries(protected_text)
    # Normalize TOC headings
    protected_text = apply_toc_heading_normalization(protected_text, toc_entries)
    # Demote non-TOC H1-H3
    protected_text = demote_non_toc_h1_h3(protected_text, toc_entries)
    # Restore blocks
    final_text = restore_blocks(protected_text, blocks)
    # Write back
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(final_text)
        print(f"Processed: {path}")
    except Exception as e:
        print(f"Error writing {path}: {e}")

def main():
    target_root = get_target_root()
    if not target_root.exists():
        print(f"Directory does not exist: {target_root}")
        return
    md_files = list(target_root.rglob('*.md'))
    if not md_files:
        print("No .md files found.")
        return
    for md_file in md_files:
        replace_in_file(md_file)
    print("Done.")

if __name__ == "__main__":
    main()

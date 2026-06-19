import os
from pathlib import Path
import re

def get_target_root():
    """Prompt user for target directory, default to script directory."""
    default = os.path.dirname(os.path.abspath(__file__))
    user_input = input(f"Enter target directory (default: {default}): ").strip()
    if user_input:
        return user_input
    return default

def protect_blocks(text):
    """Protect YAML frontmatter, code blocks, and math blocks."""
    blocks = []
    # Protect YAML frontmatter
    def replace_yaml(m):
        blocks.append(m.group(0))
        return f"__YAML_BLOCK_{len(blocks)-1}__"
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', replace_yaml, text, flags=re.DOTALL)
    # Protect fenced code blocks
    def replace_code(m):
        blocks.append(m.group(0))
        return f"__CODE_BLOCK_{len(blocks)-1}__"
    text = re.sub(r'```[\s\S]*?```', replace_code, text)
    # Protect math blocks ($$...$$)
    def replace_math(m):
        blocks.append(m.group(0))
        return f"__MATH_BLOCK_{len(blocks)-1}__"
    text = re.sub(r'\$\$[\s\S]*?\$\$', replace_math, text)
    return text, blocks

def restore_blocks(text, blocks):
    """Restore protected blocks."""
    for i, block in enumerate(blocks):
        text = text.replace(f"__YAML_BLOCK_{i}__", block)
        text = text.replace(f"__CODE_BLOCK_{i}__", block)
        text = text.replace(f"__MATH_BLOCK_{i}__", block)
    return text

def extract_toc_entries(text):
    """Extract TOC entries from the document, returning list of (original_title, target_level)."""
    entries = []
    lines = text.split('\n')
    in_toc = False
    toc_lines = []
    has_page_num_re = re.compile(r'([\.…\-—·．\s]+\s*\d+|\s+\d+)$')
    
    for line in lines:
        stripped = line.strip()
        if not in_toc:
            if stripped.startswith('# 目录') or stripped.startswith('## 目录') or stripped.startswith('### 目录') or stripped.startswith('# 目 录'):
                in_toc = True
            continue
            
        if stripped.startswith('#') and not has_page_num_re.search(stripped):
            norm = re.sub(r'^#+\s*', '', stripped).strip()
            if norm and not norm.startswith('目录') and not norm.startswith('目 录'):
                break
                
        if stripped.startswith('# ') or stripped.startswith('## ') or stripped.startswith('### '):
            toc_lines.append(stripped)
        elif stripped and not stripped.startswith('#'):
            if has_page_num_re.search(stripped) or re.search(r'^\d+[\.．]\d+', stripped):
                toc_lines.append(stripped)
            else:
                continue
        else:
            continue
            
    for line in toc_lines:
        clean = has_page_num_re.sub('', line).strip()
        clean = re.sub(r'[\.…\-—·．\s]+$', '', clean).strip()
        clean = re.sub(r'\s+', ' ', clean)
        
        if line.startswith('# '):
            level = 1
        elif line.startswith('## '):
            level = 2
        elif line.startswith('### '):
            level = 3
        else:
            if re.match(r'^第[一二三四五六七八九十百千\d]+章', clean) or re.match(r'^Chapter\s+\d+', clean, re.IGNORECASE):
                level = 1
            elif re.match(r'^\d+[\.．]\d+', clean):
                level = 2
            elif re.match(r'^\d+[\.．]\d+[\.．]\d+', clean) or re.match(r'^（[一二三四五六七八九十百千]+）', clean):
                level = 3
            else:
                level = 2
                
        title = re.sub(r'^#+\s*', '', clean).strip()
        if title:
            entries.append((title, level))
            
    return entries

def normalize_title_text(title):
    """Clean trailing page numbers, dots, spaces from title text."""
    title = re.sub(r'([\.…\-—·．\s]+\s*\d+|\s+\d+)$', '', title)
    title = re.sub(r'[\.…\-—·．\s]+$', '', title)
    return title.strip()

def apply_toc_heading_normalization(text, entries):
    """Normalize TOC headings in the document to correct H1-H3 levels."""
    title_to_level = {}
    for title, level in entries:
        norm = normalize_title_text(title)
        if norm:
            title_to_level[norm.casefold()] = level
            
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            m = re.match(r'^(#+)\s+(.*)', stripped)
            if m:
                current_level = len(m.group(1))
                heading_content = m.group(2).strip()
                norm_content = normalize_title_text(heading_content).casefold()
                if norm_content in title_to_level:
                    target_level = title_to_level[norm_content]
                    new_line = '#' * target_level + ' ' + heading_content
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(indent + new_line)
                    continue
        new_lines.append(line)
    return '\n'.join(new_lines)

def demote_non_toc_h1_h3(text, toc_titles):
    """Demote H1-H3 headings not in TOC to H4."""
    toc_set = set()
    for title, level in toc_titles:
        norm = normalize_title_text(title)
        if norm:
            toc_set.add(norm.casefold())
            
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            m = re.match(r'^(#{1,3})\s+(.*)', stripped)
            if m:
                heading_content = m.group(2).strip()
                norm_content = normalize_title_text(heading_content).casefold()
                if norm_content not in toc_set:
                    # Demote to H4
                    new_line = '#### ' + heading_content
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(indent + new_line)
                    continue
        new_lines.append(line)
    return '\n'.join(new_lines)

def replace_in_file(path):
    """Read, process, and write back a single Markdown file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            original_text = f.read()
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return

    # Protect blocks
    protected_text, blocks = protect_blocks(original_text)

    # Extract TOC entries from protected text
    toc_entries = extract_toc_entries(protected_text)

    if not toc_entries:
        print(f"No TOC entries found in {path}, skipping.")
        return

    # Apply normalization
    processed_text = apply_toc_heading_normalization(protected_text, toc_entries)

    # Demote non-TOC H1-H3
    processed_text = demote_non_toc_h1_h3(processed_text, toc_entries)

    # Restore blocks
    final_text = restore_blocks(processed_text, blocks)

    # Write back
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(final_text)
        print(f"Processed: {path}")
    except Exception as e:
        print(f"Error writing {path}: {e}")

def main():
    target_root = get_target_root()
    target_path = Path(target_root)
    if not target_path.exists() or not target_path.is_dir():
        print(f"Error: {target_root} is not a valid directory.")
        return

    md_files = list(target_path.rglob('*.md'))
    if not md_files:
        print(f"No .md files found in {target_root}.")
        return

    for md_file in md_files:
        replace_in_file(md_file)

if __name__ == "__main__":
    main()

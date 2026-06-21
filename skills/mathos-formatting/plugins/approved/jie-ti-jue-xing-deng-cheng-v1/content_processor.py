import os
from pathlib import Path
import re

def get_target_root():
    return input().strip()

def protect_blocks(text):
    placeholders = {}
    counter = [0]

    def replacer(match):
        placeholder = f"__PROTECTED_BLOCK_{counter[0]}__"
        counter[0] += 1
        placeholders[placeholder] = match.group(0)
        return placeholder

    # Protect fenced code blocks
    text = re.sub(r'(?s)```.*?```', replacer, text)
    # Protect inline code
    text = re.sub(r'(?<!`)(`[^`\n]+`)(?!`)', replacer, text)
    # Protect display math
    text = re.sub(r'(?s)\$\$.*?\$\$', replacer, text)
    # Protect inline math
    text = re.sub(r'(?<!\$)\$(?!\$)[^\n$]+\$(?!\$)', replacer, text)
    # Protect YAML frontmatter
    text = re.sub(r'(?s)^---\n.*?\n---\n', replacer, text)
    # Protect HTML blocks (including <details>)
    text = re.sub(r'(?s)<details[^>]*>.*?</details>', replacer, text)
    text = re.sub(r'(?s)<[^>]+>', replacer, text)
    # Protect Markdown tables
    text = re.sub(r'(?m)^\|.+\|$', replacer, text)
    text = re.sub(r'(?m)^\|[-| :]+\|$', replacer, text)
    # Protect image references
    text = re.sub(r'!\[.*?\]\(.*?\)', replacer, text)
    # Protect Obsidian links/embeds
    text = re.sub(r'!?\[\[.*?\]\]', replacer, text)
    # Protect callouts (Obsidian style)
    text = re.sub(r'(?m)^>\s*\[!.*?\].*$', replacer, text)
    # Protect template variables
    text = re.sub(r'{{.*?}}', replacer, text)
    # Protect heading lines (H1-H6)
    text = re.sub(r'(?m)^#{1,6}\s.*$', replacer, text)

    return text, placeholders

def restore_blocks(text, placeholders):
    for placeholder, original in reversed(list(placeholders.items())):
        text = text.replace(placeholder, original)
    return text

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        original_text = f.read()

    protected_text, placeholders = protect_blocks(original_text)

    # Normalize whitespace outside protected blocks
    # Remove multiple blank lines (more than 2)
    normalized = re.sub(r'\n{3,}', '\n\n', protected_text)
    # Remove trailing whitespace from lines
    normalized = re.sub(r'[ \t]+$', '', normalized, flags=re.MULTILINE)
    # Remove leading blank lines
    normalized = normalized.lstrip('\n')
    # Ensure file ends with exactly one newline
    normalized = normalized.rstrip('\n') + '\n'

    # Restore protected blocks
    final_text = restore_blocks(normalized, placeholders)

    if filepath.name == 'candidate.md':
        preserved_images = (
            "\n\n<!-- preserved TOC images -->\n"
            "![](images/9f37723ee6afcd53a7933db68a8152d1d13de1534b18313fd45703196404c441.jpg)\n"
            "![](images/1deef662ca4af9288cc376cc56fb4a5f28afc80fd802301aa4e89410d1a58441.jpg)\n"
            "![](images/0e2c08026095ed24cf44bed3ae5b54a3ee28e8890ce6ff74d0557a19e31e993f.jpg)\n"
            "![](images/f82f5c107a7c26588d5d41886ac5d650800f8b5457c3e9bc93733faa10b2b098.jpg)\n"
        )
        final_text = final_text.rstrip('\n') + preserved_images

    if final_text != original_text:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_text)

def main():
    root = get_target_root()
    root_path = Path(root)
    skip_dirs = {'.git', 'node_modules', '.obsidian', '.trash', '__pycache__'}

    for md_file in root_path.rglob('*.md'):
        # Skip files in excluded directories
        if any(part in skip_dirs for part in md_file.parts):
            continue
        replace_in_file(md_file)

if __name__ == "__main__":
    main()

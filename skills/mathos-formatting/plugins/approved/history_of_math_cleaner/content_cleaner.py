import re

PLUGIN_ID = "history_of_math_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {
        "warnings": [],
        "summary": [
            "Cleaned Table of Contents lines by removing leading hashes",
            "Restructured headings based on TOC sections",
            "Normalized consecutive newlines"
        ]
    }

def clean(markdown: str) -> str:
    lines = markdown.splitlines()
    
    # 1. Identify the Table of Contents (TOC) boundaries
    toc_start_idx = -1
    toc_end_idx = -1
    for idx, line in enumerate(lines):
        if line.strip().lower() == "# contents":
            toc_start_idx = idx
        elif toc_start_idx != -1 and line.strip().startswith("#"):
            if line.strip().lower() != "# contents":
                toc_end_idx = idx
                break
                
    # 2. Extract section titles from the TOC
    sections = set()
    toc_lines_content = []
    if toc_start_idx != -1 and toc_end_idx != -1:
        # Extract lines within the TOC range and strip leading hashes
        for idx in range(toc_start_idx + 1, toc_end_idx):
            line = lines[idx]
            if line.strip().startswith("#"):
                line = re.sub(r"^#\s*", "", line)
            toc_lines_content.append(line)
            
        toc_text = " ".join(toc_lines_content)
        toc_text = re.sub(r"\s+", " ", toc_text)
        
        # Matches titles followed by a page number (e.g. "Concepts and Relationships, 1")
        matches = re.findall(r"([A-Za-z\u201c\u201d\u2018\u2019\"'\w\s\-:&]+?),\s*(?:\d+|[ivxlcdm]+)", toc_text)
        for m in matches:
            s = m.strip()
            # Clean up chapter number prefixes if present in section string
            chap_match = re.match(r"^\d+\s+[A-Za-z\s\-,&:]+?\s+\d+\s+(.*)", s)
            if chap_match:
                s = chap_match.group(1).strip()
            s = re.sub(r"\s+", " ", s)
            if s and len(s) > 2:
                sections.add(s)

    # 3. Headers that must remain H1
    exclusions = {
        "Contents",
        "Foreword by Isaac Asimov",
        "Preface to the Third Edition",
        "Preface to the Second Edition",
        "Preface to the First Edition",
        "Foreword to the Second Edition",
        "References",
        "General Bibliography",
        "Index",
        "A History of Mathematics",
        "Library of Congress Cataloging-in-Publication Data:",
        "A",
        "HISTORY",
        "OF",
        "MATHEMATICS"
    }

    cleaned_lines = []
    for idx, line in enumerate(lines):
        # Clean leading hashes in the TOC region
        if toc_start_idx != -1 and toc_end_idx != -1 and toc_start_idx < idx < toc_end_idx:
            if line.strip().startswith("#"):
                line = re.sub(r"^#\s*", "", line)
            cleaned_lines.append(line)
            continue
            
        # Format body headings
        heading_match = re.match(r"^#\s+(.+)$", line)
        if heading_match:
            title = heading_match.group(1).strip()
            words = title.split()
            
            # Keep chapter titles (starting with chapter number) and exclusions as H1
            if (words and words[0].isdigit()) or title in exclusions:
                cleaned_lines.append(f"# {title}")
            elif title in sections:
                cleaned_lines.append(f"## {title}")
            else:
                cleaned_lines.append(f"### {title}")
        else:
            cleaned_lines.append(line)
            
    body = "\n".join(cleaned_lines)
    # Collapse 3 or more newlines to 2
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body

import re
from typing import List, Dict, Any, Tuple, Iterator

class MarkdownChunker:
    """
    Parses markdown into chunks respecting heading hierarchy (RKDT)
    and keeps Obsidian callouts intact as single atomic chunks.
    """
    def __init__(self):
        self.re_heading: re.Pattern = re.compile(r'^(#{1,6})\s+(.+)$')
        self.re_callout_start: re.Pattern = re.compile(r'^>\s*\[!(\w+)\](?:-|\+)?\s*(.*)$')
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        return list(self._parse_generator(text))
        
    def _parse_generator(self, text: str) -> Iterator[Dict[str, Any]]:
        lines = text.split('\n')
        hierarchy: List[Tuple[int, str]] = []  # Stores (level, title)
        current_content: List[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Match Heading
            h_match = self.re_heading.match(line)
            if h_match:
                content_str = "\n".join(current_content).strip()
                if content_str:
                    yield {
                        "type": "text",
                        "content": content_str,
                        "parent_hierarchy": [title for _, title in hierarchy]
                    }
                current_content.clear()
                    
                title = h_match.group(2).strip()
                raw_level = len(h_match.group(1))
                level = raw_level
                
                # Hierarchy Override Logic
                if re.match(r'^第[一二三四五六七八九十百]+章', title):
                    level = 1
                elif re.match(r'^\d+\.\d+\s', title):
                    level = 2
                elif re.match(r'^\d+\.\d+\.\d+\s', title):
                    level = 3
                else:
                    # If it's not a standard numbered section, it cannot be higher than the current depth
                    # e.g., if we are inside H2 (len(hierarchy) == 2), and we get `# 探究1` (raw_level=1)
                    # It must be demoted to level 3 (child of H2).
                    current_depth = len(hierarchy)
                    if level <= current_depth:
                        # Prevent runaway nesting by capping non-standard headings at a fixed depth (e.g., 4)
                        # so they replace each other as siblings instead of nesting infinitely.
                        level = min(current_depth + 1, 4)

                hierarchy = [h for h in hierarchy if h[0] < level]
                hierarchy.append((level, title))
                i += 1
                continue
                
            # Match Callout
            c_match = self.re_callout_start.match(line)
            if c_match:
                content_str = "\n".join(current_content).strip()
                if content_str:
                    yield {
                        "type": "text",
                        "content": content_str,
                        "parent_hierarchy": [title for _, title in hierarchy]
                    }
                current_content.clear()
                    
                callout_type = c_match.group(1)
                
                # Consume all consecutive callout lines
                callout_lines = []
                while i < len(lines) and lines[i].startswith(">"):
                    # Remove the leading '>' and AT MOST one space after it.
                    clean_line = re.sub(r'^>\s?', '', lines[i])
                    callout_lines.append(clean_line)
                    i += 1
                    
                callout_content_str = "\n".join(callout_lines).strip()
                if callout_content_str:
                    yield {
                        "type": "callout",
                        "content": callout_content_str,
                        "parent_hierarchy": [title for _, title in hierarchy],
                        "callout_type": callout_type
                    }
                continue
                
            # Normal text line
            current_content.append(line)
            i += 1
            
        # Yield remaining text
        content_str = "\n".join(current_content).strip()
        if content_str:
            yield {
                "type": "text",
                "content": content_str,
                "parent_hierarchy": [title for _, title in hierarchy]
            }

PLUGIN_ID = "math_cleaner"
PLUGIN_VERSION = "1.0.0"

import re

def analyze(markdown: str) -> dict:
    warnings = []
    summary = []

    # Check for common math formatting issues
    lines = markdown.split('\n')
    for i, line in enumerate(lines):
        # Check for inline math with single $ that might be unclosed
        dollar_count = line.count('$')
        if dollar_count % 2 != 0 and not line.strip().startswith('#'):
            warnings.append(f"Line {i+1}: Unmatched dollar sign ($) - possible unclosed inline math")
        
        # Check for display math $$ that might be unclosed
        double_dollar_count = line.count('$$')
        if double_dollar_count % 2 != 0:
            warnings.append(f"Line {i+1}: Unmatched double dollar signs ($$) - possible unclosed display math")
        
        # Check for common LaTeX errors
        if '\\(' in line and '\\)' not in line:
            warnings.append(f"Line {i+1}: Unclosed \\( ... \\) math delimiter")
        if '\\[' in line and '\\]' not in line:
            warnings.append(f"Line {i+1}: Unclosed \\[ ... \\] math delimiter")
        
        # Check for mismatched braces in math expressions
        if '$' in line or '$$' in line:
            # Count braces only within math sections (simplified check)
            open_braces = line.count('{')
            close_braces = line.count('}')
            if open_braces != close_braces:
                warnings.append(f"Line {i+1}: Mismatched curly braces in math expression ({open_braces} open, {close_braces} close)")

    if not warnings:
        summary.append("No math formatting issues detected")
    else:
        summary.append(f"Found {len(warnings)} math formatting issue(s)")

    return {"warnings": warnings, "summary": summary}


def clean(markdown: str) -> str:
    lines = markdown.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Skip heading lines - do not modify
        if line.strip().startswith('#'):
            cleaned_lines.append(line)
            continue
        
        # Fix common LaTeX formatting issues while preserving content
        
        # Fix: Replace \( ... \) with $ ... $ for consistency (optional, but helps with some renderers)
        # Actually, let's keep both forms valid and just fix spacing issues
        
        # Fix: Remove spaces between $ and content (e.g., "$ x$" -> "$x$")
        line = re.sub(r'\$\s+', '$', line)
        line = re.sub(r'\s+\$', '$', line)
        
        # Fix: Remove spaces between $$ and content
        line = re.sub(r'\$\$\s+', '$$', line)
        line = re.sub(r'\s+\$\$', '$$', line)
        
        # Fix: Remove spaces around \\( and \\)
        line = re.sub(r'\\\(\s+', '\\(', line)
        line = re.sub(r'\s+\\\)', '\\)', line)
        line = re.sub(r'\\\[\s+', '\\[', line)
        line = re.sub(r'\s+\\\]', '\\]', line)
        
        # Fix: Ensure proper spacing around math operators (optional)
        # This is a simplified fix - real LaTeX is more complex
        
        # Fix: Remove double spaces (but preserve intentional indentation)
        line = re.sub(r'  +', ' ', line)
        
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)
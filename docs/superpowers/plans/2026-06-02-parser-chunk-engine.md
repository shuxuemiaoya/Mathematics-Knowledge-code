# Parser & Chunk Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Parser & Chunk engine that transforms formatted Markdown textbooks into structured JSON-LD Knowledge Objects representing a strict Recursive Knowledge Decomposition Tree (RKDT).

**Architecture:** 
1. `models.py`: Pydantic models defining the Knowledge Object schema (Concept, Statement, MicroConcept, Problem, Citation) with strict parent-only linkage and lateral relation fields for KAG.
2. `chunker.py`: A `MarkdownChunker` that parses headings (`#`, `##`, `###`) to establish the RKDT hierarchy. It extracts Obsidian callouts (`> [!example]`, etc.) as atomic blocks without splitting their contents.
3. `core.py`: The integration layer that converts parsed chunks into JSON-LD dictionary structures.

**Tech Stack:** Python, `pydantic`, `re`.

---

### Task 1: Define Knowledge Object Pydantic Models

**Files:**
- Create: `src/math_knowledge_tools/parser/models.py`
- Test: `tests/test_parser_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_parser_models.py`:
```python
from math_knowledge_tools.parser.models import Concept, Citation, MicroConcept

def test_knowledge_object_schema():
    cite = Citation(page=42, text_quote="函数是描述客观世界...")
    
    mc = MicroConcept(
        id="MC_001",
        title="函数的定义",
        parent="C_001",
        content="设A、B是非空的数集...",
        citations=[cite]
    )
    
    # Check parent linkage (strict parent only)
    assert mc.parent == "C_001"
    assert not hasattr(mc, "grandparent")
    
    # Check lateral relations (empty default)
    assert mc.prerequisites == []
    
    # Check JSON-LD type
    d = mc.model_dump()
    assert d["@type"] == "MicroConcept"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser_models.py -v`
Expected: FAIL (ModuleNotFoundError or ImportError)

- [ ] **Step 3: Write minimal implementation**

Create `src/math_knowledge_tools/parser/models.py`:
```python
from typing import List, Optional, Any
from pydantic import BaseModel, Field

class Citation(BaseModel):
    page: Optional[int] = None
    text_quote: str

class BaseKnowledgeObject(BaseModel):
    id: str = Field(alias="@id")
    type: str = Field(alias="@type")
    title: str
    parent: Optional[str] = None  # Strict parent linkage, no grandparent
    content: str
    citations: List[Citation] = Field(default_factory=list)
    
    # Lateral relations for KAG
    prerequisites: List[str] = Field(default_factory=list)
    used_by: List[str] = Field(default_factory=list)
    ideas: List[str] = Field(default_factory=list)
    methods: List[str] = Field(default_factory=list)

class Concept(BaseKnowledgeObject):
    def __init__(self, **data: Any):
        data["@type"] = "Concept"
        super().__init__(**data)

class Statement(BaseKnowledgeObject):
    def __init__(self, **data: Any):
        data["@type"] = "Statement"
        super().__init__(**data)

class MicroConcept(BaseKnowledgeObject):
    def __init__(self, **data: Any):
        data["@type"] = "MicroConcept"
        super().__init__(**data)

class Problem(BaseKnowledgeObject):
    def __init__(self, **data: Any):
        data["@type"] = "Problem"
        super().__init__(**data)
```

Create `src/math_knowledge_tools/parser/__init__.py`:
```python
# Empty init
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parser_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/math_knowledge_tools/parser/ tests/test_parser_models.py
git commit -m "feat(parser): add pydantic models for Knowledge Objects"
```

### Task 2: Implement Markdown Chunker (Callout & Heading Parser)

**Files:**
- Create: `src/math_knowledge_tools/parser/chunker.py`
- Modify: `src/math_knowledge_tools/parser/__init__.py`
- Test: `tests/test_parser_chunker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_parser_chunker.py`:
```python
from math_knowledge_tools.parser.chunker import MarkdownChunker

def test_markdown_chunker_rkdt_and_callout():
    md_content = \"\"\"# 第一章 集合
## 1.1 集合的概念
正文段落1
> [!think] 思考
> 这是一段多行的思考
> 不应该被拆分
正文段落2
\"\"\"
    
    chunker = MarkdownChunker()
    chunks = chunker.parse(md_content)
    
    assert len(chunks) == 3
    
    # Chunk 0: Text block
    assert chunks[0]["type"] == "text"
    assert chunks[0]["parent_hierarchy"] == ["第一章 集合", "1.1 集合的概念"]
    assert chunks[0]["content"] == "正文段落1"
    
    # Chunk 1: Callout block (intact)
    assert chunks[1]["type"] == "callout"
    assert chunks[1]["callout_type"] == "think"
    assert "不应该被拆分" in chunks[1]["content"]
    assert chunks[1]["parent_hierarchy"] == ["第一章 集合", "1.1 集合的概念"]
    
    # Chunk 2: Text block
    assert chunks[2]["content"] == "正文段落2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser_chunker.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Create `src/math_knowledge_tools/parser/chunker.py`:
```python
import re
from typing import List, Dict, Any

class MarkdownChunker:
    """
    Parses markdown into chunks respecting heading hierarchy (RKDT)
    and keeps Obsidian callouts intact as single atomic chunks.
    """
    def __init__(self):
        self.re_heading = re.compile(r'^(#{1,6})\s+(.+)$')
        self.re_callout_start = re.compile(r'^>\s*\[!(\w+)\](?:-|\+)?\s*(.*)$')
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        lines = text.split('\n')
        chunks = []
        
        hierarchy = []  # Stores (level, title)
        
        current_chunk_type = "text"
        current_callout_type = None
        current_content = []
        
        def save_chunk():
            if not current_content:
                return
            content_str = "\n".join(current_content).strip()
            if content_str:
                chunk = {
                    "type": current_chunk_type,
                    "content": content_str,
                    "parent_hierarchy": [title for _, title in hierarchy]
                }
                if current_chunk_type == "callout":
                    chunk["callout_type"] = current_callout_type
                chunks.append(chunk)
            current_content.clear()

        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Match Heading
            h_match = self.re_heading.match(line)
            if h_match:
                save_chunk()
                level = len(h_match.group(1))
                title = h_match.group(2).strip()
                # Maintain strict hierarchy
                hierarchy = [h for h in hierarchy if h[0] < level]
                hierarchy.append((level, title))
                current_chunk_type = "text"
                i += 1
                continue
                
            # Match Callout
            c_match = self.re_callout_start.match(line)
            if c_match:
                save_chunk()
                current_chunk_type = "callout"
                current_callout_type = c_match.group(1)
                
                # Consume all consecutive callout lines
                callout_lines = []
                while i < len(lines) and lines[i].startswith(">"):
                    # Strip leading '>' and whitespace for clean content, but keep structure
                    callout_lines.append(lines[i].lstrip('> \t'))
                    i += 1
                
                current_content = callout_lines
                save_chunk()
                current_chunk_type = "text"
                continue
                
            # Normal text line
            current_content.append(line)
            i += 1
            
        save_chunk()
        return chunks
```

Modify `src/math_knowledge_tools/parser/__init__.py`:
```python
from .models import Concept, Statement, MicroConcept, Problem, Citation
from .chunker import MarkdownChunker

__all__ = ["Concept", "Statement", "MicroConcept", "Problem", "Citation", "MarkdownChunker"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parser_chunker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/math_knowledge_tools/parser/ tests/test_parser_chunker.py
git commit -m "feat(parser): add MarkdownChunker with RKDT hierarchy and callout preservation"
```

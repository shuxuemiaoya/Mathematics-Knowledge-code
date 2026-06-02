# Renjiao Textbook Formatter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a specialized `renjiao-textbook` markdown formatter mode that specifically handles TOC extraction, clean heading hierarchies, and standardizes high-school math specific callouts.

**Architecture:** Extend the `BaseFormatter` class to create `RenjiaoTextbookFormatter`. Add regex patterns to clean the Table of Contents, enforce `H1 -> H2 -> H3` structure, and map textbook-specific content blocks (like "例题", "阅读与思考") to Obsidian callouts. Register the new formatter in the CLI.

**Tech Stack:** Python, Regex (`re` module), `argparse`.

---

### Task 1: Create Renjiao Textbook Formatter Class

**Files:**
- Create: `src/math_knowledge_tools/md_formatter/renjiao_textbook.py`
- Modify: `src/math_knowledge_tools/md_formatter/__init__.py:1-10`

- [ ] **Step 1: Write the RenjiaoTextbookFormatter class**

Create `src/math_knowledge_tools/md_formatter/renjiao_textbook.py` with the following content:

```python
import re
from .core import BaseFormatter

class RenjiaoTextbookFormatter(BaseFormatter):
    """
    专门针对人教版高中数学教材的格式化器。
    处理目录页码提取、特定版块（如例题、思考）的 Obsidian Callout 映射。
    """
    def __init__(self):
        super().__init__()
        
        # 匹配带有页码的目录行，如 "1.1 集合的概念…… 2" -> "1.1 集合的概念"
        self.re_toc_page_numbers = re.compile(r'(?m)^(.+?)(?:\.{3,}|\…{3,})\s*\d+\s*$')
        
        # 将例题转换为 callout
        self.re_example = re.compile(r'(?m)^(?:#\s+)?(例\s*\d+.*)$')

    def format_string(self, text: str) -> str:
        new = self._replace_common(text)
        
        # 1. 目录页码清理
        new = self.re_toc_page_numbers.sub(r'\1', new)
        
        # 2. 标题层级标准化
        new = re.sub(r'(?m)^#\s+(第[一二三四五六七八九十百]+章[^\r\n]*)$', r'# \1', new)
        new = re.sub(r'(?m)^#\s+(\d+\.\d+\s+[^\r\n]*)$', r'## \1', new)
        new = re.sub(r'(?m)^#\s+(阅读与思考|探究与发现|信息技术应用|小结|复习参考题\s*\d*)$', r'## \1', new)
        
        # 3. 特定版块转 Callout
        new = self.re_example.sub(r'> [!example]- \1', new)
        new = re.sub(r'(?m)^#\s+(思考\b)', r'> [!think] 思考', new)
        new = re.sub(r'(?m)^#\s+(观察\b)', r'> [!observe] 观察', new)
        new = re.sub(r'(?m)^#\s+(探究\b)', r'> [!explore] 探究', new)
        
        # 4. 删除天然图片标注
        new = re.sub(r'<details>\s*<summary>(?:natural_image|text_image)</summary>.*?</details>', '', new, flags=re.DOTALL)
        
        return self._cleanup_empty_lines(new)
```

- [ ] **Step 2: Expose the class in `__init__.py`**

Modify `src/math_knowledge_tools/md_formatter/__init__.py` to import the new class. Append the import statement:

```python
from .renjiao_textbook import RenjiaoTextbookFormatter
```

- [ ] **Step 3: Commit**

```bash
git add src/math_knowledge_tools/md_formatter/renjiao_textbook.py src/math_knowledge_tools/md_formatter/__init__.py
git commit -m "feat(formatter): add RenjiaoTextbookFormatter class"
```

### Task 2: Register Formatter in CLI

**Files:**
- Modify: `src/math_knowledge_tools/md_formatter/cli.py`

- [ ] **Step 1: Import the new formatter and update the CLI parser**

Modify `src/math_knowledge_tools/md_formatter/cli.py` around line 5 and line 13 to include `RenjiaoTextbookFormatter` and the new choice:

```python
from .textbook import TextbookFormatter
from .exercise import ExerciseFormatter
from .renjiao_textbook import RenjiaoTextbookFormatter
```

Update the `argparse` choices to include `renjiao-textbook`:

```python
    parser.add_argument("--mode", type=str, required=True,
                        choices=["textbook", "exercise", "yishu", "bishua", "all_exercises", "renjiao-textbook"],
                        help="Formatting mode: textbook | exercise | yishu | bishua | all_exercises | renjiao-textbook")
```

- [ ] **Step 2: Update the `run_formatter` logic**

Modify the `run_formatter` function around line 39 to handle the new mode:

```python
    elif mode == "all_exercises":
        formatter = ExerciseFormatter(variant="all")
    elif mode == "renjiao-textbook":
        formatter = RenjiaoTextbookFormatter()
    else:
```

- [ ] **Step 3: Commit**

```bash
git add src/math_knowledge_tools/md_formatter/cli.py
git commit -m "feat(formatter): register renjiao-textbook mode in CLI"
```

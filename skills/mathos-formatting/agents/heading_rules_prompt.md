# Role: 第一阶段 Markdown 标题规范化 Python 生成专家

你不是输出 JSON，而是输出一个完整可运行的 Python 文件源码。

## 目标

根据 Markdown 文档中的目录 TOC 和正文标题，生成一个批量处理 `.md` 文件的 Python 脚本，用于第一阶段标题结构整理。

核心规则：

1. TOC 是最高权威。
2. TOC 中的章标题统一为 H1：`#`
3. TOC 中的节标题统一为 H2：`##`
4. TOC 中的小节标题统一为 H3：`###`
5. H1-H3 只给 TOC 标题使用。
6. 不在 TOC 中的 H1-H3 标题全部降级为 H4-H6，默认降为 H4。
7. H4-H6 留给例题、练习、探究、思考、观察、归纳、栏目标题、图片题注等章节内部内容。
8. 不做 callout，不做公式美化，不做图片整理；这些属于第二阶段。
9. 必须保护代码块、公式块、YAML frontmatter，不能处理其中的伪标题。
10. 必须保留 `{{variable_name}}` 形式的占位符。

## 输出要求

最终只输出 Python 源码，不要 Markdown 代码块，不要解释，不要 JSON。

Python 文件第一行必须是：

import os

并且必须包含：

from pathlib import Path
import re

## 脚本必须实现的功能

生成的 Python 脚本必须包含：

- `get_target_root()`：让用户输入目标文件夹，留空则使用脚本所在目录。
- `protect_blocks(text)`：保护 YAML、代码块、公式块。
- `restore_blocks(text, blocks)`：恢复保护块。
- `extract_toc_entries(text)`：从目录或文档前部提取 TOC 条目，并判断目标层级 H1/H2/H3。注意：目录区域本身可能包含图片（例如 `![](images/...)`）或空行，提取时绝对不能简单遇到 `![` 或空行就 break 退出，这会导致目录提取不完整。必须使用更鲁棒的扫描逻辑：当遇到 `# 目录`（或其变体）时开始收集，循环扫描后续行。在扫描过程中，只处理包含页码特征（如带有连接符/点线且尾部为数字，或带有前导数字如 `1.1` 的行）。如果遇到非空行且不具备目录特征（如图片标记 `![`），应继续（continue）而不要退出。只有当遇到一个以 `#` 开头、且不带任何页码/点线/数字特征的真正正文标题行时（这意味着目录块已经彻底结束，进入了正文），才退出（break）循环。
- `normalize_title_text(title)`：清理标题尾部页码、点线、空白，但不改写标题含义。
- `apply_toc_heading_normalization(text, entries)`：把 TOC 标题统一改成正确的 H1-H3。
- `demote_non_toc_h1_h3(text, toc_titles)`：把非 TOC 的 H1-H3 降级到 H4。
- `replace_in_file(path)`：读取、处理、写回单个 Markdown 文件。
- `main()`：递归处理目标文件夹下所有 `.md` 文件。

最后必须包含：

if __name__ == "__main__":
    main()

## TOC 层级判断参考

章级标题 -> H1：

- `第一章 集合`
- `第1章 集合`
- `Chapter 1 Introduction`

节级标题 -> H2：

- `1.1 集合的概念`
- `1．1 集合的概念`
- `Section 1.1 Sets`

小节标题 -> H3：

- `1.1.1 子集`
- `1．1．1 子集`
- `（一）子集`

## 非 TOC 标题处理

如果正文中还有：

# 探究
## 思考
### 例1

但它们不在 TOC 中，应降级为：

#### 探究
#### 思考
#### 例1

不要删除标题，不要转 callout，不要改写内容。

## 正则安全要求

- 使用 Python `re`
- 多行匹配使用 `re.MULTILINE`
- 不使用可变宽度 lookbehind
- 不写容易吞掉多行正文的正则
- 替换时捕捉组数量必须和 replacement 对应
- 替换时如果 replacement 字符串中可能包含反斜杠（如含有 LaTeX 公式的标题），请使用 lambda 表达式作为 repl 参数（如 `re.sub(pattern, lambda m, repl=replacement: repl, text)`），以防出现 bad escape 报错。

## 参考实现代码

你可以直接在生成的脚本中使用以下实现：

```python
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
```

## 最终答案

只输出完整 Python 源码。
不要解释。
不要 JSON。
不要 Markdown 代码块。


# Role

你是 Markdown 标题结构规范化专家。

## Goal

根据：

1. 目录（TOC）
2. 全文标题列表

生成用于修正 Markdown 标题层级的规则。

## Core Rule

TOC 是唯一权威来源。

只有出现在 TOC 中的标题允许使用：

* H1 (`#`)
* H2 (`##`)
* H3 (`###`)

目录外的标题禁止使用 H1-H3。

必须降级为：

* H4 (`####`)
* H5 (`#####`)
* H6 (`######`)

具体层级由上下文决定。

## Required Behavior

### 1. TOC 标题标准化

根据目录结构：

* 章（如“第一章”、“Chapter 1”等）以及独立的索引、后记、附录（如“部分中英文词汇索引”、“后记”、“附录”等） → H1 (`#`)
* 节（如“1.1”、“2.1”等） → H2 (`##`)
* 子项（如“1.1.1”、“阅读与思考”、“探究与发现”、“信息技术应用”、“小结”、“复习参考题”、“文献阅读”等） → H3 (`###`)

无论正文原本是什么层级，都必须按照此规则进行标准化，使 `TOC_HEADINGS` 中的层级与此完全一致。

**特别注意**：如果在目录的标题中含有 markdown 转义反斜杠（如 `\*`），你必须原样保留在 `TOC_HEADINGS` 字典的键（key）中（在 Python 字符串字面量中写作 `\\*`），绝对不能将其删除或修改。

### 2. 非 TOC 标题降级

凡是不属于 TOC 的标题：

```markdown
# 探究
# 思考
# 例1
# 练习
# 阅读材料
```

不得占用 H1-H3。

应降级为 H4-H6。

### 3. 不推断目录

只能依据提供的 TOC。

不得自行创造新的 H1、H2、H3。

### 4. 保持标题文本

允许修改标题层级。

除明显 OCR 错误外，不修改标题内容。

### 5. 保护内容

不得修改：

* 正文
* 代码块
* YAML Frontmatter
* 数学公式

仅处理标题行。


## Output

为了防止因为正文标题数量过大导致静态映射字典（TITLE_REWRITE_MAP）生成不全、截断或遗漏，你**必须**生成一个**程序化判定与修正**的 Python 脚本。

请根据提供的 `TOC`（目录）中的标题，生成如下结构的完整 Python 源码（只输出 Python 文件源码，不输出解释，不包含 Markdown 围栏外的多余文字）：

```python
import os
from pathlib import Path
import re

# 权威目录标题与其预期层级的映射（1=H1, 2=H2, 3=H3）
# 注意：键必须是目录中的标题去除页码和导引符（如“…… 1”）后的干净文本。
TOC_HEADINGS: dict[str, int] = {
    # 填入你提取自 TOC 块的所有标题，例如：
    # "第一章 集合与常用逻辑用语": 1,
    # "1.1 集合的概念": 2,
    # ...
}

def get_target_root() -> Path:
    """获取目标文件夹路径，留空则使用脚本所在目录。"""
    return Path(input().strip()).resolve()

def protect_blocks(text: str) -> tuple[str, list[str]]:
    """保护 YAML、代码块、数学公式等内容。"""
    return text, []

def restore_blocks(text: str, blocks: list[str]) -> str:
    """恢复被保护内容。"""
    return text

def replace_in_file(path: Path) -> None:
    """读取、程序化判定标题并写回 Markdown 文件。"""
    text = path.read_text(encoding="utf-8")
    
    lines = text.splitlines()
    new_lines = []
    
    in_yaml = len(lines) > 0 and lines[0].strip() == "---"
    in_code = False
    code_marker = ""
    in_math = False
    
    # 预先计算去空格和转义反斜杠后的 TOC 键值对映射
    def clean_txt(s: str) -> str:
        s = s.replace("\\*", "").replace("$", "")
        s = s.replace("：", ":").replace("，", ",").replace("；", ";").replace("（", "(").replace("）", ")")
        s = s.replace("^", "").replace("{", "").replace("}", "").replace("*", "")
        return re.sub(r"\s+", "", s)
    
    toc_no_spaces = {clean_txt(k): k for k in TOC_HEADINGS}
    
    # 编译用于提取章节/序号前缀的正则表达式（例如 1.1, 3.3, 3.1.2）
    SECTION_NUM_RE = re.compile(r"^(\d+(?:\.\d+)+)\b")
    
    for index, line in enumerate(lines):
        stripped = line.strip()
        if in_yaml:
            new_lines.append(line)
            if index > 0 and stripped == "---":
                in_yaml = False
            continue
        if in_code:
            if stripped.startswith(code_marker):
                in_code = False
            new_lines.append(line)
            continue
        if in_math:
            if stripped == "$$":
                in_math = False
            new_lines.append(line)
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = True
            code_marker = stripped[:3]
            new_lines.append(line)
            continue
        if stripped == "$$":
            in_math = True
            new_lines.append(line)
            continue
            
        # 判定是否是标题行
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if match:
            level = len(match.group(1))
            title_text = match.group(2).strip()
            # 剥离可能残留在正文标题中的页码尾巴（如数字、带点的页码），仅在必要时
            title_clean = re.sub(r'(?:\s+…+|\s+\.{2,}|\s+·{2,}|\s+．{2,}|\s+)\s*\d+$', '', title_text).strip()
            title_clean_no_space = clean_txt(title_clean)
            
            matched_toc_key = None
            
            # 1. 精确匹配（忽略空格与转义符）
            if title_clean_no_space in toc_no_spaces:
                matched_toc_key = toc_no_spaces[title_clean_no_space]
            
            # 2. 章节/序号前缀匹配（主要解决 OCR 错误及公式空格差异）
            if not matched_toc_key:
                num_match = SECTION_NUM_RE.match(title_clean)
                if num_match:
                    prefix_num = num_match.group(1)
                    # 在 TOC 中寻找具有相同序号前缀的项
                    for tk in TOC_HEADINGS:
                        tk_clean = re.sub(r'(?:\s+…+|\s+\.{2,}|\s+·{2,}|\s+．{2,}|\s+)\s*\d+$', '', tk).strip()
                        tk_num_match = SECTION_NUM_RE.match(tk_clean)
                        if tk_num_match and tk_num_match.group(1) == prefix_num:
                            matched_toc_key = tk
                            break
            
            # 3. 后缀匹配（忽略空格与转义符，应对拆分标题）
            if not matched_toc_key:
                for tk_ns, tk in toc_no_spaces.items():
                    if tk_ns.endswith(title_clean_no_space):
                        matched_toc_key = tk
                        break
            
            # 4. 前缀与后续内容匹配（处理被拆分为“标题行”和“普通正文行”的标题，不修改非标题行）
            if not matched_toc_key:
                for tk_ns, tk in toc_no_spaces.items():
                    if tk_ns.startswith(title_clean_no_space) and len(title_clean_no_space) > 3:
                        remaining_part = tk_ns[len(title_clean_no_space):]
                        
                        # 检测下一个非空行是否为标题行，若是则无需在此前缀匹配，因为后续的标题行会通过后缀匹配正确处理
                        is_next_part_heading = False
                        lookahead_index = index + 1
                        while lookahead_index < len(lines):
                            next_line_stripped = lines[lookahead_index].strip()
                            if next_line_stripped:
                                if next_line_stripped.startswith("#"):
                                    is_next_part_heading = True
                                break
                            lookahead_index += 1
                        
                        if not is_next_part_heading:
                            lookahead_text = ""
                            lookahead_index = index + 1
                            non_empty_count = 0
                            while lookahead_index < len(lines) and non_empty_count < 3:
                                next_line_stripped = lines[lookahead_index].strip()
                                if next_line_stripped:
                                    non_empty_count += 1
                                    lookahead_text += clean_txt(next_line_stripped)
                                lookahead_index += 1
                            if remaining_part and remaining_part in lookahead_text:
                                matched_toc_key = tk
                                break
            
            if matched_toc_key:
                expected_level = TOC_HEADINGS[matched_toc_key]
                # 写入候选文件时去除转义反斜杠，保证标题干净整洁并与 expected 保持一致
                canonical_title = matched_toc_key
                new_line = "#" * expected_level + " " + canonical_title
            else:
                # 4. 前缀匹配（忽略空格与转义符，拆分标题中的引导标题，需降级）
                is_prefix = False
                for tk_ns in toc_no_spaces:
                    if tk_ns.startswith(title_clean_no_space):
                        is_prefix = True
                        break
                
                if is_prefix or level <= 3:
                    expected_level = min(6, level + 3)
                    new_line = "#" * expected_level + " " + title_text
                else:
                    new_line = stripped
                    
            leading = line[:len(line) - len(line.lstrip())]
            trailing = line[len(line.rstrip()):]
            new_lines.append(leading + new_line + trailing)
        else:
            new_lines.append(line)
            
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def main() -> None:
    """递归处理目标目录下所有 Markdown 文件。"""
    root = get_target_root()
    for path in root.rglob("*.md"):
        replace_in_file(path)

if __name__ == "__main__":
    main()
```

只输出以上完整的 Python 源码，不得输出任何 markdown 代码包裹块之外的描述文本。确保 `TOC_HEADINGS` 字典中包含你根据 IMMUTABLE TOC 块整理出的所有正确项目和层级。

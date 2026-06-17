# 通用 Markdown 格式修正 Python 文件生成 Prompt（统一规则版）

## Role

你是一名 **通用 Markdown 格式修正 Python 代码生成专家**。

你的任务是根据用户给出的 Markdown 样本、规则需求或历史脚本效果，生成一个可以直接保存为 `.py` 并运行的 Python 脚本，用于批量修正 `.md` 文件格式。

这个 Prompt 的核心定位是：

1. 生成的是 **通用 Markdown 格式修正器**，不是只处理教科书的脚本。
2. 不要设计 `textbook / exam / notes / general` 这种文档类型分流。
3. 不要生成 `detect_document_profile()`。
4. 不要把整体结构改成“先识别文件类型，再按 profile 处理”。
5. 应生成一个统一的、顺序稳定的格式修正流水线。
6. 教科书、教材、教辅中的特殊案例，也必须作为通用规则库的一部分无条件加入统一流水线。
7. 不允许写成“只有教科书才启用这些规则”。所有 Markdown 文件都执行同一套规则。
8. 如果非教科书文件中也出现 `探究`、`思考`、`归纳`、`例1`、`图1.2`、`习题 1.1` 等明确模式，也必须照样应用这些规则。

---

## Final Output Requirement

最终只能输出 **完整 Python 源码**。

禁止输出：

- Markdown 代码块标记。
- JSON。
- 解释文字。
- 伪代码。
- 省略号。
- “你可以这样写”。
- 未完成代码。

最终源码必须可以保存为 `.py` 文件直接运行。

---

## Mandatory Imports

生成的 Python 文件开头必须包含：

```python
import os
from pathlib import Path
import re
```

必须真实使用 `os`，例如用于路径兼容、隐藏目录判断、环境变量读取或文件路径处理，避免只是形式化导入。

禁止依赖第三方库。

---

## Required Script Structure

生成的 Python 脚本必须至少包含以下结构：

```python
import os
from pathlib import Path
import re


def get_target_root() -> Path:
    """获取用户输入的目标文件夹路径，留空则使用脚本所在目录。"""


def protect_blocks(text: str) -> tuple[str, list[str]]:
    """保护 YAML frontmatter、代码块、行内代码、行间公式和行内公式，避免在格式清理中被误伤。"""


def restore_blocks(text: str, blocks: list[str]) -> str:
    """将占位符恢复为原来被保护的代码块和公式内容。"""


def replace_in_file(path: Path) -> None:
    """读取文件内容，调用 protect_blocks 保护块，在保护后的文本上执行各项格式修复，最后用 restore_blocks 恢复并写回。"""


def main() -> None:
    """遍历目标目录下所有 .md 文件并执行格式修正。"""


if __name__ == "__main__":
    main()
```

可以增加辅助函数，例如：

```python
def fix_misordered_image_caption_blocks(text: str) -> str:
    pass


def convert_labeled_figure_table(match: re.Match) -> str:
    pass


def convert_single_figure_markdown(match: re.Match) -> str:
    pass
```

但是不要增加文档 profile 分流函数。

---

## Batch Processing Requirements

脚本必须：

1. 询问用户要处理的文件夹路径。
2. 用户直接回车时，使用脚本所在目录。
3. 使用 `Path.rglob("*.md")` 递归处理 Markdown 文件。
4. 跳过隐藏目录和常见工程目录，例如 `.git`、`.obsidian`、`.venv`、`__pycache__`、`.trash`。
5. 使用 UTF-8 读取和写入。
6. 只在文件内容发生变化时写回。
7. 打印已更新文件路径。
8. 单个文件出错时捕获异常，不影响后续文件。
9. 不能访问网络。
10. 不能调用外部命令。
11. 不能改文件名。
12. 不能移动文件。
13. 不能删除 Markdown 文件。

---

## General Design Principle

脚本应采用 **统一流水线**，不是 profile 分流。

强制要求：

1. 不区分教科书、讲义、题库、普通笔记。
2. 不允许写 `if is_textbook`、`if profile == "textbook"`、`detect_document_profile()`。
3. 所有规则都在同一个 `replace_in_file()` 或同一组 `apply_*` 函数中按固定顺序执行。
4. 原脚本中的教科书规则必须被改写为通用规则：任何文件中只要出现相同模式，就执行相同修正。
5. 不能写“非教科书时不启用这些规则”。

推荐顺序：

1. 基础清理。
2. 删除 `<details>` 块。
3. 公式与 OCR 常见错误修正。
4. 选择题选项修正。
5. 通用栏目与 callout 修正：包括任何文件中出现的 `探究`、`思考`、`观察`、`归纳`、`例1` 等明确模式。
6. 明确模式下的标题层级修正。
7. 图片与题注修正。
8. 空行与段落间距修正。
9. 最终连续空行压缩。

注意：

- 所有规则都应通过具体正则模式自然触发。
- 不要先判断“这是教科书”再启用一整套规则。
- 教科书案例不是专属分支，而是所有 Markdown 文件都会执行的通用规则案例。
- 规则必须保守，不能主观改写正文。

---

## Safety Rules

必须遵守：

1. 不推断答案。
2. 不改写题目正文。
3. 不翻译内容。
4. 不总结内容。
5. 不删除图片本身，除非是明确的“教材特殊栏目标题前的装饰性图片链接”。
6. 不改变图片路径。
7. 不改变题目顺序。
8. 不改变选项顺序。
9. 不改变公式含义。
10. 不处理 fenced code block 内部内容。
11. 不处理 YAML frontmatter 内部内容。
12. 不处理 Markdown 表格内部文本，除非是由连续图片确定性转换成图片表格。
13. 不使用不安全的 Python 正则，例如可变宽度 lookbehind。

---

## Heading Protection Policy

不要笼统保护 H1-H6。

应采用以下策略：

1. H1-H3 通常视为结构标题，默认不要改动。
2. H4-H6 可以视为章节内部栏目、例题、小题、练习等局部结构。
3. 只有当 H4-H6 命中明确白名单栏目时，才允许转换为 callout 或局部格式。
4. 对旧转换结果中的 `# 探究`、`# 思考`、`# 归纳` 等精确栏目，也可以按白名单转换；但绝不能把 `# 第一章`、`# 1.1`、`# 第三节` 这类结构标题当成 callout。
5. 绝不要全局把所有 H4-H6 都删除或全部转 callout。
6. 标题层级修正只能针对非常明确的教材 / 教辅常见模式。

---

## Core Common Cleaning Rules

生成代码时应实现这些通用效果：

### 1. 删除粗体标记

删除全文中的 `**`，保留文字内容：

```python
new = new.replace("**", "")
```

### 2. 删除 `<details>` 块

删除 `<details>...</details>` 以及其中全部内容：

```python
new = re.sub(r'<details>[\s\S]*?</details>', '', new)
```

要求：

- 默认删除 `<details>` 块。
- 不只是 report。
- 不只是保护。

---

## Formula and OCR Fix Rules

应实现以下公式与 OCR 修正效果。

### 1. 选项标号 OCR 修正

```python
new = re.sub(r'\\mathrm{([A-D])[\.．]}', r'\1', new)
new = re.sub(r'\$\\mathrm{([A-D])[\.．]}', r'\1.$', new)
```

### 2. 行间公式转行内公式

应尽量实现用户旧脚本效果：

```python
new = re.sub(r"\$\$\n([\s\S]*?)\n\$\$", r"&!\1&!", new)
new = re.sub(r"(?m)^\$\n([\s\S]*?)\n\$", r"&!\1&!", new)
new = new.replace("&!", "$")
new = new.replace("$$", "$")
```

注意：

- 这是为了把 PDF/OCR 转换出的独立公式收束为行内公式。
- 不要重写公式内容。
- 不要推断公式含义。

### 3. 白名单公式修正

必须包含：

```python
new = new.replace("$^{A,B,C}$", "${A,B,C}$")
new = new.replace(r"\int_{\mathbb{R}}", r"\complement_{\mathbb{R}}")
new = new.replace(r"\overset{⃑}", r"\overrightarrow")
new = new.replace(r"\overset{→}", r"\overrightarrow")
new = new.replace(r"$\qquad$", r"$\underline{\hspace{2cm}}$")
```

---

## Choice Option Formatting Rules

应实现选择题选项拆分。

目标：

```markdown
A. ... B. ... C. ... D. ...
```

变为：

```markdown
A. ...
B. ...
C. ...
D. ...
```

可以使用多轮保守替换，接近旧脚本效果：

```python
for _ in range(4):
    new = re.sub(r'^([A-D].*?)([A-D][\.．])', r'\1\n\2', new, flags=re.MULTILINE)
```

要求：

- 不改选项正文。
- 不重排选项。
- 不判断答案。
- 不把标题行与选项合并。

---

## Callout Rules: Add Textbook-Style Cases as Universal Rules

这一部分是关键。

不要把脚本整体改成“教科书专用”。

必须把教科书中常见的栏目案例改写为通用规则加入；任何 Markdown 文件只要出现相同栏目模式，都应用相同修正。

### 1. 删除特殊栏目标题前的装饰图片

如果图片行后面紧跟明确的栏目标题，则删除这张装饰图片和中间空行：

```python
new = re.sub(
    r'(?m)^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:\r?\n)+(?=^[ \t]*#{1,6}\s*(?:归纳|练习|溯源|探究|思考|观察|复习巩固|综合运用|拓广探索)\b)',
    '',
    new,
)
```

### 2. H4-H6 栏目标题转 Obsidian callout

前置流程可能已经把栏目标题整理为：

```markdown
#### 探究
#### 思考
#### 观察
#### 归纳
#### 溯源
```

不需要保护这些 H4-H6 栏目，应允许它们转成 callout；这条规则不要求文件必须是教科书。

必须支持以下效果：

```markdown
#### 探究
```

变为：

```markdown
> [!explore] 探究
```

```markdown
#### 思考
```

变为：

```markdown
> [!think] 思考
```

```markdown
#### 观察
```

变为：

```markdown
> [!observe] 观察
```

```markdown
#### 归纳
```

变为：

```markdown
> [!tip] 归纳
```

```markdown
#### 溯源
```

变为：

```markdown
> [!quote] 溯源
```

推荐实现：

```python
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?探究\b', r'> [!explore] 探究', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?思考\b', r'> [!think] 思考', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·思考\b', r'> [!think] 尝试·思考', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?观察\b', r'> [!observe] 观察', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?归纳\b', r'> [!tip] 归纳', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·交流\b', r'> [!tip] 尝试·交流', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?回顾·反思\b', r'> [!summary] 回顾·反思', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?操作·交流\b', r'> [!todo] 操作·交流', new)
new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?溯源\b', r'> [!quote] 溯源', new)
```

### 3. 例题转 example callout

必须支持：

```markdown
#### 例1
#### 例 1
# 例1
例1
```

转为：

```markdown
> [!example]- 例1
```

推荐实现：

```python
new = re.sub(r'(?m)^[ \t]*(?:#{1,6}\s+)?(例\d+.*)$', r'> [!example]- \1', new)
new = re.sub(r'(?m)^[ \t]*(?:#{1,6}\s+)?(例 \d+\b.*)$', r'> [!example]- \1', new)
```

### 4. 删除 callout 标题后的多余空行

```python
new = re.sub(
    r'(?m)^(> \[!(?:quote|explore|think|observe|tip|summary|todo)\] (?:思考·交流|溯源|探究|思考|观察|归纳|尝试·思考|尝试·交流|回顾·反思|操作·交流))[ \t]*\r?\n[ \t]*\r?\n',
    r'\1\n',
    new,
)
new = re.sub(r'(?m)^(> \[!example\]-[^\n]*)(\n[ \t]*\n)', r'\1\n', new)
```

### 5. 确保 callout 前有空行

```python
new = re.sub(r'(?m)(?<!\n)\n(?=[ \t]*> \[!)', '\n\n', new)
```

---

## Explicit Textbook Heading Cases as Generic Pattern Rules

以下不是 profile 分流，也不是教科书专属规则；所有 Markdown 文件都执行这些规则。只要遇到这些明确模式，就修正。

生成代码时应尽量包含这些案例：

```python
# 如果章节标题后直接或间隔空行接着另一个 # 标题，则合并为同一行
new = re.sub(r'(?m)^(#\s+第[一二三四五六七八九十百]+章[^\r\n]*)\s*\r?\n\s*#\s+', r'\1 ', new)

# 小题编号不应是 H1
new = re.sub(r'(?m)^#\s+([（(]\d+[）)].*)$', r'\1', new)

# 数字题号转为 H4
new = re.sub(r'(?m)^#\s+(\d+[\.．]\s*)', r'#### \1', new)

# 习题与三级知识栏目
new = re.sub(r'(?m)^#\s+(习题\s*\d+(?:\.\d+)*)', r'## \1', new)
new = re.sub(r'(?m)^#+\s+(\d+\.\d+\.\d+\b.*)$', r'### \1', new)
new = re.sub(r'(?m)^#+\s+(\d+\.\d+\b(?!\.\d).*)$', r'## \1', new)

new = re.sub(r'(?m)^#\s+知识技能\b', r'### 知识技能', new)
new = re.sub(r'(?m)^#\s+问题解决\b', r'### 问题解决', new)
new = re.sub(r'(?m)^#\s+联系拓广\b', r'### 联系拓广', new)
new = re.sub(r'(?m)^#\s+数学理解\b', r'### 数学理解', new)

new = re.sub(r'(?m)^#\s+阅读[与·和]思考\b', r'## 阅读与思考', new)
new = re.sub(r'(?m)^(## 阅读与思考)\s*\r?\n\s*#\s+', r'\1\n### ', new)
new = re.sub(r'(?m)^#\s+探究[与·和]发现\b', r'## 探究与发现', new)
new = re.sub(r'(?m)^(## 探究与发现)\s*\r?\n\s*#\s+', r'\1\n### ', new)

new = re.sub(r'(?m)^#\s+练习\b', r'#### 练习', new)
new = re.sub(r'(?m)^#\s+随堂练习\b', r'#### 随堂练习', new)
new = re.sub(r'(?m)^#\s+尝试·思考\b', r'#### 尝试·思考', new)

new = re.sub(r'(?m)^#\s+复习参考题\s*(\d*)\b', r'## 复习参考题\1', new)
new = re.sub(r'(?m)^#\s+复习巩固\b', r'### 复习巩固', new)
new = re.sub(r'(?m)^#\s+综合运用\b', r'### 综合运用', new)
new = re.sub(r'(?m)^#\s+拓广探索\b', r'### 拓广探索', new)
new = re.sub(r'(?m)^#\s+小结\b', r'## 小结', new)
new = re.sub(r'(?m)^#\s+([一二三四五六七八九十]+、)', r'### \1', new)
new = re.sub(r'(?m)^#\s+（([一二三四五六七八九十]+)）', r'### （\1）', new)
```

注意：

- 这些是明确案例规则，会对所有 Markdown 文件执行，但不是全局标题重建。
- 不能让 AI 重新推断所有章节层级。
- 不能生成复杂语义判断。

---

## Misrecognized Image and Caption Heading Fixes

必须修正图片和题注被误识别为标题的情况：

```python
new = re.sub(r'(?m)^[ \t]*#\s*(!\[[^\]]*\]\([^\)\n]+\))[ \t]*$', r'\1', new)
new = re.sub(r'(?m)^[ \t]*#\s*(图\s*\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$', r'\1', new)
new = re.sub(r'(?m)^[ \t]*#\s*([（(][^）)\r\n]+[）)])[ \t]*$', r'\1', new)
```

---

## Image and Caption Formatting Rules

生成代码时应实现用户旧脚本中的图片处理效果，但必须保守。

### 1. 连续多张图片 + 连续多个题注

如果连续图片数量与连续题注数量相等且不少于 2，则转换为 Obsidian 引用块中的 Markdown 表格：

```markdown
> <center>
> 
> | ![](a.png) | ![](b.png) |
> | --- | --- |
> | 图1 | 图2 |
> </center>
```

要求：

- 图片数量和题注数量必须相等。
- 图片数量必须 ≥ 2。
- 不改变图片路径。
- 不改变图片顺序。
- 不改变题注顺序。

### 2. 连续图片 + 子标签

支持这种结构：

```markdown
![](a.png)
（1）xxx
![](b.png)
（2）xxx
图1.2
```

转换为图片表格，标签在图片下方。

### 3. 连续多张图片 + `（第X题）`

支持：

```markdown
![](a.png)
![](b.png)
（第3题）
```

转换为一行图片表格，题注单独居中。

### 4. 连续多张图片 + `（1）`

支持：

```markdown
![](a.png)
![](b.png)
（1）
```

转换为一行图片表格，题注单独居中。

### 5. 连续多张图片 + `图1.2`

支持：

```markdown
![](a.png)
![](b.png)
图1.2
```

转换为一行图片表格，图题单独居中。

### 6. 单张图片 + 图号 / 第 X 题

支持：

```markdown
![](a.png)
图1.2
```

转换为：

```html
<center><img src="a.png" style="max-width:100%;"></center><center>图1.2</center>
```

支持：

```markdown
![](a.png)
（第3题）
```

转换为：

```html
<center><img src="a.png" style="max-width:100%;"></center><center>（第3题）</center>
```

### 7. 图片转换后的空行清理

必须包含：

```python
new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', new)
new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=<center><img)', '\n', new)
new = re.sub(r'(?:\r?\n[ \t]*)+(?=<center>)', '', new)
new = re.sub(r'</center>\n>', '</center>', new)
```

并处理表格行和 `<center>图...` 粘连的情况。

---

## Blank Line and Paragraph Rules

生成代码时应包含以下空行修复效果。

### 1. 删除特殊行前多余空行

删除以下行前的多余空行：

- `解`
- `分析`
- `方法`
- `作法`
- `(1)` / `（1）`
- 图片行
- `<center><img...>`
- 表格行
- `$` 开头的公式行

示例：

```python
new = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=(?:解|分析|方法|作法)[^\r\n]*$)', r'\n', new)
new = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=[（(]\d+[）)][^\r\n]*$)', r'\n', new)
new = re.sub(r'(?m)(；)[ \t]*\r?\n[ \t]*\r?\n', r'\1\n', new)
new = re.sub(r'(?m)^(解[^\r\n]*)[ \t]*\r?\n[ \t]*\r?\n(?=(?:\|)|(?:!\[[^\]]*\]\()|(?:<center><img\b))', r'\1\n', new)
new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=\$)', '\n', new)
```

### 2. 问号后补空行

```python
new = re.sub(r'(?m)^(.*？[ \t]*)\r?\n(?!\s*\r?\n)', r'\1\n\n', new)
```

### 3. 删除推导句前多余空行

应包含用户旧脚本中的常见数学推导词白名单，例如：

```text
解：、列方程、综上所述、根据题意、依题意、由题意、由已知、由条件、据题意、据已知、由此可知、由此可得、这就是说、也就是说、换句话说、换言之、同理可得、分类讨论、整理得、化简得、配方得、经检验、等式两边、方程两边、两边同乘、两边同除、去括号、因式分解、所以、因为、因此、于是、从而、∵、∴、显然、如果、假设、不妨、证明、欲证、要证、解得、可得、可知、代入、联立、移项、合并、消去、配方、首先、其次、最后、利用、通过、根据、判断、验证、讨论、说明、令、设、若、则、得、故、当、由、又、再、即、将、答、Rt
```

实现时可以使用一个长正则白名单，删除这些行前面的多余空行。

### 4. 小题编号空行与手动换行

```python
new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=^[ \t]*[（(]\d+[）)])', '\n', new)
new = re.sub(r'(?m)(?<!\s{2})(\r?\n)(?=^[ \t]*[（(]\d+[）)])', r'  \1', new)
```

### 5. `※` 前添加缩进

```python
new = re.sub(r'(?m)^([ \t]*)(※)', r'\1&emsp;\2', new)
```

### 6. 压缩连续空行

```python
while '\n\n\n' in new:
    new = new.replace('\n\n\n', '\n\n')
```

---

## Implementation Quality Requirements

生成代码时必须：

1. 使用清晰函数名。
2. 给关键函数添加中文 docstring。
3. 正则尽量使用原始字符串 `r''`。
4. 涉及 LaTeX 反斜杠替换时优先使用 `.replace()`，避免 `re.sub` 的 `bad escape`。
5. 对复杂图片转换使用辅助函数，不要全部堆在一个巨大正则替换里。
6. 保持规则顺序稳定。
7. 保持代码可读。
8. 不能省略 `main()`。
9. 不能只输出片段。
10. 不能生成需要用户二次补全的代码。

---

## What the Generated Script Should Feel Like

最终生成的脚本应该像一个“通用 Markdown 清洗器”：

- 所有 Markdown 文件：都运行同一套统一流水线，不做文档类型判断。
- 普通 Markdown：如果出现粗体、details、空行、基础公式、图片题注等问题，就修正。
- 数学题库：如果出现选项、公式、解答前空行、小题编号等模式，就修正。
- 任何文件：只要出现 `#### 探究`、`#### 思考`、`#### 归纳`、`#### 例1`、`图1.2`、`习题 1.1` 等明确模式，都按用户旧脚本效果修正，而不是先判断它是不是教科书。

但代码结构上不要写成：

```python
if profile == "textbook":
    apply_textbook_rules()
```

而应写成统一流水线：

```python
new = txt
new = apply_basic_cleanup(new)
new = apply_formula_fixes(new)
new = apply_choice_fixes(new)
new = apply_callout_fixes(new)
new = apply_heading_case_fixes(new)
new = apply_image_caption_fixes(new)
new = apply_blank_line_fixes(new)
```

---

## Initialization

现在请根据以上要求，生成一个完整 Python 文件源码。

记住：

1. 只输出 Python 源码。
2. 必须包含 `import os`、`from pathlib import Path`、`import re`。
3. 不要输出 Markdown 代码块。
4. 不要输出解释。
5. 不要生成 profile 分流。
6. 不要生成 `detect_document_profile()`。
7. 把教科书案例作为所有文件都会执行的通用精确匹配规则加入，不能加“仅教科书启用”的条件。

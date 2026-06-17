import os
from pathlib import Path
import re


def get_target_root() -> Path:
    """获取用户输入的目标文件夹路径，留空则使用脚本所在目录。"""
    user_input = input("请输入要处理的文件夹路径（直接回车使用当前目录）: ").strip()
    if user_input:
        return Path(user_input).resolve()
    return Path.cwd()


def protect_blocks(text: str) -> tuple[str, list[str]]:
    """保护 YAML frontmatter、代码块、行内代码、行间公式和行内公式，避免在格式清理中被误伤。"""
    blocks = []
    # 保护 YAML frontmatter
    def protect_yaml(match):
        blocks.append(match.group(0))
        return f"__YAMLBLOCK_{len(blocks)-1}__"
    text = re.sub(r'^---\n[\s\S]*?\n---\n', protect_yaml, text)
    # 保护 fenced code blocks
    def protect_code(match):
        blocks.append(match.group(0))
        return f"__CODEBLOCK_{len(blocks)-1}__"
    text = re.sub(r'```[\s\S]*?```', protect_code, text)
    # 保护行内代码
    def protect_inline_code(match):
        blocks.append(match.group(0))
        return f"__INLINECODE_{len(blocks)-1}__"
    text = re.sub(r'`[^`\n]+`', protect_inline_code, text)
    # 保护行间公式
    def protect_display_math(match):
        blocks.append(match.group(0))
        return f"__DISPLAYMATH_{len(blocks)-1}__"
    text = re.sub(r'\$\$[\s\S]*?\$\$', protect_display_math, text)
    # 保护行内公式
    def protect_inline_math(match):
        blocks.append(match.group(0))
        return f"__INLINEMATH_{len(blocks)-1}__"
    text = re.sub(r'\$[^\$\n]+\$', protect_inline_math, text)
    return text, blocks


def restore_blocks(text: str, blocks: list[str]) -> str:
    """将占位符恢复为原来被保护的代码块和公式内容。"""
    for i, block in enumerate(blocks):
        text = text.replace(f"__YAMLBLOCK_{i}__", block)
        text = text.replace(f"__CODEBLOCK_{i}__", block)
        text = text.replace(f"__INLINECODE_{i}__", block)
        text = text.replace(f"__DISPLAYMATH_{i}__", block)
        text = text.replace(f"__INLINEMATH_{i}__", block)
    return text


def apply_basic_cleanup(text: str) -> str:
    """基础清理：删除粗体标记和 details 块。"""
    new = text
    new = new.replace("**", "")
    new = re.sub(r'<details>[\s\S]*?</details>', '', new)
    return new


def apply_formula_fixes(text: str) -> str:
    """公式与 OCR 常见错误修正。"""
    new = text
    # 选项标号 OCR 修正
    new = re.sub(r'\\mathrm{([A-D])[\.．]}', r'\1', new)
    new = re.sub(r'\$\\mathrm{([A-D])[\.．]}', r'\1.$', new)
    # 行间公式转行内公式
    new = re.sub(r"\$\$\n([\s\S]*?)\n\$\$", r"&!\1&!", new)
    new = re.sub(r"(?m)^\$\n([\s\S]*?)\n\$", r"&!\1&!", new)
    new = new.replace("&!", "$")
    new = new.replace("$$", "$")
    # 白名单公式修正
    new = new.replace("$^{A,B,C}$", "${A,B,C}$")
    new = new.replace(r"\int_{\mathbb{R}}", r"\complement_{\mathbb{R}}")
    new = new.replace(r"\overset{⃑}", r"\overrightarrow")
    new = new.replace(r"\overset{→}", r"\overrightarrow")
    new = new.replace(r"$\qquad$", r"$\underline{\hspace{2cm}}$")
    return new


def apply_choice_fixes(text: str) -> str:
    """选择题选项修正：将 A. ... B. ... 拆分为多行。"""
    new = text
    for _ in range(4):
        new = re.sub(r'^([A-D].*?)([A-D][\.．])', r'\1\n\2', new, flags=re.MULTILINE)
    return new


def apply_callout_fixes(text: str) -> str:
    """通用栏目与 callout 修正：包括探究、思考、观察、归纳、例1等明确模式。"""
    new = text
    # 删除特殊栏目标题前的装饰图片
    new = re.sub(
        r'(?m)^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:\r?\n)+(?=^[ \t]*#{1,6}\s*(?:归纳|练习|溯源|探究|思考|观察|复习巩固|综合运用|拓广探索)\b)',
        '',
        new,
    )
    # H4-H6 栏目标题转 Obsidian callout
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?探究\b', r'> [!explore] 探究', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?思考\b', r'> [!think] 思考', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·思考\b', r'> [!think] 尝试·思考', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?观察\b', r'> [!observe] 观察', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?归纳\b', r'> [!tip] 归纳', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·交流\b', r'> [!tip] 尝试·交流', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?回顾·反思\b', r'> [!summary] 回顾·反思', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?操作·交流\b', r'> [!todo] 操作·交流', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?溯源\b', r'> [!quote] 溯源', new)
    # 例题转 example callout
    new = re.sub(r'(?m)^[ \t]*(?:#{1,6}\s+)?(例\d+.*)$', r'> [!example]- \1', new)
    new = re.sub(r'(?m)^[ \t]*(?:#{1,6}\s+)?(例 \d+\b.*)$', r'> [!example]- \1', new)
    # 删除 callout 标题后的多余空行
    new = re.sub(
        r'(?m)^(> \[!(?:quote|explore|think|observe|tip|summary|todo)\] (?:思考·交流|溯源|探究|思考|观察|归纳|尝试·思考|尝试·交流|回顾·反思|操作·交流))[ \t]*\r?\n[ \t]*\r?\n',
        r'\1\n',
        new,
    )
    new = re.sub(r'(?m)^(> \[!example\]-[^\n]*)(\n[ \t]*\n)', r'\1\n', new)
    # 确保 callout 前有空行
    new = re.sub(r'(?m)(?<!\n)\n(?=[ \t]*> \[!)', '\n\n', new)
    return new


def apply_heading_case_fixes(text: str) -> str:
    """明确模式下的标题层级修正。"""
    new = text
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
    # 误识别为标题的图片和题注
    new = re.sub(r'(?m)^[ \t]*#\s*(!\[[^\]]*\]\([^\)\n]+\))[ \t]*$', r'\1', new)
    new = re.sub(r'(?m)^[ \t]*#\s*(图\s*\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$', r'\1', new)
    new = re.sub(r'(?m)^[ \t]*#\s*([（(][^）)\r\n]+[）)])[ \t]*$', r'\1', new)
    return new


def convert_labeled_figure_table(match: re.Match) -> str:
    """将连续图片和连续题注转换为 Obsidian 引用块中的 Markdown 表格。"""
    images = match.group(1).strip().split('\n')
    captions = match.group(2).strip().split('\n')
    # 过滤空行
    images = [img.strip() for img in images if img.strip()]
    captions = [cap.strip() for cap in captions if cap.strip()]
    if len(images) != len(captions) or len(images) < 2:
        return match.group(0)
    # 构建表格
    header = '| ' + ' | '.join(images) + ' |'
    sep = '| ' + ' | '.join(['---'] * len(images)) + ' |'
    cap_row = '| ' + ' | '.join(captions) + ' |'
    return f'> <center>\n> \n> {header}\n> {sep}\n> {cap_row}\n> </center>'


def convert_single_figure_markdown(match: re.Match) -> str:
    """将单张图片和题注转换为 HTML 居中格式。"""
    img = match.group(1).strip()
    caption = match.group(2).strip()
    return f'<center><img src="{img}" style="max-width:100%;"></center><center>{caption}</center>'


def apply_image_caption_fixes(text: str) -> str:
    """图片与题注修正。"""
    new = text
    # 连续多张图片 + 连续多个题注（相等且不少于2）
    new = re.sub(
        r'(?m)((?:!\[[^\]]*\]\([^\)\n]+\)\s*\r?\n\s*)+)((?:[（(]\d+[）)][^\n]*\s*\r?\n\s*)+)',
        convert_labeled_figure_table,
        new,
    )
    # 连续多张图片 + 图号
    new = re.sub(
        r'(?m)((?:!\[[^\]]*\]\([^\)\n]+\)\s*\r?\n\s*)+)(图\s*\d+(?:\.\d+)*(?:-\d+)?)',
        convert_labeled_figure_table,
        new,
    )
    # 连续多张图片 + （第X题）
    new = re.sub(
        r'(?m)((?:!\[[^\]]*\]\([^\)\n]+\)\s*\r?\n\s*)+)(（第\d+题）)',
        convert_labeled_figure_table,
        new,
    )
    # 连续多张图片 + （1）
    new = re.sub(
        r'(?m)((?:!\[[^\]]*\]\([^\)\n]+\)\s*\r?\n\s*)+)(（\d+）)',
        convert_labeled_figure_table,
        new,
    )
    # 单张图片 + 图号 / 第X题
    new = re.sub(
        r'(?m)^[ \t]*!\[([^\]]*)\]\(([^\)\n]+)\)[ \t]*\r?\n[ \t]*(图\s*\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$',
        lambda m: f'<center><img src="{m.group(2)}" style="max-width:100%;"></center><center>{m.group(3)}</center>',
        new,
    )
    new = re.sub(
        r'(?m)^[ \t]*!\[([^\]]*)\]\(([^\)\n]+)\)[ \t]*\r?\n[ \t]*（第\d+题）[ \t]*$',
        lambda m: f'<center><img src="{m.group(2)}" style="max-width:100%;"></center><center>{m.group(3)}</center>',
        new,
    )
    # 图片转换后的空行清理
    new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', new)
    new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=<center><img)', '\n', new)
    new = re.sub(r'(?:\r?\n[ \t]*)+(?=<center>)', '', new)
    new = re.sub(r'</center>\n>', '</center>', new)
    return new


def apply_blank_line_fixes(text: str) -> str:
    """空行与段落间距修正。"""
    new = text
    # 删除特殊行前多余空行
    new = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=(?:解|分析|方法|作法)[^\r\n]*$)', r'\n', new)
    new = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=[（(]\d+[）)][^\r\n]*$)', r'\n', new)
    new = re.sub(r'(?m)(；)[ \t]*\r?\n[ \t]*\r?\n', r'\1\n', new)
    new = re.sub(r'(?m)^(解[^\r\n]*)[ \t]*\r?\n[ \t]*\r?\n(?=(?:\|)|(?:!\[[^\]]*\]\()|(?:<center><img\b))', r'\1\n', new)
    new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=\$)', '\n', new)
    # 问号后补空行
    new = re.sub(r'(?m)^(.*？[ \t]*)\r?\n(?!\s*\r?\n)', r'\1\n\n', new)
    # 删除推导句前多余空行
    derivation_words = r'(?:解：|列方程|综上所述|根据题意|依题意|由题意|由已知|由条件|据题意|据已知|由此可知|由此可得|这就是说|也就是说|换句话说|换言之|同理可得|分类讨论|整理得|化简得|配方得|经检验|等式两边|方程两边|两边同乘|两边同除|去括号|因式分解|所以|因为|因此|于是|从而|∵|∴|显然|如果|假设|不妨|证明|欲证|要证|解得|可得|可知|代入|联立|移项|合并|消去|配方|首先|其次|最后|利用|通过|根据|判断|验证|讨论|说明|令|设|若|则|得|故|当|由|又|再|即|将|答|Rt)'
    new = re.sub(rf'(?m)[ \t]*\r?\n[ \t]*\r?\n(?={derivation_words}[^\r\n]*$)', r'\n', new)
    # 小题编号空行与手动换行
    new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=^[ \t]*[（(]\d+[）)])', '\n', new)
    new = re.sub(r'(?m)(?<!\s{2})(\r?\n)(?=^[ \t]*[（(]\d+[）)])', r'  \1', new)
    # ※ 前添加缩进
    new = re.sub(r'(?m)^([ \t]*)(※)', r'\1&emsp;\2', new)
    # 压缩连续空行
    while '\n\n\n' in new:
        new = new.replace('\n\n\n', '\n\n')
    return new


def replace_in_file(path: Path) -> None:
    """读取文件内容，调用 protect_blocks 保护块，在保护后的文本上执行各项格式修复，最后用 restore_blocks 恢复并写回。"""
    try:
        original = path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"读取文件失败 {path}: {e}")
        return
    # 保护块
    protected_text, blocks = protect_blocks(original)
    # 统一流水线
    new = protected_text
    new = apply_basic_cleanup(new)
    new = apply_formula_fixes(new)
    new = apply_choice_fixes(new)
    new = apply_callout_fixes(new)
    new = apply_heading_case_fixes(new)
    new = apply_image_caption_fixes(new)
    new = apply_blank_line_fixes(new)
    # 恢复块
    new = restore_blocks(new, blocks)
    # 只在内容变化时写回
    if new != original:
        path.write_text(new, encoding='utf-8')
        print(f"已更新: {path}")


def main() -> None:
    """遍历目标目录下所有 .md 文件并执行格式修正。"""
    root = get_target_root()
    if not root.exists():
        print(f"路径不存在: {root}")
        return
    # 跳过隐藏目录和常见工程目录
    skip_dirs = {'.git', '.obsidian', '.venv', '__pycache__', '.trash'}
    for md_file in root.rglob("*.md"):
        # 检查是否在跳过目录中
        parts = md_file.relative_to(root).parts
        if any(part in skip_dirs for part in parts):
            continue
        # 跳过隐藏目录
        if any(part.startswith('.') for part in parts):
            continue
        replace_in_file(md_file)


if __name__ == "__main__":
    main()

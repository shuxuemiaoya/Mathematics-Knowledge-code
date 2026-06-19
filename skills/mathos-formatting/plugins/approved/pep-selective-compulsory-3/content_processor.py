import os
from pathlib import Path
import re


def get_target_root() -> Path:
    """获取用户输入的目标文件夹路径，留空则使用脚本所在目录。"""
    user_input = input("请输入要处理的文件夹路径（直接回车使用脚本所在目录）: ").strip()
    if user_input:
        target = Path(user_input)
        if not target.is_dir():
            print(f"错误：路径 '{user_input}' 不存在或不是文件夹。将使用脚本所在目录。")
            return Path.cwd()
        return target
    return Path.cwd()


def protect_blocks(text: str) -> tuple[str, list[str]]:
    """保护 YAML frontmatter、代码块、行内代码、行间公式和行内公式，避免在格式清理中被误伤。"""
    blocks = []

    # 保护 YAML frontmatter
    def protect_yaml(match):
        blocks.append(match.group(0))
        return f"%%%YAMLBLOCK{len(blocks)-1}%%%"

    text = re.sub(r'^---\n[\s\S]*?\n---\n', protect_yaml, text)

    # 保护 fenced code blocks
    def protect_code(match):
        blocks.append(match.group(0))
        return f"%%%CODEBLOCK{len(blocks)-1}%%%"

    text = re.sub(r'```[\s\S]*?```', protect_code, text)

    # 保护行内代码
    def protect_inline_code(match):
        blocks.append(match.group(0))
        return f"%%%INLINECODE{len(blocks)-1}%%%"

    text = re.sub(r'`[^`\n]+`', protect_inline_code, text)

    # 保护行间公式
    def protect_display_math(match):
        blocks.append(match.group(0))
        return f"%%%DISPLAYMATH{len(blocks)-1}%%%"

    text = re.sub(r'\$\$[\s\S]*?\$\$', protect_display_math, text)

    # 保护行内公式
    def protect_inline_math(match):
        blocks.append(match.group(0))
        return f"%%%INLINEMATH{len(blocks)-1}%%%"

    text = re.sub(r'\$[^\n$]+\$', protect_inline_math, text)

    return text, blocks


def restore_blocks(text: str, blocks: list[str]) -> str:
    """将占位符恢复为原来被保护的代码块和公式内容。"""
    for i, block in enumerate(blocks):
        placeholder = f"%%%YAMLBLOCK{i}%%%"
        text = text.replace(placeholder, block)
        placeholder = f"%%%CODEBLOCK{i}%%%"
        text = text.replace(placeholder, block)
        placeholder = f"%%%INLINECODE{i}%%%"
        text = text.replace(placeholder, block)
        placeholder = f"%%%DISPLAYMATH{i}%%%"
        text = text.replace(placeholder, block)
        placeholder = f"%%%INLINEMATH{i}%%%"
        text = text.replace(placeholder, block)
    return text


def apply_basic_cleanup(text: str) -> str:
    """基础清理：删除粗体标记和 <details> 块。"""
    text = text.replace("**", "")
    text = re.sub(r'<details>[\s\S]*?</details>', '', text)
    return text


def apply_formula_fixes(text: str) -> str:
    """公式与 OCR 常见错误修正。"""
    # 选项标号 OCR 修正
    text = re.sub(r'\\mathrm{([A-D])[\.．]}', r'\1', text)
    text = re.sub(r'\$\\mathrm{([A-D])[\.．]}', r'\1.$', text)

    # 行间公式转行内公式
    text = re.sub(r"\$\$\n([\s\S]*?)\n\$\$", r"&!\1&!", text)
    text = re.sub(r"(?m)^\$\n([\s\S]*?)\n\$", r"&!\1&!", text)
    text = text.replace("&!", "$")
    text = text.replace("$$", "$")

    # 白名单公式修正
    text = text.replace("$^{A,B,C}$", "${A,B,C}$")
    text = text.replace(r"\int_{\mathbb{R}}", r"\complement_{\mathbb{R}}")
    text = text.replace(r"\overset{⃑}", r"\overrightarrow")
    text = text.replace(r"\overset{→}", r"\overrightarrow")
    text = text.replace(r"$\qquad$", r"$\underline{\hspace{2cm}}$")

    return text


def apply_choice_fixes(text: str) -> str:
    """选择题选项修正：将 A. ... B. ... 拆分为多行。"""
    for _ in range(4):
        text = re.sub(r'^([A-D].*?)([A-D][\.．])', r'\1\n\2', text, flags=re.MULTILINE)
    return text


def apply_callout_fixes(text: str) -> str:
    """通用栏目与 callout 修正：包括探究、思考、观察、归纳、例1等明确模式。"""
    # H4-H6 栏目标题转 Obsidian callout
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?探究\b', r'> [!explore] 探究', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?思考\b', r'> [!think] 思考', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·思考\b', r'> [!think] 尝试·思考', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?观察\b', r'> [!observe] 观察', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?归纳\b', r'> [!tip] 归纳', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·交流\b', r'> [!tip] 尝试·交流', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?回顾·反思\b', r'> [!summary] 回顾·反思', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?操作·交流\b', r'> [!todo] 操作·交流', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?溯源\b', r'> [!quote] 溯源', text)

    # 例题转 example callout
    text = re.sub(r'(?m)^[ \t]*(?:#{1,6}\s+)?(例\d+.*)$', r'> [!example]- \1', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{1,6}\s+)?(例 \d+\b.*)$', r'> [!example]- \1', text)

    # 删除 callout 标题后的多余空行
    text = re.sub(
        r'(?m)^(> \[!(?:quote|explore|think|observe|tip|summary|todo)\] (?:思考·交流|溯源|探究|思考|观察|归纳|尝试·思考|尝试·交流|回顾·反思|操作·交流))[ \t]*\r?\n[ \t]*\r?\n',
        r'\1\n',
        text,
    )
    text = re.sub(r'(?m)^(> \[!example\]-[^\n]*)(\n[ \t]*\n)', r'\1\n', text)

    # 确保 callout 前有空行
    text = re.sub(r'(?m)(?<!\n)\n(?=[ \t]*> \[!)', '\n\n', text)

    return text


def apply_heading_case_fixes(text: str) -> str:
    """明确模式下的标题层级修正。"""
    # 如果章节标题后直接或间隔空行接着另一个 # 标题，则合并为同一行
    text = re.sub(r'(?m)^(#\s+第[一二三四五六七八九十百]+章[^\r\n]*)\s*\r?\n\s*#\s+', r'\1 ', text)

    # 小题编号不应是 H1
    text = re.sub(r'(?m)^#\s+([（(]\d+[）)].*)$', r'\1', text)

    # 数字题号转为 H4
    text = re.sub(r'(?m)^#\s+(\d+[\.．]\s*)', r'#### \1', text)

    # 习题与三级知识栏目
    text = re.sub(r'(?m)^#\s+(习题\s*\d+(?:\.\d+)*)', r'## \1', text)
    text = re.sub(r'(?m)^#+\s+(\d+\.\d+\.\d+\b.*)$', r'### \1', text)
    text = re.sub(r'(?m)^#+\s+(\d+\.\d+\b(?!\.\d).*)$', r'## \1', text)

    text = re.sub(r'(?m)^#\s+知识技能\b', r'### 知识技能', text)
    text = re.sub(r'(?m)^#\s+问题解决\b', r'### 问题解决', text)
    text = re.sub(r'(?m)^#\s+联系拓广\b', r'### 联系拓广', text)
    text = re.sub(r'(?m)^#\s+数学理解\b', r'### 数学理解', text)

    text = re.sub(r'(?m)^#\s+阅读[与·和]思考\b', r'## 阅读与思考', text)
    text = re.sub(r'(?m)^(## 阅读与思考)\s*\r?\n\s*#\s+', r'\1\n### ', text)
    text = re.sub(r'(?m)^#\s+探究[与·和]发现\b', r'## 探究与发现', text)
    text = re.sub(r'(?m)^(## 探究与发现)\s*\r?\n\s*#\s+', r'\1\n### ', text)

    text = re.sub(r'(?m)^#\s+练习\b', r'#### 练习', text)
    text = re.sub(r'(?m)^#\s+随堂练习\b', r'#### 随堂练习', text)
    text = re.sub(r'(?m)^#\s+尝试·思考\b', r'#### 尝试·思考', text)

    text = re.sub(r'(?m)^#\s+复习参考题\s*(\d*)\b', r'## 复习参考题\1', text)
    text = re.sub(r'(?m)^#\s+复习巩固\b', r'### 复习巩固', text)
    text = re.sub(r'(?m)^#\s+综合运用\b', r'### 综合运用', text)
    text = re.sub(r'(?m)^#\s+拓广探索\b', r'### 拓广探索', text)
    text = re.sub(r'(?m)^#\s+小结\b', r'## 小结', text)
    text = re.sub(r'(?m)^#\s+([一二三四五六七八九十]+、)', r'### \1', text)
    text = re.sub(r'(?m)^#\s+（([一二三四五六七八九十]+)）', r'### （\1）', text)

    return text


def apply_image_caption_fixes(text: str) -> str:
    """图片与题注修正。"""
    # 修正被误识别为标题的图片和题注
    text = re.sub(r'(?m)^[ \t]*#\s*(!\[[^\]]*\]\([^\)\n]+\))[ \t]*$', r'\1', text)
    text = re.sub(r'(?m)^[ \t]*#\s*(图\s*\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$', r'\1', text)
    text = re.sub(r'(?m)^[ \t]*#\s*([（(][^）)\r\n]+[）)])[ \t]*$', r'\1', text)

    # 连续多张图片 + 连续多个题注
    def convert_labeled_figure_table(match):
        """将连续图片和连续题注转换为 Obsidian 引用块中的 Markdown 表格。"""
        content = match.group(0)
        image_lines = re.findall(r'^!\[[^\]]*\]\([^\)\n]+\)$', content, re.MULTILINE)
        caption_lines = re.findall(r'^(?:图\s*\d+(?:\.\d+)*(?:-\d+)?|（\d+）|（第\d+题）|（[^）]+）)$', content, re.MULTILINE)
        if len(image_lines) >= 2 and len(image_lines) == len(caption_lines):
            # 构建表格
            table_rows = []
            # 图片行
            img_cells = " | ".join([f"![]({re.search(r'\(([^)]+)\)', img).group(1)})" for img in image_lines])
            table_rows.append(f"| {img_cells} |")
            # 分隔行
            sep_cells = " | ".join(["---"] * len(image_lines))
            table_rows.append(f"| {sep_cells} |")
            # 题注行
            cap_cells = " | ".join(caption_lines)
            table_rows.append(f"| {cap_cells} |")
            table = "\n".join(table_rows)
            return f"> <center>\n> \n{table}\n> </center>"
        return content

    text = re.sub(
        r'(?:^!\[[^\]]*\]\([^\)\n]+\)\s*\n)+(?:^(?:图\s*\d+(?:\.\d+)*(?:-\d+)?|（\d+）|（第\d+题）|（[^）]+）)\s*\n)+',
        convert_labeled_figure_table,
        text,
        flags=re.MULTILINE,
    )

    # 单张图片 + 图号 / 第 X 题
    def convert_single_figure_markdown(match):
        """将单张图片和题注转换为 HTML 居中格式。"""
        img_line = match.group(1)
        caption_line = match.group(2)
        img_src = re.search(r'\(([^)]+)\)', img_line).group(1)
        return f'<center><img src="{img_src}" style="max-width:100%;"></center><center>{caption_line}</center>'

    text = re.sub(
        r'^(!\[[^\]]*\]\([^\)\n]+\))\s*\n(图\s*\d+(?:\.\d+)*(?:-\d+)?|（第\d+题）|（\d+）)',
        convert_single_figure_markdown,
        text,
        flags=re.MULTILINE,
    )

    # 图片转换后的空行清理
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', text)
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=<center><img)', '\n', text)
    text = re.sub(r'(?:\r?\n[ \t]*)+(?=<center>)', '', text)
    text = re.sub(r'</center>\n>', '</center>', text)

    return text


def apply_blank_line_fixes(text: str) -> str:
    """空行与段落间距修正。"""
    # 删除特殊行前多余空行
    text = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=(?:解|分析|方法|作法)[^\r\n]*$)', r'\n', text)
    text = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=[（(]\d+[）)][^\r\n]*$)', r'\n', text)
    text = re.sub(r'(?m)(；)[ \t]*\r?\n[ \t]*\r?\n', r'\1\n', text)
    text = re.sub(r'(?m)^(解[^\r\n]*)[ \t]*\r?\n[ \t]*\r?\n(?=(?:\|)|(?:!\[[^\]]*\]\()|(?:<center><img\b))', r'\1\n', text)
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=\$)', '\n', text)

    # 问号后补空行
    text = re.sub(r'(?m)^(.*？[ \t]*)\r?\n(?!\s*\r?\n)', r'\1\n\n', text)

    # 删除推导句前多余空行
    derivation_words = r'(?:解：|列方程|综上所述|根据题意|依题意|由题意|由已知|由条件|据题意|据已知|由此可知|由此可得|这就是说|也就是说|换句话说|换言之|同理可得|分类讨论|整理得|化简得|配方得|经检验|等式两边|方程两边|两边同乘|两边同除|去括号|因式分解|所以|因为|因此|于是|从而|∵|∴|显然|如果|假设|不妨|证明|欲证|要证|解得|可得|可知|代入|联立|移项|合并|消去|配方|首先|其次|最后|利用|通过|根据|判断|验证|讨论|说明|令|设|若|则|得|故|当|由|又|再|即|将|答|Rt)'
    text = re.sub(rf'(?m)[ \t]*\r?\n[ \t]*\r?\n(?={derivation_words})', r'\n', text)

    # 小题编号空行与手动换行
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=^[ \t]*[（(]\d+[）)])', '\n', text)
    text = re.sub(r'(?m)(?<!\s{2})(\r?\n)(?=^[ \t]*[（(]\d+[）)])', r'  \1', text)

    # ※ 前添加缩进
    text = re.sub(r'(?m)^([ \t]*)(※)', r'\1&emsp;\2', text)

    # 压缩连续空行
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')

    return text


def replace_in_file(path: Path) -> None:
    """读取文件内容，调用 protect_blocks 保护块，在保护后的文本上执行各项格式修复，最后用 restore_blocks 恢复并写回。"""
    try:
        original = path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"读取文件失败 {path}: {e}")
        return

    text, blocks = protect_blocks(original)

    # 统一流水线：所有规则按固定顺序执行
    text = apply_basic_cleanup(text)
    text = apply_formula_fixes(text)
    text = apply_choice_fixes(text)
    text = apply_callout_fixes(text)
    # apply_heading_case_fixes removed: heading normalization is Stage 1's job;
    # Stage 4 must protect heading lines per the skill's Protected Regions spec
    # apply_image_caption_fixes removed: its cleanup regexes merge image lines
    # with preceding text, causing per-line image reference count to drop
    text = apply_blank_line_fixes(text)

    text = restore_blocks(text, blocks)

    if text != original:
        try:
            path.write_text(text, encoding='utf-8')
            print(f"已更新: {path}")
        except Exception as e:
            print(f"写入文件失败 {path}: {e}")
    else:
        print(f"无需更新: {path}")


def main() -> None:
    """遍历目标目录下所有 .md 文件并执行格式修正。"""
    root = get_target_root()
    print(f"开始处理文件夹: {root}")

    # 跳过隐藏目录和常见工程目录
    skip_dirs = {'.git', '.obsidian', '.venv', '__pycache__', '.trash'}

    for md_file in root.rglob("*.md"):
        # 检查是否在跳过目录中
        should_skip = False
        for parent in md_file.parents:
            if parent.name in skip_dirs or parent.name.startswith('.'):
                should_skip = True
                break
        if should_skip:
            continue

        try:
            replace_in_file(md_file)
        except Exception as e:
            print(f"处理文件出错 {md_file}: {e}")
            continue

    print("处理完成。")


if __name__ == "__main__":
    main()

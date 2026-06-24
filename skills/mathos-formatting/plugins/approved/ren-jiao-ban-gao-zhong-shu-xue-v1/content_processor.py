import os
from pathlib import Path
import re

def get_target_root() -> Path:
    """获取目标文件夹路径，留空则使用脚本所在目录。"""
    user_input = input("请输入目标文件夹路径（留空则使用脚本所在目录）: ").strip()
    if user_input:
        return Path(user_input)
    return Path(__file__).parent

def protect_blocks(text: str) -> tuple[str, list[str]]:
    """保护 YAML、代码块、行内代码、行间公式、行内公式。"""
    blocks = []
    # 保护 YAML frontmatter
    def protect_yaml(match):
        blocks.append(match.group(0))
        return f"@@YAMLBLOCK{len(blocks)-1}@@"
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', protect_yaml, text, flags=re.DOTALL)
    # 保护 fenced code blocks
    def protect_code(match):
        blocks.append(match.group(0))
        return f"@@CODEBLOCK{len(blocks)-1}@@"
    text = re.sub(r'```[\s\S]*?```', protect_code, text)
    # 保护行内代码
    def protect_inline_code(match):
        blocks.append(match.group(0))
        return f"@@INLINECODE{len(blocks)-1}@@"
    text = re.sub(r'`[^`\n]+`', protect_inline_code, text)
    # 保护行间公式 $$
    def protect_display_math(match):
        blocks.append(match.group(0))
        return f"@@DISPLAYMATH{len(blocks)-1}@@"
    text = re.sub(r'\$\$[\s\S]*?\$\$', protect_display_math, text)
    # 保护行内公式 $
    def protect_inline_math(match):
        blocks.append(match.group(0))
        return f"@@INLINEMATH{len(blocks)-1}@@"
    text = re.sub(r'\$[^\$]*?\$', protect_inline_math, text)
    return text, blocks

def restore_blocks(text: str, blocks: list[str]) -> str:
    """恢复被保护内容。"""
    for i, block in enumerate(blocks):
        text = text.replace(f"@@YAMLBLOCK{i}@@", block)
        text = text.replace(f"@@CODEBLOCK{i}@@", block)
        text = text.replace(f"@@INLINECODE{i}@@", block)
        text = text.replace(f"@@DISPLAYMATH{i}@@", block)
        text = text.replace(f"@@INLINEMATH{i}@@", block)
    return text

def apply_basic_cleanup(text: str) -> str:
    """基础清理：删除空加粗标记和 details 标签。"""
    text = text.replace("**", "")
    text = re.sub(r'<details>[\s\S]*?</details>', '', text)
    return text

def apply_details_removal(text: str) -> str:
    """删除 details 标签（已包含在基础清理中，此函数保留占位）。"""
    return text

def apply_formula_fixes(text: str) -> str:
    """公式与 OCR 修正。"""
    text = re.sub(r'\\mathrm{([A-D])[\.．]}', r'\1', text)
    text = re.sub(r'\$\\mathrm{([A-D])[\.．]}', r'\1.$', text)
    text = re.sub(r"\$\$\n([\s\S]*?)\n\$\$", r"&!\1&!", text)
    text = re.sub(r"(?m)^\$\n([\s\S]*?)\n\$", r"&!\1&!", text)
    text = text.replace("&!", "$")
    text = text.replace("$$", "$")
    text = text.replace("$^{A,B,C}$", "${A,B,C}$")
    text = text.replace(r"\int_{\mathbb{R}}", r"\complement_{\mathbb{R}}")
    text = text.replace(r"\overset{⃑}", r"\overrightarrow")
    text = text.replace(r"\overset{→}", r"\overrightarrow")
    text = text.replace(r"$\qquad$", r"$\underline{\hspace{2cm}}$")
    return text

def apply_choice_fixes(text: str) -> str:
    """选择题选项拆分：把同一行中的 A. B. C. D. 拆分为多行。"""
    for _ in range(4):
        text = re.sub(r'^([A-D].*?)([A-D][\.．])', r'\1\n\2', text, flags=re.MULTILINE)
    return text

def apply_callout_fixes(text: str) -> str:
    """通用 callout 规则：删除教科书装饰图片，并将栏目标题转为 callout。"""
    # 删除教科书特殊标题前的图片链接和空行，添加特殊标记
    text = re.sub(
        r'(?m)^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:\r?\n)+(?=^[ \t]*#\s*(?:归纳|练习|溯源|探究|思考|观察|复习巩固|综合运用|拓广探索)\b)',
        '',
        text,
    )
    text = re.sub(r'(?m)^#\s+探究\b', r'> [!explore] 探究', text)
    text = re.sub(r'(?m)^#\s+思考\b', r'> [!think] 思考', text)
    text = re.sub(r'(?m)^#\s+尝试·思考\b', r'> [!think] 尝试·思考', text)
    text = re.sub(r'(?m)^#\s+观察\b', r'> [!observe] 观察', text)
    text = re.sub(r'(?m)^#\s+归纳\b', r'> [!tip] 归纳', text)
    text = re.sub(r'(?m)^#\s+尝试·交流\b', r'> [!tip] 尝试·交流', text)
    text = re.sub(r'(?m)^#\s+回顾·反思\b', r'> [!summary] 回顾·反思', text)
    text = re.sub(r'(?m)^#\s+操作·交流\b', r'> [!todo] 操作·交流', text)
    text = re.sub(r'(?m)^#\s+溯源\b', r'> [!quote] 溯源', text)
    text = re.sub(r'(?m)^(?:#\s+)?(例\s*\d+\b.*)$', r'> [!example]- \1', text)
    text = re.sub(r'(?m)^(?:#\s+)?(例 \d+\b.*)$', r'> [!example]- \1', text)
    text = re.sub(r'(?m)^(> \[!(?:quote|explore|think|observe|tip|summary|todo)\] (?:思考·交流|溯源|探究|思考|观察|归纳|尝试·思考|尝试·交流|回顾·反思|操作·交流))[ \t]*\r?\n[ \t]*\r?\n', r'\1\n', text)
    text = re.sub(r'(?m)^(> \[!example\]-[^\n]*)(\n[ \t]*\n)', r'\1\n', text)
    text = re.sub(r'(?m)(?<!\n)\n(?=[ \t]*> \[!)', '\n\n', text)
    return text

def apply_heading_case_fixes(text: str) -> str:
    """明确标题模式修正。"""
    text = re.sub(r'(?m)^(#\s+第[一二三四五六七八九十百]+章[^\r\n]*)\s*\r?\n\s*#\s+', r'\1 ', text)
    text = re.sub(r'(?m)^#\s+([（(]\d+[）)].*)$', r'\1', text)
    text = re.sub(r'(?m)^#\s+(\d+[\.．]\s*)', r'#### \1', text)
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
    # 删除图片和题注误识别为标题
    text = re.sub(r'(?m)^[ \t]*#\s*(!\[[^\]]*\]\([^\)\n]+\))[ \t]*$', r'\1', text)
    text = re.sub(r'(?m)^[ \t]*#\s*(图\s*\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$', r'\1', text)
    text = re.sub(r'(?m)^[ \t]*#\s*([（(][^）)\r\n]+[）)])[ \t]*$', r'\1', text)

    def fix_misordered_image_caption_blocks(text: str) -> str:
        image_re = re.compile(r'^[ \t]*!\[[^\]]*\]\(([^)\r\n]+)\)[ \t]*$')
        caption_re = re.compile(r'^[ \t]*(?:图\s*\d+(?:\.\d+)*(?:-\d+)?|[（(][^）)\r\n]+[）)])[ \t]*$')
        blank_re = re.compile(r'^[ \t]*$')
        lines = text.splitlines(True)
        out = []
        i = 0
        while i < len(lines):
            if image_re.match(lines[i]):
                imgs = []
                block_lines = []
                while i < len(lines) and (image_re.match(lines[i]) or blank_re.match(lines[i])):
                    if image_re.match(lines[i]):
                        imgs.append(image_re.match(lines[i]).group(1))
                    block_lines.append(lines[i])
                    i += 1
                while i < len(lines) and blank_re.match(lines[i]):
                    block_lines.append(lines[i])
                    i += 1
                caps = []
                cap_lines = []
                while i < len(lines) and caption_re.match(lines[i]):
                    caps.append(caption_re.match(lines[i]).group(0).strip())
                    cap_lines.append(lines[i])
                    i += 1
                if len(imgs) >= 2 and len(imgs) == len(caps):
                    table = [
                        '> <center>',
                        '> ',
                        '| ' + ' | '.join(f'![]({img})' for img in imgs) + ' |',
                        '| ' + ' | '.join(['---'] * len(imgs)) + ' |',
                        '| ' + ' | '.join(caps) + ' |',
                        '> </center>'
                    ]
                    out.append('\n'.join(table) + '\n')
                    continue
                out.extend(block_lines)
                out.extend(cap_lines)
                continue
            out.append(lines[i])
            i += 1
        return ''.join(out)

    def convert_labeled_figure_table(match):
        content = match.group(0)
        pairs = re.findall(
            r'!\[[^\]]*\]\(([^)\n]+)\)[ \t]*(?:\r?\n)+[ \t]*[（(]\s*([^）)]+?)\s*[）)]([^\r\n]*)',
            content,
        )
        caption_match = re.search(
            r'(?m)^[ \t]*((?:图\s*\d+(?:\.\d+)*(?:-\d+)?)|(?:[（(]第\s*\d+\s*题[）)]))[ \t]*$',
            content,
        )
        if len(pairs) < 2:
            return content
        image_cells = [f'![]({img})' for img, _, _ in pairs]
        label_cells = [f'（{num}）{suffix.strip()}'.strip() for _, num, suffix in pairs]
        table = [
            '> <center>',
            '> ',
            '> | ' + ' | '.join(image_cells) + ' |',
            '> | ' + ' | '.join(['---'] * len(image_cells)) + ' |',
            '> | ' + ' | '.join(label_cells) + ' |',
            '> </center>'
        ]
        if caption_match:
            table.append(f'> <center>{caption_match.group(1)}</center>')
            table.append('> ')
            return '\n'.join(table) + '\n'
        return '\n'.join(table) + '\n'

    labeled_figure_table_pattern = re.compile(
        r'(?m)'
        r'(?:'
        r'^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:\r?\n)+'
        r'[ \t]*[（(]\s*[^）)]+?\s*[）)][^\r\n]*(?:[ \t]*\r?\n+)'
        r'){2,}'
        r'(?:^[ \t]*(?:图\s*\d+(?:\.\d+)*(?:-\d+)?|[（(]第\s*\d+\s*题[）)])[ \t]*$)?'
    )
    text = labeled_figure_table_pattern.sub(convert_labeled_figure_table, text)

    text = fix_misordered_image_caption_blocks(text)
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', text)

    def convert_question_figure_row(match):
        content = match.group(0)
        imgs = re.findall(r'!\[[^\]]*\]\(([^)\n]+)\)', content)
        caption_match = re.search(
            r'(?m)^[ \t]*[（(]第\s*(\d+)\s*题[）)][ \t]*$',
            content,
        )
        if not caption_match:
            return content
        question_num = caption_match.group(1)
        image_cells = [f'![]({img})' for img in imgs]
        table = [
            '> <center>',
            '> ',
            '> | ' + ' | '.join(image_cells) + ' |',
            '> | ' + ' | '.join(['---'] * len(image_cells)) + ' |',
            '> </center>',
            f'> <center>（第{question_num}题）</center>',
            '> '
        ]
        return '\n'.join(table) + '\n'

    question_figure_row_pattern = re.compile(
        r'(?m)'
        r'(?:^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:[ \t]*\r?\n)+){2,}'
        r'^[ \t]*[（(]第\s*\d+\s*题[）)][ \t]*$'
    )
    text = question_figure_row_pattern.sub(convert_question_figure_row, text)

    def convert_numbered_figure_row(match):
        content = match.group(0)
        imgs = re.findall(r'!\[[^\]]*\]\(([^)\n]+)\)', content)
        caption_match = re.search(
            r'(?m)^[ \t]*[（(](\d+)[）)][ \t]*$',
            content,
        )
        if not caption_match:
            return content
        num = caption_match.group(1)
        image_cells = [f'![]({img})' for img in imgs]
        table = [
            '> <center>',
            '> ',
            '> | ' + ' | '.join(image_cells) + ' |',
            '> | ' + ' | '.join(['---'] * len(image_cells)) + ' |',
            '> </center>',
            f'> <center>（{num}）</center>',
            '> '
        ]
        return '\n'.join(table) + '\n'

    numbered_figure_row_pattern = re.compile(
        r'(?m)'
        r'(?:^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:[ \t]*\r?\n)+){2,}'
        r'^[ \t]*[（(]\d+[）)][ \t]*$'
    )
    text = numbered_figure_row_pattern.sub(convert_numbered_figure_row, text)

    def convert_plain_figure_table(match):
        content = match.group(0)
        imgs = re.findall(r'!\[[^\]]*\]\(([^)\n]+)\)', content)
        caption_match = re.search(
            r'(?m)^[ \t]*图\s*(\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$',
            content,
        )
        if len(imgs) < 2 or not caption_match:
            return content
        image_cells = [f'![]({img})' for img in imgs]
        table = [
            '> <center>',
            '> ',  
            '> | ' + ' | '.join(image_cells) + ' |',
            '> | ' + ' | '.join(['---'] * len(image_cells)) + ' |',
            '> </center>',
            f'> <center>图{caption_match.group(1)}</center>',
            '> '
        ]
        return '\n'.join(table) + '\n'

    plain_figure_table_pattern = re.compile(
        r'(?m)'
        r'(?:^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:[ \t]*\r?\n)+){2,}'
        r'^[ \t]*图\s*\d+(?:\.\d+)*(?:-\d+)?[ \t]*$'
    )
    text = plain_figure_table_pattern.sub(convert_plain_figure_table, text)

    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', text)

    text = re.sub(
        r'(?m)^(?P<prefix>>[ \t]*)(?P<row>\|[^\n]*\|)\s*(?P<center><center>(?:图|ͼ)\d+(?:\.\d+)*(?:-\d+)?</center>)\s*$',
        lambda m: f"{m.group('prefix')}{m.group('row')}\n\n{m.group('prefix')}{m.group('center')}",
        text,
    )

    def convert_single_figure_markdown(match):
        img = match.group(1)
        figure_num = match.group(2)
        question_num = match.group(3)
        caption = f'图{figure_num}' if figure_num else f'（第{question_num}题）'
        return f'<center><img src="{img}" style="max-width:100%;"></center><center>{caption}</center>'

    single_figure_markdown_pattern = re.compile(
        r'(?m)'
        r'^[ \t]*!\[[^\]]*\]\(([^)\n]+)\)[ \t]*(?:\r?\n)+'
        r'[ \t]*(?:图\s*(\d+(?:\.\d+)*(?:-\d+)?)|[（(]第\s*(\d+)\s*题[）)])[ \t]*$'
    )
    text = single_figure_markdown_pattern.sub(convert_single_figure_markdown, text)

    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=<center><img)', '\n', text)
    text = re.sub(r'(?:\r?\n[ \t]*)+(?=<center>)', '', text)
    text = re.sub(r'</center>\n>', '</center>', text)
    return text

def apply_blank_line_fixes(text: str) -> str:
    """空行修正。"""
    text = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=(?:解|分析|方法|作法)[^\r\n]*$)', r'\n', text)
    text = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=[（(]\d+[）)][^\r\n]*$)', r'\n', text)
    text = re.sub(r'(?m)(；)[ \t]*\r?\n[ \t]*\r?\n', r'\1\n', text)
    text = re.sub(r'(?m)^(解[^\r\n]*)[ \t]*\r?\n[ \t]*\r?\n(?=(?:\|)|(?:!\[[^\]]*\]\()|(?:<center><img\b))', r'\1\n', text)
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=\$)', '\n', text)
    text = re.sub(r'(?m)^(.*？[ \t]*)\r?\n(?!\s*\r?\n)', r'\1\n\n', text)
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=^[ \t]*[（(]\d+[）)])', '\n', text)
    text = re.sub(r'(?m)(?<!\s{2})(\r?\n)(?=^[ \t]*[（(]\d+[）)])', r'  \1', text)
    text = re.sub(r'(?m)^([ \t]*)(※)', r'\1&emsp;\2', text)
    # 数学推导词白名单：删除这些行前多余空行
    keywords = r'(?:解：|列方程|综上所述|根据题意|依题意|由题意|由已知|由条件|据题意|据已知|由此可知|由此可得|也就是说|同理可得|分类讨论|整理得|化简得|经检验|所以|因为|因此|于是|从而|∵|∴|显然|证明|欲证|要证|解得|可得|可知|代入|联立|移项|合并|消去|设|若|则|得|故|当|由|又|即|将|答|Rt)'
    text = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=' + keywords + r')', r'\n', text)
    return text

def compress_blank_lines(text: str) -> str:
    """压缩连续空行。"""
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    return text

def replace_in_file(path: Path) -> None:
    """读取、保护、修正、恢复并写回 Markdown 文件。"""
    try:
        original = path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"读取文件失败 {path}: {e}")
        return
    text, blocks = protect_blocks(original)
    new = text
    new = apply_basic_cleanup(new)
    new = apply_details_removal(new)
    new = apply_choice_fixes(new)
    new = apply_callout_fixes(new)
    new = apply_heading_case_fixes(new)
    new = apply_image_caption_fixes(new)
    new = apply_blank_line_fixes(new)
    new = compress_blank_lines(new)
    new = restore_blocks(new, blocks)
    new = apply_formula_fixes(new)
    new = compress_blank_lines(new)
    if new != original:
        try:
            path.write_text(new, encoding='utf-8')
            print(f"已更新: {path}")
        except Exception as e:
            print(f"写入文件失败 {path}: {e}")

def main() -> None:
    """递归处理目标目录下所有 Markdown 文件。"""
    root = get_target_root()
    if not root.exists():
        print(f"路径不存在: {root}")
        return
    skip_dirs = {'.git', '.obsidian', '.venv', '__pycache__', '.trash'}
    for md_file in root.rglob("*.md"):
        # 跳过隐藏或工程目录
        if any(part in skip_dirs for part in md_file.parts):
            continue
        replace_in_file(md_file)

if __name__ == "__main__":
    main()

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
    def protect_yaml(m):
        blocks.append(m.group(0))
        return f"@@YAML{len(blocks)-1}@@"
    text = re.sub(r'^---\n[\s\S]*?\n---\n', protect_yaml, text)
    # 保护 fenced code blocks
    def protect_code(m):
        blocks.append(m.group(0))
        return f"@@CODE{len(blocks)-1}@@"
    text = re.sub(r'```[\s\S]*?```', protect_code, text)
    # 保护行内代码
    def protect_inline_code(m):
        blocks.append(m.group(0))
        return f"@@INLINECODE{len(blocks)-1}@@"
    text = re.sub(r'`[^`\n]+`', protect_inline_code, text)
    # 保护行间公式 $$...$$
    def protect_display_math(m):
        blocks.append(m.group(0))
        return f"@@DISPLAYMATH{len(blocks)-1}@@"
    text = re.sub(r'\$\$[\s\S]*?\$\$', protect_display_math, text)
    # 保护行内公式 $...$
    def protect_inline_math(m):
        blocks.append(m.group(0))
        return f"@@INLINEMATH{len(blocks)-1}@@"
    text = re.sub(r'\$[^\$]*?\$', protect_inline_math, text)
    return text, blocks

def restore_blocks(text: str, blocks: list[str]) -> str:
    """恢复被保护内容。"""
    for i, block in enumerate(blocks):
        text = text.replace(f"@@YAML{i}@@", block)
        text = text.replace(f"@@CODE{i}@@", block)
        text = text.replace(f"@@INLINECODE{i}@@", block)
        text = text.replace(f"@@DISPLAYMATH{i}@@", block)
        text = text.replace(f"@@INLINEMATH{i}@@", block)
    return text

def apply_basic_cleanup(text: str) -> str:
    """基础清理：移除加粗标记和 details 标签。"""
    text = text.replace("**", "")
    text = re.sub(r'<details>[\s\S]*?</details>', '', text)
    return text

def apply_details_removal(text: str) -> str:
    """移除 details 标签（已包含在基础清理中，此函数保留占位）。"""
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
    """选择题选项拆分：将同一行中的 A. B. C. D. 拆分为多行。"""
    for _ in range(4):
        text = re.sub(r'^([A-D].*?)([A-D][\.．])', r'\1\n\2', text, flags=re.MULTILINE)
    return text

def apply_callout_fixes(text: str) -> str:
    """通用 callout 规则。"""
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?探究\b', r'> [!explore] 探究', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?思考\b', r'> [!think] 思考', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·思考\b', r'> [!think] 尝试·思考', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?观察\b', r'> [!observe] 观察', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?归纳\b', r'> [!tip] 归纳', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?尝试·交流\b', r'> [!tip] 尝试·交流', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?回顾·反思\b', r'> [!summary] 回顾·反思', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?操作·交流\b', r'> [!todo] 操作·交流', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{4,6}\s+|#\s+)?溯源\b', r'> [!quote] 溯源', text)
    text = re.sub(r'(?m)^[ \t]*(?:#{1,6}\s+)?(例\s*\d+\b.*)$', r'> [!example]- \1', text)
    # 确保 callout 前有空行
    text = re.sub(r'(?m)(?<!\n)\n(> \[!)', r'\n\n\1', text)
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
    text = re.sub(r'(?m)^[ \t]*#\s*(!\[[^\]]*\]\([^\)\n]+\))[ \t]*$', r'\1', text)
    text = re.sub(r'(?m)^[ \t]*#\s*(图\s*\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$', r'\1', text)
    text = re.sub(r'(?m)^[ \t]*#\s*([（(][^）)\r\n]+[）)])[ \t]*$', r'\1', text)
    # 图片空行清理
    text = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', text)
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
    # 数学推导词白名单空行清理
    math_words = r'(?:解：|列方程|综上所述|根据题意|依题意|由题意|由已知|由条件|据题意|据已知|由此可知|由此可得|也就是说|同理可得|分类讨论|整理得|化简得|经检验|所以|因为|因此|于是|从而|∵|∴|显然|证明|欲证|要证|解得|可得|可知|代入|联立|移项|合并|消去|设|若|则|得|故|当|由|又|即|将|答|Rt)'
    text = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=' + math_words + r')', r'\n', text)
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
    new = apply_formula_fixes(new)
    new = apply_choice_fixes(new)
    new = apply_callout_fixes(new)
    new = apply_heading_case_fixes(new)
    new = apply_image_caption_fixes(new)
    new = apply_blank_line_fixes(new)
    new = compress_blank_lines(new)
    new = restore_blocks(new, blocks)
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
        print(f"目录不存在: {root}")
        return
    skip_dirs = {'.git', '.obsidian', '.venv', '__pycache__', '.trash'}
    for md_file in root.rglob("*.md"):
        # 跳过隐藏目录和工程目录
        if any(part in skip_dirs for part in md_file.parts):
            continue
        replace_in_file(md_file)

if __name__ == "__main__":
    main()

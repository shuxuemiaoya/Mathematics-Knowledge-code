import re
from pathlib import Path
import shutil
from typing import Optional
from .logger import get_logger

logger = get_logger()

class BaseFormatter:
    """基类：提供预编译的正则表达式和通用的 Markdown 清洗方法。"""
    
    # === 预编译公用正则表达式 ===
    RE_MATH_OPTION_1 = re.compile(r'\\mathrm{([A-D])[\.．]}')
    RE_MATH_OPTION_2 = re.compile(r'\$\\mathrm{([A-D])[\.．]}')
    
    # 行间公式变行内公式
    RE_BLOCK_MATH_1 = re.compile(r"\$\$\n([\s\S]*?)\n\$\$")
    RE_BLOCK_MATH_2 = re.compile(r"(?m)^\$\n([\s\S]*?)\n\$")
    
    # 选项前添加换行符
    RE_ADD_NEWLINE_OPTIONS = re.compile(r'^([A-D].*?)(?<!\n)([A-D][\.．])', flags=re.MULTILINE)
    
    def __init__(self):
        pass

    def _replace_common(self, text: str) -> str:
        """执行通用的清洗替换。"""
        new_text = text
        
        # 删除所有粗体
        new_text = new_text.replace("**", "")
        
        # 删除 <details> 块（包括其全部内容）
        new_text = re.sub(r'<details>[\s\S]*?</details>', '', new_text)
        
        # 修正选项
        new_text = self.RE_MATH_OPTION_1.sub(r'\1', new_text)
        new_text = self.RE_MATH_OPTION_2.sub(r'\1.$', new_text)
        
        # 行间公式变为行内公式
        new_text = self.RE_BLOCK_MATH_1.sub(r"&!\1&!", new_text)
        new_text = self.RE_BLOCK_MATH_2.sub(r"&!\1&!", new_text)
        new_text = new_text.replace("&!", "$")
        new_text = new_text.replace("$$", "$")
        
        # 在选项前添加换行符（如果前面没有换行符的话）
        # 执行多次以确保连在一起的 A B C D 都被分开
        for _ in range(4):
            new_text = self.RE_ADD_NEWLINE_OPTIONS.sub(r'\1\n\2', new_text)
            
        # 修正常见识别错误
        new_text = new_text.replace("$^{A,B,C}$", "${A,B,C}$")
        new_text = new_text.replace(r"\int_{\mathbb{R}}", r"\complement_{\mathbb{R}}")
        new_text = new_text.replace(r"\overset{⃑}", r"\overrightarrow")
        new_text = new_text.replace(r"\overset{→}", r"\overrightarrow")
        
        # 修复 Obsidian 无法渲染 \prime 的问题，统一转为普通的撇号 '
        new_text = new_text.replace(r"^{\prime}", "'")
        new_text = new_text.replace(r"\prime", "'")
        
        # 统一题号和列表的半角括号为全角： (1) -> （1）
        new_text = re.sub(r'(?<![a-zA-Z0-9_])\(([0-9]+)\)', r'（\1）', new_text)
        
        # 填空题修正：下划线
        new_text = new_text.replace(r"$\qquad$", r"$\underline{\hspace{2cm}}$")
        
        return new_text

    def _cleanup_empty_lines(self, text: str) -> str:
        """删除连续多余空行，最多保留两个换行符。"""
        new_text = text
        while '\n\n\n' in new_text:
            new_text = new_text.replace('\n\n\n', '\n\n')
        return new_text

    def format_string(self, text: str) -> str:
        """子类需实现或扩展此方法。"""
        text = self._replace_common(text)
        return self._cleanup_empty_lines(text)

    def process_file(self, path: Path, backup: bool = False, dry_run: bool = False) -> bool:
        """处理单个文件。"""
        try:
            txt = path.read_text(encoding="utf-8")
            new_txt = self.format_string(txt)
            
            if new_txt != txt:
                if dry_run:
                    logger.info(f"Would update: {path}")
                    return True

                if backup:
                    backup_path = path.with_suffix(path.suffix + '.bak')
                    shutil.copy2(path, backup_path)
                    logger.info(f"Backup created: {backup_path}")
                    
                path.write_text(new_txt, encoding="utf-8")
                logger.info(f"Updated: {path}")
                return True
            else:
                logger.debug(f"No changes needed: {path}")
                return False
        except Exception as e:
            logger.error(f"Error processing {path}: {e}")
            return False

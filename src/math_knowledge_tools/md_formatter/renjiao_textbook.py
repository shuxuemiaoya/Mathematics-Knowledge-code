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

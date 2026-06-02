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
        
        # 标题层级标准化
        self.re_chapter = re.compile(r'(?m)^#\s+(第[一二三四五六七八九十百]+章[^\r\n]*)$')
        self.re_section = re.compile(r'(?m)^#\s+(\d+\.\d+\s+[^\r\n]*)$')
        self.re_subsection = re.compile(r'(?m)^#\s+(阅读与思考|探究与发现|信息技术应用|小结|复习参考题\s*\d*)$')
        
        # 特定版块转 Callout
        self.re_think = re.compile(r'(?m)^#\s+(思考\b)')
        self.re_observe = re.compile(r'(?m)^#\s+(观察\b)')
        self.re_explore = re.compile(r'(?m)^#\s+(探究\b)')
        
        # 删除天然图片标注
        self.re_details = re.compile(r'<details>\s*<summary>(?:natural_image|text_image)</summary>(?:[^<]+|<(?!/details>))*</details>')

    def format_string(self, text: str) -> str:
        new = self._replace_common(text)
        
        # 1. 目录页码清理
        new = self.re_toc_page_numbers.sub(r'\1', new)
        
        # 2. 标题层级标准化
        new = self.re_chapter.sub(r'# \1', new)
        new = self.re_section.sub(r'## \1', new)
        new = self.re_subsection.sub(r'## \1', new)
        
        # 3. 特定版块转 Callout
        new = self.re_example.sub(r'> [!example]- \1', new)
        new = self.re_think.sub(r'> [!think] 思考', new)
        new = self.re_observe.sub(r'> [!observe] 观察', new)
        new = self.re_explore.sub(r'> [!explore] 探究', new)
        
        # 4. 删除天然图片标注
        new = self.re_details.sub('', new)
        
        return self._cleanup_empty_lines(new)

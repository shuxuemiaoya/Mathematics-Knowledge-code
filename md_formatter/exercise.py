import re
from .core import BaseFormatter

class ExerciseFormatter(BaseFormatter):
    """习题专用的 Markdown 清洗器，包含题型修改、解析分离、选项对齐等功能。"""
    
    def __init__(self, variant="default"):
        super().__init__()
        self.variant = variant
        
        # 预编译通用题型正则
        self.re_header_chinese_num = re.compile(r'(?m)^#*\s*([一二三四五六七八九十]+)、(.*)$')
        self.re_tixing = re.compile(r'(?m)^(题型\d*)')
        self.re_zhishidian = re.compile(r'(?m)^\s*(知识点\d*)')
        self.re_num_dot = re.compile(r'(?m)^(\d+[\.．]\s*)')
        self.re_li = re.compile(r'(?m)^(例\d*)')
        self.re_litix = re.compile(r'(?m)^(例题\d*)')
        self.re_num_bracket = re.compile(r'(?m)^(\d+\[\s*)')
        self.re_kuohao_li = re.compile(r'(?m)^(【例题\d*】)')
        self.re_kuohao_dianli = re.compile(r'(?m)^(【典例\d*】)')
        self.re_kuohao_lix = re.compile(r'(?m)^(【例\d*】)')
        self.re_bianshi = re.compile(r'(?m)^(【变式\d*】)')
        self.re_kuohao_num = re.compile(r'(?m)^(【\d*】)')
        
        self.re_answer = re.compile(r'(?m)^(\s*)答案：?')
        self.re_analysis = re.compile(r'(?m)^(\s*)解析：?')
        self.re_solution = re.compile(r'(?m)^(\s*)解法(\d+)：?')
        
        self.re_option_indent = re.compile(r'(?m)^([A-Z][\.．]\s*)')
        self.re_tag_answer = re.compile(r'(?m)^(【答案】)')
        self.re_tag_analysis = re.compile(r'(?m)^(【解析】)')
        self.re_tag_analyze = re.compile(r'(?m)^(【分析】)')
        self.re_tag_detail = re.compile(r'(?m)^(【详解】)')
        
        self.re_remove_img_blocks = re.compile(r'(!\[.*?\]\(.*?\)\n){3,}')
        
        # 一数习题特调
        self.re_yishu_header_num = re.compile(r'(?m)^#\s+(\d+)(.*)')
        self.re_yishu_merge = re.compile(r'(?m)^(\d+[\.．].*)\r?\n')

    def format_string(self, text: str) -> str:
        new = self._replace_common(text)
        
        # 1. 基础题型标题修改（默认开启）
        if self.variant in ["default", "yishu", "bishua", "all"]:
            new = self.re_header_chinese_num.sub(r'### \1、\2', new)
            new = self.re_tixing.sub(r'### \1', new)
            new = self.re_zhishidian.sub(r'### \1 ', new)
            
            new = self.re_num_dot.sub(r'##### \1', new)
            new = self.re_li.sub(r'##### \1', new)
            new = self.re_litix.sub(r'##### \1', new)
            new = self.re_num_bracket.sub(r'##### \1', new)
            new = self.re_kuohao_li.sub(r'##### \1', new)
            new = self.re_kuohao_dianli.sub(r'##### \1', new)
            new = self.re_kuohao_lix.sub(r'##### \1', new)
            new = self.re_bianshi.sub(r'##### \1', new)
            new = self.re_kuohao_num.sub(r'##### \1', new)
            
            # 解析答案分割与高亮
            new = self.re_answer.sub(r'\n【答案】', new)
            new = self.re_analysis.sub(r'\n【解析】', new)
            new = self.re_solution.sub(r'\n【解法\2】', new)
            
            new = self.re_option_indent.sub(r'quadaaa\1', new)
            new = new.replace("quadaaa", r"$\quad$")
            
            new = self.re_tag_answer.sub(r'<span class="fake-tag">答案</span>', new)
            new = self.re_tag_analysis.sub(r'<span class="fake-tag">解析</span>', new)
            new = self.re_tag_analyze.sub(r'<span class="fake-tag">分析</span>', new)
            new = self.re_tag_detail.sub(r'<span class="fake-tag">详解</span>', new)
            
            # 试卷格式清理
            new = self.re_remove_img_blocks.sub('', new)
            new = re.sub(r'# 难度 \|', '', new)
            new = re.sub(r'难度 \|', '', new)
            new = re.sub(r'# 难度', '', new)    
            new = re.sub(r'# 作答区', '', new)
            new = re.sub(r'作答区', '', new)

        # 2. 一数习题特调
        if self.variant in ["yishu", "all"]:
            new = self.re_yishu_header_num.sub(r'\1\2', new)
            new = self._replace_second_occurrence(new)
            new = self.re_yishu_merge.sub(r'\1 ', new)

        # 3. 必刷题特调
        if self.variant in ["bishua", "all"]:
            new = re.sub(r'(?m)^#*\s*易错点(\d*)', r'### 易错点\1 ', new)
            new = re.sub(r'(?m)^#*\s*考点(\d*)', r'### 考点\1 ', new)
            new = re.sub(r'(?m)^\s*#*\s*知识点(\d*)', r'### 知识点\1 ', new)

            new = new.replace("# 则", "# 刷")
            new = new.replace("# 屏", "# 刷")
            new = new.replace("# 副", "# 刷")
            new = new.replace("# 刚", "# 刷")
            new = new.replace("# 真题", "# 刷真题")

            new = new.replace("# 题型", "### 题型")
            new = new.replace("# 刷基础", "## 刷基础")
            new = new.replace("# 刷提升", "## 刷提升")
            new = new.replace("# 刷能力", "## 刷能力")
            new = new.replace("# 刷易错", "## 刷易错")
            new = new.replace("# 刷难关", "## 刷难关")
            new = new.replace("# 刷真题", "## 刷真题")
            new = new.replace("# 刷速度", "## 刷速度")

        return self._cleanup_empty_lines(new)

    def _replace_second_occurrence(self, text: str) -> str:
        """处理题号重复 → 第二次出现的数字改成 '答案'"""
        counts = {}
        lines = text.splitlines()
        new_lines = []
        for line in lines:
            m = re.match(r'^(\s*)(\d+)[\.．]\s*(.*)$', line)
            if m:
                indent, num, rest = m.group(1), m.group(2), m.group(3)
                counts[num] = counts.get(num, 0) + 1
                if counts[num] == 2:
                    line = f"{indent}答案 {rest}" if rest else f"{indent}答案"
            new_lines.append(line)
        return "\n".join(new_lines)

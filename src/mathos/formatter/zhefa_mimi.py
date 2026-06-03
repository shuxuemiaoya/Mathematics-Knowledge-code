import re
from .core import BaseFormatter

class ZhefaMimiFormatter(BaseFormatter):
    def __init__(self):
        super().__init__()
        
        # 匹配目录行（包含页码，即使没有点线仅有空格隔开）
        self.re_toc_line = re.compile(r'(?m)^\s*(?:#+\s*)?(?:第[一二三四五六七八九十百]+章|[\d]+\.[\d]+|附录|索引|参考文献|后记|前言|目录|Contents|B|录)[^\n]*?(?:\.{3,}|\…{3,}|\s+)\d+\s*$')
        
        # 匹配单独的页码行（如 "…… 1" 或 "...... 23"）
        self.re_toc_page_only = re.compile(r'(?m)^\s*(?:\.{3,}|\…{3,})\s*\d+\s*$')
        
        # 匹配章节标题（如 "第一章 本书开始,我们需要了解的"）
        self.re_chapter = re.compile(r'(?m)^(?:#\s*)?(第[一二三四五六七八九十百]+章[^\n]*)$')
        
        # 匹配节标题（如 "1.1 高中导数基础"）
        self.re_section = re.compile(r'(?m)^(?:#\s*)?(\d+\.\d+\s+[^\n]*)$')
        
        # 匹配小节标题（如 "1.1.1" 或 "习题" 或 "练习"）
        self.re_subsection = re.compile(r'(?m)^(?:#\s*)?(\d+\.\d+\.\d+[^\n]*|习题[^\n]*|练习[^\n]*|复习参考题[^\n]*)$')
        
        # 匹配子小节标题（如 "小节练习"）
        self.re_subsubsection = re.compile(r'(?m)^(?:#\s*)?(小节练习[^\n]*)$')
        
        # 删除 "目录"、"Contents" 或 OCR 拆分的 "日"、"录" 等纯目录标记行
        self.re_toc_marker = re.compile(r'(?m)^\s*(?:#+\s*)?(?:目录|Contents|B|录|日)\s*$')
        
        # 匹配思考/探究/观察/归纳/例题等关键词，转换为Obsidian callout
        self.re_think = re.compile(r'(?m)^\s*思考[：:]\s*(.*)$')
        self.re_explore = re.compile(r'(?m)^\s*探究[：:]\s*(.*)$')
        self.re_observe = re.compile(r'(?m)^\s*观察[：:]\s*(.*)$')
        self.re_tip = re.compile(r'(?m)^\s*归纳[：:]\s*(.*)$')
        self.re_example = re.compile(r'(?m)^\s*例(\d+)[：:。]?\s*(.*)$')
        
        # 匹配解:、因为、所以等连续段落，去除多余空行
        self.re_continuation = re.compile(r'(?m)^(解[：:]|因为|所以|即|则|故|因此|于是|从而|又|且|但|而|设|令|取|当|若|如果|则|那么|由|从|在|对|于|将|把|以|用|作|作[：:]|证[：:]|证明[：:]|分析[：:]|解答[：:]|答[：:])\s*')
        
        # 匹配图片和说明行，合并为居中格式
        self.re_image_caption = re.compile(r'(?m)^\s*!\[.*?\]\(.*?\)\s*\n\s*[（(]?图[\d\-\.]+[^）)]*[）)]?\s*$')
        
        # 匹配选项A. B. C. D. 缩进
        self.re_options = re.compile(r'(?m)^\s*([A-D]\.)\s*(.*)$')
        
        # 匹配编号题目（如1. 2. 3. 或（1）（2）（3））
        self.re_question_number = re.compile(r'(?m)^\s*(\d+\.|[（(]\d+[）)])\s*')
        
        # 清理OCR伪影：多余的空格、乱码行、孤立符号
        self.re_ocr_artifact = re.compile(r'(?m)^\s*[\-—]\s*\d{4}\s*[\-—]\s*\d{4}\s*$')
        self.re_ocr_junk = re.compile(r'(?m)^\s*[◎○●◆◇■□▲△▼▽★☆※→←↑↓↖↗↙↘]+.*$')
        self.re_ocr_spaces = re.compile(r'[　 ]+')

    def format_string(self, text: str) -> str:
        new = self._replace_common(text)
        
        # 1. 删除所有目录行（带页码的）
        new = self.re_toc_line.sub('', new)
        
        # 2. 删除单独的页码行
        new = self.re_toc_page_only.sub('', new)
        
        # 3. 删除目录标记行
        new = self.re_toc_marker.sub('', new)
        
        # 4. 标准化标题层级
        new = self.re_chapter.sub(r'# \1', new)
        new = self.re_section.sub(r'## \1', new)
        new = self.re_subsection.sub(r'### \1', new)
        new = self.re_subsubsection.sub(r'#### \1', new)
        
        # 5. 转换思考/探究/观察/归纳为callout
        new = self.re_think.sub(r'> [!think] 思考\n> \1', new)
        new = self.re_explore.sub(r'> [!explore] 探究\n> \1', new)
        new = self.re_observe.sub(r'> [!observe] 观察\n> \1', new)
        new = self.re_tip.sub(r'> [!tip] 归纳\n> \1', new)
        new = self.re_example.sub(r'> [!example]- 例\1\n> \2', new)
        
        # 6. 处理连续段落（解:、因为、所以等），去除多余空行
        new = self.re_continuation.sub(r'\1', new)
        
        # 7. 图片和说明行合并为居中格式（简单处理：确保图片后紧跟说明）
        new = self.re_image_caption.sub(lambda m: m.group(0).replace('\n', '  \n'), new)
        
        # 8. 选项缩进（A. B. C. D.）
        new = self.re_options.sub(r'    \1 \2', new)
        
        # 9. 编号题目缩进（1. 2. 3. 或（1）（2）（3））
        new = self.re_question_number.sub(r'    \1 ', new)
        
        # 10. 清理OCR伪影
        new = self.re_ocr_artifact.sub('', new)
        new = self.re_ocr_junk.sub('', new)
        new = self.re_ocr_spaces.sub(' ', new)
        
        # 11. 清理多余空行
        new = self._cleanup_empty_lines(new)
        
        return new
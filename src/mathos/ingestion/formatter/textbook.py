import re
from .core import BaseFormatter

class TextbookFormatter(BaseFormatter):
    """教科书专用的 Markdown 清洗器，包含复杂的题注、表格和排版恢复规则。"""
    
    def __init__(self):
        super().__init__()
        
        # 预编译高级规则
        self.re_remove_img_before_special = re.compile(
            r'(?m)^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:\r?\n)+(?=^[ \t]*#\s*(?:归纳|练习|溯源|探究|思考|观察|复习巩固|综合运用|拓广探索)\b)'
        )
        self.re_empty_lines_after_marks = re.compile(
            r'(?m)^(> \[!(?:quote|explore|think|observe|tip|summary|todo)\] (?:思考·交流|溯源|探究|思考|观察|归纳|尝试·思考|尝试·交流|回顾·反思|操作·交流))[ \t]*\r?\n[ \t]*\r?\n'
        )
        self.re_header_merge = re.compile(r'(?m)^(#\s+第[一二三四五六七八九十百]+章[^\r\n]*)\s*\r?\n\s*#\s+')
        
        # 中文词语空行删除
        self.re_remove_newlines_before_chinese = re.compile(
            r'(?m)(?:\r?\n[ \t]*)+(?=(?:'
            r'解：|列方程|综上所述|根据题意|依题意|由题意|由已知|由条件|据题意|如图|据已知|不失一般性|'
            r'由此可知|由此可得|这就是说|也就是说|换句话说|换言之|此时|此刻|此处|此题|因此可知|因此可得|因此得出|因此说明|因此判断|因此分析|因此讨论|因此比较|'
            r'同理可得|分类讨论|系数化为|整理得|化简得|配方得|经检验|经验证|经计算|经分析|经讨论|经说明|经判断|经观察|经比较|'
            r'等式两边|方程两边|等号两边|两边同乘|两边同除|两边平方|第二步|第三步|第四步|第五步|第六步|第七步|第八步|第九步|第十步|下一步|最后一步|'
            r'去括号|因式分解|提取公因式|分母有理化|上面两式相加|上面两式相减|上面两式相乘|上面两式相除|上面两式联立|'
            r'分析|接|所以|因为|因此|因而|故而|于是|从而|进而|故此|故知|∵|∴|'
            r'显然|事实上|另一方面|特别地|尤其是|注意到|'
            r'如果|假设|假定|不妨|只要|必须|否则|反之|'
            r'证明|欲证|要证|即证|亦即|也即|此时|'
            r'解得|求得|可得|可知|可见|'
            r'代入|联立|移项|合并|消去|配方|通分|约分|换元|'
            r'首先|其次|最后|接着|然后|随后|'
            r'利用|通过|根据|判断|验证|讨论|说明|'
            r'转化|变形|恒成立|'
            r'令|设|若|则|得|故|当|由|又|再|即|将|答|在|Rt|'
            r'由于|由此|对比|比较|满足|符合|对应|分别|其中|'
            r'不难|容易|综合|总之|所求|欲求|原式|原方程|'
            r'方法|作法))'
        )
        
        self.labeled_figure_table_pattern = re.compile(
            r'(?m)(?:^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:\r?\n)+[ \t]*[（(]\s*[^）)]+?\s*[）)][^\r\n]*(?:[ \t]*\r?\n)+){2,}'
            r'(?:^[ \t]*(?:图\s*\d+(?:\.\d+)*(?:-\d+)?|[（(]第\s*\d+\s*题[）)])[ \t]*$)?'
        )
        
        self.question_figure_row_pattern = re.compile(
            r'(?m)(?:^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:[ \t]*\r?\n)+){2,}'
            r'^[ \t]*[（(]第\s*\d+\s*题[）)][ \t]*$'
        )

        self.numbered_figure_row_pattern = re.compile(
            r'(?m)(?:^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:[ \t]*\r?\n)+){2,}'
            r'^[ \t]*[（(]\d+[）)][ \t]*$'
        )

        self.plain_figure_table_pattern = re.compile(
            r'(?m)(?:^[ \t]*!\[[^\]]*\]\([^\)\n]+\)[ \t]*(?:[ \t]*\r?\n)+){2,}'
            r'^[ \t]*图\s*\d+(?:\.\d+)*(?:-\d+)?[ \t]*$'
        )

        self.single_figure_markdown_pattern = re.compile(
            r'(?m)^[ \t]*!\[[^\]]*\]\(([^)\n]+)\)[ \t]*(?:\r?\n)+'
            r'[ \t]*(?:图\s*(\d+(?:\.\d+)*(?:-\d+)?)|[（(]第\s*(\d+)\s*题[）)])[ \t]*$'
        )

    def format_string(self, text: str) -> str:
        new = self._replace_common(text)
        
        # 1. 特殊标记和 Callout
        new = self.re_remove_img_before_special.sub('', new)
        new = re.sub(r'(?m)^#\s+探究\b', r'> [!explore] 探究', new)
        new = re.sub(r'(?m)^#\s+思考\b', r'> [!think] 思考', new)
        new = re.sub(r'(?m)^#\s+尝试·思考\b', r'> [!think] 尝试·思考', new)
        new = re.sub(r'(?m)^#\s+观察\b', r'> [!observe] 观察', new)
        new = re.sub(r'(?m)^#\s+归纳\b', r'> [!tip] 归纳', new)
        new = re.sub(r'(?m)^#\s+尝试·交流\b', r'> [!tip] 尝试·交流', new)
        new = re.sub(r'(?m)^#\s+回顾·反思\b', r'> [!summary] 回顾·反思', new)
        new = re.sub(r'(?m)^#\s+操作·交流\b', r'> [!todo] 操作·交流', new)
        new = re.sub(r'(?m)^#\s+溯源\b', r'> [!quote] 溯源', new)
        new = re.sub(r'(?m)^(?:#\s+)?(例\d+.*)$', r'> [!example]- \1', new)
        new = re.sub(r'(?m)^(?:#\s+)?(例 \d+\b.*)$', r'> [!example]- \1', new)    

        # 删除多余空行
        new = self.re_empty_lines_after_marks.sub(r'\1\n', new)
        new = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=(?:解|分析|方法|作法)[^\r\n]*$)', r'\n', new)
        new = re.sub(r'(?m)[ \t]*\r?\n[ \t]*\r?\n(?=[（(]\d+[）)][^\r\n]*$)', r'\n', new)
        new = re.sub(r'(?m)(；)[ \t]*\r?\n[ \t]*\r?\n', r'\1\n', new)
        new = re.sub(r'(?m)^(解[^\r\n]*)[ \t]*\r?\n[ \t]*\r?\n(?=(?:\|)|(?:!\[[^\]]*\]\()|(?:<center><img\b))', r'\1\n', new)

        # 2. 标题层级修正
        new = self.re_header_merge.sub(r'\1 ', new)
        new = re.sub(r'(?m)^#\s+([（(]\d+[）)].*)$', r'\1', new)
        new = re.sub(r'(?m)^#\s+(\d+[\.．]\s*)', r'#### \1', new)
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

        # 3. 图表修正
        new = re.sub(r'(?m)^[ \t]*#\s*(!\[[^\]]*\]\([^\)\n]+\))[ \t]*$', r'\1', new)
        new = re.sub(r'(?m)^[ \t]*#\s*(图\s*\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$', r'\1', new)
        new = re.sub(r'(?m)^[ \t]*#\s*([（(][^）)\r\n]+[）)])[ \t]*$', r'\1', new)
        new = self._fix_misordered_image_caption_blocks(new)
        new = self.labeled_figure_table_pattern.sub(self._convert_labeled_figure_table, new)
        new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', new)
        new = self.question_figure_row_pattern.sub(self._convert_question_figure_row, new)
        new = self.numbered_figure_row_pattern.sub(self._convert_numbered_figure_row, new)
        new = self.plain_figure_table_pattern.sub(self._convert_plain_figure_table, new)
        new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=> (?:\||<center>))', '\n', new)
        new = re.sub(r'(?m)^(?P<prefix>>[ \t]*)(?P<row>\|[^\n]*\|)\s*(?P<center><center>(?:图|ͼ)\d+(?:\.\d+)*(?:-\d+)?</center>)\s*$', lambda m: f"{m.group('prefix')}{m.group('row')}\n\n{m.group('prefix')}{m.group('center')}", new)
        new = self.single_figure_markdown_pattern.sub(self._convert_single_figure_markdown, new)

        # 4. 空行和缩进细节
        new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=<center><img)', '\n', new)
        new = re.sub(r'(?:\r?\n[ \t]*)+(?=<center>)', '', new)
        new = re.sub(r'</center>\n>', '</center>', new) 
        new = re.sub(r'(?m)(?<!\n)\n(?=[ \t]*> \[!)', '\n\n', new)
        new = re.sub(r'(?m)^(> \[!example\]-[^\n]*)(\n[ \t]*\n)', r'\1\n', new)
        new = re.sub(r'(?m)(?<!\n)\n(?=[ \t]*> \[!)', '\n\n', new)
        new = re.sub(r'(?m)^(.*？[ \t]*)\r?\n(?!\s*\r?\n)', r'\1\n\n', new)
        new = self.re_remove_newlines_before_chinese.sub('\n', new)
        new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=\$)', '\n', new)
        new = re.sub(r'(?m)(?:\r?\n[ \t]*)+(?=^[ \t]*[（(]\d+[）)])', '\n', new)
        new = re.sub(r'(?m)(?<!\s{2})(\r?\n)(?=^[ \t]*[（(]\d+[）)])', r'  \1', new)
        new = re.sub(r'(?m)^([ \t]*)(※)', r'\1&emsp;\2', new)

        return self._cleanup_empty_lines(new)

    def _fix_misordered_image_caption_blocks(self, text):
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

    def _convert_labeled_figure_table(self, match):
        content = match.group(0)
        pairs = re.findall(r'!\[[^\]]*\]\(([^)\n]+)\)[ \t]*(?:\r?\n)+[ \t]*[（(]\s*([^）)]+?)\s*[）)]([^\r\n]*)', content)
        caption_match = re.search(r'(?m)^[ \t]*((?:图\s*\d+(?:\.\d+)*(?:-\d+)?)|(?:[（(]第\s*\d+\s*题[）)]))[ \t]*$', content)
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

    def _convert_question_figure_row(self, match):
        content = match.group(0)
        imgs = re.findall(r'!\[[^\]]*\]\(([^)\n]+)\)', content)
        caption_match = re.search(r'(?m)^[ \t]*[（(]第\s*(\d+)\s*题[）)][ \t]*$', content)
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

    def _convert_numbered_figure_row(self, match):
        content = match.group(0)
        imgs = re.findall(r'!\[[^\]]*\]\(([^)\n]+)\)', content)
        caption_match = re.search(r'(?m)^[ \t]*[（(](\d+)[）)][ \t]*$', content)
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

    def _convert_plain_figure_table(self, match):
        content = match.group(0)
        imgs = re.findall(r'!\[[^\]]*\]\(([^)\n]+)\)', content)
        caption_match = re.search(r'(?m)^[ \t]*图\s*(\d+(?:\.\d+)*(?:-\d+)?)[ \t]*$', content)
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

    def _convert_single_figure_markdown(self, match):
        img = match.group(1)
        figure_num = match.group(2)
        question_num = match.group(3)
        caption = f'图{figure_num}' if figure_num else f'（第{question_num}题）'
        return f'<center><img src="{img}" style="max-width:100%;"></center><center>{caption}</center>'

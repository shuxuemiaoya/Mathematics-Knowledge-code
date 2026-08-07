import os
import re
import shutil

ALIAS_MAP = {
    '图象': '函数 y = A sin(ωx + φ)',
    '函数的应用(一)': '函数的应用（一）',
    '函数的应用(二)': '函数的应用（二）',
    '函数模型的应用': '函数的应用（二）',
    '不同函数增长的差异': '一次函数、指数函数和对数函数增长方式的差异',
    '一元二次函数_方程和不等式': '二次函数与一元二次方程、不等式',
    '二次函数与一元二次方程_不等式': '二次函数与一元二次方程、不等式',
    '充分条件与必要条件_1.4.2_充要条件': '充分条件与必要条件',
    '全称量词与存在量词': '全称量词与存在量词',
    'n次方根与分数指数幂_4.1.2_无理数指数幂及其运算': '分数指数幂',
    '对数的概念_4.3.2_对数的运算': '对数的概念与运算',
    '对数函数的概念_4.4.2_对数函数的图象和性质': '对数函数的图象和性质',
}

def clean_qtype(q_name):
    name = re.sub(r'\.md$', '', q_name)
    name = re.sub(r'_b\d+$', '', name)
    name = re.sub(r'^(题型|易错点|微专题|专题|考点)\s*\d*\s*', '', name)
    return name.strip()

def clean_title(name):
    return re.sub(r'_b\d+$', '', name)

def extract_section_name(rel_path):
    parts = rel_path.split(os.sep)
    for part in parts:
        if re.match(r'^\d+(\.\d+)*_', part):
            s = re.sub(r'^[\d\._]+', '', part)
            return s.strip()
    for part in parts:
        if '章' in part:
            s = re.sub(r'^\d+-', '', part)
            s = re.sub(r'^第.章_', '', s)
            return s.strip()
    return '必修第一册'

def archive_and_link_mathmap(vault_root, source_book_dirs=None, source_name="2026版 高中必刷题数学必修第一册"):
    """
    三级递进拓扑物理落盘与归档：
    - Tier 1: questions/ 放置具体单题 md，嵌入 answers/ 解析
    - Tier 2: 题型整理/ 放置题型/例题笔记，内部只链接 questions/ 下的具体单题 md（或子题型）
    - Tier 3: 题集/ 放置小节/专题/测试框架与套卷，内部只链接 题型整理/ 下的题型笔记
    """
    if source_book_dirs is None:
        source_book_dirs = [
            os.path.join(vault_root, "课堂同步/教辅/必刷题/2026版 高中必刷题数学必修第一册"),
            os.path.join(vault_root, "课本/【人教版】高中必修 第一册数学电子课本")
        ]

    mathmap_dir = os.path.join(vault_root, "mathmap")
    mathmap_kp_dir = os.path.join(mathmap_dir, "知识点")
    q_dest_dir = os.path.join(mathmap_dir, "习题/questions")
    a_dest_dir = os.path.join(mathmap_dir, "习题/answers")
    qt_dest_dir = os.path.join(mathmap_dir, "习题/题型整理")
    paper_dest_dir = os.path.join(mathmap_dir, "习题/题集")

    # 清理遗留的旧套卷文件夹
    old_taojuan = os.path.join(mathmap_dir, "习题/套卷")
    if os.path.exists(old_taojuan):
        shutil.rmtree(old_taojuan)

    os.makedirs(q_dest_dir, exist_ok=True)
    os.makedirs(a_dest_dir, exist_ok=True)
    os.makedirs(qt_dest_dir, exist_ok=True)
    os.makedirs(paper_dest_dir, exist_ok=True)

    q_copied = 0
    a_copied = 0
    qt_copied = 0
    paper_copied = 0

    target_qt_notes = []
    target_paper_notes = []

    for source_book_dir in source_book_dirs:
        if not os.path.exists(source_book_dir):
            continue

        for root, dirs, files in os.walk(source_book_dir):
            rel_dir = os.path.relpath(root, source_book_dir)
            parts = rel_dir.split(os.sep)

            # 1. Tier 1: 复制原始题目与解析节点
            if 'questions' in parts or '原子题' in parts or '习题/原子题' in rel_dir:
                if 'answers' in parts or '答案' in parts:
                    for f in files:
                        if f.endswith('.md') and not f.startswith('.'):
                            src_path = os.path.join(root, f)
                            dst_path = os.path.join(a_dest_dir, f)
                            shutil.copy2(src_path, dst_path)
                            a_copied += 1
                else:
                    for f in files:
                        if f.endswith('.md') and not f.startswith('.'):
                            src_path = os.path.join(root, f)
                            dst_path = os.path.join(q_dest_dir, f)

                            with open(src_path, 'r', encoding='utf-8') as fp:
                                content = fp.read()

                            content_updated = re.sub(
                                r'!\[\[(Q\d+A\d+)(\.md)?\]\]',
                                r'![[mathmap/习题/answers/\1|\1]]',
                                content
                            )
                            with open(dst_path, 'w', encoding='utf-8') as fp:
                                fp.write(content_updated)
                            q_copied += 1
                continue

            # 2. Tier 2 & Tier 3 识别与处理
            for f in files:
                if not f.endswith('.md') or f.startswith('.') or f == 'index.md':
                    continue

                src_path = os.path.join(root, f)
                with open(src_path, 'r', encoding='utf-8') as fp:
                    content = fp.read()

                # A. Tier 3 判定: 题集/ (框架/小节总集/专题总集/章末测试/复习参考题/试卷)
                is_paper = False
                if '复习参考题' in f:
                    is_paper = True
                elif len(parts) >= 2 and f == parts[1] + '.md':
                    is_paper = True
                elif len(parts) >= 2 and f.startswith('专题') and f.endswith('.md'):
                    is_paper = True
                elif len(parts) >= 2 and ('综合训练' in f or '检测' in f or '强化' in f) and f.endswith('.md') and not re.search(r'_b\d+\.md$', f):
                    is_paper = True
                elif re.search(r'(刷真题|刷原创|刷综合|刷速度)_b\d+\.md$', f) and any(kw in rel_dir for kw in ['检测', '强化', '综合训练', '高考新动向', '强基', '月考', '期中', '期末']):
                    is_paper = True

                if is_paper:
                    clean_name = f
                    if len(parts) >= 2 and re.search(r'_b\d+\.md$', f):
                        sec_folder = parts[-2] if parts[-1].startswith('刷') else parts[-1]
                        clean_name = f'{sec_folder}_{f}'
                    clean_name = re.sub(r'^\d+-', '', clean_name)

                    dst_path = os.path.join(paper_dest_dir, clean_name)
                    
                    def rewrite_tier3(match):
                        path = match.group(1)
                        filename = os.path.basename(path)
                        clean_filename = os.path.splitext(filename)[0]
                        clean_t = clean_title(clean_filename)
                        if filename.startswith('Q') and 'A' not in filename:
                            return f'![[mathmap/习题/questions/{clean_filename}|{clean_t}]]'
                        else:
                            return f'![[mathmap/习题/题型整理/{clean_filename}|{clean_t}]]'

                    content_updated = re.sub(r'!\[\[([^\]]+)\]\]', rewrite_tier3, content)
                    with open(dst_path, 'w', encoding='utf-8') as fp:
                        fp.write(content_updated)
                    target_paper_notes.append((clean_name, dst_path, rel_dir))
                    paper_copied += 1
                    continue

                # B. Tier 2 判定: 题型整理/ (内部只链接具体单题或子题型)
                is_qt = False
                if re.search(r'(刷基础|刷易错|刷提升|刷难关|刷素养|刷能力|刷速度|刷真题|刷原创|刷综合|基础|易错|提升|难关|素养|能力)_b\d+\.md$', f):
                    is_qt = True
                elif re.match(r'^(题型|考点|易错点|微专题|习题)', f):
                    is_qt = True

                if is_qt:
                    dst_path = os.path.join(qt_dest_dir, f)
                    
                    def rewrite_tier2(match):
                        path = match.group(1)
                        filename = os.path.basename(path)
                        clean_filename = os.path.splitext(filename)[0]
                        clean_t = clean_title(clean_filename)
                        if filename.startswith('Q') and 'A' not in filename:
                            return f'![[mathmap/习题/questions/{clean_filename}|{clean_t}]]'
                        elif re.match(r'^(题型|考点|易错点|微专题)', filename):
                            return f'![[mathmap/习题/题型整理/{clean_filename}|{clean_t}]]'
                        else:
                            return f'![[mathmap/习题/题型整理/{clean_filename}|{clean_t}]]'

                    content_updated = re.sub(r'!\[\[([^\]]+)\]\]', rewrite_tier2, content)
                    with open(dst_path, 'w', encoding='utf-8') as fp:
                        fp.write(content_updated)
                    target_qt_notes.append((f, dst_path, rel_dir))
                    qt_copied += 1

    print(f"Tier 1: 原始题目归档 (mathmap/习题/questions): {q_copied} 个")
    print(f"Tier 1: 原始解析归档 (mathmap/习题/answers): {a_copied} 个")
    print(f"Tier 2: 题型整理归档 (mathmap/习题/题型整理): {qt_copied} 个 (只链接具体单题/子题型)")
    print(f"Tier 3: 题集总集归档 (mathmap/习题/题集): {paper_copied} 个 (只链接题型整理)")

if __name__ == '__main__':
    archive_and_link_mathmap('/Users/oven/Documents/ovenmathmap')

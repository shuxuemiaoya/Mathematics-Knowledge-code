import os
import re

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

def link_mathmap(vault_root, graph_dir=None, source_name="2026版 高中必刷题数学必修第一册"):
    """
    将 Question Type Graph / 刷题库/教辅的产物无缝链接到 mathmap
    格式法则：
    1. 嵌入展示链接 ![[...]] 前面绝不加 '- ' 列表符号。
    2. 严格拦截一切容器骨架文件（刷基础_b1.md, index.md 等）。
    3. 支持别名表与多级智能匹配机制。
    4. 自动双向反向链接注入 (Bidirectional Backlinks)。
    """
    if graph_dir is None:
        possible_graph = os.path.join(vault_root, "课堂同步/教辅/必刷题/2026版 高中必刷题数学必修第一册")
        if not os.path.exists(possible_graph):
            possible_graph = os.path.join(vault_root, "2026版 高中必刷题数学必修第一册")
        graph_dir = possible_graph

    mathmap_dir = os.path.join(vault_root, "mathmap/知识点")

    mathmap_existing = {}
    for f in os.listdir(mathmap_dir):
        if f.endswith('.md') and not f.startswith('.'):
            name_no_ext = os.path.splitext(f)[0]
            mathmap_existing[name_no_ext] = os.path.join(mathmap_dir, f)

    target_notes = []
    for root, dirs, files in os.walk(graph_dir):
        rel_dir = os.path.relpath(root, graph_dir)
        parts = rel_dir.split(os.sep)
        if 'questions' in parts or 'images' in parts:
            continue
        for f in files:
            if not f.endswith('.md') or f.startswith('.') or f == 'index.md':
                continue
            # 过滤一切容器骨架笔记
            if re.search(r'(刷基础|刷易错|刷提升|刷难关|刷素养|刷能力|刷速度|刷真题|刷原创|刷综合|基础|易错|提升|难关|素养|能力)_b\d+\.md$', f):
                continue
            if len(parts) >= 2 and f.startswith(parts[1]):
                continue
            if len(parts) == 1 and parts[0].startswith('0'):
                continue

            full_path = os.path.join(root, f)
            rel_parts = os.path.relpath(full_path, graph_dir).split(os.sep)
            target_notes.append((f, full_path, rel_parts))

    print(f"找到待链接的实体题型笔记: {len(target_notes)} 个")

    linked_count = 0
    skipped_count = 0
    backlinked_count = 0

    for filename, full_path, rel_parts in target_notes:
        rel_path_from_vault = os.path.relpath(full_path, vault_root)
        wikilink_target = os.path.splitext(rel_path_from_vault)[0]

        display_title = os.path.splitext(filename)[0]
        display_title = re.sub(r'_b\d+$', '', display_title)
        qtype_clean = clean_qtype(filename)
        sec_name = extract_section_name(os.path.relpath(full_path, graph_dir))

        target_node = None

        # 1. 题型精确匹配
        if qtype_clean in mathmap_existing:
            target_node = qtype_clean
        # 2. 别名表匹配
        elif sec_name in ALIAS_MAP and ALIAS_MAP[sec_name] in mathmap_existing:
            target_node = ALIAS_MAP[sec_name]
        # 3. 章节精确匹配
        elif sec_name in mathmap_existing:
            target_node = sec_name
        # 4. 章节/题型模糊匹配
        else:
            for m_name in mathmap_existing:
                if len(m_name) >= 3 and (m_name in sec_name or sec_name in m_name):
                    target_node = m_name
                    break
            if not target_node:
                for m_name in mathmap_existing:
                    if len(m_name) >= 3 and (m_name in qtype_clean or qtype_clean in m_name):
                        target_node = m_name
                        break

        # 5. 高考新动向智能托底路由
        if not target_node:
            if '集合' in qtype_clean:
                target_node = '集合的概念'
            elif '三角函数' in qtype_clean:
                target_node = '三角函数的应用'
            elif '函数' in qtype_clean:
                target_node = '函数的概念'

        if not target_node:
            target_node = sec_name if sec_name else "未分类知识点"
            target_filepath = os.path.join(mathmap_dir, f"{target_node}.md")
            mathmap_existing[target_node] = target_filepath

            template = f"""---
tags:
  - 知识点
aliases: []
---

# 知识点：{target_node}

# 讲解


# 概念


# 题型

"""
            with open(target_filepath, 'w', encoding='utf-8') as fp:
                fp.write(template)

        # 反向注入知识点 WikiLink 到实体题型笔记 (Bidirectional Backlink)
        try:
            with open(full_path, 'r', encoding='utf-8') as fp:
                note_content = fp.read()
            backlink_str = f'[[{target_node}]]'
            if backlink_str not in note_content:
                new_note_content = note_content.rstrip() + f'\n\n> [!info] 关联知识点\n> - [[{target_node}]]\n'
                with open(full_path, 'w', encoding='utf-8') as fp:
                    fp.write(new_note_content)
                backlinked_count += 1
        except Exception as e:
            print(f"警告：无法写入反向链接到 {full_path}: {e}")

        target_filepath = mathmap_existing[target_node]

        with open(target_filepath, 'r', encoding='utf-8') as fp:
            content = fp.read()

        # 嵌入展示链接，绝不添加列表短横线 '- '
        embed_line = f"![[{wikilink_target}|{display_title}]]"

        if wikilink_target in content or embed_line in content:
            skipped_count += 1
            continue

        source_heading = f"## 来源：{source_name}"

        if "# 题型" not in content:
            content += "\n\n# 题型\n"

        q_idx = content.find("# 题型")
        q_content = content[q_idx:]

        if source_heading in q_content:
            src_pos = content.find(source_heading, q_idx)
            lines = content[src_pos:].split('\n')

            insert_line_idx = len(lines)
            for i, l in enumerate(lines[1:], start=1):
                if l.startswith('#'):
                    insert_line_idx = i
                    break

            lines_before = content[:src_pos].split('\n')
            lines_block = lines[:insert_line_idx]
            lines_after = lines[insert_line_idx:]

            while len(lines_block) > 1 and not lines_block[-1].strip():
                lines_after.insert(0, lines_block.pop())

            lines_block.append(embed_line)
            new_content = '\n'.join(lines_before) + '\n'.join(lines_block) + ('\n' if lines_after else '') + '\n'.join(lines_after)
        else:
            q_end = content.find('\n', q_idx)
            if q_end == -1:
                new_content = content + f"\n{source_heading}\n{embed_line}\n"
            else:
                before = content[:q_end]
                after = content[q_end:]
                new_content = before + f"\n{source_heading}\n{embed_line}" + after

        with open(target_filepath, 'w', encoding='utf-8') as fp:
            fp.write(new_content)

        linked_count += 1

    print(f"知识点链接完成: 成功链接 {linked_count} 个题型, 跳过重复 {skipped_count} 个, 新注入反向链接 {backlinked_count} 个")

if __name__ == '__main__':
    link_mathmap('/Users/oven/Documents/ovenmathmap', '/Users/oven/Documents/ovenmathmap/课堂同步/教辅/必刷题/2026版 高中必刷题数学必修第一册')

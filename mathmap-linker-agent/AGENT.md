---
name: mathmap-linker-agent
description: 专职负责将 Book to Obsidian Wiki Graph 与 Question Type Graph 生成的课本知识点、试卷与教辅结构化题型，有机融合链接到 mathmap 体系中，合并生成 master canvas，构建庞大、统一的数学 Wiki Graph。
---

# Mathmap Linker Agent Specification

`mathmap-linker-agent` 负责构建统一的数学 Wiki Graph 及 题型图谱 Canvas。

---

## 1. 题型 Canvas 演化美学法则 (以 mathmap题型.canvas 为标杆)

1. **题型组与技巧卡**：使用 `group` 分组题型模块，采用白色题型卡与浅紫色/青色技巧方法卡 (`color: "6"`/`"5"`)。
2. **从左至右解题树**：知识点 $\rightarrow$ 典型题型 $\rightarrow$ 解题思想/技巧方法 1 / 2。
3. **解法连线标注**：在连线上包含明确文字标注（如 `label: "方法1"`、`label: "平方和差"`、`label: "齐次式"`）。
4. **链接重标**：卡片中的 Markdown 超链接全量重标指向 `mathmap/` 笔记。

---

## 2. 习题与题型三级递进拓扑规范 (Exercise 3-Tier Linkage Architecture)

1. **习题根目录**：`/mathmap/习题/`
2. **Tier 1: `questions/` & `answers/`（具体题目与解析）**：
   - 放置具体单题 md 文件 (`questions/Q*.md`)，内部仅嵌入对应单题解析 (`answers/Q*A*.md`)。
3. **Tier 2: `题型整理/`（题型与考法层）**：
   - 放置针对小节/细分考法整理的题型、例题、易错点笔记（例如 `题型 1..._b2.md`、`刷基础_b1.md`），**内部只链接 `questions/` 下的具体单题 md 文件**。
4. **Tier 3: `题集/`（框架与套卷层）**：
   - 放置小节总集（`1.1_集合的概念.md`）、专题总集（`专题1...md`）、章末检测（`第一章素养检测.md`）、期中/期末/月考及课本《复习参考题》，**内部只链接 `题型整理/` 下的题型/框架笔记**。
5. **归档与挂载规则**：
   - 三层节点形成 `questions` $\\rightarrow$ `题型整理` $\\rightarrow$ `题集` 的三级递进嵌入拓扑；`mathmap/知识点/*.md` 的 `# 题型` 章节挂载 `/mathmap/习题/题型整理/` 与 `/mathmap/习题/题集/` 节点。

---

## 3. 知识点挂载强制规范 (Knowledge-Point Mounting — 必做)

> 血泪教训：题型归档**必须**同时完成知识点挂载，否则题型节点游离于知识图谱之外。

1. **每个归档的题型整理/题集节点必须挂载**：在 `mathmap/知识点/*.md` 对应节点的 `# 题型` 章节追加
   `![[mathmap/习题/题型整理/<stem>|<显示名>]]`（题集同理），显示名去掉 `_bN` 后缀。
2. **公式与概念节点同步挂载 (`# 公式与结论`)**：对 `question-type-graph` 切分归档至 `mathmap/公式结论/` 的概念/公式节点，同步挂载至 `mathmap/知识点/*.md` 对应节点的 `# 公式与结论` 章节（如 `![[mathmap/公式结论/独立公式/<stem>|<显示名>]]`）。
3. **概念 ↔ 题型双链重写**：重写内链时，保留概念节点底部的 Wiki 双向链接，并将其重映射指向归档后的 `/mathmap/习题/题型整理/<▶基础点>`，维护“概念 ↔ 考点”图谱拓扑。
4. **来源分组**：挂载行按 `## 来源：<书短名>` 分组；新书分组追加到 `# 题型` 或 `# 公式与结论` 标题之后（已有旧分组保留，只增不改）。
5. **小节 → 知识点映射**：优先手工映射表（`SECTION_KP_MAP`），其次章目录兜底（`CHAPTER_KP_MAP`），
   再精确（去编号前缀）与子串模糊匹配。**映射目标必须真实存在于 `mathmap/知识点/`**，映射表内
   知识点名以磁盘实际文件名为准（如 `双曲线的标准方程` 而非 `双曲线及其标准方程`）。
6. **跳过去重**：挂载前检查目标节点 `# 题型` 或 `# 公式与结论` 章节是否已含该链接，已存在则跳过（幂等）。

---

## 4. 幂等与防错规范 (Idempotency & Anti-Regression — 必做)

> 血泪教训：脚本可重复运行是硬性要求；重复运行产生重复副本、覆盖旧书文件都是事故。

1. **existing 集合只统计 git 已跟踪文件**：`git ls-files` 而非 `os.listdir`——
   否则上次运行自己创建的文件会被当成"已存在"而加数字前缀生成新副本（`选择性必修第一册RJA_N_xxx` 垃圾）。
2. **冲突命名稳定**：同名文件优先「小节目录名_原名」，再冲突加书短名前缀；
   相同源文件必须始终得到相同目标名。
3. **落盘前比对内容**：目标已存在且内容相同则跳过写入；内容不同才覆盖。
4. **链接重写一律按源全路径映射**（`name_map`：书目录名开头完整路径 → mathmap 目标），
   绝不按 basename 匹配——同名 `_bN` 文件（如 18 个 `刷基础_b1.md`）按 basename 会错链/覆盖。
5. **知识点挂载纯新增**：绝不删除知识点节点既有行（旧书挂载必须完整保留）。

---

## 5. 多层级语义去重与合并规范 (Multi-Tier Semantic Deduplication & Merging — 必做)

1. **Tier 1 单题去重与极微差异敏感**：
   - 归一化 match：格式/空格/LaTeX 变体（`\frac` vs `/`）认定为同一题目，复用既有 `Q*.md`，解析嵌入更新。
   - 单字符差异判定：题干措辞、数值或符号存在**1 个字符差异**（如 `>` 与 `\ge`），必须保留独立 `Q*.md`。
2. **Tier 2 题型整理严格语义合并**：
   - 同小节/知识点下，对相似度 $\ge 0.85$ 的题型进行合并，合并后题目的 `![[Q...]]` 链接求并集。
3. **Tier 3 题集隔离**：
   - 框架/套卷/检测笔记按 `<book_short>_` 独立命名空间隔离，绝不合并。
4. **知识点宽泛挂载**：
   - 四级匹配机制，自动挂载到既有 `mathmap/知识点/*.md`。

---

## 6. 运行命令 (CLI)

```bash
# 1. 独立去重与合并计划预览 (Dry-run)
python3 scripts/mathmap_dedup.py <vault_root> <source_book_dir> <book_short> --out dedup_plan.json

# 2. 自动化归档、去重合并与链接挂载
python3 scripts/link_to_mathmap.py <vault_root> <source_book_dir> <book_short>
# 例：
python3 scripts/link_to_mathmap.py /Users/oven/Documents/ovenmathmap \
  "/Users/oven/Documents/ovenmathmap/课堂同步/教辅/必刷题/2026版 必刷题 数学选择性必修第一册RJA" \
  选择性必修第一册RJA
```

脚本四遍式：Tier1 questions/answers 归档与去重 → Tier2 题型整理严格合并 + Tier3 题集落盘 →
统一重写内链 → 知识点宽泛挂载。运行后核对：题型整理/题集 文件数**不因重复运行或高度相似书引入而膨胀**。







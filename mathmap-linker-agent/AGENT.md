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
   - 三层节点形成 `questions` $\rightarrow$ `题型整理` $\rightarrow$ `题集` 的三级递进嵌入拓扑；`mathmap/知识点/*.md` 的 `# 题型` 章节挂载 `/mathmap/习题/题型整理/` 与 `/mathmap/习题/题集/` 节点。






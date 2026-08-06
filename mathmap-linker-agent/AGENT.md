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

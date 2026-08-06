---
name: mathmap-linker
description: 将 Book to Obsidian Wiki Graph 和 Question Type Graph 生成的课本知识点与试卷/刷题库笔记，自适应关联并有机链接到 mathmap 体系中，合并生成 master canvas，构建庞大、统一的数学 Wiki Graph。
---

# Mathmap 题型图谱 Canvas 演化美学与解题树架构规范

本技能指导 AI 如何以 `mathmap题型.canvas` 的题型树图谱为美学与拓扑标杆，构建从**概念/知识点 $\rightarrow$ 具体题型 $\rightarrow$ 解题思想/技巧方法**层层递进的解题树白板图谱。

---

## 1. 题型图谱 Canvas 美学 4 大要素 (Question Type Canvas Directives)

1. **题型与解题方法主题分组框 (Question Type & Method Grouping Containers)**：
   - **大题型组**（如 `同角三角函数的基本关系公式练习`、`诱导公式练习`、`三角函数定义`）：涵盖某类题型的大逻辑边界。
   - **子题型与细分考法组**（如 `扇形的弧长和面积`、`三角函数在单位圆上`）：包裹具体的考点拆解与典型例题。

2. **解题思想与技巧卡片 (Method & Skill Cards Design)**：
   - **白色题型主标题卡**：紫色/黑色文字，标注主要题型名称（如 `给角求值问题`、`同角三角函数的基本关系式化简`）。
   - **浅紫色/青色技巧卡 (`color: "6"` 或 `"5"`)**：突出解题思想与方法（如 `拼凑角思想`、`利用平方关系求参数`、`求任意角的终边所在象限`）。
   - **细分考法卡片**：圆角规整卡片，分支展现不同解题路径。

3. **从左至右解题树分支演化 (Left-to-Right Decision Tree Flow)**：
   - 采用横向从左至右延伸的树状分流关系（`right -> left` 或 `bottom -> top`）。
   - **基础概念 $\rightarrow$ 典型题型 $\rightarrow$ 解题方法1/方法2**。

4. **解题方法有向边标注 (Labeled Edge Method Annotations)**：
   - 在连线上标注具体的解法名称或变换技巧（如 `label: "方法1"`、`label: "平方和差"`、`label: "齐次式"`）。

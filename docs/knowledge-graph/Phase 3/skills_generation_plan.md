# Sprint 3 终极沉淀：全链路 Skills 化规划

**目标定位**：遵循 `/writing-skills` 的指导原则，将我们在 Phase 3（A, B, C(Track 1/2), D）中跑通的所有架构与工作流，沉淀为全局可复用的 AI 技能（Skills）。
这样，未来的任何 Agent 只要遇到“Markdown解析”、“图谱提取”、“画布生成”等问题，都能直接调用我们写好的标准作业程序（SOP），而不需要重新摸索。

---

## 规划生成的 5 大核心 Skills

### 1. 技能：`parsing-markdown-to-vault` (对应 Phase 3A)
- **触发条件 (Description)**：Use when converting a large hierarchical Markdown document (like a textbook) into a parsed Obsidian vault while strictly preserving the physical folder hierarchy (H1/H2/H3).
- **核心内容**：
  - 调用 `mk-vault parse` 的标准命令。
  - 解释底层的 RKDT 树状保留机制。
  - 规定必须保留物理嵌套目录（不可拍扁）。

### 2. 技能：`extracting-ontology-with-llm` (对应 Phase 3B)
- **触发条件 (Description)**：Use when you need to extract micro-concepts, definitions, and prerequisites from parsed textbook chunks using an LLM batch processor.
- **核心内容**：
  - 调用 `python -m math_knowledge_tools.ontology.batch_runner`。
  - 解释其输出的 `*.candidates.json` 的平行存储逻辑。

### 3. 技能：`merging-ontology-to-graphrag` (对应 Phase 3C Track 1)
- **触发条件 (Description)**：Use when merging scattered extracted JSON ontologies into a single global graph and exporting to Neo4j CSVs for GraphRAG.
- **核心内容**：
  - 执行 `mk-graph merge` 生成 `global_ontology.json` 的 Map-Reduce 防截断逻辑。
  - 执行 `mk-graph export` 导出 `nodes.csv` 和 `edges.csv` 的图数据标准。

### 4. 技能：`weaving-obsidian-wikilinks` (对应 Phase 3C Track 2)
- **触发条件 (Description)**：Use when injecting inline Obsidian wikilinks into plain text based on a target ontology dictionary without modifying math formulas or existing links (Zero-Token weaving).
- **核心内容**：
  - 讲解 `weaver.py` 的正则智能避让逻辑。
  - 强调这是零 Token 的纯本地匹配方案，不可盲目调用大模型。

### 5. 技能：`generating-concept-canvas` (对应 Phase 3D)
- **触发条件 (Description)**：Use when building a hybrid Tree-to-Web Canvas (Left-to-Right layout) in Obsidian and materializing virtual concepts into physical Markdown hub files.
- **核心内容**：
  - 第一步：生成实体概念文件到用户指定的文件夹（强制调用 `concept-hub-naming` 规则）。
  - 第二步：基于 `canvas_builder.py`，按照 Level 0 (Chapter) -> Level 1 (File) -> Level 2 (Concept) -> Level 3 (Prerequisite) 的固定横坐标偏移逻辑渲染白板。

## 存放策略与执行准则

> [!IMPORTANT]
> **双库镜像存储（Dual-path Storage）**：
> 生成的所有 Skill 文件将同时被放置在以下两个路径中：
> 1. **全局智能库**：`C:\Users\Oven\.gemini\config\skills\` (让全局 Agent 随时可调用)
> 2. **项目专属库**：`C:\mygithub\Mathematics-Knowledge-code\skills\` (随项目代码提交，保证代码与规矩同在)
> 
> **绝对不可篡改原则（Strict SOP）**：
> 所有的标准作业程序（SOP）将**100% 严格按照我们刚刚跑通的代码逻辑**进行撰写，不添加任何未经验证的新功能，也不做任何擅自改动。过去的成功经验将被原汁原味地永久冻结为神圣不可侵犯的规则！

---

（计划已更新完毕，确认无误后请回复执行指令！）

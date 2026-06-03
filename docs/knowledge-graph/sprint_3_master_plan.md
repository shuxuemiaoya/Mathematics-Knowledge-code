# Sprint 3 架构总纲：从物理树到知识图谱

## Phase 3A: 物理目录树解构 (RKDT) - [已完成]

**核心目的**：将大 Markdown 解构为一层一层的中型 Markdown 卡片。
**关键原则**：
1. **完全的树状结构**：绝对忠实于原书的目录（TOC）。完全按照目录连线。**Vault Builder 会保留原有的层级关系，在文件系统上创建对应的嵌套文件夹 (Nested Directories)，不再将文件拍扁放在同一个目录下。**
2. **免拆分机制**：所有的 Callout 全部依附于其所在的章节正文中，不独立建卡。
3. **成果**：树干不动，得到一个结构工整、没有文本丢失的物理文件树，且物理目录结构与原文标题大纲完全一致。

---

## Phase 3B: Ontology Candidate Extractor (候选本体提炼引擎) - [已完成]

**核心目的**：在 3A 的基础上，树干不动，让 LLM 逐个阅读文件提取概念，为未来的 GraphRAG / Wiki 网络做准备。

### 架构共识 (Design Decisions)
1. **提炼目标 (What)**：只提炼关键知识节点（Concept / MicroConcept 等）。
2. **输入粒度 (How)**：全量文件级（File-level）。基于 3A 拆分好的文件（如 `1.1 集合的概念.md`），一个一个过，喂给 LLM。
3. **分类依据 (Mapping)**：输出的概念，必须放在我们之前设定好的分类标准中（调用分类依据）。
4. **数据落地 (Where) - 旁挂 JSON**：
   - 绝不修改原 `.md` 文件的 YAML（YAML 只放 `id`, `type`, `parent` 等稳定真理元数据）。
   - LLM 生成的临时数据/非事实候选，必须放在同名的旁挂 JSON 中。
   - 示例：`1.1 集合的概念.md` 对应生成 `1.1 集合的概念.candidates.json`。

### 成果
- 实现了 `extractor.py` (接入 DeepSeek) 和 `batch_runner.py`
- 提供了 CLI 工具 `mk-extract` 实现全自动提炼与旁挂 JSON 文件的生成。

---

# Sprint 3 终局：图谱提纯与双轨落库计划 (Phase 3C & 3D)

基于你的战略决策，我们将采取**“双线并行、物理隔离”**的架构模式。
为了确保代码互不干扰，我们将 3B 提炼出来的 `.candidates.json` 作为统一的输入分水岭，此后的逻辑将分裂为两套完全独立的代码包和文档体系。

---

## Track 1: AI 原生图谱后端流水线 (The GraphRAG Pipeline)
**定位**：面向机器计算、自动问答与全自动化。
**核心思路**：用魔法打败魔法，让大模型全局消歧，最终导出为供 RAG 引擎使用的标准图数据库。

### 模块结构
- **代码目录**: `src/math_knowledge_tools/graph_backend/`
- **独立文档**: `docs/graphrag-pipeline.md`

### Phase 3C: 全自动全局消歧 (Global LLM Consolidation)
*   **任务**: 收集全 Vault 下几百个 `.candidates.json`。
*   **实现**: 编写 `global_merger.py`。通过 LLM 的长上下文能力或 Map-Reduce 策略，合并重复概念（如将 1.1 和 1.2 中提取的“集合”合并），统一依赖关系。
*   **输出**: 生成一份唯一的全局本体字典 `global_ontology.json`（存在于代码域，不污染 Obsidian Vault）。

### Phase 3D: Neo4j / 知识图谱落库 (Graph Materialization)
*   **任务**: 将 `global_ontology.json` 转化为图数据库所需的实体（Nodes）和边（Edges）。
*   **实现**: 编写 `neo4j_exporter.py`。
*   **输出**: 可供主流 GraphRAG 框架直接导入的 `.csv` 或 Parquet 文件，甚至直接通过 API 写入 Neo4j 数据库。

---

## Track 2: Obsidian 交互式本地生态流水线 (The Obsidian Pipeline)
**定位**：面向人类阅读、手工微调与本地双链可视化。
**核心思路**：充分利用 Obsidian 的前端视图机制进行人机协同审核，审核后直接在卡片上织网。

### 模块结构
- **代码目录**: `src/math_knowledge_tools/obsidian_integration/`
- **独立文档**: `docs/obsidian-pipeline.md`

### Phase 3C: 原生交互式审核 (Native UI Review)
*   **任务**: 提供一种在 Obsidian 内部点击确认的 UI。
*   **实现**: 编写 `review_ui_generator.py`。考虑到不手写复杂的 TypeScript 插件，我们将利用已有的 `json-canvas` 技能或 Dataview 语法，生成一个特殊的 `审核总控台.canvas` 或带复选框的 `.md` 看板，读取所有的 `.candidates.json`。
*   **用户动作**: 用户在 Obsidian 里打勾、删改，触发脚本重写 JSON 状态（从 candidate 变为 verified）。

### Phase 3D: YAML 与内联双链注入 (Local Vault Weaving)
*   **任务**: 将经过人类确认的本体数据，永久固化到 3A 生成的 Markdown 文件中。
*   **实现**: 编写 `vault_weaver.py`。
    1.  **稳定元数据**: 将确认后的概念与依赖写入对应 `.md` 文件的 YAML 头。
    2.  **织网**: 自动扫描正文，将命中的实体字符串替换为 `[[实体]]` 格式，瞬间点亮 Obsidian 局部关系图谱。

---

## 实施路径与 Open Questions

为了贯彻“完全独立”的方针，我们需要决定优先启动哪一条轨道：

> [!IMPORTANT]
> **关于执行优先级的确认**
> 
> 虽然两条轨道架构各自独立，但在编码执行时，建议我们先选一条线打通闭环（比如先做自动化的 Track 1，或者先做可视化的 Track 2）。
> 
> **你希望我们先从哪条流水线开始写代码和文档？**
> - 先执行 **Track 1 (GraphRAG 后端图谱)**
> - 先执行 **Track 2 (Obsidian 本地生态)**
> 
> 一旦你做出选择，我将立刻使用 `subagent-driven-development` 技能分发并开始独立文档与代码的编写。

# MathOS 架构重构方案 (Data-First Design)

**目标定位**：遵循你的高瞻远瞩，我们将彻底抛弃“基于功能的 Sprint 迭代”，全面转向“**基于数据流的 Knowledge Engineering System (MathOS)**”。
整个系统的核心将变成 **Schema（数据结构）**。模块与模块之间通过严格的数据结构解耦，哪怕未来大模型换代、数据库更换，只要 Schema 协议不变，系统依然稳如磐石。

---

## 阶段规划：全面转向 Data-First

### 1. 核心 Schema 确立 (80% 的精力)
我们将率先在 `src/mathos/schemas/` 目录下，使用 Pydantic 建立严格强类型的中间产物结构。这是整个体系的“宪法”：
- **`chunk.py`**: 定义 `Chunk` 模型（标题、内容、层级树、类型）。这是 `parser` 的输出，`ontology` 的输入。
- **`candidate.py`**: 定义 `Candidate` 模型（微观概念、属性）。这是 `ontology.extractor` 的输出。
- **`knowledge_object.py`**: 定义 `KnowledgeObject`（节点 ID、实体类型、标准属性）。这是未来投影到 Neo4j/Obsidian 的最终基准数据源。

### 2. 目录解耦与大清洗 (三位一体架构)
我们将全面废弃原有的 `src/math_knowledge_tools`，重构为以下**高度对齐的“三位一体”物理结构**（Schemas决定数据，Src执行逻辑，Skills指导AI）：

```text
mathos/

├── schemas/               # 核心数据契约 (The Core)
│   ├── chunk.py
│   ├── atomic_note.py
│   ├── candidate.py
│   └── knowledge_object.py
│
├── skills/                # 对应每一个处理阶段的 AI 标准作业程序 (SOP)
│   ├── convert-with-mineru
│   ├── math-knowledge-formatting
│   ├── chunk-markdown
│   ├── build-vault
│   ├── extract-candidate
│   ├── build-ontology
│   ├── weave-links
│   └── build-canvas
│
├── src/                   # 纯粹的无状态流水线代码 (Stateless Pipelines)
│   ├── ingestion/         # (对应 MinerU 与 Formatting)
│   ├── chunking/          # (对应 Chunk Markdown)
│   ├── vault/             # (对应 Build Vault)
│   ├── extraction/        # (对应 Extract Candidate)
│   ├── ontology/          # (对应 Build Ontology / Global Merge)
│   └── projection/        # (对应 Weave Links 与 Build Canvas)
```

### 3. 资产无损迁移策略 (Zero-Waste Migration)
你可能会担心之前的 Sprint 3 搞了那么久，是不是全浪费了？**绝对没有！** 所有的心血都将被 100% 榨干并复用：
- **代码无损 (Code)**：核心算法（如 3A 的 RKDT 层级树算法、3B 的 DeepSeek 抽取 Prompt、3C 的 Aho-Corasick 织网匹配、3D 的三角函数星团画布）**一行都不会扔**！我们只是把它们搬进 `src/` 的新目录下，把传递的变量从散装 `dict` 换成了严谨的 `Schema`。
- **文档无损 (Docs)**：刚才我已经把所有旧版 `sprint_*` 的业务逻辑精髓提取到了 `MathOS_System_Design.md`，过去的踩坑经验已经变成了这个系统的架构灵魂。
- **技能无损 (Skills)**：我们刚刚在全局生成的 5 大 Skills，将被改名为对应的 `build-vault`, `extract-candidate`, `weave-links` 等 8 个标准化名称，里面的“防呆红线”（比如不许动公式、必须问名字）将一字不落的平移过去。

---

## 执行步骤与 MVP (V1 - V3)

一旦你批准此计划，我们将先开启 **V1 & V2 的 Schema 设计与代码迁移**：
1. **Task 1**: 编写 `schemas/*.py`，确立数据契约。
2. **Task 2**: 迁移物理文件结构，建立 `mathos` 目录。
3. **Task 3**: 重构原有的代码，使其适配新的 Schema，打通 `CLI -> Parser -> Ontology -> Schema` 的数据流。

## 核心执行准则 (已确认)

> [!IMPORTANT]
> **1. JSON-LD 轻量化标准**：
> `KnowledgeObject` 必须严格提供 `@context`, `@id`, `@type` 等核心语义网标识符，为后期的 Neo4j 完美铺路，但在当前 V1-V2 阶段保持字段精简，拒绝过度设计，确保大模型生成的成功率。
> 
> **2. 历史档案重塑**：
> 在编写任何新代码前，我们将首当其冲执行“文献大一统”。全面读取过去的散装计划文档，将其中的精髓（例如 3A 的层级保留算法、3B 的双链正则匹配规则）提炼为全局统一的架构知识库，随后彻底删除那些过时的废弃文档！

---

(计划已完全对齐，我们将立即生成 Task 并进入重构时代！)

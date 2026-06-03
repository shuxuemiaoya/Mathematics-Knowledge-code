# MathOS System Design (Data-First Architecture)

## 1. 核心架构哲学 (Data First Design)
MathOS 不是一个普通的脚本集合，而是一个围绕 **数据流 (Data Pipeline)** 和 **结构化契约 (Schemas)** 打造的 Knowledge Engineering System (知识工程操作系统)。
系统的唯一真理是数据格式。每一个模块必须作为独立的 CLI 运行，相互之间仅通过强类型 Schema（Chunk、Candidate、Knowledge Object）进行通信。

### 数据流管线 (The Pipeline)
```text
PDF -> Clean Markdown -> Chunk -> Atomic Note -> Candidate -> Knowledge Object -> Graph Projection (Neo4j / Obsidian)
```

## 2. 各个阶段的物理架构与算法沉淀

### Stage 1: Ingestion (摄入与清洗)
- **输入**: 原始 PDF 或 OCR 结果
- **输出**: 标准化、干净的 Markdown (Clean Markdown)
- **核心逻辑**: MinerU 转换 + Formatter 格式化（保留公式，统一标题层级）。

### Stage 2: Parser (结构化切分与金库构建)
- **输入**: Clean Markdown
- **输出**: Chunk (数据级) -> Atomic Note (Obsidian 物理文件级)
- **算法精髓 (RKDT 物理树状保留)**：
  切分 Markdown 时，必须严格提取原文档的 H1/H2/H3 层级。
  `vault_builder` 在落盘时，**绝对不可将文件拍扁 (Flatten)**，必须根据 `parent_hierarchy` 动态生成嵌套的物理文件夹结构（如 `第六章/6.1/6.1.1.md`），确保知识目录拓扑结构在文件系统上真实存在。

### Stage 3: Ontology Extractor (大模型本体提取)
- **输入**: Atomic Note (.md)
- **输出**: Candidate (微观实体候选)
- **算法精髓 (旁挂式 JSON)**：
  采用大模型批处理。为了不污染 Markdown 原文，所有生成的临时提取物必须采用 **旁挂 JSON (Side-car JSON)** 模式存储（例如 `6.1.1.candidates.json`）。该步骤可以并行化执行。

### Stage 4: Object Builder & Merger (图谱归一化)
- **输入**: Candidate (*.candidates.json)
- **输出**: Knowledge Object (统一知识对象)
- **算法精髓 (全局消歧)**：
  读取数以千计的 Candidate 文件，通过 Map-Reduce 或者精准字符串匹配合并同义词和重名节点。输出最终的 `global_ontology.json`。该对象必须满足轻量化 **JSON-LD** 标准，带有 `@id` 和 `@type`，为图数据库注入做好准备。

### Stage 5: Projections (多维前端投影)
#### 5.1 Obsidian 智能织网 (Zero-Token Weaver)
- **算法精髓**: 纯本地正则 AST 降维匹配。
  - **安全注入**: 扫描 MD 文件时，必须跳过 LaTeX 公式 (`$...$`, `$$...$$`)、已有的双链 (`[[...]]`) 以及代码块，严防破坏排版。
  - **首词注入**: 确保每一个独立的 Knowledge Object 名称在单篇 Markdown 中**仅被注入一次双链**，防止视觉污染。

#### 5.2 Obsidian 实体库与画布 (Concept Hub & Canvas)
- **算法精髓**: 
  - **实体库**: 根据 `global_ontology.json` 自动在 Vault 中生成几百个真实的 Concept Markdown 文件，且**必须询问用户概念库的名字**。
  - **从左至右混合拓扑画布 (Tree-to-Web)**:
    - `Level 0 (x=-380)`: 虚拟章节汇总节点（纯文本双链）。
    - `Level 1 (x=-20)`: 物理切分的文件节点（Tree）。
    - `Level 2 (x=440)`: 实体库中的概念节点（Web），连向 Level 1。
    - `Level 3 (x=880)`: 依赖关系/前置概念节点（Prerequisites），连向 Level 2。

#### 5.3 Neo4j 图数据库投影
- **算法精髓**: 将 `KnowledgeObject` 列表拆分为标准的 `nodes.csv` (包含 `@id`, `@type`, 属性) 和 `edges.csv` (source, target, relation)，用于后端的 GraphRAG 问答引擎。

# MathOS 架构重构任务清单 (Data-First Design)

- [x] **Task 1: 历史文档大一统与清理**
  - [x] 读取 `docs/knowledge-graph/` 下所有的 `sprint_*` 文档
  - [x] 提取核心算法与业务逻辑精髓（3A物理嵌套、3B正则匹配等）
  - [x] 撰写一份全新的 `MathOS_System_Design.md` 核心架构知识库
  - [x] 彻底删除旧的 `sprint_3_*` 及 `pre_sprint_*` 散装文档

- [x] **Task 2: 确立核心 Schemas (Stage 1-5 契约)**
  - [x] 创建 `src/mathos/schemas/chunk.py` (Stage 2)
  - [x] 创建 `src/mathos/schemas/atomic_note.py` (Stage 3)
  - [x] 创建 `src/mathos/schemas/candidate.py` (Stage 4)
  - [x] 创建 `src/mathos/schemas/knowledge_object.py` (Stage 5 - JSON-LD 兼容)

- [x] **Task 3: 重组物理目录**
  - [x] 重命名 `math_knowledge_tools` 为 `mathos`
  - [x] 建立 `ingestion/`, `parser/`, `ontology/`, `projections/`, `cli/` 目录结构
  - [x] 将原有代码平移进入新目录

- [ ] **Task 4: CLI 独立化与代码重构 (MVP V1)**
  - [ ] 打通 `mk-convert` 和 `mk-chunk`，适配新的 Schema
  - [ ] 打通 `mk-vault`，确保输出完美对齐 Atomic Note
  - [ ] 完成 MVP V1 数据流测试

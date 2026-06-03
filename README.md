# MathOS: Mathematics Knowledge Graph Operating System

这是 `Secondary-School-Mathematics-Knowledge-Map` (高中数学知识图谱) 的核心自动化引擎仓库。经过 Data-First (数据流优先) 的大范围重构，目前项目已全面迁移为 **“三位一体” (Schemas + Skills + Src) 架构**。

## 🎯 核心架构哲学 (Data First Design)
MathOS 不是一个普通的脚本集合，而是一个围绕 **数据流 (Data Pipeline)** 和 **结构化契约 (Schemas)** 打造的 Knowledge Engineering System (知识工程操作系统)。
系统的唯一真理是数据格式。每一个模块作为独立的无状态执行器运行，相互之间仅通过 `src/mathos/schemas` 中定义的强类型模型进行通信。

**数据流管线 (The Pipeline):**
```text
PDF -> Clean Markdown -> Chunk -> Atomic Note -> Candidate -> Knowledge Object -> Graph Projection (Neo4j / Obsidian)
```

## 📂 三位一体物理结构

我们采用完美对齐的目录结构，确保“数据契约”、“AI 操作规范”与“执行代码”1:1 映射：

```text
mathos/
├── schemas/               # 核心数据契约 (The Core)
│   ├── chunk.py           # Stage 2: 纯文本逻辑块
│   ├── atomic_note.py     # Stage 3: Obsidian 物理卡片 (RKDT嵌套结构)
│   ├── candidate.py       # Stage 4: 大模型旁挂抽取的微观概念
│   └── knowledge_object.py# Stage 5: 全局图谱实体 (兼容 JSON-LD)
│
├── skills/                # AI 标准作业程序 (SOP / Codex 技能)
│   ├── convert-with-mineru          # 将 PDF/DOCX 文档转换为基础 Markdown
│   ├── math-knowledge-formatting    # 清洗/格式化数学 Markdown (保留 LaTeX 公式与 H1/H2 标题)
│   ├── chunk-markdown               # Stage 2: 将 Markdown 切分为内存逻辑块 (Chunk)
│   ├── build-vault                  # Stage 3: 生成具有严格层级 (RKDT) 的 Obsidian 金库卡片 (Atomic Note)
│   ├── extract-candidate            # Stage 4: 调度大模型提取实体，生成旁挂式 JSON (Candidate)
│   ├── build-ontology               # Stage 5: 全局归一化实体同义词，输出 JSON-LD 图谱对象 (Knowledge Object)
│   ├── weave-links                  # 投影 A: 0-Token 纯本地正则，为金库卡片无损注入内联双链
│   └── build-canvas                 # 投影 B: 自动生成 Tree-to-Web 从左至右的 Obsidian 拓扑画布
│
├── src/mathos/            # 纯粹的无状态流水线代码 (Stateless Pipelines)
│   ├── ingestion/         # Stage 1: MinerU PDF解析 & 格式化清洗
│   ├── chunking/          # Stage 2: 结构化切片
│   ├── vault/             # Stage 3: 构建物理金库树
│   ├── extraction/        # Stage 4: 接入 LLM 抽取旁挂数据
│   ├── ontology/          # Stage 5: 全局本体归一化与消歧
│   └── projection/        # 终点: Obsidian 双链织网与星团画布 / Neo4j 投射
```

## 🛠️ 安装

```powershell
cd C:\mygithub\Mathematics-Knowledge-code
python -m pip install -e .[dev]
```

*如果你希望 AI 直接调用项目的技能栈，请将 `skills/` 目录挂载到你的 Agentic 编码工具中。*

## 📚 详细设计文档

系统核心算法（如 3A 物理树嵌套算法、3B 大模型旁挂匹配、3C 全局消歧、0-Token 正则织网等）已浓缩于架构设计文档中。详细架构请阅读：
👉 [MathOS System Design (Data-First 架构总纲)](./docs/architecture/MathOS_System_Design.md)

## 🔐 环境变量
程序会按以下顺序读取配置：
1. `MATH_KNOWLEDGE_ENV` 指定的文件
2. 本仓库根目录的 `.env`
3. `C:\mygithub\.env`
4. 当前 Shell 环境变量

*(注意：请勿将 `DEEPSEEK_API_KEY` 或 `MINERU_API_KEY` 提交到版本库)*

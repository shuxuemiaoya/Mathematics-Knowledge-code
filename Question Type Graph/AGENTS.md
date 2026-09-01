# Question Type Graph Agent Contract

This directory is a standalone, profile-driven supplementary-book agent. Do
not import runtime code from `Book to Obsidian Wiki Graph` and do not modify
that agent while operating here.

## Required Sequence

```text
freeze typed sources
  -> deterministic preflight and immutable run record
  -> forced MinerU OCR for every PDF source
  -> page/bbox provenance index, format inventory, and reviewed adapter worksheet
  -> hierarchy segmentation
  -> functional-block and atomic-question segmentation
  -> generated-title cleanup
  -> optional authoritative answer matching
  -> reviewed supplementation for unresolved enabled answers
  -> markup-only Markdown standardization
  -> optional structural Canvas
  -> final audit
```

## Invariants

- Treat every source PDF and registered raw Markdown file as immutable.
- Run preflight before OCR or graph mutation. Resolve credentials from an
  explicit path, process environment, or deterministic profile/project-root
  search; never make launch-directory choice part of format behavior.
- Append immutable run and stage-attempt IDs with input fingerprints and
  artifact hashes. Never overwrite the history of a terminal attempt.
- Bind every reusable compiler stage fingerprint to the concrete Python
  modules that implement that stage. A resume after compiler changes must
  invalidate stale stage artifacts and rebuild descendants without adapter
  cachebuster edits.
- When one OCR row contains several leader-delimited TOC entries, inventory
  every entry with its raw column and propose source-stream and column-major
  orders. Prefer a continuous printed ordinal ledger only as a review proposal;
  a reviewer still confirms authority and reading order. Coverage is per
  leader-delimited entry, not per Markdown line: registering one item on a
  multi-entry row cannot cover its siblings.
- Review a printed TOC from its first leader-delimited entry through its last
  entry across every TOC page. The hierarchy planner must reject any
  leader-delimited row before the first body anchor that is absent from the
  primary ledger. A printed answer-key entry may be omitted from the content
  hierarchy only through `primary_authority.excluded_entries` with its exact
  source line, title, concrete reason, and reviewer confirmation.
- Cross-check conventional printed numbering against hierarchy semantics. If a
  book uses `第N讲` and `N.M`, each `N.M` node must be deeper than and directly
  parented by the matching `第N讲`; a repeated `思考题` must be a child of the
  nearest preceding lecture. Never flatten these titles into sibling folders.
- When the first hierarchy level exists only to organize second-level files,
  mark every first-level entry `structural_only: true`, scope questions only to
  second-level leaf contexts, and set `question_ownership_policy: leaf-only`.
  This strict mode requires exact scope coverage and a complete reviewed
  leaf-by-question-kind count matrix, including zeroes. Verify globally that
  every Q embed occurs once and that no Q is owned by a structural parent, so a
  last-node content swallow or duplicate navigation link cannot pass audit.
- Classify the source format before adapting it: single-topic teacher edition,
  structured monograph, or exercise bank. For a structured monograph or a
  multi-book series, visually review each volume's complete printed TOC and
  freeze its own `entry -> level -> parent -> body anchor -> output` ledger.
  Never copy line anchors, answer boundaries, or hierarchy depth between
  sibling volumes; only path-free recognition semantics may be reused.
- Record reviewed output policy and root layout in every adapter. When the user
  or series convention disables index and Canvas, set both switches false and
  audit away stale artifacts. When `graph_root` is already the book directory,
  never append another same-title wrapper directory.
- Build a source-provenance index from MinerU content-list artifacts. Preserve
  original Markdown line ownership through hierarchy snapshots and attach an
  exact PDF page/bbox to atomic questions whenever evidence resolves; retain
  all candidates when it does not.
- Carry the same absolute profile path and frozen source hashes through every
  structured handoff.
- Keep publisher labels, titles, page ranges, numbering rules, answer layouts,
  and output folder templates in a reviewed `format-adapter.json`, never in
  reusable compiler code.
- Treat reviewed `output_policy.generate_index` and
  `output_policy.generate_canvas` as authoritative output switches. When either
  is false, do not publish that artifact and remove only hash-matching outputs
  previously owned by its pipeline stage; final audit must reject stale root
  index notes, `.canvas` files, or Canvas manifests.
- Scope numeric question detection to reviewed question-bearing functional
  roles, contexts, or source ranges before adding source-line exclusions for
  isolated false positives.
- Create one leaf note per semantic question. Keep genuinely shared-stem or
  dependent subparts together, but split publisher packet wrappers whose
  independently stated items alternate with their own authoritative solutions.
- Treat every adapter-recognized publisher worked example or variant as an
  atomic question leaf. The compiler must globally add `重要程度: 重要`, retain
  only the stem in that leaf, move the publisher's analysis into a separate
  authoritative `<QID>A1.md` answer note, and embed it from the question. Keep
  these leaves out of external answer matching. Recognition and exact solution
  boundary syntax remain in `content.question_kind_rules` and
  `content.worked_example_solution_patterns`, never in reusable compiler
  vocabulary.
- Treat teacher-edition exercises with publisher answers printed inside each
  question span as adapter-recognized `separate-authoritative` kinds rather
  than fake non-overlapping combined-source answer regions. Only the
  `worked-example` kind receives `重要程度: 重要`; other publisher-solved kinds
  retain their reviewed numbering policy. For interleaved subpart solutions,
  use adapter-owned solution start/resume patterns. Atomize independently
  stated and independently solved packet items into separate Q/A1 pairs; keep
  only genuine shared-stem or dependent subparts in one composite leaf.
- For the single-topic teacher-edition format represented by
  `专题01 导数的运算(教师版)`, set both reviewed output switches to false: its
  topic and functional notes are the navigation surface, so it must not create
  a synthetic root `index.md` or structural Canvas.
- When such a PDF already lives inside its dedicated source-topic directory,
  use that directory itself as `graph_root`; do not append another wrapper
  directory derived from the PDF filename. Record the reviewed direct-root
  layout in adapter inventory evidence and keep entry outputs root-relative.
- Flatten question-bearing HTML tables into semantic column streams before
  segmentation. Merge streams by the next printed question number, keep each
  image or strategy with its column record, and expose adapter-matched labels
  inside cells as their own nodes; never leave orphan `<td>` or `<tr>` tags in
  an atomic question.
- Final audit must require a continuous `1..N` question-number ledger inside
  every reviewed answer context. Gaps, duplicates, and reordered numbers are
  blocking errors rather than warnings.
- Treat every authoritative `unmatched-answer` review record as a blocking
  `answer-without-question` error. Reviewer confirmation cannot waive it,
  because it may be the only evidence that a continuous-looking question
  ledger lost its entire tail.
- Preserve a publisher/OCR numbering reset in the immutable source body, but
  use matching reviewed question/answer number-shift ranges when semantic
  identity must remain continuous.
- If visual PDF review proves that conversion omitted a complete question,
  recover it only through a page-provenanced, reviewer-confirmed virtual
  question entry anchored to the immutable hierarchy corpus; never reconstruct
  a missing stem from the answer alone.
- If visual PDF review proves that conversion omitted a fragment inside an
  otherwise preserved question, use an adapter-owned
  `recovered_question_fragments` insertion bound to the hierarchy snapshot's
  exact raw line/column, before/after position, drift anchor, PDF page/bbox, and
  reviewer confirmation. It may only insert PDF-visible text into the semantic
  virtual copy; it must never edit, replace, or delete frozen OCR text.
- If visual PDF review proves that OCR joined the end of one solved item and
  the next question header on one physical line, split only the semantic copy
  through adapter-owned `reviewed_semantic_line_splits` with exact
  hierarchy-local Unicode columns, drift anchor, PDF page/bbox, reason, and
  reviewer confirmation. Never edit the frozen raw line.
- Also use a reviewed semantic line split when OCR joins a worked-example stem
  and its publisher `分析/解答` on one line. Before delivery, scan every generated
  worked-example question source block; any remaining publisher solution marker
  in the Q body is a blocking boundary defect, even if an A1 note exists.
- Preserve source text, formulas, images, tables, numbering, and order. Add
  Markdown structure and navigation only.
- Keep a chapter's explanatory introduction in the chapter note unless the
  reviewed structure explicitly makes it an independent navigational node.
  Move publisher-labeled chapter metadata into YAML frontmatter only through
  adapter-declared `content.note_properties` rules with named `value` groups;
  do not leave duplicate metadata lines in the rendered body.
- After content segmentation, clean every generated title and corresponding
  filename by preserving only Unicode letters, digits, and `_` and replacing
  every other character (including whitespace, full-width punctuation such as
  `：`, ASCII punctuation, symbols, and emoji) with `_`. Never rewrite frozen
  OCR text or question bodies during title cleanup.
- Never accept fuzzy answer similarity by itself. Route ambiguous or missing
  matches to a blocking review queue.
- A source-confirmed question for which the publisher supplies no answer may be
  retained with per-question `answer_handling: unavailable`. It must render
  `answer_status: unavailable`, own no A1 or answer record, and bypass neither a
  publisher answer that actually exists nor any unresolved matching evidence.
- Never bypass `review_required` by calling component apply functions directly.
  Resolve the owning adapter/review artifact and resume through the coordinator.
  Compiler implementation hashes, not adapter cachebuster metadata, invalidate
  stale stages and descendants.
- Assign each answer block to at most one question and each question to at most
  one answer. A re-claimed candidate routes to the blocking review queue,
  never to a second match (the final audit hard-errors on
  `answer-owned-more-than-once`).
- Answer patterns must accept real "N.M…" answers (e.g. `8.2或-2或…`,
  `5.2 【解析】`) while rejecting section-number phantoms (`1.3 空间向量…`).
  Verify the pattern set against every `^\d+[.．、]\d` line in the answer raw,
  and keep the same patterns in the adapter and any build-script event scanner.
- Answer application is declarative: automatically remove owned answer notes
  and embeds when a question flips matched → unmatched, and record removals in
  `answer-application-report.json`.
- Store reviewer-authored solutions that must survive pipeline regeneration in
  staging `reviewed-supplement-overrides.json`, keyed by `question_id` and
  `question_body_sha256`. Regenerated supplement plans must reuse only entries
  whose body digest still matches, and the coordinator should reapply those
  reviewed solutions without another manual copy/paste cycle.
- Keep atomic questions off the structural Canvas.
- Leave knowledge-point linking disabled until a later explicit stage.
- Keep staging outside published vault roots and create no backup directories.
- Use adapter-configured `answers.callout_title` for answer callouts rather than hardcoding publisher names.
- When OCR drops a choice answer header but preserves an explicit authoritative conclusion such as `故选:D`, recover `D` into a separate `**【答案】** D` field. Never infer an option from isolated capital letters or mathematical prose. Choice-question audit must fail on a missing answer field, and authoritative notes must agree with the source conclusion.
- Every generated solution note must use a collapsible outer
  `> [!faq]- <title>` and three collapsible nested callouts:
  `> > [!success]- **【答案】**`, `> > [!note]- **【分析】**`, and
  `> > [!note]- **【解析】**`. All nested content lines must retain the `> >`
  prefix. Recover a bounded publisher-stated result that appears before
  an explicit `解析:`/`【解析】` marker. When a non-choice problem has no safely
  separable short result, write `**【答案】** 详见解析`; never use that fallback
  for a choice problem, whose exact option remains mandatory.
- Ensure question and answer regex patterns use a single named group (e.g. `^【?(?P<number>\d+)[】.．、]?\s*`) to prevent Python regex duplicate group name errors.
- Bound ordinary question `end_line` before any internal markdown heading
  (`^\s*#{1,6}\s+\S`) in `plan_note()`. A reviewed worked-example kind may set
  `preserve_internal_headings: true` so publisher `分析/解析/评注` headings stay
  inside the atomic leaf.
- Automatically deduplicate adjacent OCR duplicate answer header lines for the same `(context, number)` in `answers.py`.
- Allocate question sequence numbers through the locked vault registry
  `.question-type-graph/question-id-registry.json`. Seed a new registry from
  the vault and any adapter-configured central question repository.
- Pre-split inline answer headers (e.g. `... 故选：B 【5】A`) in `parse_answer_blocks()` before scanning so OCR lines containing concatenated answer headers are isolated into separate answer blocks.
- Update `format_answer_callout()` option extraction regex (`^【?\d+】?[\.、\s]*([A-Z]+)`) to accept bracketed question numbers (`【N】A`) as well as plain numbers (`N. A`).
- Validate and align `answers.contexts` `start_line` boundaries against exact section heading positions in `answers.raw.md` during format inventory to prevent cross-section answer block misattribution and duplicate-number collisions.
- Preserve `## 知识导学` knowledge guide sections and all nested subheadings (`## 一. ...`, `## 1. ...`), formulas, diagram asset paths, and comparison tables within primary section notes without splitting them into separate question notes.
- Enforce zero-tolerance validation for questions lacking explanations during
  graph audit. External-answer exercises MUST embed a valid solution callout
  note; publisher worked examples MUST embed a separate, provenance-marked
  authoritative solution note and MUST NOT retain that solution inside the
  question-source block. Any failure is blocking and reports the exact cause.
- Treat this file and `skills/question-type-graph/references/pipeline-contract.md`
  as the canonical policy. Knowledge linking remains deferred; component skill
  documentation must not activate it implicitly.

## Canonical Skills

The canonical skills live under `skills/`. Install or link that directory using
the host platform's Codex skill location; do not maintain copied duplicates.

---

## 3. Codebase Markdown Documents Map / 文档全景导航与说明

本仓库中所有 `.md` 文件的职责定位与功能划分如下：

### 3.1 根目录核心文档 (Root Documents)

| 文档路径 | 作用与功能说明 |
| :--- | :--- |
| [`AGENTS.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/AGENTS.md) | **顶层 Agent 核心契约与执行规范说明书**。定义了题型图谱构建流水线标准顺序、全局不变量（Invariants）、审计硬性指标以及全仓库 Markdown 文档的职责全景导航。 |
| [`README.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/README.md) | **项目概览与上手指南**。介绍 Question Type Graph 系统的设计背景、核心特性、安装运行步骤、CLI 命令行工具用法及基础配置示例。 |
| [`IDEA.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/IDEA.md) | **设计思考与技术愿景**。记录系统在设计初期的灵感来源、图谱化题库建模哲学、核心算法构想以及长期演进路线。 |

### 3.2 智能体与变更日志 (Agents & Changelogs)

| 文档路径 | 作用与功能说明 |
| :--- | :--- |
| [`agents/question-type-graph-agent.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/agents/question-type-graph-agent.md) | **专职 Agent 的完整 System Prompt 与实战经验库**。包含系统提示词、实战总结（如【反思】模块独立 Callout、短答案提取、星级难度自动注入、三级大纲防扁平化、高考真题汇编适配、教师版交错解析等规则）。 |
| [`agents/CHANGELOG.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/agents/CHANGELOG.md) | **Agent 版本演进与变更记录**。详细记录 Agent 提示词、规则集与核心规范的历次版本修复、功能新增与行为演进历史。 |

### 3.3 各阶段流水线技能与参考规范 (`skills/`)

#### 阶段 0/1：PDF 转写与 OCR
- [`skills/question-type-pdf-to-markdown/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-pdf-to-markdown/SKILL.md): **PDF 强制 OCR 与原始 Markdown 转写技能**。指导调用 MinerU 进行 PDF 高精度解析、智能分片、公式识别与图片资产提取。
- [`skills/question-type-pdf-to-markdown/references/mineru-api.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-pdf-to-markdown/references/mineru-api.md): **MinerU API 调用与分片契约**。定义云端/本地 OCR API 接口协议、80 页安全分片上限以及排队重试策略。

#### 阶段 2：目录大纲识别与层级切分
- [`skills/question-type-toc-segmentation/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-toc-segmentation/SKILL.md): **目录大纲建模与层级规划技能**。负责分析教辅印刷目录与正文标题，规划章/节/考点层级树与文件夹结构。
- [`skills/question-type-toc-segmentation/references/hierarchy-manifest.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-toc-segmentation/references/hierarchy-manifest.md): **大纲层级清单契约**。定义 `hierarchy-coverage-manifest.json` 结构、单调递增行号约束与 100% 覆盖率验证标准。

#### 阶段 3：内容切分与原子题抽取
- [`skills/question-type-content-segmentation/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-content-segmentation/SKILL.md): **内容功能块切分与原子题生成技能**。将正文切分为结构笔记、知识导学与原子题目笔记（`Q*.md`），自动分离例题题干与解析。
- [`skills/question-type-content-segmentation/references/content-manifest.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-content-segmentation/references/content-manifest.md): **内容清单契约**。定义 `question-type-manifest.json` 格式、QID 全局唯一分配规则与星级难度等 Frontmatter 属性。

#### 阶段 4 & 4.5：答案匹配与补充解析
- [`skills/question-answer-matching/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-answer-matching/SKILL.md): **题目与权威答案精准对齐技能**。基于题号、题干特征与上下文边界进行严格对齐，生成 `Q*A1.md` 解析嵌入卡片。
- [`skills/question-answer-matching/references/answer-matching.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-answer-matching/references/answer-matching.md): **答案匹配清单契约**。定义 `answer-match-manifest.json` 格式、`used_answer_ids` 唯一认领守卫与冲突阻塞机制。
- [`skills/supplement-question-type-solutions/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/supplement-question-type-solutions/SKILL.md): **缺失答案补充与审核技能**。针对权威答案缺失题目生成高质量 AI 解析，并通过 `reviewed-supplement-overrides.json` 实现持久化绑定。

#### 阶段 5：Markdown 标准化
- [`skills/question-type-markdown/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-markdown/SKILL.md): **Markdown 标准化排版与语法清洗技能**。规范折叠 Callout（【答案】/【分析】/【解析】/【反思】）、KaTeX 数学公式与相对图片链接。
- [`skills/question-type-markdown/references/preservation-contract.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-markdown/references/preservation-contract.md): **内容无损保护契约**。严格保证清洗排版过程中原始数学公式、中文推导字句与题干内容 0 丢失、0 篡改。

#### 阶段 6：Canvas 白板编译
- [`skills/question-type-canvas/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-canvas/SKILL.md): **结构化 Obsidian Canvas 编译技能**。自动生成章节拓扑白板，仅包含结构与考点笔记，排除海量原子题目。
- [`skills/question-type-canvas/references/canvas-contract.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-canvas/references/canvas-contract.md): **Canvas 白板契约**。定义节点坐标网格计算、父子连线拓扑与边界尺寸规范。

#### 总控流程与适配器规范
- [`skills/question-type-graph/SKILL.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-graph/SKILL.md): **总控编排技能**。统筹调度 0~6 全部阶段、管理断点续跑（`resume`）并执行最终全图谱审计（`audit_graph`）。
- [`skills/question-type-graph/references/pipeline-contract.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-graph/references/pipeline-contract.md): **总控流水线契约**。定义阶段间输入/输出状态机、Stage Fingerprint 哈希失效与零警告完成标准。
- [`skills/question-type-graph/references/format-adapter.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-graph/references/format-adapter.md): **教辅格式适配器规范**。全面定义 `format-adapter.json` 中所有大纲规则、题号正则、解析边界与输出模板字段。
- [`skills/question-type-graph/references/structured-monograph.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/skills/question-type-graph/references/structured-monograph.md): **结构化专著与系列教辅批处理协议**。定义多卷丛书独立 staging、多层目录拓扑与逐册审计规范。

### 3.4 历史运行报告 (`reports/`)

| 文档路径 | 作用与功能说明 |
| :--- | :--- |
| [`reports/高中数学思想方法导引2023版-adaptability-run-2026-08-11.md`](file:///Users/oven/Documents/Mathematics-Knowledge-code/Question%20Type%20Graph/reports/高中数学思想方法导引2023版-adaptability-run-2026-08-11.md) | **《高中数学思想方法导引》实战运行报告**。记录该专著全书切分运行、大纲适配配置、题目切分统计与最终审计归档数据。 |


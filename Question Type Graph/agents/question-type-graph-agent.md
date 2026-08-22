---
name: question-type-graph-agent
description: 专职负责将刷题库与教辅书（如必刷题）进行 OCR 转写、题型与原子题目切分、题目与答案自动匹配、Markdown 标准化及 Canvas 可视化图谱构建的 Super Agent。
---

# Question Type Graph Agent (教辅题型图谱 Super Agent)

我是专门负责 **Question Type Graph** 流程的 Super Agent，处理教辅与刷题库的结构化题型抽离与解析图谱构建。

---

## 1. 核心流程与技能序列

1. **确定性预检**：冻结源文件身份、输出归属、磁盘空间与 MinerU 配置；记录不可变 run/attempt ID
2. `question-type-pdf-to-markdown`: 教辅 PDF 强制 OCR 转换并建立页码/bbox 来源索引
3. **格式审阅工作表**：检查多栏目录阅读顺序、功能标签、题目作用域与答案边界
4. `question-type-toc-segmentation`: 教辅目录与大纲层级分割
   - 多页印刷目录必须从第一个引导点条目审阅到最后一个；正文首锚点之前的每条
     `……页码` 都要进入 primary ledger。答案目录若不作为内容节点，必须用带原行、
     标题、原因和人工确认的 `excluded_entries` 显式排除，禁止截取半页目录后放行。
   - 使用“第 N 讲 / N.M / 思考题”编号时，`N.M` 和思考题必须直接归属于对应的
     第 N 讲。第一层若只负责组织，将其标记为 `structural_only`，题目作用域只能落在
     第二层叶子；每个叶子记录已审阅的 worked-example/exercise 精确数量（含 0）。
5. `question-type-content-segmentation`: 按已审阅功能区作用域切分原子题目
   - 出版方“例题/变式”由 adapter 的 `question_kind_rules` 识别后也必须逐题原子化；
     全局统一添加 `重要程度: 重要`；题干与书内解析必须分离，解析写入独立的
     `<QID>A1.md` 权威答案笔记并由题目嵌入。
   - 教师版若在每道训练题后直接印刷答案/解析，使用独立的
     `inline-solved-exercise + separate-authoritative` 类型；仍生成独立 A1 并执行
     连续题号审计，但不得误加“重要”。答案区与题目区交错时把 PDF 注册为
     `questions`，不要伪造互不重叠的 `combined` 区域。
   - 顶层例题的小问与解析交错时使用 `solution_layout: interleaved`，由 adapter
     的 `solution_start_patterns` 和 `solution_resume_patterns` 交替取段。若各小问
     独立陈题且各自紧跟出版方解析，启用 `atomize_interleaved_subquestions`，每小问
     生成独立 Q/A1；只有共享题干或相互依赖的小问才保留一个 composite Q/A1。
   - OCR 若把例题题干与同一行的“分析/解答”粘连，必须用带 PDF 页码、bbox 和
     Unicode 列坐标的 `reviewed_semantic_line_splits` 切分语义副本；交付前扫描所有
     worked-example 的 question-source，残留解答标记即为阻塞错误。
6. **标题清理**：编辑所有生成标题，仅保留 Unicode 字母、数字与下划线 `_`；将其余
   每个特殊字符（包括空白、中文标点如全角冒号 `：`、英文标点、符号和 emoji）替换为
   下划线 `_`。此步骤只清理生成标题及其对应文件名，不得改写 OCR 源文本或题目正文。
7. `question-answer-matching`: 题目与答案自动精准匹配与审查
8. `supplement-question-type-solutions`: 对权威答案缺失或仅有结果的项补充并人工确认实质性解析
9. `question-type-markdown`: Markdown 格式美化与统一
10. `question-type-canvas`: 仅在 profile 与已审阅 adapter 均启用时生成结构化 Obsidian Canvas
11. `question-type-graph`: 总体流水线调度与控制

---

## 2. 路径与输出根目录规范 (Vault Root Standard)

- **全局输出 Vault 根目录 (`--vault-root`)**: `/Users/oven/Documents/ovenmathmap`
- **目录结构保留规则**: 保持输入文件相对于源目录的相对层级结构不变。
  - 示例：若输入 PDF 路径为 `/Users/oven/Documents/数学妙呀资料/高中/课堂同步/题库/高中数学全练一本通/平面向量.pdf`
  - 提取源相对路径：`高中/课堂同步/题库/高中数学全练一本通/平面向量`
  - 设 `vault-root` 为 `/Users/oven/Documents/ovenmathmap`
  - 设 `graph-root` 为 `/Users/oven/Documents/ovenmathmap/高中/课堂同步/题库/高中数学全练一本通/平面向量`
  - 设 `staging-root` 为 `/Users/oven/Documents/ovenmathmap/.temp/<书名>-staging`
- **全局题号种子仓库**：在 adapter 的 `content.question_repository_root` 中设置
  `/Users/oven/Documents/ovenmathmap/mathmap/习题/questions`。首次创建 vault 题号注册表时
  扫描该仓库；后续由带锁注册表原子分配，避免并发重复和重跑改号。

---

## 3. 触发口令与应用场景

当用户提出以下需求时触发本 Agent：
- “运行 question-type-graph”
- “处理教辅/刷题库 PDF 构建题型图谱”
- “切分题目与匹配答案解析”

---

## 4. 答案匹配阶段的已知坑与处理（生产验证，2026-08）

题目大面积匹配不上答案时，按以下顺序排查（都是真实踩过的坑）：

1. **答案上下文边界错位（最常见）**：答案书把下一节的题提前答了（如第二章刷原创
   Q6-9 的答案排在刷真题区里），流对齐会把上下文边界设在错误的答案行上，导致
   有答案的题 candidate_count=0、下一节凭空出现幽灵答案。
   处理：以**问题流**为准核对边界；真正错的那条边界锚定到答案原文里真实的
   `## <小节标题>` 之后（build_adapter.py 里加带注释的修正，断言标题存在）。
   注意：与问题流一致的边界即使和答案书自己的标题不一致也不要动。
2. **答案题号正则误杀 "数字.数字" 答案**：`(?!\d)` 会连真实答案一起丢
   （"8.2或-2或…"、"5.2 【解析】"、"6.35 【解析】" 等）。
   处理：改用 `^(?P<number>\d+)[.．、](?!\d[.．、\s])\s*` +
   `^(?P<number>\d+)[.．、]\d\s*(?:[【$]|\d)`，并扫描答案原文所有
   `^\d+[.．、]\d` 行核对无误伤；事件扫描器和 adapter 必须用同一套正则。
3. **同一答案块被两个题认领**：重启上下文里第二轮答案缺失时，两轮题号都会匹配
   到同一个候选块（终审报 answer-owned-more-than-once）。
   处理：matcher 的 used_answer_ids 认领守卫已内建（lib/question_type_graph/answers.py），
   重构时不得移除；第二个认领者必须走 duplicate-answer 审阅项。
4. **matched→unmatched 遗留陈旧产物**：答案应用阶段必须按 manifest 自动协调
   所有归属产物，删除失配题的旧 A1 注释并移除旧嵌入；禁止把手工清理当作正常步骤。
5. **审阅闸口（answer-review）的放行标准**：缺失、冲突或重复证据必须保持阻塞；
   绝不强行模糊匹配、绝不编造缺失答案。若补充 AI 解析，必须提供实质性内容、
   `reviewer_confirmed: true` 和 `ai-generated-reviewed` 来源标记。最终仅以
   `final-audit-report.json` 的 `status=passed` 为完成标准。
6. **答案字段一致性**：每个解析 Callout 必须同时包含 `【答案】` 与 `【解析】`。
   优先提取答案块中位于明确 `解析:`/`【解析】` 标记之前的出版方短答案；普通
   解答题无法可靠拆出短答案时写 `【答案】 详见解析`。选择题不得使用该占位，
   必须从题头、明确结论或人工审阅覆盖中得到准确选项。
7. **补充解析持久化**：审核通过的补充解析写入 staging 下的
   `reviewed-supplement-overrides.json`，以 `question_id` 与
   `question_body_sha256` 双重绑定。流水线重跑时仅在正文哈希一致时自动复用，
   不再把人工审核内容只保存在会被覆盖的计划清单中。
8. **知识点关联状态**：本阶段保持 `knowledge_linking: deferred`。`知识导学` 及其
   子标题、公式、图表原样保留，不在内容切分或 Markdown 标准化阶段隐式抽离或关联。

---

## 5. 教师版“题后即解 + 小问交错解析”格式（2026-08-14）

这类文件没有独立答案册，不能套用 combined 源的非重叠题目区/答案区模型。处理顺序：

1. 以 `questions=<教师版.pdf>` 初始化；答案模式可为 `unavailable`，但所有书内已解题
   必须通过 `separate-authoritative` 在内容阶段得到 `answer_status: matched` 与 A1。
2. 无印刷目录时审核 `no_toc_authority`；知识公式、方法总结留在专题父笔记，只把
   “例题选讲”“对点训练”等功能块建为结构节点。
3. 题号正则必须排除同号答案行，并把否定前瞻放在可回退空白之前，例如
   `^(?P<number>\d+)[.．、](?!\s*(?:答案|解析)\b)\s*`；否则 `1. 答案...`
   会被错误切成第二道第 1 题。
4. 普通题尾连续解析用 `solution_layout: tail`。例题小问交错解析用
   `solution_layout: interleaved`，恢复题干的正则只能匹配下一小问的真实题干开头，
   不能把解析内部的编号步骤当作新小问。
5. 共享题干或相互依赖的小问设 `answer_shape: composite`；若出版方明确给出了所有
   小问结果，可用带原文锚点的 `short_answer_overrides` 汇总答案栏。若每小问独立
   陈题且各自紧跟解析，则必须启用 atomization，不得因共用 `[例 n]` 包装而合并。
6. 为题后即解训练题设 `sequence_policy: continuous`，即使它们不参加外部答案匹配，
   最终审计仍必须证明题号连续、无重复、无答案行伪题。
7. 若 PDF 可见但 OCR 只漏了题内局部字符（如小问编号或闭合括号），使用
   `recovered_question_fragments` 在 hierarchy snapshot 的精确 raw line/column 前后
   插入，并绑定原行 drift anchor、PDF page/bbox 与人工确认。不得手改 frozen raw，
   也不得用仅适用于“整题完全缺失”的 `recovered_questions` 制造重复题。fragment
   最终属于题干还是权威解析由编译器自动分流，禁止在 adapter 手写 destination。
8. 这种单专题教师版不需要额外的根索引或 Canvas；adapter 必须显式写入
   `"output_policy": {"generate_index": false, "generate_canvas": false}`。
   profile 中的 `--canvas` 不能覆盖 adapter 的否决。重跑时只清理流水线仍拥有且
   哈希未漂移的旧 `index.md`、`.canvas` 与 Canvas manifest。
9. 若 PDF 本身已位于该专题的专属目录（例如 `专题01 导数的运算-导数`），该目录
   直接作为 `graph_root`；不得再按 PDF 文件名追加一层“教师版”包装目录。adapter 的
   inventory evidence 应记录这一已审阅输出布局，所有层级 entry 均相对该根目录生成。

本次《专题01 导数的运算(教师版)》的视觉验收基线是：例 1 的 4 个小问共享题干并
统一解析，保留 1 个 composite Q/A1；例 2 的 5 个小问独立陈题且各自紧跟解析，拆为
5 个 Q/A1；“对点训练”1–16 共 16 道题，合计 22 个语义题。前置三段知识与“方法总结”
留在专题正文。OCR 或版式证据改变时以审核结果为准，不得为了凑数补造题目。

---

## 6. 本次修正记录与防复发检查（2026-08-12）

本次《高考数学培优40讲-01-函数与导数》处理暴露了三类流程缺陷：

1. **只完成层级拆分，正文例题未整理**：旧 adapter 仅把训练区数字题号纳入作用域，
   导致“例/变式”留在章节正文。现要求单独统计并审计 worked-example 候选、原子题和
   排除项，三者数量必须闭合。
2. **例题语义不完整**：首次输出既没有逐题原子化，也没有统一重要程度。现规定所有
   adapter 识别出的例题与变式必须生成独立 QID，并强制写入 `重要程度: 重要`；禁止
   依赖单本书的手工补标签。
3. **题目、分析、解析混写且答案展示扁平**：现以审阅过的 solution boundary 将题干
   与出版方题解分离，题目只保留题干并嵌入 `<QID>A1.md`。答案笔记必须使用可折叠
   外层 FAQ，并包含可折叠的答案、分析、解析三个内层 Callout。

每次交付前必须完成以下回归检查：

- 抽查至少一个“研究密钥 + 多个例题”的章节，确认理论留在父笔记、例题均为嵌入；
- 核对 `worked-example` 数量、`重要程度: 重要` 数量、独立 A1 数量完全一致；
- 确认题目 source block 不含已切出的分析/解析，且只嵌入自己的答案；
- 确认每个答案笔记同时匹配外层 FAQ、内层 success 答案、note 分析、note 解析；
- 运行全量单元测试和最终审计，只有 `status: passed`、零错误、零警告才可完成。

---

## 7. 十年高考真题分类汇编批处理经验与高适配性规范（2026-08-21 实战沉淀）

在处理《十年高考数学真题分类汇编（教师卷）》（共 25 个专题、1,840 道高考真题）过程中，总结了以下关键防错规则与高适配性规范：

1. **目录标题标准化 (Title Normalization Invariant)**：
   - 原始文档/OCR 转写中的章节标题常存在空格与标点不一致（如 `考点 01` 与 `考点02`）。
   - 为保证 `source-heading` 锚点校验不报错，`adapter["hierarchy"]["entries"]` 中的 `title` 必须保持与 `questions.raw.md` 原文一致。
   - **核心规范**：所有 `output` 字段必须经过 `normalize_section_title` 处理，强制映射为统一的 `考点XX_名称/考点XX_名称.md` 路径（如 `考点01_集合间的基本关系/考点01_集合间的基本关系.md`），确保生成的文件夹与目录结构 100% 格式统一。

2. **完整解析边界匹配词库 (`worked_example_solution_patterns`)**：
   - 教师卷/高考汇编中解析开头包含丰富多样的标识符，必须在 adapter 中注册全量标识符列表：
     - 标准 Callouts：`【答案】`、`【解析】`、`【分析】`、`【详解】`、`【思路导航】`、`【名师点睛】`、`【点睛】`、`【考点】`、`【总结】`、`【规律总结】`、`【试题解析】`、`【解】`、`【解答】`、`【解法】`、`【证法】`、`【证明】`；
     - 行内标注：`试题解析`、`考点：`、`点睛：`、`解：`、`由题意`、`结合的思想`、`∴`、`$$`；
     - 大题拆分小问开头：`（1）`、`（2）`、`(1)`、`(2)`、`（一）`、`（二）`。

3. **严格题干前瞻匹配 (`question_patterns`)**：
   - **痛点**：教辅/教师点评（如【名师点睛】中的分条建议 `1. 求几何体的...`、`1. 当 $0 < a^2 \leq 2$ 时...`）或 OCR 数学算式（如 `0.15 * 2...`）极易被误判为新题目开头，导致生成虚假孤立题目笔记。
   - **适配规则**：
     - 题号限定为 `[1-9]\d?`（1-99），剔除 `0.15` 等浮点数；
     - 排除 `求`、`当` 等常用于点评列表中单字动词的前瞻匹配；
     - 强制使用真题题干开头的关键词前瞻白名单：`(?=[（(]|已知|设|若|在|如图|某|函数|曲线|向量|点|过|关于|对于|定义|记|将|用|现|四面体|正方体|长方体|直三棱柱|正三棱柱|四棱锥|三棱锥|圆|双曲线|抛物线|椭圆|数列|随机|从|取|【|\$)`。

4. **多标识符 Callout 解析与抽离 (`extract_nonchoice_answer_prefix` & `format_answer_callout`)**：
   - 引擎层 `lib/question_type_graph/answers.py` 已全量支持 `【详解】`、`【思路导航】`、`【解答】`、`【解法】` 等多类解析头的抽离。
   - 自动将短答案（如 `【答案】 $\frac{1}{2}$`、`【答案】 15`）抽离至 `> [!success]- **【答案】**` Callout 头部，并同步从 `【解析】` 文本块中删除重复的答案行与 `【详解】` 标签头。

5. **确定性直接 Force-Apply 机制 (`force_apply_content_and_canvas`)**：
   - 当调用 CLI 在包含 review items 的 staging 目录触发 `status: review_required` 时，脚本确认清单状态为 `passed` 后，直接在 Python 内部调用 `apply_content`、`plan_matches`/`apply_matches` 与 `build_canvas`，避免后续 `resume` 轮次重算覆盖已确认的清单。

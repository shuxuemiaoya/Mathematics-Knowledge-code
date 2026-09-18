# Book to Obsidian Wiki Graph 流程审查

审查日期：2026-09-17。结论：现有流程具备清晰的阶段分工、源身份冻结、目录/教学顺序审核和参考版本约束，但目前的通过条件不足以证明内容无损，且中断恢复和部分阶段接口存在可复现缺陷。应先补齐保真验证、产物绑定和事务恢复，再扩展语义图谱。

本次审查沿 intake → OCR → TOC → splitting → concepts → Markdown → audit → Canvas → metadata → final 的控制流核对文档与实现，重点追踪跨阶段产物。目录包含 32 个生产 Python 脚本和 22 个测试文件；按技能设置 scripts 的 PYTHONPATH 后，现有 245 个测试全部通过。另做了 8 项临时故障注入/边界探针，归纳为下面 6 个实现问题。未调用真实 MinerU 服务、未重新转换整本教材，未修改生产代码或现有书库。

复现脚本：[review-repros.py](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/reviews/2026-09-17-review-repros.py>)；结果：[review-repros.json](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/reviews/2026-09-17-review-repros.json>)；现有测试结果：[test-results.json](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/reviews/2026-09-17-test-results.json>)。

## R1 · P1：内容保真门禁没有验证正文、公式和真实顺序

定位：[standardize_markdown.py:627](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-markdown/scripts/standardize_markdown.py:627>)、[audit_obsidian_graph.py:678](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-audit/scripts/audit_obsidian_graph.py:678>)、[textbook_node_architecture.py:531](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-toc-splitting/scripts/textbook_node_architecture.py:531>)。

`invariants()` 的 `source_order` 固定为 true；公式只比较编号，表格只比较含 `<table` / `</table>` 的行，未覆盖全部表格数据。`audit_coverage()` 检查 unit 标识、状态、目标存在性，没有验证实际正文是否对应 source range，也未检查原始单位全集是否被完整覆盖。教材 architecture 审计补充了父子关系和链接顺序，但其渲染检查同样没有重建并比较原始正文。

复现：把“条件为 $x>0$，结论为 $x=1$”改成只剩“结论为 $x=2$”，全部 protected invariants 仍为 true；在精简 profile 的合法样例中删除必要条件后，`--stage final` 对应的审计函数在修改前后均 passed。

影响：文件存在、链接正确、清单宣称 assigned，并不能排除正文遗漏、条件变更或推导缺失。配置 same-book reference 可以补充发现部分差异，但新书没有参考库时缺少这层保护。

建议：建立稳定 source block ID 与内容摘要；按所有权递归展开笔记，扣除有清单依据的标题规范化、概念副本和预览副本，再与源块顺序和内容比较。正文、TeX、表格数据必须分别核对。任何内容修复须记录 exact before/after 和原书页证据。上述复现是精简样例，不代表已证明任意教材损坏都能通过所有默认门禁。

## R2 · P1：OCR 页覆盖标志只证明上传分片覆盖，不能证明识别输出覆盖

定位：[book_pdf_to_markdown.py:498](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-pdf-to-markdown/scripts/book_pdf_to_markdown.py:498>)、[book_pdf_to_markdown.py:561](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-pdf-to-markdown/scripts/book_pdf_to_markdown.py:561>)、[book_pdf_to_markdown.py:715](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-pdf-to-markdown/scripts/book_pdf_to_markdown.py:715>)。

`validate_coverage()` 验证输入 PDF 分片范围；解包只保留 full.md 和图片，忽略逐页结构数据。最后直接输出 `page_coverage_complete: true`。完整分片数量与非空 Markdown 不能证明分片内部没有漏页。

复现：模拟 100 页输入，服务返回成功，但 ZIP 中只有第 1 页正文和 page_idx=0 的结构记录；转换仍返回 completed、page_coverage_complete=true。这是模拟服务响应，不是声称真实 MinerU 已发生该故障。

建议：持久化转换报告和页级 source map，区分 `upload_ranges_complete` 与 `extracted_pages_verified`；缺少页记录时不得把后者设为 true。空白页、图片页和识别失败页应显式分类；公式密集、双栏、跨页表格、题目子项等样页须做 PDF 对照。保留当前强制 OCR 策略即可，重点是验证输出。

## R3 · P1：same-run recovery 尚未形成完整的可重入事务

定位：[pipeline_runtime.py:1592](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-to-obsidian-wiki-graph/scripts/pipeline_runtime.py:1592>)、[apply_concept_candidates.py:241](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-concepts/scripts/apply_concept_candidates.py:241>)、[apply_concept_candidates.py:301](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-concepts/scripts/apply_concept_candidates.py:301>)。

两项复现：

1. begin 后模拟中断，resume 只复核 completed 阶段，当前阶段仍是 running；再次 begin 报 `stage cannot begin from status running`。可以手工 fail 后重试，但合同没有自动处理“执行进程已经消失”的状态。
2. 概念笔记先落盘，来源笔记和 manifest 后落盘。在来源笔记写入处注入失败后，留下概念文件、没有 backlink、没有 manifest；再次运行被“concept directory is not empty”拒绝。即使先手工 fail，组件仍无法直接重放。正常拆分已经产生概念候选时，该空目录前置条件也与文档所说的“验证并接纳候选”不兼容。

单文件 atomic_write 无法保证整批笔记、反向链接和 manifest 的一致提交。splitter 也在移入最终目录后才写 coverage 清单，存在类似的提交边界。

建议：记录执行 lease/进程信息，确认执行已终止后进入 interrupted/recoverable；把所有拟写文件和 manifest 放入同一事务计划，逐项保存原输入摘要与预期输出摘要，支持安全重放或恢复。可选测试 checkpoint 不应是默认生产运行恢复能力的前提。

## R4 · P1：阶段完成校验未绑定报告与它宣称验证的实际文件

定位：[pipeline_runtime.py:1310](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-to-obsidian-wiki-graph/scripts/pipeline_runtime.py:1310>)、[pipeline_runtime.py:1395](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-to-obsidian-wiki-graph/scripts/pipeline_runtime.py:1395>)。

运行时分别验证报告结构、profile/source 身份和输出文件存在性，但普通阶段缺少报告与输出之间的交叉摘要校验。begin 的输入列表也允许为空，未强制继承上游产物。Canvas style report 对 candidate 文件有专门摘要绑定，其他报告未统一采用。

复现：生成 passed 的 TOC 格式报告后修改实际 formatted.md，使其不再匹配 `candidate_markdown_sha256`；`complete_stage(toc-formatting)` 仍接受并标记 completed。后续 splitter 的自身校验能挡住部分情况，但无法替代协调器声称的统一严格交接。

建议：按 stage 定义 required_inputs 和 outputs 的对应关系；complete 重新计算报告中的 input/output 摘要，检查报告的对象路径。审计报告应绑定当前 corpus revision；mutable directory 可以允许合法下游编辑，但仍需保留每阶段的文件清单和摘要，防止旧报告给新内容背书。

## R5 · P2：元数据处理会静默丢失合法 YAML 数据

定位：[tag_book_metadata.py:93](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-metadata/scripts/tag_book_metadata.py:93>)、[tag_book_metadata.py:123](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-metadata/scripts/tag_book_metadata.py:123>)、[tag_book_metadata.py:379](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-metadata/scripts/tag_book_metadata.py:379>)。

frontmatter 由逐行冒号切分读取、字符串拼接写回，无法保存 YAML 列表、嵌套结构和多行文本。复现中 `aliases` 和 `tags` 的列表值均被删除，metadata-report 仍 passed。该阶段正文文件使用直接 write_text，也与 README 的原子更新承诺不一致。

另一个已验证的分类偏差：标题“数学 必修第二册”被判定为高二，因为“第二册”优先命中；与本技能 README 的必修一/二→高一规则不一致。对一般书籍也默认填入高中属性，难度和学习时长是启发式估算却没有标明来源。

建议：使用真实 YAML 解析/序列化，保留未归本阶段管理的字段及数据类型；先渲染并重新解析验证，再原子写入。年级采用 profile 显式值或经审查映射；难度、时长等估算应标注推断来源。最终审计应校验实际 frontmatter，而不只是接纳先前的报告。

## R6 · P2：非教材的概念阶段禁用逻辑不一致

定位：[audit_obsidian_graph.py:1135](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-audit/scripts/audit_obsidian_graph.py:1135>)、[audit_obsidian_graph.py:1208](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-audit/scripts/audit_obsidian_graph.py:1208>)。

intake 给 general book 的默认 categories 只有 content；runtime 在不存在启用的 concept role 时不要求概念清单。然而 audit 把 concept_directory 初始化为“概念”，仅在存在显式 disabled 的 concept 配置时清空。类别完全缺省时仍在 concepts/formatting/pre-canvas/final 阶段要求 concept-manifest。

复现：用 create_profile 创建 general profile，仅有 content，concepts 审计失败并报 concept-manifest-not-provided。

建议：所有组件共用 profile 的能力判定；不存在的可选 role 与 enabled=false 都应跳过对应产物门禁。若仅支持高中数学，则收紧入口承诺；若继续支持一般书籍，TOC、概念和元数据均需明确的 profile 分支。

## GitHub 对照与架构建议

这些项目作为设计参考，不据 README 中的效果宣称认定其正确性。本项目的无损教材转写目标应保留。

| 参考项目 | 核对到的机制 | 对当前流程的启示 |
| --- | --- | --- |
| [virgiliojr94/book-to-skill](https://github.com/virgiliojr94/book-to-skill/blob/master/docs/how-it-works.md) | 确定性提取与 agent 生成分离，主入口加按需章节；产物是蒸馏后的技能 | 借鉴按需读取和检索入口。其摘要压缩策略不适合代替本项目的原文保存层 |
| [zhimaAi/BookToSkill](https://github.com/zhimaAi/BookToSkill/blob/main/scripts/merge_index.py) | 校验证据 ID 属于当前 chunk，从证据单元重建正文，再附加章节/页码等来源信息 | 把可验证 source block 作为接口；LLM 提交分类、范围和关系，正文由确定性程序复制 |
| [rahulnyk/knowledge_graph](https://github.com/rahulnyk/knowledge_graph/blob/main/README.md) | chunk_id、概念与关系抽取、关系合并、图可视化分步进行；另有共现关系 | 把关系抽取放在布局之前。共现只能作为相关候选，不能直接充当数学先修或推理关系 |
| [vanderbilt-data-science/knowledge-spaces](https://github.com/vanderbilt-data-science/knowledge-spaces/blob/main/schemas/knowledge-graph.schema.json) | 独立知识项 ID、先修关系，以及可选 confidence/rationale/source；配有[结构验证工具](https://github.com/vanderbilt-data-science/knowledge-spaces/blob/main/scripts/kst_utils.py) | 若要支持学习路径，应独立保存并审计语义关系。图结构验证仍不能取代数学语义审核 |

当前语义关系主要在可选 Canvas 阶段出现：[plan_from_manifests.py:376](</Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph/skills/book-graph-canvas/scripts/plan_from_manifests.py:376>) 把关系转换为端点、label、颜色和连线位置，没有要求每条关系带原书证据范围。现有 Wiki 链接足以表达组织结构和定义来源；若目标进一步包括“为什么依赖”“先学什么”“此例题使用哪些定理”，还需要独立语义层。这是目标能力上的架构缺口，不应混同于上述已复现的实现错误。

建议增加 `knowledge-relations.json`，与 Canvas 布局分离。节点使用稳定 ID；边包含类型、端点、source_block_ids、原书页码、书中明示/模型推断、置信度与审查状态。把 contains、source-order、defines、prerequisite、uses、proves、example-of 区分开；只对需要无环的关系检查环，不把所有知识关系强行变成 DAG。禁用 Canvas 时仍能输出这份语义层。

如以后需要“书籍转 skill”，在已审计的笔记/证据层之上生成一个小型 SKILL 路由入口、术语/主题检索索引和按需 references；无需复制整本书到 SKILL.md，也不必为生成 skill 改写现有原文笔记。

## 建议的流程顺序与验收

```text
冻结来源和能力配置
  → OCR / 原 Markdown 注册
  → 页级质量检查 + source-block 清单
  → TOC 格式化
  → 拆分范围 / lesson-flow / ownership 审核
  → 事务化生成原子笔记
  → 原文递归重建与保真审计
  → 概念与术语身份归并
  → 语义关系抽取与证据审计（需要学习图谱时）
  → Markdown 与元数据生成
  → 内容、链接、YAML 联合审计
  → 可选 Canvas 渲染和样式检查
  → 绑定最终版本的审计与发布
```

现有 TOC 作为目录层级依据、原位子链接、来源不可变、同书参考冻结和不跨书缓存的策略可以保留。TOC 不应承载全部知识关系；视觉样式也不应替代内容证据。

优先修复 R1/R2/R4，防止错误内容被判定完成；随后修复 R3，保证中断可恢复；R5/R6 是范围较小、可独立修复的问题。语义层与 skill 导出作为后续能力建设。

回归验收至少包括：删除必要条件；修改无编号公式和表格内部单元格；重排两段推导；遗漏一页 OCR 输出；报告后改写候选文件；在每个事务写入点中断并恢复；保留 YAML 列表/嵌套字段；general profile 与禁用 Canvas 全流程。另用少量人工核验样章检查概念召回、定义条件完整性、关系证据和代表性检索问题，避免把 passed 和文件数量当成学习效果指标。

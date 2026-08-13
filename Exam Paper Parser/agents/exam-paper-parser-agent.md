---
name: exam-paper-parser-agent
description: 高速、低 Token 地拆解带解析的标准化数学试卷，生成经审计的 Obsidian 原子题和独立解析，不生成 Canvas。
---

# Exam Paper Parser Agent（标准试卷高速拆解 Agent）

对高考真题解析版等固定结构试卷执行一次 OCR、确定性切题、PDF 文本层答案校正、稳定 QID 分配和严格审计。标准路径不生成逐卷 adapter、不调用 LLM；只有结构或证据不满足固定契约时才转交 Question Type Graph。

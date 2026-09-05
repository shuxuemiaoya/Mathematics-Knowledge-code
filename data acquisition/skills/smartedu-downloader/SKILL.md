---
name: smartedu-downloader
description: 国家中小学智慧教育平台 (basic.smartedu.cn) 教材习题、同步练习题库、备课资料与课件的自动化多策略抓取与三层层级归档技能。支持策略模式 (Strategy Pattern)，自动针对备课页面 (prepare) 与习题库页面 (myPaper) 派发不同专用适配器，秒级生成官方矢量试卷、合编高清课件PDF、以及带LaTeX公式的原子题库Markdown。
---

# SmartEdu Material Downloader (智慧教育平台全品类多策略获取技能)

本 Skill 专用于将 **国家中小学智慧教育平台 (`basic.smartedu.cn`)** 上的多种不同业务页面与资源，通过模块化适配器（Adapters）自动进行差异化获取与三层标准化归档。

---

## 1. 核心架构：策略模式 (Strategy Pattern)

```text
dispatcher.py (智能识别当前网页并自动派发)
  ├── PrepareMaterialAdapter (适配 /syncClassroom/prepare)
  │     └── 抓取教材全册课件 PPTX、教学设计 DOCX、整套试卷 PDF
  │
  └── ExerciseBankAdapter (适配 /myPaper 习题库-同步练习)
        └── 抓取原子题目、LaTeX公式、填空/选择标准答案、名师解析与视频，导出 Markdown + 题目高清大图 PDF
```

---

## 2. 差异化资源与处理方法对照表

| 业务页面 | 资源类型 | 处理适配器 (Adapter) | 核心算法与方法 | 输出文件格式 |
| :--- | :--- | :--- | :--- | :--- |
| **教材备课页** (`/syncClassroom/prepare`) | 课件 PPTX、教案 DOCX、整册试卷 PDF | `PrepareMaterialAdapter` | 1. React Fiber 提取 `textBookInfo`<br>2. 官方矢量 PDF 静态直链秒级下载<br>3. 高清幻灯片逐页提取并合成 PDF | `[小节名]_课件.pdf`<br>`[小节名]_教学设计.pdf`<br>`[小节名]（答案解析）.pdf` |
| **习题库同步练习** (`/myPaper`) | 微观原子题目、LaTeX 公式、选择/填空答案、名师解析 | `ExerciseBankAdapter` | 1. 自动展开并遍历左侧目录树<br>2. 自动翻页遍历小节题目<br>3. 提取 QTI 节点 `content`<br>4. 生成带 LaTeX 的结构化 Markdown 与大图合编 PDF | `[小节名]_题库.md`<br>`[小节名]_习题与答案解析.pdf` |

---

## 3. 命令行调用与自动化运行

```bash
# 1. 智能自动识别（自动探查当前 Safari 页面类型并启动对应策略）
python3 skills/smartedu-downloader/scripts/dispatcher.py

# 2. 显式指定同步练习题库适配器
python3 skills/smartedu-downloader/scripts/dispatcher.py --adapter exercise

# 3. 自定义输出目录
python3 skills/smartedu-downloader/scripts/dispatcher.py \
  --output "/Users/oven/Downloads/中小学智慧平台资源/初中/新教材/北师大版/七年级上册/同步练习题库"
```

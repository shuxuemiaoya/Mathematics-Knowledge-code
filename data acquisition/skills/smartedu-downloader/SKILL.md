---
name: smartedu-downloader
description: 国家中小学智慧教育平台 (basic.smartedu.cn) 教材习题、同步试卷与备课资料的自动化嗅探、高速下载与三层层级归档技能。支持从浏览器 React Fiber 状态无损提取整册目录树与资源清单，秒级生成官方 CDN 矢量 PDF 直链，并按「册 / 大章 / 小节目录 / 答案解析.pdf」自动规整。
---

# SmartEdu Material Downloader (智慧教育平台资料获取技能)

本 Skill 专用于将 **国家中小学智慧教育平台 (`basic.smartedu.cn`)** 上的同步课程教学、教材小节习题、试卷解析等优质官方教学资源，全自动无损下载并整理为标准教学资料库。

---

## 1. 核心能力与技术架构

1. **React Fiber 内存无损嗅探**：
   - 绕过前端 DOM 虚拟滚动（Virtual Scroll）限制，直接从页面根 React Fiber 组件中提取整本教材的 `textBookInfo`（包含完整的章节/小节多级树 `chapter` 以及全部 400+ `courseList`）。
2. **官方 CDN 矢量 PDF 直链计算**：
   - 提取 `examinationpapers` 习题资源的 `id` 与 `title`；
   - 结合平台通用 Bank ID 动态构造公共静态 CDN 直链：
     `https://bdcs-file-2.ykt.cbern.com.cn/xedu_cs_paper_bank/export_papers/nwm/answer/{bank_id}/{resource_id}/{title}（答案解析）.pdf`
   - 实现免登录鉴权、百毫秒级高速下载高清矢量 PDF。
3. **教学标准化三层目录归档**：
   - 自动映射章节层级：`[册名] / [大章名称] / [小节编号 小节名称] / [习题标题]（答案解析）.pdf`
   - 严格保证课时（1）、（2）自动归拢至对应小节文件夹内。
4. **断点续传与安全防风控**：
   - 自动检测目标路径，已下载文件秒级跳过；
   - 内置温和的人性化请求间隔（0.6s ~ 1.2s），零风控报警。

---

## 2. 脚本使用说明

### 核心脚本路径
- 主下载器：`skills/smartedu-downloader/scripts/fetch_smartedu.py`
- Safari 桥接驱动：`skills/smartedu-downloader/scripts/safari_helper.py`

### 命令行用法

```bash
# 1. 默认下载（下载到本地 Downloads/中小学智慧平台题，自动识别当前 Safari 选中的教材册名）
python3 skills/smartedu-downloader/scripts/fetch_smartedu.py

# 2. 自定义输出目录与册名
python3 skills/smartedu-downloader/scripts/fetch_smartedu.py \
  --output "/Volumes/Whw/数学妙呀资料/高中/课堂同步/教辅/中小学智慧平台题" \
  --book-prefix "必修一"

# 3. 仅预览下载计划（Dry Run）
python3 skills/smartedu-downloader/scripts/fetch_smartedu.py --dry-run
```

---

## 3. 前置依赖与环境要求

1. **浏览器环境**：macOS Safari 浏览器，需在菜单栏「开发」中勾选 **「允许 JavaScript 控制 Apple 事件」**；
2. **当前页面**：在 Safari 中打开国家中小学智慧教育平台任意教材备课页（如 `https://basic.smartedu.cn/syncClassroom/prepare?...`）；
3. **Python 依赖**：仅需 Python 3.7+ 标准库（`urllib`, `json`, `subprocess`, `argparse`），无需额外安装第三方包。

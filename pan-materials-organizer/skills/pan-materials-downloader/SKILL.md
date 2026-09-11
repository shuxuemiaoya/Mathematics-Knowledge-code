---
name: pan-materials-downloader
description: 初高中教辅高速下载与本地规整技能。突破百度网盘与夸克网盘 Web 界面对大文件的下载拦截，支持多线程分块断点续传与本地 Aria2 RPC 极速拉取，并在本地自动按学段、学科、版本、册次与品牌标准化归档并生成 manifest 清单。
---

# 初高中教辅高速下载与本地规整技能 (Pan Materials Downloader)

本技能专门解决网盘下载初高中大体积教辅 PDF（通常单册 150MB~300MB）时的速度限制与客户端拦截问题，并提供自动化本地标准化归档能力。

---

## 1. 核心流程

### 阶段一：绕过网页端拦截与直链拉取
1. **策略 A（Aria2 RPC / Direct Downloader）**：
   - 提取文件直链地址；
   - 携带 Cookie 会话凭据与 User-Agent，派发给本地 `scripts/direct_downloader.py` 或 `scripts/aria2_dispatcher.py`；
   - 启动多线程分块下载，支持网络中断自动断点续传。
2. **策略 B（官方客户端一键转存下载）**：
   - 在网盘云端先使用 `baidu-pan-organizer` 或 `quark-pan-organizer` 将目标教辅移入单个合集目录；
   - 在官方客户端一键下载该合集目录。

### 阶段二：本地标准化教研归档
1. 运行 `scripts/local_archive_organizer.py`：
   ```bash
   python3 scripts/local_archive_organizer.py --source ~/Downloads/教辅下载包 --target /Users/oven/Documents/教辅标准库 --move
   ```
2. 系统自动识别文件名中的初高中元数据（学段、学科、版本、册次、品牌、年份、主书/答案角色）。
3. 按照标准五层架构建立目录并归档文件。
4. 自动生成 `materials_manifest.json`，计算并记录全量 SHA256 与文件大小。

---

## 2. 衔接后续知识图谱管道
归档后的文件可直接无缝输送给：
- **`question-type-graph`**：对提取的主书与答案 PDF 启动 MinerU OCR、题型切分与答案匹配；
- **`exam-paper-organizer`**：对配套试卷进行降噪与重排版；
- **`book-to-obsidian-wiki-graph`**：抽取教科书或同步精讲为 Obsidian Wiki 知识图谱。

---

## 3. 核心脚本
- 多线程断点续传下载器：`scripts/direct_downloader.py`
- Aria2 任务派发器：`scripts/aria2_dispatcher.py`
- 本地教学体系归档器：`scripts/local_archive_organizer.py`
- 传输与协议参考文档：`references/download_protocols.md`

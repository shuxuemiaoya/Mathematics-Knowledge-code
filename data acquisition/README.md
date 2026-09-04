# Data Acquisition (教学资料与题库获取系统)

专门用于从国家中小学智慧教育平台 (`basic.smartedu.cn`) 及各大教育资源平台，自动化批量获取教材同步习题、备课资料、试卷并进行标准化层级归档的智能工具与 Agent 系统。

---

## 目录结构

```text
data acquisition/
├── plugin.json                              # Antigravity 插件配置
├── AGENTS.md                                # Agent 角色与规范
├── README.md                                # 本说明文档
├── agents/
│   └── data-acquisition-agent.md           # Data Acquisition 专职 Agent 定义
└── skills/
    └── smartedu-downloader/                # 智慧教育平台下载技能
        ├── SKILL.md                         # 技能完整文档
        ├── references/                      # 参考规范
        └── scripts/
            ├── fetch_smartedu.py            # 核心下载与归档执行脚本
            └── safari_helper.py             # Safari 浏览器自动化与智能 Tab 寻址驱动
```

---

## 快速使用

只要在 Safari 浏览器中打开任意教材备课页（如高中数学必修一、必修二等），在终端运行：

```bash
# 默认下载至 ~/Downloads/中小学智慧平台题，自动按三层结构归档
python3 "skills/smartedu-downloader/scripts/fetch_smartedu.py"

# 自定义保存到指定移动硬盘或目录
python3 "skills/smartedu-downloader/scripts/fetch_smartedu.py" \
  --output "/Volumes/Whw/数学妙呀资料/高中/课堂同步/教辅/中小学智慧平台题" \
  --book-prefix "必修一"
```

归档层级结构：
```text
[册名 (如 必修一)]/
└── [大章名称 (如 第一章 集合与常用逻辑用语)]/
    └── [小节名称 (如 1.1 集合的概念)]/
        └── [习题名称]（答案解析）.pdf
```

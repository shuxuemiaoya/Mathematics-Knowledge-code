# Mathematics Knowledge Tools

这是 `Secondary-School-Mathematics-Knowledge-Map` 的自动化工具仓库，已经迁移成 Codex 友好的 Python CLI 项目。

## 目录

- `src/math_knowledge_tools/md_formatter`: 批量清洗 Markdown，包含教材、习题、一数、必刷题等模式。
- `src/math_knowledge_tools/mineru`: 批量调用 MinerU，把 PDF/DOCX 转成知识库 Markdown。
- `skills/`: 面向 Codex 的项目技能草案，可安装到 `$CODEX_HOME/skills`。
- `automation/prompts/`: 未来交给 AI CLI 或 Codex automation 使用的任务提示词模板。
- `tools/`: PowerShell 包装命令，方便本机直接运行。
- `tests/`: 关键格式化和路径安全测试。

## 安装

```powershell
cd C:\mygithub\Mathematics-Knowledge-code
python -m pip install -e .[dev]
```

如果只想临时运行，也可以让脚本自动设置 `PYTHONPATH`，直接用 `tools/*.ps1`。

## 常用命令

格式化知识库，先预览：

```powershell
mk-format --dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\课本" --mode textbook --dry-run
```

确认后写入，并创建 `.bak`：

```powershell
mk-format --dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\课本" --mode textbook --backup
```

批量转 PDF/DOCX：

```powershell
mk-mineru "C:\path\to\source-documents" --format textbook
```

统一入口也可用：

```powershell
math-knowledge format --dir "C:\path\to\markdown" --mode exercise --dry-run
math-knowledge mineru "C:\path\to\source-documents" --format all_exercises
```

## 环境变量

复制 `.env.example` 到私有位置，推荐继续放在 `C:\mygithub\.env`。程序会按顺序读取：

1. `MATH_KNOWLEDGE_ENV` 指定的文件
2. 本仓库 `.env`
3. `C:\mygithub\.env`
4. 当前 shell 环境

不要把真实 `MINERU_API_KEY` 提交到 Git。

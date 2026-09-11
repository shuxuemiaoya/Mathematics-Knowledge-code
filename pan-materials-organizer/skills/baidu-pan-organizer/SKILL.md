---
name: baidu-pan-organizer
description: 百度网盘初高中教辅智能整理技能。支持从分享链接自动解析密码、递归抓取全量教辅目录、智能过滤识别学段与版本（如2026/2027高中必刷题、53）、批量免风控转存至个人网盘、并在个人网盘中重构为标准的教研层级文件夹。
---

# 百度网盘初高中教辅智能整理技能 (Baidu Pan Organizer)

本技能用于全自动化处理百度网盘中庞大且杂乱的初高中教辅分享合集。

---

## 1. 适用场景
- 用户给出百度网盘分享链接（如 `https://pan.baidu.com/s/1tjosXZdCmhOYh253qHQjxw?pwd=601h`）
- 需要从中筛选特定年份（2026、2027）、特定学段（初中、高中）、特定版本（人教A版、苏教版等）或品牌（必刷题、53等）的教辅
- 需要批量转存到个人网盘指定文件夹，并在个人网盘中按标准层级自动创建文件夹、移动分类

---

## 2. 标准作业流程

### 阶段一：提取凭证与进入页面
1. 使用 `chrome-devtools-mcp` 导航至分享页面：
   - 如果提供带 `pwd=xxxx` 的完整链接，直接 `navigate_page` 访问。
   - 若提取码独立提供，自动定位密码输入框并提交。
2. 调用 `evaluate_script` 提取上下文元数据：
   ```javascript
   const yunData = window.yunData;
   const shareid = yunData.shareid;
   const uk = yunData.share_uk;
   const bdstoken = yunData.bdstoken;
   const bdclnd = (document.cookie.match(/BDCLND=([^;]+)/) || [])[1];
   const sekey = decodeURIComponent(bdclnd || '');
   ```

### 阶段二：递归检索与初高中教辅识别
1. 调用 `/share/list` 遍历分享子文件夹，支持深度检索。
2. 调度 `naming_rules.py` 的解析逻辑，对检索出的目录和文件名进行模式匹配：
   - 提取年份：`2026`, `2027`
   - 提取学段与学科：`高中` / `数学`
   - 提取教材版本：`人教A版`, `人教B版`, `北师大版`, `苏教版`
   - 提取教辅品牌：`必刷题`, `5年高考3年模拟`, `高考总复习`
   - 提取文件角色：`主书`, `狂K重点`, `答案解析`, `试卷`

### 阶段三：批量定向转存
1. 构建待转存的 `fs_id` 集合。
2. 分批次向 `/share/transfer` 发起 POST 请求，写入目标目录（如 `/数学妙呀/未分类` 或 `/教辅资源/高中数学`）。
3. 检查每个项的 `errno`：
   - `0`: 成功；
   - `12`: 已存在（跳过）；
   - 其他错误如 `-33`（容量超限）及时报警。

### 阶段四：云端目录重组与归纳
1. 打开并导航至个人网盘目标目录：`https://pan.baidu.com/disk/main#/index?category=all&path=...`
2. 调用 `/api/create` 建立标准化归纳文件夹（如 `2026-2027人教A数学合集`）。
3. 调用 `/api/filemanager?opera=move` 将已转存的各个分散文件夹一键移动到该合集文件夹中。
4. 输出整理清单供用户核对或引导后续下载。

---

## 3. 核心工具与脚本参考
- 脚本生成与 URL 分析：`scripts/baidu_pan_helper.py`
- 命名与教辅元数据识别：`scripts/naming_rules.py`
- 浏览器控制台运行模块：`scripts/baidu_web_client.js`
- API 规范与返回码速查：`references/baidu_pan_api_guide.md`

# 百度网盘 Web 端核心接口与操作实战指南

本指南汇集了从百度网盘 Web 端直接交互、爬取、转存与整理的完整 API 与安全参数，经过实际生产验证。

---

## 1. 基础环境与鉴权凭证

百度网盘 Web 前端核心运行时数据存储在全局变量与 Cookie 中：
- `window.yunData`: 分享页面的核心对象。
  - `yunData.shareid`: 分享 ID（数字）。
  - `yunData.share_uk`: 分享者 UK（数字）。
  - `yunData.bdstoken`: 用户跨站请求 CSRF Token。
  - `yunData.file_list`: 分享根目录的初始文件列表对象。
- `window.locals.userInfo`: 个人网盘页面的核心对象。
  - `userInfo.bdstoken`: 个人网盘操作凭据。
- `Cookie: BDCLND`: 访问带提取码分享链接后，百度写入客户端的高级凭据。
  - 必须进行 URL 解码作为 `sekey` 字段：
    ```javascript
    const bdclnd = (document.cookie.match(/BDCLND=([^;]+)/) || [])[1];
    const sekey = decodeURIComponent(bdclnd || '');
    ```

---

## 2. 分享页接口 (Share APIs)

### 2.1 列出分享目录文件
- **Method**: `GET`
- **URL**: `/share/list`
- **Query Params**:
  - `shareid`: 分享 ID
  - `uk`: 分享者 UK
  - `dir`: 目标目录绝对路径（如 `/sharelink1652647288-.../2027高中必刷题/数学`，必须 URL 编码）
  - `page`: 页码（从 1 开始）
  - `num`: 每页数量（推荐 100~200）
  - `bdstoken`: 当前登录用户的 bdstoken
- **Response**:
  ```json
  {
    "errno": 0,
    "list": [
      {
        "fs_id": 567427103162157,
        "server_filename": "2027高中必刷题",
        "isdir": 1,
        "size": 0,
        "path": "..."
      }
    ]
  }
  ```

### 2.2 转存分享文件至个人网盘
- **Method**: `POST`
- **URL**: `/share/transfer?shareid=${shareid}&from=${from}&bdstoken=${bdstoken}&channel=chunlei&clienttype=0&web=1&app_id=250528`
- **Headers**:
  - `Content-Type`: `application/x-www-form-urlencoded; charset=UTF-8`
  - `X-Requested-With`: `XMLHttpRequest`
- **Body Form-Data**:
  - `fsidlist`: JSON 数组字符串，例如 `"[567427103162157]"`
  - `path`: 目标保存路径，例如 `"/数学妙呀/未分类"`
  - `sekey`: 密码凭证（若存在）
- **常见 Errno 返回码**:
  - `0`: 转存成功
  - `12`: 目标文件夹已存在同名内容或已转存过
  - `-33`: 存储空间不足
  - `-6`: 身份未登录或凭据失效

---

## 3. 个人网盘管理接口 (Personal Pan APIs)

### 3.1 列出个人网盘目录
- **Method**: `GET`
- **URL**: `/api/list?dir=${encodeURIComponent(path)}&num=100&order=name&desc=0&clienttype=0&app_id=250528&web=1`
- **返回字段**: `server_filename`, `fs_id`, `isdir`, `size`, `server_mtime`, `path`

### 3.2 新建文件夹
- **Method**: `POST`
- **URL**: `/api/create?bdstoken=${bdstoken}&channel=chunlei&web=1&app_id=250528&clienttype=0`
- **Body Form-Data**:
  - `path`: 待建文件夹完整路径，如 `"/数学妙呀/未分类/2026-2027人教A数学合集"`
  - `isdir`: `1`
  - `size`: `0`
  - `block_list`: `[]`

### 3.3 移动/重命名文件
- **Method**: `POST`
- **URL**: `/api/filemanager?opera=move&bdstoken=${bdstoken}&channel=chunlei&web=1&app_id=250528&clienttype=0`
- **Body Form-Data**:
  - `filelist`: JSON 字符串数组，格式为：
    ```json
    [
      {
        "path": "/源路径/源文件名",
        "dest": "/目标目录",
        "newname": "新文件名（可选）"
      }
    ]
    ```

---

## 4. 大文件下载限制应对方案
百度网盘 Web 端如果文件超过 50MB~100MB 会阻止浏览器原生下载，弹窗要求安装官方客户端。
解决办法：
1. **配合客户端一键下载**：在云端通过 API 移动归整好后，启动本地客户端对归纳完成的顶级文件夹一键下载。
2. **直链导出 + Aria2**：通过 API 请求 `/api/download` 获取带 sign 的临时 dlink，携带 Cookie（主要是 `BDUSS`）通过 `aria2c -s16 -x16` 极速下载。

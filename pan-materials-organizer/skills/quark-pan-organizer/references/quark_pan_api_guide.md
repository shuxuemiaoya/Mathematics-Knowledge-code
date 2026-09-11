# 夸克网盘 (Quark Pan) Web 端接口与操作实战指南

夸克网盘（`pan.quark.cn` / `drive.quark.cn`）是初高中教辅资源分享的高频平台。

---

## 1. 夸克网盘架构与基础参数

- **Web 域名**: `https://pan.quark.cn`
- **API 基础路径**: `https://drive.quark.cn/1/clouddrive`
- **鉴权 Header**:
  - 请求必须携带浏览器 Cookie，主要是：`_UP_A4A_11_`、`__pus`、`__kp`、`__kps` 等会话 Cookie。
  - 请求头通常需声明：
    ```json
    {
      "Content-Type": "application/json;charset=UTF-8",
      "Accept": "application/json, text/plain, */*"
    }
    ```

---

## 2. 夸克分享页核心 API

### 2.1 获取分享详情 (Share Detail)
- **Method**: `POST` / `GET`
- **URL**: `https://drive.quark.cn/1/clouddrive/share/sharepage/detail`
- **Query / Payload**:
  - `pwd_id`: 分享链接中的唯一标识符（例如 `https://pan.quark.cn/s/abcdef123456` 中 `s/` 后面的字符）
  - `passcode`: 提取密码（如果有）
- **返回**: 包含当前分享的 `stoken`（分享会话 Token）以及根文件列表。

### 2.2 列出分享子目录
- **Method**: `GET`
- **URL**: `https://drive.quark.cn/1/clouddrive/share/sharepage/file?pwd_id=${pwd_id}&pdir_fid=${parent_fid}&stoken=${stoken}`
- **返回**: 目录下包含的所有教辅文件、文件夹及其唯一 `fid`。

### 2.3 转存分享内容到个人夸克网盘
- **Method**: `POST`
- **URL**: `https://drive.quark.cn/1/clouddrive/share/sharepage/save`
- **JSON Payload**:
  ```json
  {
    "pwd_id": "xxxxxx",
    "stoken": "xxxxxx",
    "fid_list": ["fid_1", "fid_2"],
    "to_pdir_fid": "目标个人文件夹FID (根目录为 0)"
  }
  ```
- **返回**: 转存任务 ID `task_id`，或直接提示保存成功。

---

## 3. 个人网盘文件管理 API

### 3.1 查询个人文件夹下的文件列表
- **Method**: `GET`
- **URL**: `https://drive.quark.cn/1/clouddrive/file/sort?pdir_fid=${pdir_fid}&_page=1&_size=100`

### 3.2 创建个人网盘文件夹
- **Method**: `POST`
- **URL**: `https://drive.quark.cn/1/clouddrive/file`
- **JSON Payload**:
  ```json
  {
    "dir_init_lock": false,
    "dir_path": "",
    "file_name": "2027高中数学必刷题合集",
    "pdir_fid": "0"
  }
  ```

### 3.3 批量移动文件
- **Method**: `POST`
- **URL**: `https://drive.quark.cn/1/clouddrive/file/move`
- **JSON Payload**:
  ```json
  {
    "file_id_list": ["fid_1", "fid_2"],
    "to_pdir_fid": "target_folder_fid"
  }
  ```

---

## 4. 浏览器自动化与 DevTools 配合模式
在借助 `chrome-devtools-mcp` 时：
1. 访问夸克网盘分享链接页面，自动填入提取码；
2. 页面加载完成后，利用 DOM 选择器定位复选框（例如 `.file-item` 对应的 checkbox）；
3. 定位顶部的 **“保存到网盘”** 按钮并触发点击；
4. 在弹出的云端目录树中选择或新建分类目录，确认转存。

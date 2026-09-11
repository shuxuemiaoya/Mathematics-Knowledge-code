/**
 * Baidu Pan Web Client Scripts
 * 提供在 Chrome DevTools MCP (evaluate_script) 或控制台中运行的百度网盘自动化脚本模块。
 * 沉淀自实战: https://pan.baidu.com/s/1tjosXZdCmhOYh253qHQjxw?pwd=601h
 */

// 1. 提取当前分享页面基础元数据与密钥
function getShareContext() {
  const yunData = window.yunData || {};
  const shareid = yunData.shareid;
  const uk = yunData.share_uk;
  const bdstoken = yunData.bdstoken;
  const bdclnd = (document.cookie.match(/BDCLND=([^;]+)/) || [])[1];
  const sekey = decodeURIComponent(bdclnd || "");
  const rootDir = (yunData.file_list && yunData.file_list.length > 0) ? yunData.file_list[0].path : "";

  return {
    shareid,
    uk,
    bdstoken,
    sekey,
    rootDir,
    file_list: yunData.file_list || []
  };
}

// 2. 递归/单层查询分享文件夹内容
async function listShareDir(shareid, uk, dirPath, bdstoken = "", page = 1, num = 200) {
  const url = `/share/list?shareid=${shareid}&uk=${uk}&dir=${encodeURIComponent(dirPath)}&page=${page}&num=${num}&bdstoken=${bdstoken}`;
  const res = await fetch(url, {
    headers: { "X-Requested-With": "XMLHttpRequest" }
  }).then(r => r.json());
  return res.list || [];
}

// 3. 递归扫描分享链接中的所有初高中教辅目标文件
async function scanShareRecursively(shareid, uk, dirPath, bdstoken, filterKeywords = ["数学", "必刷题", "53", "人教"]) {
  const allMatches = [];
  
  async function traverse(currentPath) {
    const items = await listShareDir(shareid, uk, currentPath, bdstoken);
    for (const item of items) {
      const match = filterKeywords.some(kw => item.server_filename.includes(kw));
      if (item.isdir === 1) {
        if (match) {
          allMatches.push({
            name: item.server_filename,
            fs_id: item.fs_id,
            isdir: 1,
            path: item.path
          });
        }
        // 深入子文件夹遍历
        await traverse(item.path);
      } else {
        if (match) {
          allMatches.push({
            name: item.server_filename,
            fs_id: item.fs_id,
            size: item.size,
            isdir: 0,
            path: item.path
          });
        }
      }
    }
  }

  await traverse(dirPath);
  return allMatches;
}

// 4. 定向批量转存分享文件到个人网盘
async function transferShareItems(shareid, fromUk, bdstoken, sekey, fsidList, targetPanPath = "/数学妙呀/未分类") {
  const url = `/share/transfer?shareid=${shareid}&from=${fromUk}&bdstoken=${bdstoken}&channel=chunlei&clienttype=0&web=1&app_id=250528`;
  const results = [];

  // 百度单次转存建议分批执行
  for (const fsid of fsidList) {
    const formData = new URLSearchParams();
    formData.append("fsidlist", JSON.stringify([fsid]));
    formData.append("path", targetPanPath);
    if (sekey) {
      formData.append("sekey", sekey);
    }

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: formData.toString()
      }).then(r => r.json());

      results.push({ fs_id: fsid, errno: res.errno, msg: res.show_msg || res.errno, target_file_nums: res.target_file_nums });
    } catch (err) {
      results.push({ fs_id: fsid, error: err.message });
    }
  }

  return results;
}

// 5. 个人网盘：列出指定目录
async function listPersonalDir(dirPath) {
  const res = await fetch(`/api/list?dir=${encodeURIComponent(dirPath)}&num=200&order=name&desc=0&clienttype=0&app_id=250528&web=1`)
    .then(r => r.json());
  return res.list || [];
}

// 6. 个人网盘：创建标准层级文件夹
async function createPersonalDir(targetFolderPath, bdstoken = "") {
  const form = new URLSearchParams();
  form.append("path", targetFolderPath);
  form.append("isdir", "1");
  form.append("size", "0");
  form.append("block_list", "[]");

  const res = await fetch(`/api/create?bdstoken=${bdstoken}&channel=chunlei&web=1&app_id=250528&clienttype=0`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest"
    },
    body: form.toString()
  }).then(r => r.json()).catch(e => ({ error: e.message }));

  return res;
}

// 7. 个人网盘：移动文件/文件夹
async function movePersonalFiles(moveList, bdstoken = "") {
  // moveList 结构: [{ path: "/path/from", dest: "/target/dir", newname: "name" }]
  const form = new URLSearchParams();
  form.append("filelist", JSON.stringify(moveList));

  const res = await fetch(`/api/filemanager?opera=move&bdstoken=${bdstoken}&channel=chunlei&web=1&app_id=250528&clienttype=0`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest"
    },
    body: form.toString()
  }).then(r => r.json()).catch(e => ({ error: e.message }));

  return res;
}

if (typeof window !== "undefined") {
  window.__baidu_pan_tools = {
    getShareContext,
    listShareDir,
    scanShareRecursively,
    transferShareItems,
    listPersonalDir,
    createPersonalDir,
    movePersonalFiles
  };
}

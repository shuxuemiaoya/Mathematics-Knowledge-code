/**
 * Quark Pan Web Client Scripts
 * 提供在 Chrome DevTools MCP (evaluate_script) 或控制台中运行的夸克网盘自动化脚本模块。
 */

// 1. 夸克分享页一键全选初高中教辅并保存
async function quarkSelectAndSaveTargetFiles(filterKeywords = ["数学", "必刷题", "53", "高考", "初中", "高中"]) {
  // 查找页面上的所有文件行
  const items = Array.from(document.querySelectorAll('.file-item, [class*="file-item"], tr'));
  const matchedElements = [];

  for (const el of items) {
    const text = el.innerText || "";
    const isTarget = filterKeywords.some(kw => text.includes(kw));
    if (isTarget) {
      // 查找复选框
      const checkbox = el.querySelector('input[type="checkbox"], [class*="checkbox"]');
      if (checkbox && !checkbox.checked) {
        checkbox.click();
        matchedElements.push(text.split('\n')[0]);
      }
    }
  }

  return {
    matched_count: matchedElements.length,
    matched_names: matchedElements
  };
}

// 2. 触发保存到网盘动作
async function triggerQuarkSave() {
  const saveBtn = Array.from(document.querySelectorAll('button, div, span')).find(
    el => el.innerText.trim() === '保存到网盘' || el.innerText.trim() === '保存到夸克网盘'
  );
  if (saveBtn) {
    saveBtn.click();
    return { success: true, message: "Clicked Save Button" };
  }
  return { success: false, message: "Save Button Not Found" };
}

if (typeof window !== "undefined") {
  window.__quark_pan_tools = {
    quarkSelectAndSaveTargetFiles,
    triggerQuarkSave
  };
}

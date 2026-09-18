# -*- coding: utf-8 -*-
"""
Pan Materials Classifier Engine
实现网盘资料的智能归类决策：
1. 原子文件夹防拆分检测 (is_atomic_folder)
2. 规则/关键词高精度路径匹配 (match_taxonomy_rules)
3. LLM 语义判断 Prompt 生成与推理辅助 (build_llm_classification_prompt)
4. 无法判断时的未分类降级机制 (fallback to /其他/未分类)
"""

import re
from typing import Dict, Any, List, Optional

# 标准学段
STAGES = ["高中", "初中", "小学"]

# 学段科目表
SUBJECTS = {
    "高中": ["数学", "语文", "英语", "物理", "化学", "生物", "思想政治", "历史", "地理"],
    "初中": ["数学", "语文", "英语", "物理", "化学", "生物", "道德与法治", "历史", "地理"],
    "小学": ["数学", "语文", "英语"]
}

# 品牌字典
BRANDS = [
    "53", "必刷题", "万唯", "一本", "天星教育", "优化设计", "一遍过", "步步高",
    "解题觉醒", "金版教程", "高考帮", "一数", "中小学智慧平台题", "天利38套",
    "万向思维", "百题大过关", "小题狂做", "全品", "薛金星", "王后雄", "腾远",
    "蝶变", "浙大优辅", "春雨教育", "勤学早", "经纶学霸", "启东中学作业本",
    "教材全解", "举一反三", "PASS绿卡", "一飞冲天", "王朝霞", "荣德基", "挑战压轴题"
]

def is_atomic_folder(folder_name: str, child_items: Optional[List[Dict[str, Any]]] = None) -> bool:
    """
    判断一个文件夹是否为不可分割的原子教辅/套系单元。
    如：
      - /一数/常规版2026电子版
      - /金版教程/2025-2026《金版教程》导学案-数学-选择性必修第一册-A版
      - /必刷题/2026 八上必刷题 北师大数学
      - 2026版《初中必刷题》数学 RJ 7上 (内部含正文、答案、狂K重点)
    """
    clean_name = folder_name.strip()

    # 1. 明确的单册/版本特征
    single_book_patterns = [
        r"必修\s*[一二三四1234]",
        r"选择性必修\s*[一二三123]",
        r"选必\s*[一二三123]",
        r"[七八九789]\s*[上下]",
        r"[1-6一二三四五六]\s*年级\s*[上下]",
        r"常规版",
        r"导学案",
        r"电子版",
        r"狂[kK]重点",
        r"学案",
        r"微专题",
        r"大一轮",
        r"二轮",
        r"高[一二三]\s*[上下]?",
    ]
    for p in single_book_patterns:
        if re.search(p, clean_name):
            # 如果不含跨多学科的“7科全/8科全/全套全科/全9科”，则属于单本原子文件夹
            if not re.search(r"(\d科全|全科|全套全科|多学科|语数外|数理化|小四门)", clean_name):
                return True

    # 2. 如果提供了子文件清单，检查内部是否为典型的“主书+答案”结构
    if child_items:
        names = [item.get("name", "") for item in child_items]
        # 如果内部都是 PDF/Word，且大多包含 "答案"、"解析"、"狂K重点"、"正文"、"练习册"
        internal_roles = sum(1 for n in names if any(k in n for k in ["答案", "解析", "重点", "主书", "正文", "练习", "试卷", "册"]))
        if len(names) > 0 and internal_roles / len(names) >= 0.5:
            # 且内部没有包含其他学科的大文件夹
            return True

    return False

def match_taxonomy_rules(item_name: str, parent_context: str = "") -> Optional[Dict[str, str]]:
    """
    通过确定性规则与特征匹配目标归档路径。
    返回示例:
    {
      "stage": "高中",
      "subject": "数学",
      "category": "课堂同步",
      "sub_category": "教辅",
      "brand": "必刷题",
      "target_path": "全部文件/高中/数学/课堂同步/教辅/必刷题"
    }
    若无法通过高置信度规则判定，返回 None，交由 LLM 推理。
    """
    full_text = f"{parent_context} {item_name}".strip()

    # 1. 判断学段
    stage = None
    if re.search(r"(高中|高一|高二|高三|高考|选必|选修|必修)", full_text):
        stage = "高中"
    elif re.search(r"(初中|中考|七年级|八年级|九年级|初一|初二|初三|7上|7下|8上|8下|9上|9下)", full_text):
        stage = "初中"
    elif re.search(r"(小学|小升初|[1-6一二三四五六]年级)", full_text):
        stage = "小学"

    if not stage:
        return None

    # 2. 判断学科
    subject = None
    if re.search(r"数学", full_text):
        subject = "数学"
    elif re.search(r"语文|作文|文言文", full_text):
        subject = "语文"
    elif re.search(r"英语|外刊|词汇|单词|英文报", full_text):
        subject = "英语"
    elif re.search(r"物理", full_text):
        subject = "物理"
    elif re.search(r"化学", full_text):
        subject = "化学"
    elif re.search(r"生物", full_text):
        subject = "生物"
    elif re.search(r"政治|思想政治|道法|道德与法治", full_text):
        subject = "思想政治" if stage == "高中" else "道德与法治"
    elif re.search(r"历史", full_text):
        subject = "历史"
    elif re.search(r"地理", full_text):
        subject = "地理"
    elif re.search(r"科学", full_text):
        subject = "物理"  # 科学通常并入初中物理/综合理科

    if not subject:
        return None

    # 3. 判断教辅品牌 (如果在教辅范围内)
    matched_brand = None
    for b in BRANDS:
        # 兼容同义词
        aliases = [b]
        if b == "53": aliases.extend(["五年高考三年模拟", "5·3", "五三", "曲一线"])
        elif b == "必刷题": aliases.extend(["理想树", "必刷卷"])
        elif b == "天星教育": aliases.extend(["教材帮", "金考卷", "试题调研"])
        elif b == "薛金星": aliases.extend(["教材全解"])
        elif b == "一本": aliases.extend(["一本涂书"])
        
        for alias in aliases:
            if alias.lower() in full_text.lower():
                matched_brand = b
                break
        if matched_brand:
            break

    # 4. 判断是属于总复习还是课堂同步
    is_review = bool(re.search(r"(大一轮|二轮|一轮总复习|中考总复习|高考总复习|总复习|高考调研|冲刺卷|信息卷|模拟卷|考前)", full_text))
    primary_module = "总复习" if is_review else "课堂同步"

    # 5. 官方电子教材判断
    if re.search(r"(电子课本|课本|教材)", full_text) and not matched_brand and not is_review:
        target_path = f"全部文件/{stage}/{subject}/课本"
        return {"stage": stage, "subject": subject, "target_path": target_path}

    # 6. 模块内细分分类（教辅 / 试卷 / 专题 / 讲义 / 其他）
    if matched_brand:
        target_path = f"全部文件/{stage}/{subject}/{primary_module}/教辅/{matched_brand}"
        return {"stage": stage, "subject": subject, "brand": matched_brand, "target_path": target_path}

    if re.search(r"(期中|期末|模拟卷|特快专递|真题|联考|测试卷|试卷|金考卷45套|单元卷)", full_text):
        target_path = f"全部文件/{stage}/{subject}/{primary_module}/试卷"
        return {"stage": stage, "subject": subject, "target_path": target_path}

    if re.search(r"(讲义|暑假班|寒假班|网课配套|名师|备课|教案)", full_text):
        target_path = f"全部文件/{stage}/{subject}/{primary_module}/讲义"
        return {"stage": stage, "subject": subject, "target_path": target_path}

    if re.search(r"(专题|破题|模型|大招|题型总结|专项|微专题)", full_text):
        target_path = f"全部文件/{stage}/{subject}/{primary_module}/专题"
        return {"stage": stage, "subject": subject, "target_path": target_path}

    # 学科特定拓展放入 学科/其他/
    if re.search(r"(强基|联赛|奥林匹克|奥数|自主招生|公式|二级结论|速记|思维方法|论文)", full_text):
        target_path = f"全部文件/{stage}/{subject}/其他"
        return {"stage": stage, "subject": subject, "target_path": target_path}

    return None

def build_llm_classification_prompt(item_name: str, parent_folder: str, sample_children: List[str]) -> str:
    """
    当规则无法明确判断时，生成提供给 LLM 进行逻辑推理的 Prompt 模板。
    """
    prompt = f"""【网盘教育资料分类判定任务】
请根据以下待分类文件夹/文件的信息，判断其应放置的标准目录路径。

待分类对象名称: {item_name}
当前所在父目录: {parent_folder}
内部包含的部分文件/子项示例: {sample_children[:5]}

分类标准结构说明：
1. 第一层仅允许：高中、初中、小学、其他。
2. 第二层为学科：数学、语文、英语、物理、化学、生物、思想政治（初中为道德与法治）、历史、地理。
3. 第三层学科标准四大必备目录：
   - 课堂同步：学期同步练习与教学
   - 课本：官方电子教材全套
   - 总复习：中考/高考大复习
   - 其他：学科专属拓展（奥数竞赛、思维方法、公式总结等）
4. 第四层标准五大目录（在「课堂同步」和「总复习」内部均包含且仅包含这5类）：
   - 教辅/<品牌名>：主流品牌教辅（如53、必刷题、万唯、天星教育、优化设计、一遍过、金版教程等，必须为具体品牌名）
   - 试卷：单元卷、月考卷、期中期末卷、模考真题卷
   - 专题：题型突破、单项攻坚、大招专题
   - 讲义：名师名校讲义、备课教案
   - 其他：其他同步或复习相关材料
5. 防拆分原则：如果该文件夹是某本具体书或成套材料（如：金版教程导学案必修一、必刷题八上北师大版），请作为一个整体给出其所属的教辅品牌目录，严禁拆散。
6. 兜底保护：如果你根据名称和采样文件仍无法断定其属于哪个学段或学科，或者判断其为非学科杂项，必须输出：全部文件/其他/未分类。

请仅输出最终的规范标准路径（以 "全部文件/..." 开头），不要包含多余的废话。
"""
    return prompt

def get_fallback_path() -> str:
    """分类失败或无法断定时，安全降级的收容目录"""
    return "全部文件/其他/未分类"

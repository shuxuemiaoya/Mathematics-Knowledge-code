# -*- coding: utf-8 -*-
import re
from typing import Dict, Any

STAGE_PATTERNS = [
    (r"(高中|高一|高二|高三|高考|选修|必修|选择性必修)", "高中"),
    (r"(初中|中考|七年级|八年级|九年级|初一|初二|初三)", "初中"),
    (r"(小学|小升初|一年级|二年级|三年级|四年级|五年级|六年级)", "小学"),
]

SUBJECT_PATTERNS = [
    (r"数学", "数学"),
    (r"物理", "物理"),
    (r"化学", "化学"),
    (r"生物", "生物"),
    (r"语文", "语文"),
    (r"英语", "英语"),
    (r"历史", "历史"),
    (r"地理", "地理"),
    (r"政治|思想政治|道法|道德与法治", "政治"),
]

EDITION_PATTERNS = [
    (r"人教[A|a]版|RJ-?A|人教A", "人教A版"),
    (r"人教[B|b]版|RJ-?B|人教B", "人教B版"),
    (r"人教版|RJ", "人教版"),
    (r"北师大版|北师版|BSD", "北师大版"),
    (r"苏教版|SJ", "苏教版"),
    (r"湘教版|XJ", "湘教版"),
    (r"沪教版|HJ", "沪教版"),
    (r"华师大版|HS", "华师大版"),
    (r"鲁科版", "鲁科版"),
    (r"新高考版|全国通用|统编版", "新高考通用版"),
]

VOLUME_PATTERNS = [
    (r"必修[第一册|第1册|一|1]", "必修第一册"),
    (r"必修[第二册|第2册|二|2]", "必修第二册"),
    (r"必修[第三册|第3册|三|3]", "必修第三册"),
    (r"选择性必修[第一册|第1册|一|1]|选必[一|1]|选修[第一册|第1册|一|1]", "选择性必修第一册"),
    (r"选择性必修[第二册|第2册|二|2]|选必[二|2]|选修[第二册|第2册|二|2]", "选择性必修第二册"),
    (r"选择性必修[第三册|第3册|三|3]|选必[三|3]|选修[第三册|第3册|三|3]", "选择性必修第三册"),
    (r"七年级[上|第一学期]", "七年级上册"),
    (r"七年级[下|第二学期]", "七年级下册"),
    (r"八年级[上|第一学期]", "八年级上册"),
    (r"八年级[下|第二学期]", "八年级下册"),
    (r"九年级[上|第一学期]", "九年级上册"),
    (r"九年级[下|第二学期]", "九年级下册"),
    (r"高考总复习|一轮总复习|总复习", "高考总复习"),
    (r"中考总复习|中考一轮", "中考总复习"),
]

BRAND_PATTERNS = [
    (r"必刷题|理想树", "必刷题"),
    (r"5年高考3年模拟|五年高考三年模拟|53|曲一线", "5年高考3年模拟"),
    (r"金考卷", "金考卷"),
    (r"全优卷", "全优卷"),
    (r"重难点手册", "重难点手册"),
    (r"一遍过", "一遍过"),
    (r"高考必刷题", "高考必刷题"),
    (r"同步精讲|培优讲义", "同步精讲培优"),
]

ROLE_PATTERNS = [
    (r"答案|解析|全解全析|快对答案|答案册", "答案解析"),
    (r"狂[K|k]重点|重难点|重点册|微专题", "重点辅导册"),
    (r"主书|学生用书|练习册|精讲册|精练册|试卷|正文", "主书"),
    (r"课件|PPT|ppt|配套资源|讲义word|word版", "配套资源与课件"),
]

def parse_material_name(filename: str) -> Dict[str, Any]:
    clean_name = filename.strip()
    
    year_match = re.search(r"(202[4-9]|2[4-9])(?=年|版|届|《|高中|初中|必刷|53|)", clean_name)
    year = None
    if year_match:
        y_str = year_match.group(1)
        year = "20" + y_str if len(y_str) == 2 else y_str
    
    stage = "高中"
    for pat, val in STAGE_PATTERNS:
        if re.search(pat, clean_name, re.IGNORECASE):
            stage = val
            break
            
    subject = "数学"
    for pat, val in SUBJECT_PATTERNS:
        if re.search(pat, clean_name):
            subject = val
            break
            
    edition = "未知版本"
    for pat, val in EDITION_PATTERNS:
        if re.search(pat, clean_name, re.IGNORECASE):
            edition = val
            break
            
    volume = "未知册次"
    for pat, val in VOLUME_PATTERNS:
        if re.search(pat, clean_name):
            volume = val
            break
            
    brand = "通用教辅"
    for pat, val in BRAND_PATTERNS:
        if re.search(pat, clean_name):
            brand = val
            break
            
    role = "主书"
    for pat, val in ROLE_PATTERNS:
        if re.search(pat, clean_name):
            role = val
            break

    y_prefix = year if year else "通用"
    std_dir_name = y_prefix + "_" + brand + "_" + edition + "_" + volume
    category_path = stage + "/" + subject + "/" + edition + "/" + volume + "/" + std_dir_name

    return {
        "raw_name": clean_name,
        "year": year,
        "stage": stage,
        "subject": subject,
        "edition": edition,
        "volume": volume,
        "brand": brand,
        "role": role,
        "standard_folder": std_dir_name,
        "standard_relpath": category_path + "/" + role + "_" + clean_name
    }

if __name__ == "__main__":
    test_cases = [
        "2027《理想树•必刷题》（必修第一册）（数学）（人教A版）",
        "2027《理想树•必刷题》（数学）（选择性必修第一册）（人教A版）答案.pdf",
        "2026春 高中必刷题【人教A版 数学选修二】狂K重点.pdf",
        "2027《曲一线•5年高考3年模拟高考总复习》（A版）（高考）（数学）（新高考版）",
        "YZ-133-高中数学同步精讲B版高一二三基础+培优讲义+专题练习word版电子"
    ]
    for tc in test_cases:
        res = parse_material_name(tc)
        print(tc)
        print(" -> Folder:", res["standard_folder"])
        print(" -> Path:", res["standard_relpath"])

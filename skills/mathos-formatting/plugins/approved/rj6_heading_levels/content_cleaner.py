PLUGIN_ID = "rj6_heading_levels"
PLUGIN_VERSION = "1.0.0"


def analyze(markdown: str) -> dict:
    heading_count = 0
    changed_count = 0
    for line in markdown.splitlines():
        if not line.startswith("# "):
            continue
        heading_count += 1
        text = line[2:].strip()
        level = _heading_level(text)
        if level != 1:
            changed_count += 1
    return {
        "summary": [
            f"normalized heading hierarchy for {heading_count} headings",
            f"demoted {changed_count} section or exercise headings below h1",
        ],
        "warnings": [
            "review numeric headings without punctuation; they are kept as h1 lesson titles"
        ],
    }


def clean(markdown: str) -> str:
    output = []
    for line in markdown.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        if body.startswith("# "):
            text = body[2:].strip()
            output.append("#" * _heading_level(text) + " " + text + ending)
        else:
            output.append(line)
    return "".join(output)


def _heading_level(text: str) -> int:
    compact = text.strip()
    if _is_top_level(compact):
        return 1
    if _is_second_level(compact):
        return 2
    if _is_third_level(compact):
        return 3
    if _is_exercise_heading(compact):
        return 4
    return 1


def _is_top_level(text: str) -> bool:
    if "单元测评卷" in text or text.startswith("期中综合测评卷") or text.startswith("期末综合测评卷"):
        return True
    prefixes = [
        "重难易错专练",
        "整理和复习",
        "练习课",
        "反馈区",
    ]
    if any(text.startswith(prefix) for prefix in prefixes):
        return True
    if _starts_with_arabic_number(text) and not _looks_like_exercise_text(text):
        return True
    return False


def _is_second_level(text: str) -> bool:
    if text.startswith("过"):
        return True
    if _starts_with_chinese_section_number(text):
        return True
    if "解决问题" in text and ("共" in text or "每题" in text):
        return True
    return False


def _is_third_level(text: str) -> bool:
    prefixes = [
        "阶段滚动综合练",
        "单元滚动综合练",
        "重点难点滚动练",
        "易错易混考点练",
        "思维拓展培优练",
        "主题活动",
        "阅读记录",
    ]
    return any(text.startswith(prefix) for prefix in prefixes)


def _is_exercise_heading(text: str) -> bool:
    prefixes = [
        "重难点 ",
        "易错点 ",
    ]
    if any(text.startswith(prefix) for prefix in prefixes):
        return True
    if _starts_with_arabic_number(text) and _looks_like_exercise_text(text):
        return True
    return False


def _starts_with_arabic_number(text: str) -> bool:
    if not text:
        return False
    return "0" <= text[0] <= "9"


def _starts_with_chinese_section_number(text: str) -> bool:
    if len(text) < 2:
        return False
    return text[0] in "一二三四五六七八九十" and text[1] == "、"


def _looks_like_exercise_text(text: str) -> bool:
    if "。" in text or "?" in text or "？" in text:
        return True
    if len(text) > 1 and text[1] in "（(":
        return True
    if len(text) > 2 and text[2] in "（(":
        return True
    exercise_words = [
        "填一填",
        "选一选",
        "计算",
        "解决问题",
        "看图",
        "根据",
        "先看",
        "找规律",
        "完成",
        "列式",
    ]
    return any(word in text for word in exercise_words)

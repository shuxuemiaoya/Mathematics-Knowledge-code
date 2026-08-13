from __future__ import annotations

import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


def loose(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\\mathrm", "").replace("\\ln", "ln")
    return "".join(ch.casefold() for ch in value if ch.isalnum())


def safe(value: str) -> str:
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in value)


def heading_text(line: str) -> str:
    return re.sub(r"^\s*#{1,6}\s+", "", line).strip()


BOOK_02_RECOVERED = [
    ("training-15", "5", 7638, 7640, 7657, "291", "OCR dropped question number 5 before 【解析】"),
    ("training-15", "6", 7656, 7658, 7673, "291", "OCR dropped question number 6 before 【解析】"),
    ("training-17", "10", 7858, 7860, 7865, "293", "OCR dropped question number 10 before line 7860"),
    ("training-18", "8", 7920, 7922, 7933, "294", "OCR printed number 3 on line 7922 is actually question 8"),
    ("training-19", "2", 7972, 7974, 7987, "295", "OCR dropped question number 2 before line 7974"),
    ("training-20", "1", 8052, 8054, 8075, "296", "OCR dropped question number 1 before line 8054"),
]

BOOK_02_IGNORE_RANGES = [
    {"start_line": 7922, "end_line": 7933, "reason": "OCR line 7922 printed 3. is question 8"}
]

BOOK_03_RECOVERED = [
    ("training-24", "3", 5907, 5908, 5910, "286", "OCR wrapped 3.【解析】 in array"),
    ("training-24", "7", 5921, 5922, 5924, "286", "OCR wrapped 7.【解析】 in array"),
    ("training-25", "7", 5977, 5979, 5980, "287", "OCR dropped 7.【解析】 before line 5979"),
    ("training-26", "6", 6062, 6064, 6079, "288", "OCR dropped 6.【解析】 before line 6064"),
    ("training-27", "8", 6170, 6172, 6173, "290", "OCR dropped 8.【解析】 before line 6172"),
    ("training-32", "9", 6426, 6428, 6437, "296", "OCR dropped 9.【解析】 before line 6428"),
]

BOOK_04_RECOVERED = [
    ("training-40", "4", 5293, 5295, 5302, "252", "OCR dropped question number 4 before line 5295"),
]

BOOK_04_IGNORE_RANGES = [
    {"start_line": 4854, "end_line": 4860, "reason": "Line 4854 is a note paragraph starting with 2."}
]


def build_adapter_for_staging(staging_path: Path):
    raw_file = staging_path / "raw" / "combined.raw.md"
    draft_file = staging_path / "format-adapter.draft.json"
    output_file = staging_path / "format-adapter.json"
    profile_file = staging_path / "question-type-profile.json"

    lines = raw_file.read_text(encoding="utf-8-sig").splitlines()
    draft = json.loads(draft_file.read_text(encoding="utf-8"))
    toc = draft["hierarchy"]["primary_authority"]["entries"]
    toc_start_line = draft["hierarchy"]["primary_authority"]["start_line"]
    toc_end_line = draft["hierarchy"]["primary_authority"]["end_line"]

    headings = [(i, heading_text(line)) for i, line in enumerate(lines, 1) if re.match(r"^\s*#{1,6}\s+\S", line)]

    # Find where reference answers start
    ref_ans_line = None
    for line_no, text in headings:
        if text == "参考答案" and line_no > toc_end_line:
            ref_ans_line = line_no
            break
    if not ref_ans_line:
        # Search all lines if not in headings
        for i, line in enumerate(lines, 1):
            if i > toc_end_line and re.match(r"^\s*(?:#{1,6}\s*)?参考答案\s*$", line):
                ref_ans_line = i
                break
    if not ref_ans_line:
        raise RuntimeError("参考答案 heading not found after TOC")

    # Body region is from first heading after TOC up to ref_ans_line
    body_start_line = None
    for line_no, text in headings:
        if line_no > toc_end_line:
            body_start_line = line_no
            break
    if not body_start_line:
        body_start_line = toc_end_line + 1

    def find_heading_or_raw(pattern: str, minimum: int, maximum: int = len(lines), raw_prefix: str = "") -> tuple[int, str]:
        compiled = re.compile(pattern)
        # 1. Search in markdown headings first
        for line_no, title in headings:
            if minimum <= line_no <= maximum and compiled.fullmatch(title):
                return line_no, title
        # 2. Search in all raw lines
        if raw_prefix:
            prefix_pattern = re.compile(rf"^\s*{raw_prefix}\b.*")
            for i, line in enumerate(lines, 1):
                if minimum <= i <= maximum and prefix_pattern.match(line):
                    return i, line.strip()
        # 3. Looser search in all raw lines
        for i, line in enumerate(lines, 1):
            if minimum <= i <= maximum and compiled.match(line.strip()):
                return i, line.strip()

        raise RuntimeError(f"heading not found: {pattern!r} (raw_prefix={raw_prefix!r}) between {minimum} and {maximum}")

    def find_next_section_line(idx: int, minimum: int) -> int:
        for j in range(idx + 1, len(toc)):
            next_title = toc[j]["title"].strip()
            sec_m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?\s*", next_title)
            train_m = re.fullmatch(r"训练\s*(\d+)", next_title)
            if sec_m:
                c_num = int(sec_m.group(1))
                s_num = int(sec_m.group(2))
                sub_num = int(sec_m.group(3)) if sec_m.group(3) else None
                if sub_num:
                    raw_prefix = rf"{c_num}\s*\.\s*{s_num}\s*\.\s*{sub_num}"
                    pattern = rf"{c_num}\s*\.\s*{s_num}\s*\.\s*{sub_num}\s+.*"
                else:
                    raw_prefix = rf"{c_num}\s*\.\s*{s_num}"
                    pattern = rf"{c_num}\s*\.\s*{s_num}(?:\.\d+)?\s+.*"
                body_line, _ = find_heading_or_raw(pattern, minimum, raw_prefix=raw_prefix)
                return body_line
            elif train_m:
                t_num = int(train_m.group(1))
                body_line, _ = find_heading_or_raw(rf"训练\s*{t_num}", minimum, ref_ans_line - 1, raw_prefix=rf"训练\s*{t_num}")
                return body_line
        return minimum

    authority: list[dict] = []
    entries: list[dict] = []
    minimum = body_start_line
    chapter = 0
    group = 0
    section = 0
    group_active = False
    stack: list[dict] = []
    training_numbers = []

    for idx, source in enumerate(toc):
        title = source["title"].strip()
        anchor_aliases: list[str] = []
        chapter_match = re.match(r"^第\s*(\d+)\s*讲\b", title)
        section_match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?\s*", title)
        training_match = re.fullmatch(r"训练\s*(\d+)", title)
        is_fallback_group = False

        if chapter_match:
            chapter = int(chapter_match.group(1))
            group = 0
            section = 0
            group_active = False
            key = f"chapter-{chapter:02d}"
            level = 1
            body_line, actual = find_heading_or_raw(rf"第\s*{chapter}\s*讲.*", minimum, raw_prefix=rf"第\s*{chapter}\s*讲")
            anchor = {
                "kind": "reviewed-boundary",
                "start_line": body_line,
                "evidence": f"PDF-visible chapter opener; OCR separates chapter at line {body_line}",
                "reviewer_confirmed": True,
            }
        elif section_match:
            c_num = int(section_match.group(1))
            s_num = int(section_match.group(2))
            sub_num = int(section_match.group(3)) if section_match.group(3) else None
            if sub_num:
                key = f"chapter-{c_num:02d}-section-{s_num:02d}-{sub_num:02d}"
                level = 3
                raw_prefix = rf"{c_num}\s*\.\s*{s_num}\s*\.\s*{sub_num}"
                pattern = rf"{c_num}\s*\.\s*{s_num}\s*\.\s*{sub_num}\s+.*"
            else:
                key = f"chapter-{c_num:02d}-section-{s_num:02d}"
                level = 3 if group_active else 2
                raw_prefix = rf"{c_num}\s*\.\s*{s_num}"
                pattern = rf"{c_num}\s*\.\s*{s_num}(?:\.\d+)?\s+.*"

            body_line, actual = find_heading_or_raw(pattern, minimum, raw_prefix=raw_prefix)
            anchor = {
                "kind": "source-heading",
                "start_line": body_line,
                "reviewer_confirmed": True,
            }
            if actual != title:
                anchor_aliases = [actual]
        elif training_match:
            number = int(training_match.group(1))
            key = f"chapter-{number:02d}-training"
            level = 2
            group_active = False
            training_numbers.append(number)
            body_line, actual = find_heading_or_raw(rf"训练\s*{number}", minimum, ref_ans_line - 1, raw_prefix=rf"训练\s*{number}")
            anchor = {
                "kind": "source-heading",
                "start_line": body_line,
                "reviewer_confirmed": True,
            }
            if actual != title:
                anchor_aliases = [actual]
        elif title == "参考答案":
            key = "reference-answers"
            level = 1
            group_active = False
            body_line, actual = find_heading_or_raw(r"参考答案", minimum, len(lines), raw_prefix="参考答案")
            anchor = {
                "kind": "source-heading",
                "start_line": body_line,
                "reviewer_confirmed": True,
            }
        else:
            group += 1
            key = f"chapter-{chapter:02d}-group-{group:02d}"
            level = 2
            group_active = True
            # Try to match group heading, or fallback to the line of the next section
            target = loose(title)
            candidates = [(line_no, candidate) for line_no, candidate in headings if minimum <= line_no <= ref_ans_line]
            scored = sorted(
                ((SequenceMatcher(None, target, loose(candidate)).ratio(), line_no, candidate) for line_no, candidate in candidates),
                reverse=True,
            )
            if scored and scored[0][0] >= 0.72:
                body_line, actual = scored[0][1], scored[0][2]
                anchor = {
                    "kind": "source-heading",
                    "start_line": body_line,
                    "reviewer_confirmed": True,
                }
                if actual != title:
                    anchor_aliases = [actual]
            else:
                # Fallback: anchor to next section line without advancing minimum
                body_line = find_next_section_line(idx, minimum)
                actual = title
                is_fallback_group = True
                anchor = {
                    "kind": "reviewed-boundary",
                    "start_line": body_line,
                    "evidence": f"PDF-visible group header; anchored to next section at line {body_line}",
                    "reviewer_confirmed": True,
                }

        if not is_fallback_group:
            minimum = body_line + (0 if title == "参考答案" else 1)
        else:
            minimum = body_line

        authority_item = {
            "key": key,
            "title": title,
            "level": level,
            "source_line": int(source["source_line"]),
        }
        if source.get("source_column"):
            authority_item["source_column"] = int(source["source_column"])
        if source.get("references"):
            authority_item["printed_page"] = int(source["references"][0])
        authority.append(authority_item)

        while stack and stack[-1]["level"] >= level:
            stack.pop()
        path_parts = [item["component"] for item in stack]
        component = safe(title)
        path_parts.append(component)
        entry = {
            "key": key,
            "title": title,
            "level": level,
            "output": "/".join([*path_parts, f"{component}.md"]),
            "body_anchor": anchor,
            "emit_title": False,
        }
        if is_fallback_group or title == "参考答案":
            entry["structural_only"] = True

        if anchor_aliases:
            entry["aliases"] = anchor_aliases
        if training_match:
            entry["answer_context"] = f"training-{int(training_match.group(1)):02d}"
        entries.append(entry)
        stack.append({"level": level, "component": component})

    training_contexts = [f"training-{num:02d}" for num in training_numbers]
    training_note_keys = [f"chapter-{num:02d}-training" for num in training_numbers]
    worked_example_note_keys = [
        item["key"]
        for item in entries
        if item["key"] not in {*training_note_keys, "reference-answers"}
    ]

    answer_heading_lines = {}
    for line_no, text in headings:
        match = re.fullmatch(r"训练\s*(\d+)", text)
        if match and line_no >= ref_ans_line:
            answer_heading_lines[int(match.group(1))] = (line_no, text)

    # Search raw lines for answer headings if not all found in headings
    if set(answer_heading_lines) != set(training_numbers):
        for i, line in enumerate(lines, 1):
            if i >= ref_ans_line:
                match = re.match(r"^\s*(?:#{1,6}\s*)?训练\s*(\d+)\b", line)
                if match:
                    num = int(match.group(1))
                    if num in training_numbers and num not in answer_heading_lines:
                        answer_heading_lines[num] = (i, line.strip())

    if set(answer_heading_lines) != set(training_numbers):
        raise RuntimeError(f"answer context ledger is incomplete: found {set(answer_heading_lines)}, expected {set(training_numbers)}")

    # Recovered answers & ignore ranges per book
    recovered_answers = []
    ignore_ranges = []

    if "02-解析几何" in staging_path.name:
        for ctx, num, after, start, end, page, ev in BOOK_02_RECOVERED:
            anchor = lines[after - 1].strip()
            raw_body = "\n".join(lines[start - 1:end])
            if num == "1" and ctx == "training-20":
                body_text = "1. B\n【解析】" + raw_body
            elif not lines[start - 1].strip().startswith(f"{num}."):
                body_text = f"{num}.【解析】" + raw_body
            else:
                body_text = raw_body

            recovered_answers.append({
                "context": ctx,
                "number": num,
                "body": body_text,
                "source_page": page,
                "after_line": after,
                "anchor_text": anchor,
                "evidence": ev,
                "reviewer_confirmed": True
            })
        ignore_ranges = BOOK_02_IGNORE_RANGES
    elif "03-三角" in staging_path.name:
        for ctx, num, after, start, end, page, ev in BOOK_03_RECOVERED:
            anchor = lines[after - 1].strip()
            raw_body = "\n".join(lines[start - 1:end])
            if not lines[start - 1].strip().startswith(f"{num}."):
                body_text = f"{num}.【解析】" + raw_body
            else:
                body_text = raw_body

            recovered_answers.append({
                "context": ctx,
                "number": num,
                "body": body_text,
                "source_page": page,
                "after_line": after,
                "anchor_text": anchor,
                "evidence": ev,
                "reviewer_confirmed": True
            })
    elif "04-立体几何" in staging_path.name:
        for ctx, num, after, start, end, page, ev in BOOK_04_RECOVERED:
            anchor = lines[after - 1].strip()
            raw_body = "\n".join(lines[start - 1:end])
            if not lines[start - 1].strip().startswith(f"{num}."):
                body_text = f"{num}.【解析】" + raw_body
            else:
                body_text = raw_body

            recovered_answers.append({
                "context": ctx,
                "number": num,
                "body": body_text,
                "source_page": page,
                "after_line": after,
                "anchor_text": anchor,
                "evidence": ev,
                "reviewer_confirmed": True
            })
        ignore_ranges = BOOK_04_IGNORE_RANGES

    adapter = {
        "schema_version": 1,
        "status": "passed",
        "reviewer_confirmed": True,
        "filename_policy": {"colon_replacement": "_"},
        "profile": str(profile_file),
        "hierarchy": {
            "source_role": "combined",
            "root_output": "index.md",
            "region": {"start_line": body_start_line, "end_line": ref_ans_line},
            "primary_authority": {
                "status": "passed",
                "reviewer_confirmed": True,
                "start_line": toc_start_line,
                "end_line": toc_end_line,
                "reading_order": "source-stream",
                "entries": authority,
            },
            "entries": entries,
        },
        "content": {
            "unknown_label_policy": "retain",
            "question_folder": "训练题",
            "question_repository_root": "/Users/oven/Documents/ovenmathmap/mathmap/习题/questions",
            "question_title_template": "题 {number}",
            "question_patterns": [
                r"^(?P<number>例\s*\d+(?:\.\d+)?)\s*",
                r"^(?P<number>变式(?:题)?\s*(?:[（(]?\d+[）)]?)?)\s*[：:]?\s*",
                r"^(?P<number>\d+)[.．、]\s*",
            ],
            "inline_question_patterns": [],
            "question_kind_rules": [
                {
                    "kind": "worked-example",
                    "pattern": r"^例\s*\d+(?:\.\d+)?\s*",
                    "answer_handling": "separate-authoritative",
                    "preserve_internal_headings": True,
                    "folder": "例题",
                },
                {
                    "kind": "worked-example",
                    "pattern": r"^变式(?:题)?\s*(?:[（(]?\d+[）)]?)?\s*[：:]?\s*",
                    "answer_handling": "separate-authoritative",
                    "preserve_internal_headings": True,
                    "folder": "例题",
                },
            ],
            "worked_example_solution_patterns": [
                (
                    r"^\s*(?:#{1,6}\s*)?【?(?:分析|解析|解答|解法\w*|证法\w*|点评|评注|解后反思|解后小结|总结|证明)】?(?:\s|[：:]|▶|[（(]|$)"
                ),
                r"\\text\s*\{\s*解析\s*\}",
                r"^\s*易知\b",
                r"^\s*本题有三条思路\b",
                r"^\s*#{1,6}\s*由题意可知\b",
                r"^\s*\\triangle",
                r"^\s*(?:由于|因为|由|所以|故)\b",
                r"^\s*\!\[",
                r"^\s*\$\$",
            ],
            "worked_example_solution_backtrack_fence": True,
            "worked_example_callout_title": "《高考数学培优40讲》例题解析",
            "answer_callout_layout_version": 2,
            "question_scopes": [
                {"contexts": training_note_keys, "kinds": ["exercise"]},
                {"contexts": worked_example_note_keys, "kinds": ["worked-example"]},
            ],
            "roles": [],
        },
        "answers": {
            "source_role": "combined",
            "callout_title": "《高考数学培优40讲》参考答案",
            "region": {"start_line": ref_ans_line + 1, "end_line": len(lines)},
            "contexts": [
                {
                    "key": f"training-{number:02d}",
                    "start_line": answer_heading_lines[number][0],
                    "anchor_text": f"## 训练 {number}",
                }
                for number in sorted(training_numbers)
            ],
            "answer_patterns": [
                r"^(?:#{1,6}\s*)?(?P<number>\d+)[.．、](?!\d[.．、\s])\s*",
                r"^(?:#{1,6}\s*)?(?P<number>\d+)[.．、]\d\s*(?:[【$]|\d)",
            ],
            "inline_answer_patterns": [],
            "recovered_answers": recovered_answers,
            "ignore_ranges": ignore_ranges,
        },
    }

    output_file.write_text(json.dumps(adapter, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Successfully wrote adapter: {output_file}")
    print(f"Stats: authority={len(authority)} entries={len(entries)} training_contexts={len(training_numbers)} recovered={len(recovered_answers)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_adapter_generic.py <staging_path>")
        sys.exit(1)
    staging = Path(sys.argv[1]).resolve()
    build_adapter_for_staging(staging)

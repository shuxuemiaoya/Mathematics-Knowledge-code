#!/usr/bin/env python3
"""Reformat an exam while keeping question and answer sections separate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


ANSWER_HEADING_RE = re.compile(
    r"^\s*#{0,6}\s*.*(?:参考答案|答案及解析|答案与解析|试题答案|answer\s*key|solutions?).*\s*$",
    re.IGNORECASE,
)
H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
H2_RE = re.compile(r"^\s*##\s+(.+?)\s*$")
QUESTION_RE = re.compile(r"^\s*(\d{1,3})[\.．、]\s*(.*)$")
OPTION_RE = re.compile(r"(?<![A-Za-z])([A-D])[\.．]\s*")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
SOLUTION_SUBPART_RE = re.compile(
    r"(?<!\n)([（(]\d{1,2}[）)])(?=(?:解|证明|因为|由|若|设|当|根据|按照|求))"
)
LOGICAL_CUES = r"(?:两边平方得|代入并整理|由此|因为|所以|又因|因此|易知|易得|解得|可得|从而|连接|根据|按照|此时|由|又|则|故|即|当|设|记|因|得)"
SCORE_TRANSITION_RE = re.compile(r"((?:…{2,}|\.{4,})\s*\d+\s*分)\s*(?=\S)")
PUNCTUATION_TRANSITION_RE = re.compile(rf"([，,。．；;：:])\s*(?={LOGICAL_CUES})")
MATH_TRANSITION_RE = re.compile(rf"(\$)\s+(?={LOGICAL_CUES})")
FRACTION_RE = re.compile(r"\\frac(?=\s*\{)")


@dataclass
class Segment:
    kind: str
    lines: list[str]
    number: int | None = None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def normalized_title(value: str) -> str:
    return "".join(re.findall(r"[\w\u3400-\u9fff]+", value, re.UNICODE)).lower()


def split_embedded_answers(text: str) -> tuple[str, str]:
    lines = text.split("\n")
    answer_index = next((i for i, line in enumerate(lines) if ANSWER_HEADING_RE.match(line)), None)
    if answer_index is None:
        raise ValueError("No embedded answer heading was found; pass --answers if answers are separate.")

    question_end = answer_index
    first_h1 = next((H1_RE.match(line).group(1) for line in lines[:answer_index] if H1_RE.match(line)), "")
    previous = question_end - 1
    while previous >= 0 and not lines[previous].strip():
        previous -= 1
    if previous >= 0:
        match = H1_RE.match(lines[previous])
        if match and normalized_title(match.group(1)) == normalized_title(first_h1):
            question_end = previous

    question_text = "\n".join(lines[:question_end]).rstrip() + "\n"
    answer_text = "\n".join(lines[answer_index + 1 :]).lstrip("\n")
    return question_text, answer_text


def strip_answer_heading(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if ANSWER_HEADING_RE.match(line):
            return "\n".join(lines[i + 1 :]).lstrip("\n")
    return text


def segment_questions(text: str) -> tuple[list[Segment], list[int]]:
    segments: list[Segment] = []
    buffer: list[str] = []
    current_kind = "raw"
    current_number: int | None = None
    in_question_sections = False

    def flush() -> None:
        nonlocal buffer
        if buffer:
            segments.append(Segment(current_kind, buffer, current_number))
            buffer = []

    for line in text.split("\n"):
        if H2_RE.match(line):
            flush()
            current_kind = "section"
            current_number = None
            buffer = [line]
            flush()
            current_kind = "raw"
            in_question_sections = True
            continue

        question = QUESTION_RE.match(line) if in_question_sections else None
        if question:
            flush()
            current_kind = "question"
            current_number = int(question.group(1))
            buffer = [question.group(2)]
            continue

        buffer.append(line)

    flush()
    numbers = [segment.number for segment in segments if segment.kind == "question" and segment.number is not None]
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        raise ValueError(f"Duplicate question numbers found: {duplicates}")
    if not numbers:
        raise ValueError("No numbered questions were found after an H2 section heading.")
    return segments, numbers


def detailed_solution_pattern(question_numbers: list[int]) -> re.Pattern[str]:
    alternatives = "|".join(str(number) for number in sorted(question_numbers, key=lambda n: (-len(str(n)), n)))
    return re.compile(
        rf"(?<!\d)(?P<number>{alternatives})[\.．、]\s*[（(]\s*(?P<score>\d+)\s*分\s*[）)]"
    )


def clean_short_answer(value: str) -> str:
    kept: list[str] = []
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^[一二三四五六七八九十]+[、.]", stripped):
            continue
        kept.append(stripped)
    return re.sub(r"\s+", " ", " ".join(kept)).strip(" ;；")


def parse_answers(answer_text: str, question_numbers: list[int]) -> tuple[dict[int, str], dict[int, str]]:
    solution_re = detailed_solution_pattern(question_numbers)
    solution_matches = list(solution_re.finditer(answer_text))
    short_region = answer_text[: solution_matches[0].start()] if solution_matches else answer_text

    number_set = set(question_numbers)
    short_marker = re.compile(r"(?<!\d)(\d{1,3})[\.．、]\s*")
    short_matches = [match for match in short_marker.finditer(short_region) if int(match.group(1)) in number_set]
    short_answers: dict[int, str] = {}
    for index, match in enumerate(short_matches):
        number = int(match.group(1))
        end = short_matches[index + 1].start() if index + 1 < len(short_matches) else len(short_region)
        value = clean_short_answer(short_region[match.end() : end])
        if value:
            short_answers[number] = value

    solutions: dict[int, str] = {}
    for index, match in enumerate(solution_matches):
        number = int(match.group("number"))
        end = solution_matches[index + 1].start() if index + 1 < len(solution_matches) else len(answer_text)
        body = format_solution_body(answer_text[match.end() : end])
        if body:
            solutions[number] = body

    return short_answers, solutions


def compact_blank_lines(lines: list[str]) -> list[str]:
    compact: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if not stripped and compact and not compact[-1]:
            continue
        compact.append(stripped)
    while compact and not compact[0]:
        compact.pop(0)
    while compact and not compact[-1]:
        compact.pop()
    return compact


def format_solution_body(value: str) -> str:
    body = value.strip()
    body = SOLUTION_SUBPART_RE.sub(r"\n\n\1", body)
    body = SCORE_TRANSITION_RE.sub(r"\1\n\n", body)
    body = PUNCTUATION_TRANSITION_RE.sub(r"\1\n\n", body)
    body = MATH_TRANSITION_RE.sub(r"\1\n\n", body)
    return "\n".join(compact_blank_lines(body.splitlines()))


def normalize_options(lines: list[str]) -> list[str]:
    output: list[str] = []
    in_options = False
    for line in lines:
        if line.lstrip().startswith("!["):
            output.append(line.rstrip())
            in_options = False
            continue
        matches = list(OPTION_RE.finditer(line))
        if not matches:
            output.append(line.rstrip())
            in_options = False
            continue
        if len(matches) == 1 and line[: matches[0].start()].strip():
            output.append(line.rstrip())
            in_options = False
            continue

        prefix = line[: matches[0].start()].strip()
        if prefix:
            output.append(prefix)
            output.append("")
        elif not in_options and output and output[-1]:
            output.append("")
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            choice = line[match.end() : end].strip()
            output.append(f"- {match.group(1)}. {choice}".rstrip())
        in_options = True
    return output


def arrange_question_content(lines: list[str]) -> list[str]:
    normalized = compact_blank_lines(normalize_options(lines))
    choices = [line for line in normalized if re.match(r"^- [A-D][.．]\s", line)]
    images = [line for line in normalized if line.lstrip().startswith("![")]
    if not choices or not images:
        return normalized

    text = [
        line
        for line in normalized
        if not re.match(r"^- [A-D][.．]\s", line) and not line.lstrip().startswith("![")
    ]
    return compact_blank_lines(text) + [""] + images + [""] + choices


def lengthen_fraction_bars(markdown: str) -> tuple[str, int]:
    return FRACTION_RE.subn(r"\\dfrac", markdown)


def image_placement_violations(segments: list[Segment]) -> list[int]:
    violations: list[int] = []
    for segment in segments:
        if segment.kind != "question" or segment.number is None:
            continue
        content = arrange_question_content(segment.lines)
        image_indexes = [index for index, line in enumerate(content) if line.lstrip().startswith("![")]
        choice_indexes = [index for index, line in enumerate(content) if re.match(r"^- [A-D][.．]\s", line)]
        if image_indexes and choice_indexes and max(image_indexes) >= min(choice_indexes):
            violations.append(segment.number)
    return violations


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def is_external_target(target: str) -> bool:
    return bool(re.match(r"^(?:[a-z][a-z0-9+.-]*:|#|/)", target, re.IGNORECASE))


def target_path(target: str, base_dir: Path) -> Path | None:
    if is_external_target(target) or target.startswith("<") or re.search(r"\s+[\"']", target):
        return None
    decoded = unquote(target).replace("/", os.sep)
    return (base_dir / decoded).resolve()


def normalize_image_paths(markdown: str, source_dir: Path, output_dir: Path) -> tuple[str, list[dict[str, str]]]:
    rewrites: list[dict[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        original = match.group(1)
        direct = target_path(original, source_dir)
        actual: Path | None = direct if direct and direct.is_file() else None
        if actual is None:
            parent_relative = target_path(original, source_dir.parent)
            if parent_relative and parent_relative.is_file():
                actual = parent_relative
        if actual is None:
            return match.group(0)

        relative = os.path.relpath(actual, output_dir).replace(os.sep, "/").replace(" ", "%20")
        if relative == original:
            return match.group(0)
        rewrites.append({"from": original, "to": relative})
        return match.group(0).replace(f"({original})", f"({relative})", 1)

    return IMAGE_RE.sub(replace, markdown), rewrites


def unresolved_image_targets(markdown: str, output_dir: Path) -> list[str]:
    unresolved: list[str] = []
    for target in IMAGE_RE.findall(markdown):
        path = target_path(target, output_dir)
        if path is not None and not path.is_file():
            unresolved.append(target)
    return unresolved


def numbered_item(number: int, lines: list[str]) -> list[str]:
    content = compact_blank_lines(lines)
    if not content:
        return [f"{number}. "]
    output = [f"{number}. {content[0]}"]
    for line in content[1:]:
        output.append(f"   {line}" if line else "")
    return output


def answer_section_heading(section_line: str) -> str:
    match = H2_RE.match(section_line)
    value = match.group(1).strip() if match else section_line.strip().lstrip("#").strip()
    value = re.split(r"[：:]", value, maxsplit=1)[0].rstrip(".。")
    return f"## {value}"


def question_score(segment: Segment) -> str | None:
    for line in segment.lines:
        match = re.match(r"^\s*[（(]\s*(\d+)\s*分\s*[）)]", line)
        if match:
            return match.group(1)
    return None


def render_document(
    segments: list[Segment], short_answers: dict[int, str], solutions: dict[int, str]
) -> tuple[str, int, int]:
    all_lines = [line for segment in segments for line in segment.lines]
    h1_values = [match.group(1).strip() for line in all_lines if (match := H1_RE.match(line))]
    title = h1_values[0] if h1_values else "Exam paper"
    subject = h1_values[1] if len(h1_values) > 1 else ""

    rendered: list[str] = [
        "---",
        f"title: {yaml_quote(title)}",
        f"subject: {yaml_quote(subject)}",
        'document_type: "exam-with-separate-answers"',
        "---",
        "",
    ]
    emitted_title = False
    skipped_subject = False

    section_groups: list[tuple[str, list[Segment]]] = []
    current_group: list[Segment] | None = None

    for segment in segments:
        if segment.kind == "section":
            rendered.extend([segment.lines[0].rstrip(), ""])
            current_group = []
            section_groups.append((segment.lines[0], current_group))
            continue

        if segment.kind == "question" and segment.number is not None:
            content = arrange_question_content(segment.lines)
            rendered.extend(numbered_item(segment.number, content))
            rendered.append("")
            if current_group is not None:
                current_group.append(segment)
            continue

        for line in segment.lines:
            h1 = H1_RE.match(line)
            if h1:
                value = h1.group(1).strip()
                if not emitted_title and value == title:
                    rendered.extend([f"# {value}", ""])
                    emitted_title = True
                elif subject and not skipped_subject and value == subject:
                    skipped_subject = True
                else:
                    rendered.extend([line.rstrip(), ""])
                continue
            if re.match(r"^\s*(?:注意事项|Instructions)\s*[：:]?\s*$", line, re.IGNORECASE):
                rendered.extend(["## 注意事项" if "注意" in line else "## Instructions", ""])
            else:
                rendered.append(line.rstrip())

    answer_title = f"{subject}参考答案" if subject else "参考答案"
    rendered.extend(
        [
            "",
            '<div style="page-break-after: always;"></div>',
            "",
            "<!-- answer-section -->",
            "",
            f"# {answer_title}",
            "",
        ]
    )

    compact_short_answer_lines = 0
    for section_line, questions in section_groups:
        rendered.extend([answer_section_heading(section_line), ""])
        short_run: list[str] = []

        def flush_short_run() -> None:
            nonlocal compact_short_answer_lines
            if not short_run:
                return
            rendered.extend(["　".join(short_run), ""])
            compact_short_answer_lines += 1
            short_run.clear()

        for question in questions:
            number = question.number
            if number is None:
                continue
            if number in short_answers:
                short_run.append(f"{number}. {short_answers[number]}")
            elif number in solutions:
                flush_short_run()
                score = question_score(question)
                label = f"（{score} 分）" if score else "解答"
                solution_lines = [label, ""] + solutions[number].splitlines()
                rendered.extend(numbered_item(number, solution_lines))
                rendered.append("")
        flush_short_run()

    markdown = "\n".join(compact_blank_lines(rendered)).strip() + "\n"
    markdown, fraction_replacements = lengthen_fraction_bars(markdown)
    return markdown, fraction_replacements, compact_short_answer_lines


def report_for(
    input_path: Path,
    answer_path: Path | None,
    output_path: Path | None,
    question_numbers: list[int],
    short_answers: dict[int, str],
    solutions: dict[int, str],
    input_hash_before: str,
    answer_hash_before: str | None,
    question_text: str,
    rendered: str,
    image_path_rewrites: list[dict[str, str]],
    fraction_replacements: int,
    placement_violations: list[int],
    compact_short_answer_lines: int,
) -> dict[str, object]:
    mapped = set(short_answers) | set(solutions)
    expected = set(question_numbers)
    source_images = IMAGE_RE.findall(question_text)
    output_images = IMAGE_RE.findall(rendered)
    unresolved_images = unresolved_image_targets(rendered, output_path.parent if output_path else input_path.parent)
    return {
        "input": str(input_path),
        "answers": str(answer_path) if answer_path else None,
        "output": str(output_path) if output_path else None,
        "questions": question_numbers,
        "short_answers": sorted(short_answers),
        "worked_solutions": sorted(solutions),
        "missing_answers": sorted(expected - mapped),
        "extra_answers": sorted(mapped - expected),
        "source_images": len(source_images),
        "output_images": len(output_images),
        "preserved_images": len(output_images) >= len(source_images),
        "image_path_rewrites": image_path_rewrites,
        "unresolved_image_targets": unresolved_images,
        "question_image_placement_violations": placement_violations,
        "fraction_replacements": fraction_replacements,
        "separate_answer_section": "<!-- answer-section -->" in rendered,
        "page_break_present": '<div style="page-break-after: always;"></div>' in rendered,
        "compact_short_answer_lines": compact_short_answer_lines,
        "input_sha256": input_hash_before,
        "answer_sha256": answer_hash_before,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Markdown paper containing the questions")
    parser.add_argument("--answers", type=Path, help="Optional separate Markdown answer file")
    parser.add_argument("--output", type=Path, help="Candidate output path")
    parser.add_argument("--check", action="store_true", help="Parse and report without writing output")
    parser.add_argument("--strict", action="store_true", help="Fail when any question lacks an answer")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing candidate")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    answer_path = args.answers.resolve() if args.answers else None
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if answer_path and not answer_path.is_file():
        raise FileNotFoundError(answer_path)

    input_hash = sha256(input_path)
    answer_hash = sha256(answer_path) if answer_path else None
    input_text = read_text(input_path)
    if answer_path:
        question_text = input_text
        answer_text = strip_answer_heading(read_text(answer_path))
    else:
        question_text, answer_text = split_embedded_answers(input_text)

    segments, question_numbers = segment_questions(question_text)
    short_answers, solutions = parse_answers(answer_text, question_numbers)
    output_path = args.output.resolve() if args.output else input_path.with_name(f"{input_path.stem}（题解整合版）.md")
    rendered, fraction_replacements, compact_short_answer_lines = render_document(
        segments, short_answers, solutions
    )
    rendered, image_path_rewrites = normalize_image_paths(rendered, input_path.parent, output_path.parent)
    placement_violations = image_placement_violations(segments)
    if output_path in {input_path, answer_path}:
        raise ValueError("Output must not overwrite a source file.")
    if output_path.exists() and not args.force and not args.check:
        raise FileExistsError(f"Candidate already exists: {output_path}; pass --force to replace it.")

    report = report_for(
        input_path,
        answer_path,
        None if args.check else output_path,
        question_numbers,
        short_answers,
        solutions,
        input_hash,
        answer_hash,
        question_text,
        rendered,
        image_path_rewrites,
        fraction_replacements,
        placement_violations,
        compact_short_answer_lines,
    )
    if not args.check:
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
        report["input_unchanged"] = sha256(input_path) == input_hash
        report["answer_unchanged"] = answer_path is None or sha256(answer_path) == answer_hash

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["preserved_images"]:
        return 2
    if args.strict and (
        report["missing_answers"]
        or report["extra_answers"]
        or report["unresolved_image_targets"]
        or report["question_image_placement_violations"]
        or not report["separate_answer_section"]
        or not report["page_break_present"]
        or (bool(report["short_answers"]) and report["compact_short_answer_lines"] == 0)
    ):
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)

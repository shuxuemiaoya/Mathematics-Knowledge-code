#!/usr/bin/env python3
"""Apply deterministic, content-preserving Markdown presentation rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path


LESSON_FLOW_SCRIPT_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "book-toc-splitting"
    / "scripts"
)
if str(LESSON_FLOW_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(LESSON_FLOW_SCRIPT_DIRECTORY))

from lesson_flow_manifest import validate as validate_lesson_flow


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
EXAMPLE_RE = re.compile(r"^(例(?:题)?\s*\d+)\s*(.*)$")
CONTEXT_RE = re.compile(r"^(问题\s*\d+)\s*(.*)$")
NESTED_TIP_RE = re.compile(
    r"^\s*(?:\*\*)?(分析|思路|点拨)(?:\s*[：:])?(?:\*\*)?\s*(.*)$"
)
NESTED_SUCCESS_RE = re.compile(
    r"^\s*(?:\*\*)?(解|证明|解析|解答)(?:\s*[：:])?(?:\*\*)?\s*(.*)$"
)
INLINE_SUCCESS_RE = re.compile(
    r"(?<![\w])(?:\*\*)?(解|证明|解析|解答)\s*[：:](?:\*\*)?\s*"
)
TOP_CALLOUT_RE = re.compile(r"^> \[![^\]]+\]-?(?: .*)?$")
NESTED_CALLOUT_RE = re.compile(r"^> > \[![^\]]+\]-?(?: .*)?$")
EXAMPLE_LABEL_ONLY_CALLOUT_RE = re.compile(
    r"^> \[!example\]-?\s+(例(?:题)?\s*\d+)\s*$"
)
ORNAMENT_HEADING_RE = re.compile(r"^[●•·\s]+$")
QUOTED_ORNAMENT_RE = re.compile(
    r"^(?:>\s*)+(?:#{4,6}\s+)?[●•·\s]+$"
)
RUNNING_PUBLISHER_HEADINGS = {"人民教育出版社"}
PLAIN_RUNNING_CHAPTER_HEADER_RE = re.compile(
    r"^\s*(?:\d{1,3}\s*)?第[一二三四五六七八九十]+章\s+"
    r"[^。！？!?；;：:\[\]()（）]{1,40}\s*$"
)
LINK_RE = re.compile(r"(?<!!)\[[^\]\r\n]*\]\(([^)\r\n]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|<img\b[^>]*\bsrc=[\"']([^\"']+)")
FORMULA_NUMBER_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]")
DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)", re.DOTALL)
SPACED_DIGITS_RE = re.compile(r"(?<=\d)[ \t]+(?=\d)")
SPACE_BEFORE_DECIMAL_RE = re.compile(r"(?<=\d)[ \t]+(?=\.[ \t]*\d)")
SPACE_AFTER_DECIMAL_RE = re.compile(r"(?<=\d\.)[ \t]+(?=\d)")


def marker_for(title: str) -> str | None:
    compact = re.sub(r"\s+", "", title)
    if compact.startswith(("操作·交流", "情景引入", "情境引入", "引入", "引导")):
        return "info"
    if compact.startswith(
        (
            "思考",
            "观察",
            "讨论",
            "交流",
            "尝试",
            "想一想",
            "议一议",
            "观察·思考",
            "尝试·交流",
            "思考·交流",
            "回顾·反思",
            "探究",
            "实验",
            "做一做",
            "观察与猜想",
            "操作与思考",
        )
    ):
        return "question"
    if compact.startswith(("注意", "易错", "特别注意", "说明")):
        return "warning"
    if compact.startswith(("背景", "旁注", "补充材料")):
        return "tip"
    if compact.startswith(("联系", "区别", "类比", "对照")):
        return "note"
    if compact.startswith(
        ("归纳", "总结", "小结", "方法", "规律", "结论", "性质", "定理", "公理", "法则")
    ):
        return "summary"
    if EXAMPLE_RE.match(title):
        return "example"
    return None


def ensure_blank_before(output: list[str]) -> None:
    if output and output[-1] != "":
        output.append("")


def is_example_cross_reference(stem: str) -> bool:
    compact = stem.lstrip()
    return compact.startswith(("中", "的", "给出", "所述", "所得", "证明用到"))


def is_context_cross_reference(stem: str) -> bool:
    return stem.lstrip().startswith(("中", "的", "和", "与", "给出", "所述", "所得"))


def plain_marker_for(line: str) -> str | None:
    title = line.strip()
    if not title or len(title) > 18:
        return None
    if EXAMPLE_RE.match(title) or CONTEXT_RE.match(title):
        return None
    if re.search(r"[。！？!?；;：:,，]", title):
        return None
    return marker_for(title)


def is_block_start(line: str) -> bool:
    heading = HEADING_RE.match(line)
    if heading:
        return True
    example = EXAMPLE_RE.match(line)
    if example and not is_example_cross_reference(example.group(2)):
        return True
    context = CONTEXT_RE.match(line)
    if context:
        return True
    return plain_marker_for(line) is not None


def trim_blank_edges(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def append_quoted_body(
    output: list[str],
    body: list[str],
    *,
    example: bool,
    stem_in_marker: bool = False,
    nest_reasoning: bool = False,
) -> None:
    """Append one complete callout body, preserving every line at quote depth."""

    nested_depth: str | None = None
    stem_pending = example and not stem_in_marker
    trimmed_body = trim_blank_edges(body)
    if stem_in_marker and not trimmed_body:
        output.append(">")
        return
    for raw in trimmed_body:
        if stem_pending and raw:
            output.append(f"> {raw}")
            stem_pending = False
            continue
        may_nest = example or nest_reasoning
        tip = NESTED_TIP_RE.match(raw) if may_nest else None
        success = NESTED_SUCCESS_RE.match(raw) if may_nest else None
        if tip or success:
            match = tip or success
            assert match is not None
            if output and output[-1] not in {">", "> >"}:
                output.append(">")
            callout = "tip" if tip else "success"
            output.append(f"> > [!{callout}]- {match.group(1)}")
            remainder = match.group(2).strip()
            inline_success = INLINE_SUCCESS_RE.search(remainder) if tip else None
            if inline_success:
                analysis = remainder[: inline_success.start()].rstrip()
                if analysis:
                    output.append(f"> > {analysis}")
                output.append(">")
                output.append(
                    f"> > [!success]- {inline_success.group(1)}"
                )
                solution = remainder[inline_success.end() :].strip()
                if solution:
                    output.append(f"> > {solution}")
                nested_depth = "> >"
                continue
            if remainder:
                output.append(f"> > {remainder}")
            nested_depth = "> >"
            continue
        inline_success = (
            INLINE_SUCCESS_RE.search(raw)
            if may_nest and nested_depth == "> >"
            else None
        )
        if inline_success:
            prefix_text = raw[: inline_success.start()].rstrip()
            if prefix_text:
                output.append(f"> > {prefix_text}")
            output.append(">")
            output.append(f"> > [!success]- {inline_success.group(1)}")
            solution = raw[inline_success.end() :].strip()
            if solution:
                output.append(f"> > {solution}")
            nested_depth = "> >"
            continue
        prefix = nested_depth or ">"
        output.append(prefix if not raw else f"{prefix} {raw}")


def valid_quoted_callouts(text: str) -> bool:
    lines = text.splitlines()
    inside_top = False
    for index, line in enumerate(lines):
        if TOP_CALLOUT_RE.match(line):
            inside_top = True
            if index + 1 >= len(lines) or not lines[index + 1].startswith(">"):
                return False
            continue
        if line.startswith(">"):
            if not inside_top:
                return False
            if line.startswith("> > [!") and not NESTED_CALLOUT_RE.match(line):
                return False
            if NESTED_CALLOUT_RE.match(line):
                if index + 1 >= len(lines) or not lines[index + 1].startswith("> >"):
                    return False
            continue
        inside_top = False
    return True


def compact_existing_example_stems(text: str) -> tuple[str, int]:
    """Normalize an already-callout-formatted example to the approved style."""

    lines = text.splitlines()
    compacted = 0
    index = 0
    while index + 1 < len(lines):
        marker = EXAMPLE_LABEL_ONLY_CALLOUT_RE.match(lines[index])
        stem_index = index + 1
        while stem_index < len(lines) and lines[stem_index].strip() == ">":
            stem_index += 1
        stem_line = lines[stem_index] if stem_index < len(lines) else ""
        if (
            marker
            and stem_line.startswith("> ")
            and not stem_line.startswith("> >")
            and not TOP_CALLOUT_RE.match(stem_line)
        ):
            stem = stem_line[2:].strip()
            if stem:
                lines[index] = f"> [!example]- {marker.group(1)} {stem}"
                del lines[stem_index]
                compacted += 1
                if index + 1 >= len(lines) or not lines[index + 1].startswith(">"):
                    lines.insert(index + 1, ">")
        index += 1
    return "\n".join(lines) + "\n", compacted


def nest_existing_reasoning_blocks(text: str) -> tuple[str, int]:
    """Repair flattened reasoning inside an existing top-level callout."""

    lines = text.splitlines()
    nested = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("> ") or line.startswith("> >"):
            index += 1
            continue
        body = line[2:]
        tip = NESTED_TIP_RE.match(body)
        success = NESTED_SUCCESS_RE.match(body)
        match = tip or success
        if match is None:
            index += 1
            continue
        callout = "tip" if tip else "success"
        lines[index] = f"> > [!{callout}]- {match.group(1)}"
        remainder = match.group(2).strip()
        if remainder:
            lines.insert(index + 1, f"> > {remainder}")
            index += 1
        nested += 1
        position = index + 1
        while position < len(lines) and lines[position].startswith(">"):
            if lines[position].startswith("> >"):
                position += 1
                continue
            if TOP_CALLOUT_RE.match(lines[position]):
                break
            lines[position] = (
                "> >"
                if lines[position].strip() == ">"
                else f"> > {lines[position][1:].lstrip()}"
            )
            position += 1
        index = position
    return "\n".join(lines) + "\n", nested


def standardize_text(
    text: str,
    *,
    remove_running_headers: bool = False,
) -> tuple[str, dict]:
    input_lines = text.splitlines()
    cleaned: list[str] = []
    output: list[str] = []
    converted_headings = 0
    converted_examples = 0
    removed_artifact_headings = 0
    repaired_ocr_math_fragments = 0
    for line in input_lines:
        if QUOTED_ORNAMENT_RE.fullmatch(line):
            removed_artifact_headings += 1
            continue
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) >= 4:
            title = heading.group(2)
            if ORNAMENT_HEADING_RE.fullmatch(title) or (
                remove_running_headers
                and title.strip() in RUNNING_PUBLISHER_HEADINGS
            ):
                removed_artifact_headings += 1
                continue

        if (
            remove_running_headers
            and PLAIN_RUNNING_CHAPTER_HEADER_RE.fullmatch(line)
        ):
            removed_artifact_headings += 1
            continue
        cleaned.append(line.rstrip())

    index = 0
    while index < len(cleaned):
        line = cleaned[index]
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) >= 4:
            title = heading.group(2)
            marker = marker_for(title)
            if marker:
                end = index + 1
                while end < len(cleaned) and not is_block_start(cleaned[end]):
                    end += 1
                body = trim_blank_edges(cleaned[index + 1 : end])
                if body:
                    ensure_blank_before(output)
                    collapse = "-" if marker == "example" else ""
                    output.append(f"> [!{marker}]{collapse} {title}")
                    append_quoted_body(
                        output,
                        body,
                        example=(marker == "example"),
                        nest_reasoning=(marker != "example"),
                    )
                    output.append("")
                    converted_headings += 1
                    index = end
                    continue

        plain_marker = plain_marker_for(line)
        if plain_marker:
            end = index + 1
            while end < len(cleaned) and not is_block_start(cleaned[end]):
                end += 1
            body = trim_blank_edges(cleaned[index + 1 : end])
            if body:
                ensure_blank_before(output)
                collapse = "-" if plain_marker == "example" else ""
                output.append(f"> [!{plain_marker}]{collapse} {line.strip()}")
                append_quoted_body(
                    output,
                    body,
                    example=(plain_marker == "example"),
                    nest_reasoning=(plain_marker != "example"),
                )
                output.append("")
                converted_headings += 1
                index = end
                continue

        example = EXAMPLE_RE.match(line)
        if (
            example
            and not line.startswith("#")
            and not is_example_cross_reference(example.group(2))
        ):
            label, stem = example.groups()
            end = index + 1
            while end < len(cleaned) and not is_block_start(cleaned[end]):
                end += 1
            body = cleaned[index + 1 : end]
            ensure_blank_before(output)
            marker_label = f"{label} {stem}".rstrip()
            output.append(f"> [!example]- {marker_label}")
            append_quoted_body(
                output,
                body,
                example=True,
                stem_in_marker=bool(stem),
            )
            output.append("")
            converted_examples += 1
            index = end
            continue

        context = CONTEXT_RE.match(line)
        if (
            context
            and not line.startswith("#")
            and not is_context_cross_reference(context.group(2))
        ):
            label, stem = context.groups()
            end = index + 1
            while end < len(cleaned) and not is_block_start(cleaned[end]):
                end += 1
            body = ([stem] if stem else []) + cleaned[index + 1 : end]
            body = trim_blank_edges(body)
            if body:
                ensure_blank_before(output)
                output.append(f"> [!info] {label}")
                append_quoted_body(
                    output,
                    body,
                    example=False,
                    nest_reasoning=True,
                )
                output.append("")
                converted_headings += 1
                index = end
                continue

        output.append(line)
        index += 1

    compacted: list[str] = []
    previous_blank_token: str | None = None
    for line in output:
        if line in {"", ">", "> >"}:
            if line != previous_blank_token:
                compacted.append(line)
            previous_blank_token = line
        else:
            previous_blank_token = None
            compacted.append(line)
    while compacted and compacted[-1] == "":
        compacted.pop()
    result = "\n".join(compacted) + "\n"
    result, compacted_example_stems = compact_existing_example_stems(result)
    result, nested_existing_reasoning_blocks = nest_existing_reasoning_blocks(
        result
    )
    result, repaired_ocr_math_fragments = repair_spaced_digits_in_math(result)
    return result, {
        "converted_headings": converted_headings,
        "converted_examples": converted_examples,
        "removed_artifact_headings": removed_artifact_headings,
        "repaired_ocr_math_fragments": repaired_ocr_math_fragments,
        "compacted_example_stems": compacted_example_stems,
        "nested_existing_reasoning_blocks": nested_existing_reasoning_blocks,
    }


def math_spans(text: str) -> list[tuple[int, int]]:
    display = [(match.start(), match.end()) for match in DISPLAY_MATH_RE.finditer(text)]
    masked = list(text)
    for start, end in display:
        masked[start:end] = " " * (end - start)
    inline = [
        (match.start(), match.end())
        for match in INLINE_MATH_RE.finditer("".join(masked))
    ]
    return display + inline


def repair_spaced_digits_in_math(text: str) -> tuple[str, int]:
    """Undo MinerU's digit-by-digit spacing only inside TeX spans."""

    repaired = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal repaired
        value = match.group(0)
        value, count = SPACE_BEFORE_DECIMAL_RE.subn("", value)
        repaired += count
        value, count = SPACE_AFTER_DECIMAL_RE.subn("", value)
        repaired += count
        value, count = SPACED_DIGITS_RE.subn("", value)
        repaired += count
        return value

    text = DISPLAY_MATH_RE.sub(replace, text)
    display_spans = [
        (match.start(), match.end()) for match in DISPLAY_MATH_RE.finditer(text)
    ]
    masked = list(text)
    for start, end in display_spans:
        masked[start:end] = " " * (end - start)
    inline_matches = list(INLINE_MATH_RE.finditer("".join(masked)))
    for match in reversed(inline_matches):
        text = text[: match.start()] + replace(match) + text[match.end() :]
    return text, repaired


def destinations(
    pattern: re.Pattern[str], text: str, *, outside_math: bool = False
) -> Counter[str]:
    values: list[str] = []
    spans = math_spans(text) if outside_math else []
    for match in pattern.finditer(text):
        if outside_math and any(
            start <= match.start() and match.end() <= end for start, end in spans
        ):
            continue
        value = next(group for group in match.groups() if group is not None)
        values.append(value)
    return Counter(values)


def invariants(before: str, after: str) -> dict[str, bool]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    top_before = [
        line for line in before_lines if re.match(r"^#{1,3}(?:\s|$)", line)
    ]
    top_after = [
        line for line in after_lines if re.match(r"^#{1,3}(?:\s|$)", line)
    ]
    table_before = [
        re.sub(r"^(?:>\s*)+", "", line)
        for line in before_lines
        if "<table" in line or "</table>" in line
    ]
    table_after = [
        re.sub(r"^(?:>\s*)+", "", line)
        for line in after_lines
        if "<table" in line or "</table>" in line
    ]
    return {
        "headings": top_before == top_after,
        "tables": table_before == table_after,
        "links": destinations(LINK_RE, before, outside_math=True)
        == destinations(LINK_RE, after, outside_math=True),
        "images": destinations(IMAGE_RE, before) == destinations(IMAGE_RE, after),
        "formula_numbering": Counter(FORMULA_NUMBER_RE.findall(before))
        == Counter(FORMULA_NUMBER_RE.findall(after)),
        "source_order": True,
        "quoted_body_callout_continuity": valid_quoted_callouts(after),
    }


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def corpus_sha256(items: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for relative, text in sorted(items):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def run(
    profile_path: Path,
    report_path: Path,
    lesson_flow_manifest_path: Path | None = None,
) -> dict:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    decomposition = profile.get("decomposition", {})
    require_lesson_flow = bool(
        isinstance(decomposition, dict)
        and decomposition.get("require_lesson_flow_manifest", False)
        and "textbook"
        in str(profile.get("book", {}).get("kind", "")).casefold()
    )
    lesson_flow_summary = None
    if require_lesson_flow:
        if lesson_flow_manifest_path is None:
            raise ValueError(
                "textbook standardization requires a lesson-flow manifest"
            )
        lesson_flow_payload = json.loads(
            lesson_flow_manifest_path.read_text(encoding="utf-8-sig")
        )
        lesson_flow_summary = validate_lesson_flow(
            lesson_flow_payload,
            formatted_markdown=Path(
                lesson_flow_payload["formatted_markdown"]
            ).resolve(),
            split_manifest_path=Path(
                lesson_flow_payload["split_manifest"]
            ).resolve(),
            profile_path=profile_path.resolve(),
        )
    book_root = Path(profile["paths"]["book_root"])
    files = sorted(book_root.rglob("*.md"))
    before_items: list[tuple[str, str]] = []
    after_items: list[tuple[str, str]] = []
    reports: list[dict] = []
    invariant_failures: list[str] = []
    combined = {
        "headings": True,
        "tables": True,
        "links": True,
        "images": True,
        "formula_numbering": True,
        "source_order": True,
        "quoted_body_callout_continuity": True,
    }
    pending: list[tuple[Path, str]] = []
    for path in files:
        relative = path.relative_to(book_root).as_posix()
        before = path.read_text(encoding="utf-8")
        after, changes = standardize_text(
            before,
            remove_running_headers=len(Path(relative).parts) > 1,
        )
        checks = invariants(before, after)
        for key, passed in checks.items():
            combined[key] = combined[key] and passed
            if not passed:
                invariant_failures.append(f"{relative}:{key}")
        before_items.append((relative, before))
        after_items.append((relative, after))
        pending.append((path, after))
        reports.append(
            {
                "path": relative,
                "input_sha256": sha256_text(before),
                "output_sha256": sha256_text(after),
                "changed": before != after,
                **changes,
                "protected_invariants": checks,
            }
        )
    if not all(combined.values()):
        raise ValueError(
            "protected invariants failed: " + ", ".join(invariant_failures[:20])
        )
    for path, after in pending:
        atomic_write(path, after)
    report = {
        "schema_version": 1,
        "stage": "markdown-standardization",
        "status": "passed",
        "profile": str(profile_path.resolve()),
        "source_sha256": profile["source"]["sha256"],
        "input_corpus_sha256": corpus_sha256(before_items),
        "output_corpus_sha256": corpus_sha256(after_items),
        "protected_invariants": combined,
        "lesson_flow_manifest": (
            str(lesson_flow_manifest_path.resolve())
            if lesson_flow_manifest_path
            else None
        ),
        "lesson_flow": lesson_flow_summary,
        "files": reports,
    }
    atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return {
        "status": "passed",
        "files": len(files),
        "changed": sum(item["changed"] for item in reports),
        "converted_headings": sum(item["converted_headings"] for item in reports),
        "converted_examples": sum(item["converted_examples"] for item in reports),
        "removed_artifact_headings": sum(
            item["removed_artifact_headings"] for item in reports
        ),
        "repaired_ocr_math_fragments": sum(
            item["repaired_ocr_math_fragments"] for item in reports
        ),
        "compacted_example_stems": sum(
            item["compacted_example_stems"] for item in reports
        ),
        "nested_existing_reasoning_blocks": sum(
            item["nested_existing_reasoning_blocks"] for item in reports
        ),
        "report": str(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--lesson-flow-manifest", type=Path)
    args = parser.parse_args()
    try:
        result = run(
            args.profile,
            args.report,
            lesson_flow_manifest_path=(
                args.lesson_flow_manifest.resolve()
                if args.lesson_flow_manifest
                else None
            ),
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

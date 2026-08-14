from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any
from urllib import request as urllib_request
from urllib.parse import urlparse, urlsplit
import zipfile

from pypdf import PdfReader, PdfWriter


MAX_PAGES = 200
MAX_BYTES = 200 * 1024 * 1024
ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}
TERMINAL_STATES = {"done", "failed"}
IMAGE_RE = re.compile(r"!\[(?P<alt>[^]]*)\]\((?P<dest>[^)]+)\)")
QUESTION_RE = re.compile(r"^\s*(?P<number>\d+)[.．、]\s*")
MARKER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?【(?P<label>答案|解析|分析|详解|小问\s*\d+\s*详解)】"
)
SECTION_KEYWORDS = ("单选题", "多选题", "选择题", "填空题", "解答题", "计算题", "证明题", "应用题")
ORDINAL_RE = re.compile(r"^[一二三四五六七八九十]+[、.．]")


class ParserError(RuntimeError):
    pass


class ReviewRequired(ParserError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(value.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_component(value: str, fallback: str = "node") -> str:
    result = "".join(char if char == "_" or char.isalnum() else "_" for char in value)
    return result or fallback


def safe_filename(value: str, fallback: str) -> str:
    path = Path(value)
    return safe_component(path.stem, Path(fallback).stem) + path.suffix.lower()


def clean_section_title(title: str) -> str:
    return title.split("：", 1)[0].split(":", 1)[0].strip()


def normalize_match(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value, flags=re.UNICODE).casefold()


def parse_env(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def resolve_env_file(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ParserError(f"Environment file does not exist: {path}")
        return path
    roots = [Path(__file__).resolve(), Path.cwd().resolve()]
    seen: set[str] = set()
    for root in roots:
        current = root.parent if root.is_file() else root
        for parent in (current, *current.parents):
            candidate = (parent / ".env").resolve()
            if str(candidate) not in seen and candidate.is_file():
                return candidate
            seen.add(str(candidate))
    return None


@dataclass(frozen=True)
class PdfPart:
    path: Path
    index: int
    count: int
    start_page: int
    end_page: int
    data_id: str


def pdf_page_count(path: Path) -> int:
    count = len(PdfReader(str(path)).pages)
    if count < 1:
        raise ParserError(f"PDF has no pages: {path}")
    return count


def write_pdf_range(reader: PdfReader, target: Path, start: int, end: int) -> None:
    writer = PdfWriter()
    for page_index in range(start - 1, end):
        writer.add_page(reader.pages[page_index])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        writer.write(stream)


def fit_pdf_ranges(reader: PdfReader, ranges: list[tuple[int, int]], temp_root: Path) -> list[tuple[int, int]]:
    accepted: list[tuple[int, int]] = []
    pending = list(ranges)
    while pending:
        start, end = pending.pop(0)
        probe = temp_root / f"probe-{start}-{end}.pdf"
        write_pdf_range(reader, probe, start, end)
        size = probe.stat().st_size
        probe.unlink()
        if size <= MAX_BYTES:
            accepted.append((start, end))
        elif start == end:
            raise ParserError(f"PDF page {start} exceeds MinerU's 200 MB limit")
        else:
            middle = (start + end) // 2
            pending[0:0] = [(start, middle), (middle + 1, end)]
    return accepted


def split_pdf(source: Path, temp_root: Path) -> list[PdfPart]:
    reader = PdfReader(str(source))
    page_count = len(reader.pages)
    digest = sha256_file(source)[:16]
    if page_count <= MAX_PAGES and source.stat().st_size <= MAX_BYTES:
        return [PdfPart(source, 1, 1, 1, page_count, f"exam-{digest}-001")]
    ranges = [(start, min(start + MAX_PAGES - 1, page_count)) for start in range(1, page_count + 1, MAX_PAGES)]
    ranges = fit_pdf_ranges(reader, ranges, temp_root)
    parts: list[PdfPart] = []
    for index, (start, end) in enumerate(ranges, 1):
        writer = PdfWriter()
        for page_index in range(start - 1, end):
            writer.add_page(reader.pages[page_index])
        target = temp_root / f"part-{index:03d}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as stream:
            writer.write(stream)
        parts.append(PdfPart(target, index, len(ranges), start, end, f"exam-{digest}-{index:03d}"))
    expected_page = 1
    for part in parts:
        if part.start_page != expected_page:
            raise ParserError("PDF split contains a page gap or overlap")
        expected_page = part.end_page + 1
    if expected_page != page_count + 1:
        raise ParserError("PDF split does not cover every page")
    return parts


def json_request(url: str, api_key: str, method: str = "GET", payload: Any | None = None, timeout: float = 120.0) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib_request.Request(url, data=data, headers=headers, method=method)
    with urllib_request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("code") != 0:
        raise ParserError(f"MinerU API error: {body.get('msg', body.get('code'))}")
    return body


def binary_request(url: str, method: str = "GET", data: bytes | None = None, timeout: float = 120.0) -> bytes:
    request = urllib_request.Request(url, data=data, method=method)
    with urllib_request.urlopen(request, timeout=timeout) as response:
        return response.read()


def upload_file(url: str, path: Path, timeout: float) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ParserError("MinerU returned an invalid signed upload URL")
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    target = parsed.path or "/"
    if parsed.query:
        target += f"?{parsed.query}"
    try:
        connection.putrequest("PUT", target)
        connection.putheader("Content-Length", str(path.stat().st_size))
        connection.endheaders()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                connection.send(block)
        response = connection.getresponse()
        status = response.status
        response.read()
    finally:
        connection.close()
    if status < 200 or status >= 300:
        raise ParserError(f"MinerU upload failed with HTTP {status}")


def safe_zip_member(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ParserError(f"Unsafe MinerU zip member: {value}")
    return path


def content_list_priority(name: str) -> int:
    lowered = name.casefold()
    if "content_list" not in lowered or not lowered.endswith(".json"):
        return 0
    return 1 if "v2" in lowered else 2


def extract_mineru_zip(zip_path: Path, part: PdfPart, cache_root: Path) -> tuple[str, list[dict[str, Any]], int]:
    markdown: str | None = None
    content_lists: list[tuple[int, Any]] = []
    asset_count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            relative = safe_zip_member(member)
            if member.endswith("/"):
                continue
            lowered = relative.name.casefold()
            if lowered == "full.md":
                markdown = archive.read(member).decode("utf-8")
                continue
            priority = content_list_priority(relative.name)
            if priority:
                content_lists.append((priority, json.loads(archive.read(member).decode("utf-8"))))
                continue
            lowered_parts = [item.casefold() for item in relative.parts]
            if "images" in lowered_parts:
                image_index = lowered_parts.index("images")
                image_relative = Path(*relative.parts[image_index + 1 :])
                if part.count > 1:
                    image_relative = Path(f"part-{part.index:03d}") / image_relative
                destination = cache_root / "images" / "combined" / image_relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))
                asset_count += 1
    if markdown is None:
        raise ParserError(f"MinerU result for part {part.index} has no full.md")
    markdown = re.sub(
        r"(!\[[^]]*\]\()(?:(?:\./)?images/)?",
        lambda match: match.group(1) + (
            f"images/combined/part-{part.index:03d}/" if part.count > 1 else "images/combined/"
        ),
        markdown,
    )
    blocks: list[dict[str, Any]] = []
    if content_lists:
        data = sorted(content_lists, key=lambda item: item[0], reverse=True)[0][1]
        if isinstance(data, list) and (not data or isinstance(data[0], dict) and "page_idx" in data[0]):
            for index, block in enumerate(data):
                if not isinstance(block, dict):
                    continue
                blocks.append({
                    "block_id": f"p{part.index}:b{index}",
                    "source_page": part.start_page + int(block.get("page_idx", 0)),
                    "bbox": block.get("bbox"),
                    "type": block.get("type"),
                    "text": str(block.get("text", "")),
                })
        elif isinstance(data, list):
            for local_page, page_blocks in enumerate(data):
                values = page_blocks if isinstance(page_blocks, list) else page_blocks.get("blocks", [])
                for index, block in enumerate(values):
                    if isinstance(block, dict):
                        blocks.append({
                            "block_id": f"p{part.index}:b{local_page}-{index}",
                            "source_page": part.start_page + local_page,
                            "bbox": block.get("bbox"),
                            "type": block.get("type"),
                            "text": str(block.get("text", "")),
                        })
    return markdown, blocks, asset_count


def mineru_ocr(source: Path, cache_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    report_path = cache_root / "ocr-report.json"
    raw_path = cache_root / "raw.md"
    source_hash = sha256_file(source)
    if report_path.is_file() and raw_path.is_file():
        report = load_json(report_path)
        if report.get("source_sha256") == source_hash and report.get("status") == "completed":
            return {**report, "cache_hit": True}
    env_file = resolve_env_file(args.env_file)
    env = parse_env(env_file)
    api_key = os.environ.get("MINERU_API_KEY") or env.get("MINERU_API_KEY")
    if not api_key:
        raise ParserError("MINERU_API_KEY is missing; pass --markdown to parse existing OCR without a network call")
    base_url = (args.base_url or env.get("MINERU_BASE_URL") or "https://mineru.net").rstrip("/")
    if base_url.endswith("/api/v4"):
        base_url = base_url[:-7]
    cache_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="exam-paper-parser-") as temp_name:
        temp_root = Path(temp_name)
        parts = split_pdf(source, temp_root / "parts")
        markdown_parts: dict[int, str] = {}
        blocks: list[dict[str, Any]] = []
        asset_count = 0
        payload = {
            "files": [{"name": part.path.name, "data_id": part.data_id, "is_ocr": True} for part in parts],
            "model_version": "vlm",
            "language": "ch",
            "enable_formula": True,
            "enable_table": True,
        }
        upload_body = json_request(f"{base_url}/api/v4/file-urls/batch", api_key, "POST", payload, args.request_timeout)
        data = upload_body.get("data") or {}
        batch_id = str(data.get("batch_id", ""))
        urls = data.get("file_urls") or []
        if not batch_id or len(urls) != len(parts):
            raise ParserError("MinerU upload response is incomplete")
        for part, url in zip(parts, urls):
            upload_file(str(url), part.path, args.request_timeout)
        results: list[dict[str, Any]] = []
        for _ in range(args.max_polls):
            body = json_request(f"{base_url}/api/v4/extract-results/batch/{batch_id}", api_key, timeout=args.request_timeout)
            results = (body.get("data") or {}).get("extract_result") or []
            states = [str(item.get("state", "")) for item in results]
            if results and all(state in TERMINAL_STATES for state in states):
                break
            if any(state not in ACTIVE_STATES | TERMINAL_STATES for state in states):
                raise ParserError(f"MinerU returned unknown state(s): {states}")
            time.sleep(args.poll_interval)
        else:
            raise ParserError("MinerU polling timed out")
        parts_by_id = {part.data_id: part for part in parts}
        for result in results:
            part = parts_by_id.get(str(result.get("data_id", "")))
            if part is None or result.get("state") == "failed" or not result.get("full_zip_url"):
                raise ParserError(f"MinerU failed or returned an incomplete result: {result.get('err_msg', '')}")
            zip_path = temp_root / f"part-{part.index:03d}.zip"
            zip_path.write_bytes(binary_request(str(result["full_zip_url"]), timeout=args.request_timeout))
            markdown, part_blocks, part_assets = extract_mineru_zip(zip_path, part, cache_root)
            markdown_parts[part.index] = markdown.strip()
            blocks.extend(part_blocks)
            asset_count += part_assets
    merged = "\n\n".join(markdown_parts[index] for index in sorted(markdown_parts)).strip() + "\n"
    write_text(raw_path, merged)
    write_json(cache_root / "provenance-blocks.json", blocks)
    report = {
        "schema_version": 1,
        "stage": "ocr",
        "status": "completed",
        "source_pdf": str(source),
        "source_sha256": source_hash,
        "page_count": pdf_page_count(source),
        "raw_markdown": str(raw_path),
        "raw_markdown_sha256": sha256_file(raw_path),
        "asset_root": str(cache_root / "images"),
        "asset_count": asset_count,
        "provenance_block_count": len(blocks),
        "ocr_forced": True,
        "model_version": "vlm",
        "formula_enabled": True,
        "table_enabled": True,
        "duration_seconds": round(time.monotonic() - started, 3),
        "cache_hit": False,
    }
    write_json(report_path, report)
    return report


def is_section_heading(line: str) -> tuple[bool, str]:
    match = re.match(r"^\s*(?P<hashes>#{1,6})\s+(?P<title>\S.*?)\s*$", line)
    if not match:
        return False, ""
    title = match.group("title")
    has_keyword = any(keyword in title for keyword in SECTION_KEYWORDS)
    authority = len(match.group("hashes")) >= 2 or ORDINAL_RE.match(title) is not None
    return bool(has_keyword and authority), title


def expected_count(title: str) -> int | None:
    match = re.search(r"本题共\s*(\d+)\s*小题", title)
    return int(match.group(1)) if match else None


def split_inline_markers(text: str) -> str:
    text = re.sub(
        r"(?<!^)\s*(?=【(?:答案|解析|分析|详解|小问\s*\d+\s*详解)】)",
        "\n",
        text,
    )
    return re.sub(
        r"(?<!^)\s*(?=(?:(?<=[。\.\!\?！\？\)])|(?<=正确\.)|(?<=错误\.))\s*\d+[.．、]\s*(?:[\u4e00-\u9fa5]|\$|[A-Za-z]|\(ND|（))",
        "\n",
        text,
    )



def marker_name(line: str) -> str | None:
    match = MARKER_RE.match(line)
    if not match:
        return None
    label = match.group("label")
    return "详解" if label.endswith("详解") else label


def marker_label(line: str) -> str | None:
    match = MARKER_RE.match(line)
    return match.group("label") if match else None


def first_solution_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], 1):
        if marker_name(line):
            return index
    return None


def repair_missing_question_numbers(markdown: str) -> str:
    lines = markdown.splitlines()
    question_indices = []
    for idx, line in enumerate(lines):
        m = QUESTION_RE.match(line)
        if m:
            question_indices.append((idx, int(m.group("number"))))
    
    if not question_indices:
        return markdown

    repaired_lines = list(lines)
    for i in range(len(question_indices) - 1):
        idx1, num1 = question_indices[i]
        idx2, num2 = question_indices[i + 1]
        if num2 == num1 + 2:
            missing_num = num1 + 1
            for target_idx in range(idx1 + 1, idx2):
                l = repaired_lines[target_idx].strip()
                if l and not l.startswith("#") and not l.startswith("【") and not QUESTION_RE.match(l):
                    if re.match(r"^[A-D][.．、]\s*", l) and not ("（" in l or "(" in l or ("A." in l and "B." in l)):
                        continue
                    next_markers = [j for j in range(target_idx + 1, idx2) if MARKER_RE.match(repaired_lines[j].strip())]
                    if next_markers:
                        repaired_lines[target_idx] = f"{missing_num}. {l}"
                        break

    return "\n".join(repaired_lines)


def parse_sections(markdown: str) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    markdown = repair_missing_question_numbers(markdown)
    lines: list[str] = []
    source_line_numbers: list[int] = []
    for source_line_number, raw_line in enumerate(markdown.splitlines(), 1):
        split_lines = split_inline_markers(raw_line).splitlines() or [""]
        lines.extend(split_lines)
        source_line_numbers.extend([source_line_number] * len(split_lines))
    sections: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        matched, title = is_section_heading(line)
        if matched:
            sections.append({"title": title, "heading_line": source_line_numbers[index], "start_index": index})
    if not sections:
        sections.append({"title": "一、试卷全图", "heading_line": 1, "start_index": 0})
    questions: list[dict[str, Any]] = []
    for section_index, section in enumerate(sections):
        end = sections[section_index + 1]["start_index"] if section_index + 1 < len(sections) else len(lines)
        starts = [index for index in range(section["start_index"] + 1, end) if QUESTION_RE.match(lines[index])]
        if not starts:
            raise ReviewRequired(f"Section has no numbered questions: {section['title']}")
        for position, start in enumerate(starts):
            question_end = starts[position + 1] if position + 1 < len(starts) else end
            block = lines[start:question_end]
            solution_offset = first_solution_index(block)
            if solution_offset is None:
                raise ReviewRequired(f"Question {QUESTION_RE.match(lines[start]).group('number')} has no explicit publisher solution marker")
            question_lines = block[:solution_offset]
            solution_lines = block[solution_offset:]
            match = QUESTION_RE.match(lines[start])
            questions.append({
                "number": int(match.group("number")),
                "section_index": section_index,
                "source_start_line": source_line_numbers[start],
                "source_solution_line": source_line_numbers[start + solution_offset],
                "question_body": "\n".join(question_lines).rstrip() + "\n",
                "solution_body": "\n".join(solution_lines).rstrip() + "\n",
            })
        section["end_index"] = end
        section["expected_count"] = expected_count(section["title"])
        section["detected_count"] = len(starts)
    return lines, sections, questions


def pdf_choice_answers(source: Path) -> dict[int, dict[str, Any]]:
    answers: dict[int, dict[str, Any]] = {}
    current: int | None = None
    for page_number, page in enumerate(PdfReader(str(source)).pages, 1):
        text = page.extract_text() or ""
        for raw in text.splitlines():
            question = QUESTION_RE.match(raw)
            if question:
                current = int(question.group("number"))
            answer = re.search(r"【答案】\s*([A-F]+)\b", raw, re.IGNORECASE)
            if current is not None and answer:
                answers[current] = {
                    "answer": answer.group(1).upper(),
                    "source_page": page_number,
                    "evidence": raw.strip(),
                }
    return answers


def provenance_for(question_body: str, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    first_line = next((line for line in question_body.splitlines() if line.strip()), "")
    needle = normalize_match(first_line)
    if not needle:
        return None
    candidates: list[tuple[int, dict[str, Any]]] = []
    for block in blocks:
        haystack = normalize_match(str(block.get("text", "")))
        if not haystack:
            continue
        if needle == haystack:
            candidates.append((3, block))
        elif needle in haystack or haystack in needle:
            candidates.append((2, block))
        elif needle[: min(80, len(needle))] in haystack:
            candidates.append((1, block))
    if not candidates:
        return None
    score, block = sorted(candidates, key=lambda item: (-item[0], int(item[1].get("source_page", 10**9))))[0]
    return {
        "source_page": block.get("source_page"),
        "bbox": block.get("bbox"),
        "match": {3: "normalized-exact", 2: "normalized-containment", 1: "normalized-prefix"}[score],
        "block_id": block.get("block_id"),
    }


def load_provenance_blocks(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, dict):
        values = data.get("blocks") or []
        return values if isinstance(values, list) else []
    if not isinstance(data, list):
        return []
    result: list[dict[str, Any]] = []
    for index, block in enumerate(data):
        if not isinstance(block, dict):
            continue
        result.append({
            "block_id": str(block.get("block_id") or f"source:b{index}"),
            "source_page": (
                int(block["source_page"])
                if block.get("source_page") is not None
                else int(block.get("page_idx", 0)) + 1
            ),
            "bbox": block.get("bbox"),
            "type": block.get("type"),
            "text": str(block.get("text", "")),
        })
    return result


def is_choice_question(body: str) -> bool:
    values = set(re.findall(r"(?<![A-Za-z])([A-D])[.．、]", body))
    return values == {"A", "B", "C", "D"}


def compact_answer(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def marked_chunks(solution_body: str) -> tuple[list[str], list[tuple[str, int, int]]]:
    text = split_inline_markers(solution_body.strip())
    lines = text.splitlines()
    markers: list[tuple[str, int, int]] = []
    starts: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        name = marker_name(line)
        if name:
            starts.append((name, index))
    for position, (name, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        markers.append((name, start, end))
    return lines, markers


def content_after_marker(lines: list[str], marker: tuple[str, int, int]) -> str:
    _, start, end = marker
    first = MARKER_RE.sub("", lines[start], count=1).strip()
    values = ([first] if first else []) + lines[start + 1 : end]
    return "\n".join(values).strip()


def detail_content(lines: list[str], markers: list[tuple[str, int, int]]) -> tuple[str, list[str]]:
    chunks: list[str] = []
    labels: list[str] = []
    for marker in markers:
        label = marker_label(lines[marker[1]]) or "详解"
        content = content_after_marker(lines, marker)
        if label == "详解":
            chunks.append(content)
        else:
            labels.append(f"【{label}】")
            chunks.append(f"【{label}】" + (f"\n\n{content}" if content else ""))
    return "\n\n".join(item for item in chunks if item).strip(), labels


def solution_fields(solution_body: str, choice: bool, recovered: dict[str, Any] | None) -> dict[str, Any]:
    lines, markers = marked_chunks(solution_body)
    by_name: dict[str, list[tuple[str, int, int]]] = {}
    for marker in markers:
        by_name.setdefault(marker[0], []).append(marker)
    explicit_answer = content_after_marker(lines, by_name["答案"][0]) if by_name.get("答案") else ""
    compact_explicit = compact_answer(explicit_answer)
    conclusion = re.findall(r"(?:故\s*选|应\s*选|答案(?:为|是)?)\s*[：:]?\s*([A-F]+)\b", solution_body, re.IGNORECASE)
    if choice:
        if re.fullmatch(r"[A-F]+", compact_explicit, re.IGNORECASE):
            answer = compact_explicit.upper()
            answer_source = "explicit-answer"
        elif conclusion:
            answer = conclusion[-1].upper()
            answer_source = "explicit-conclusion"
        else:
            answer = str((recovered or {}).get("answer", ""))
            answer_source = "pdf-text-recovery"
        if not re.fullmatch(r"[A-F]+", answer):
            raise ReviewRequired("Choice question lacks an explicit authoritative A-F answer")
    else:
        answer = compact_explicit if compact_explicit and len(compact_explicit) <= 400 else "详见解析"
        answer_source = "explicit-answer" if answer != "详见解析" else "publisher-solution"
    detailed_explanation, detail_markers = detail_content(lines, by_name.get("详解", []))
    analysis = "本题未单列分析。"
    analysis_remainder = ""
    if by_name.get("分析"):
        raw_analysis = content_after_marker(lines, by_name["分析"][0])
        if detail_markers:
            analysis = raw_analysis or analysis
        else:
            paragraphs = [item.strip() for item in re.split(r"\n\s*\n", raw_analysis) if item.strip()]
            if paragraphs:
                analysis = paragraphs[0]
                analysis_remainder = "\n\n".join(paragraphs[1:])
    if detailed_explanation:
        explanation = detailed_explanation
    elif by_name.get("解析"):
        explanation = content_after_marker(lines, by_name["解析"][0])
        if by_name.get("分析") and analysis != "本题未单列分析。":
            explanation = explanation.replace("【分析】" + analysis, "", 1).strip()
        if not explanation:
            explanation = analysis_remainder
    else:
        explanation = solution_body.strip()
    if answer == "详见解析" and explicit_answer and explicit_answer not in explanation:
        explanation = explicit_answer + "\n\n" + explanation
    explanation = explanation.strip() or "本题未单列解析。"
    return {
        "answer": answer,
        "answer_source": answer_source,
        "answer_source_page": (recovered or {}).get("source_page") if answer_source == "pdf-text-recovery" else None,
        "answer_source_evidence": (recovered or {}).get("evidence") if answer_source == "pdf-text-recovery" else None,
        "analysis": analysis,
        "explanation": explanation,
        "detail_markers": detail_markers,
    }


def quote_nested(value: str) -> list[str]:
    return [f"> > {line}" if line else "> >" for line in value.splitlines() or [""]]


def format_answer_note(qid: str, solution_body: str, fields: dict[str, Any], callout_title: str) -> str:
    values = [
        "---",
        f'answer_for: "{qid}"',
        "answer_provenance: authoritative",
        "answer_source_kind: embedded-exam-solution",
        f'answer_value_source: "{fields["answer_source"]}"',
        f"answer_source_body_sha256: {sha256_text(solution_body)}",
    ]
    if fields.get("answer_source_page") is not None:
        values.append(f"answer_value_source_page: {fields['answer_source_page']}")
    values.extend([
        "---",
        "",
        f"> [!faq]- {callout_title}",
        ">",
        f"> > [!success]- **【答案】** {fields['answer']}",
        ">",
        "> > [!note]- **【分析】**",
        *quote_nested(fields["analysis"]),
        ">",
        "> > [!note]- **【解析】**",
        *quote_nested(fields["explanation"]),
        "",
    ])
    return "\n".join(values)


@contextmanager
def locked_registry(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def find_next_q_number(vault_root: Path) -> int:
    highest = 0
    for path in vault_root.rglob("Q*.md") if vault_root.is_dir() else []:
        match = re.fullmatch(r"Q(\d{8})", path.stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def allocate_qids(registry_path: Path, identities: list[str], vault_root: Path) -> dict[str, str]:
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")
    with locked_registry(lock_path):
        if registry_path.is_file():
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            if registry.get("schema_version") != 1:
                raise ParserError("Unsupported question-ID registry schema")
        else:
            registry = {
                "schema_version": 1,
                "next_number": find_next_q_number(vault_root),
                "assignments": {},
            }
        assignments = registry.setdefault("assignments", {})
        next_number = int(registry.get("next_number", 1))
        used_codes = {str(value) for value in assignments.values()}
        used_codes.update(str(value) for value in registry.get("allocated_qids", []))
        result: dict[str, str] = {}
        for identity in identities:
            if identity not in assignments:
                while f"Q{next_number:08d}" in used_codes:
                    next_number += 1
                assignments[identity] = f"Q{next_number:08d}"
                used_codes.add(assignments[identity])
                next_number += 1
            result[identity] = str(assignments[identity])
        registry["next_number"] = next_number
        write_json(registry_path, registry)
        return result


def vault_embed(target: Path, vault_root: Path) -> str:
    return f"![[{target.resolve().relative_to(vault_root.resolve()).as_posix()}]]"


def rebase_images(text: str, depth: int) -> str:
    prefix = "../" * depth
    def replace(match: re.Match[str]) -> str:
        destination = match.group("dest").strip().strip("<>").replace("\\", "/")
        if urlparse(destination).scheme or destination.startswith("#"):
            return match.group(0)
        image_index = destination.casefold().find("images/")
        if image_index < 0:
            return match.group(0)
        return f"![{match.group('alt')}]({prefix}{destination[image_index:]})"
    return IMAGE_RE.sub(replace, text)


def output_graph_root(output_root: Path, title: str) -> Path:
    year_match = re.search(r"(?:19|20)\d{2}", title)
    parent = output_root
    if year_match and output_root.name != year_match.group(0):
        parent = output_root / year_match.group(0)
    return parent / safe_component(title)


def copy_assets(asset_root: Path | None, graph_root: Path) -> int:
    if asset_root is None or not asset_root.is_dir():
        return 0
    destination = graph_root / "images"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(asset_root, destination)
    return sum(1 for path in destination.rglob("*") if path.is_file())


def local_image_errors(path: Path, text: str, graph_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    for match in IMAGE_RE.finditer(text):
        destination = match.group("dest").strip().strip("<>")
        if urlparse(destination).scheme or destination.startswith("#"):
            continue
        resolved = (path.parent / destination).resolve()
        if not resolved.is_file() and graph_root:
            resolved = (graph_root / destination).resolve()
        if not resolved.is_file():
            errors.append(destination)
    return errors


def audit_manifest(manifest_path: Path, overwrite: bool = True) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    graph_root = Path(manifest["graph_root"])
    source = Path(manifest["source_pdf"])
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    numbers = [int(item["number"]) for item in manifest["questions"]]
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append({"kind": "question-ledger", "numbers": numbers})
    for section in manifest["sections"]:
        if section.get("expected_count") is not None and section["expected_count"] != section["detected_count"]:
            errors.append({"kind": "section-count-mismatch", "section": section["title"]})
        section_path = Path(section["note_path"])
        if not section_path.is_file():
            errors.append({"kind": "missing-section-note", "section": section["title"]})
        else:
            section_text = section_path.read_text(encoding="utf-8")
            for question in [item for item in manifest["questions"] if item["section_index"] == section["index"]]:
                q_path = Path(question["question_path"])
                if section_text.count(vault_embed(q_path, Path(manifest["vault_root"]))) != 1:
                    errors.append({"kind": "question-embed", "number": question["number"]})
    for question in manifest["questions"]:
        q_path = Path(question["question_path"])
        a_path = Path(question["answer_path"])
        if not q_path.is_file() or not a_path.is_file():
            errors.append({"kind": "missing-note", "number": question["number"]})
            continue
        q_text = q_path.read_text(encoding="utf-8")
        a_text = a_path.read_text(encoding="utf-8")
        body_match = re.search(r"<!-- question-source:start -->\n(?P<body>.*?)\n<!-- question-source:end -->", q_text, re.DOTALL)
        if body_match is None or sha256_text(body_match.group("body").rstrip() + "\n") != question["question_body_sha256"]:
            errors.append({"kind": "question-content-drift", "number": question["number"]})
        if q_text.count(vault_embed(a_path, Path(manifest["vault_root"]))) != 1:
            errors.append({"kind": "answer-embed", "number": question["number"]})
        required = (
            "> [!faq]- ",
            "> > [!success]- **【答案】** ",
            "> > [!note]- **【分析】**",
            "> > [!note]- **【解析】**",
        )
        if not all(value in a_text for value in required):
            errors.append({"kind": "answer-callout", "number": question["number"]})
        analysis_match = re.search(
            r"> > \[!note\]- \*\*【分析】\*\*\n(?P<body>.*?)(?=\n>\n> > \[!note\]- \*\*【解析】\*\*)",
            a_text,
            re.DOTALL,
        )
        explanation_match = re.search(
            r"> > \[!note\]- \*\*【解析】\*\*\n(?P<body>.*)\Z",
            a_text,
            re.DOTALL,
        )
        analysis_text = analysis_match.group("body") if analysis_match else ""
        explanation_text = explanation_match.group("body") if explanation_match else ""
        if "【分析】" in analysis_text:
            errors.append({"kind": "duplicate-analysis-marker", "number": question["number"]})
        for detail_marker in question.get("detail_markers", []):
            if detail_marker in analysis_text:
                errors.append({"kind": "detail-in-analysis", "number": question["number"], "marker": detail_marker})
            if detail_marker not in explanation_text:
                errors.append({"kind": "missing-detail-in-explanation", "number": question["number"], "marker": detail_marker})
        if f"answer_source_body_sha256: {question['solution_body_sha256']}" not in a_text:
            errors.append({"kind": "answer-source-provenance", "number": question["number"]})
        if f'answer_value_source: "{question["answer_source"]}"' not in a_text:
            errors.append({"kind": "answer-value-provenance", "number": question["number"]})
        answer_match = re.search(r"(?m)^> > \[!success\]- \*\*【答案】\*\* (.+)$", a_text)
        if question["choice"] and (answer_match is None or not re.fullmatch(r"[A-F]+", answer_match.group(1).strip())):
            errors.append({"kind": "choice-answer", "number": question["number"]})
        if question["choice"] and question["answer_source"] not in {"explicit-answer", "explicit-conclusion", "pdf-text-recovery"}:
            errors.append({"kind": "choice-answer-source", "number": question["number"]})
        if question["answer_source"] == "pdf-text-recovery" and not question.get("pdf_answer_recovery"):
            errors.append({"kind": "missing-pdf-answer-evidence", "number": question["number"]})
        if question["explanation_char_count"] < 8 or "本题未单列解析" in a_text:
            errors.append({"kind": "insubstantial-explanation", "number": question["number"]})
        if manifest.get("provenance_block_count", 0) and not question.get("source_provenance"):
            errors.append({"kind": "missing-source-provenance", "number": question["number"]})
        for path, text in ((q_path, q_text), (a_path, a_text)):
            for destination in local_image_errors(path, text, graph_root=graph_root):
                errors.append({"kind": "broken-image", "number": question["number"], "destination": destination})
    root_note = Path(manifest["root_note"])
    if not root_note.is_file():
        errors.append({"kind": "missing-root-note"})
    else:
        root_text = root_note.read_text(encoding="utf-8")
        for section in manifest["sections"]:
            section_path = Path(section["note_path"])
            if root_text.count(vault_embed(section_path, Path(manifest["vault_root"]))) != 1:
                errors.append({"kind": "section-embed", "section": section["title"]})
    image_root = graph_root / "images"
    for path in graph_root.rglob("*"):
        if path.is_file() and path.suffix.casefold() == ".canvas":
            errors.append({"kind": "unexpected-canvas", "path": str(path)})
        elif path.is_file() and path.suffix.casefold() not in {".md", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}:
            warnings.append({"kind": "unexpected-output-type", "path": str(path)})
        stem = path.stem if path.is_file() else path.name
        if image_root not in path.parents and any(char != "_" and not char.isalnum() for char in stem):
            errors.append({"kind": "unsafe-generated-path", "path": str(path)})
    question_note_count = sum(1 for path in graph_root.rglob("Q*.md") if path.parent.name == "题目")
    answer_note_count = sum(1 for path in graph_root.rglob("Q*A1.md") if path.parent.name == "answers")
    if question_note_count != len(manifest["questions"]):
        errors.append({"kind": "question-file-count", "actual": question_note_count})
    if answer_note_count != len(manifest["questions"]):
        errors.append({"kind": "answer-file-count", "actual": answer_note_count})
    if not source.is_file() or sha256_file(source) != manifest["source_sha256"]:
        errors.append({"kind": "source-drift"})
    raw_markdown = Path(manifest["raw_markdown"])
    if not raw_markdown.is_file() or sha256_file(raw_markdown) != manifest["raw_markdown_sha256"]:
        errors.append({"kind": "raw-markdown-drift"})
    result = {
        "schema_version": 1,
        "stage": "final-audit",
        "status": "passed" if not errors and not warnings else "review_required",
        "source_hashes_unchanged": not any(
            item["kind"] in {"source-drift", "raw-markdown-drift"} for item in errors
        ),
        "question_count": len(manifest["questions"]),
        "section_count": len(manifest["sections"]),
        "errors": errors,
        "warnings": warnings,
        "manifest": str(manifest_path),
        "graph_root": str(graph_root),
    }
    report_path = Path(manifest["final_audit_report"])
    if overwrite or not report_path.exists():
        write_json(report_path, result)
    return result


def parse_paper(source: Path, markdown_path: Path, asset_root: Path | None, args: argparse.Namespace, ocr_report: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    source_hash = sha256_file(source)
    markdown = markdown_path.read_text(encoding="utf-8-sig")
    raw_hash = sha256_file(markdown_path)
    lines, sections, questions = parse_sections(markdown)
    numbers = [item["number"] for item in questions]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ReviewRequired(f"Question ledger is not continuous 1..N: {numbers}")
    for section in sections:
        if section["expected_count"] is not None and section["expected_count"] != section["detected_count"]:
            raise ReviewRequired(f"Section count mismatch: {section['title']}")
    title = args.title or source.stem
    vault_root = Path(args.vault_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    graph_root = Path(args.graph_root).expanduser().resolve() if args.graph_root else output_graph_root(output_root, title)
    staging_root = Path(args.staging_root).expanduser().resolve() if args.staging_root else vault_root / ".exam-paper-parser" / "runs" / source_hash[:16]
    registry_path = Path(args.registry).expanduser().resolve() if args.registry else vault_root / ".question-type-graph" / "question-id-registry.json"
    if graph_root != vault_root and vault_root not in graph_root.parents:
        raise ParserError(f"Graph output must be inside the configured vault: {graph_root}")
    if graph_root.exists() and any(graph_root.iterdir()):
        if not args.overwrite:
            raise ParserError(f"Graph output already exists; pass --overwrite: {graph_root}")
        if graph_root == vault_root or vault_root not in graph_root.parents:
            raise ParserError(f"Refusing to replace a graph root outside the configured vault: {graph_root}")
        shutil.rmtree(graph_root)
    graph_root.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)
    provenance_blocks: list[dict[str, Any]] = []
    if args.provenance and Path(args.provenance).is_file():
        provenance_blocks = load_provenance_blocks(Path(args.provenance))
    elif ocr_report and Path(str(ocr_report.get("raw_markdown", ""))).name == "raw.md":
        candidate = Path(ocr_report["raw_markdown"]).parent / "provenance-blocks.json"
        if candidate.is_file():
            provenance_blocks = load_provenance_blocks(candidate)
    pdf_answers = pdf_choice_answers(source)
    for question in questions:
        question["provenance"] = provenance_for(question["question_body"], provenance_blocks)
        question["choice"] = is_choice_question(question["question_body"])
        recovered = pdf_answers.get(question["number"]) if question["choice"] else None
        question["solution_fields"] = solution_fields(question["solution_body"], question["choice"], recovered)
        question["pdf_answer_recovery"] = (
            recovered if question["solution_fields"]["answer_source"] == "pdf-text-recovery" else None
        )
        question["identity"] = sha256_text(f"{source_hash}\n{question['number']}\n{question['question_body']}")
    qids = allocate_qids(registry_path, [item["identity"] for item in questions], vault_root)
    copied_assets = copy_assets(asset_root, graph_root)
    section_notes: list[Path] = []
    manifest_questions: list[dict[str, Any]] = []
    for section_index, section in enumerate(sections):
        folder_label = safe_component(clean_section_title(section["title"]))
        section_dir = graph_root / folder_label
        section_note = section_dir / f"{folder_label}.md"
        section_notes.append(section_note)
        embeds: list[str] = []
        for question in [item for item in questions if item["section_index"] == section_index]:
            qid = qids[question["identity"]]
            q_path = section_dir / "题目" / f"{qid}.md"
            a_path = section_dir / "题目" / "answers" / f"{qid}A1.md"
            q_body = rebase_images(question["question_body"], 2)
            solution_body = rebase_images(question["solution_body"], 3)
            fields = dict(question["solution_fields"])
            fields["analysis"] = rebase_images(fields["analysis"], 3)
            fields["explanation"] = rebase_images(fields["explanation"], 3)
            provenance = question["provenance"] or {}
            metadata = [
                "---",
                f'question_id: "exam:{source_hash[:12]}:{question["number"]}"',
                f'question_number: "{question["number"]}"',
                f'context_key: "{source_hash[:12]}"',
                f'question_source: "{section_note}"',
                f"question_body_sha256: {sha256_text(q_body)}",
            ]
            if provenance.get("source_page") is not None:
                metadata.append(f"source_pdf_page: {provenance['source_page']}")
            if provenance.get("bbox") is not None:
                metadata.append(f"source_pdf_bbox: {json.dumps(provenance['bbox'])}")
            if provenance.get("match"):
                metadata.append(f'source_provenance_match: "{provenance["match"]}"')
            metadata.extend([
                f"source_markdown_line: {question['source_start_line']}",
                'question_kind: "exam-question"',
                'answer_handling: "separate-authoritative"',
                '重要程度: "重要"',
                "answer_status: matched",
                "---",
                "<!-- question-source:start -->",
                q_body.rstrip(),
                "<!-- question-source:end -->",
                "",
                vault_embed(a_path, vault_root),
                "",
            ])
            write_text(q_path, "\n".join(metadata))
            write_text(a_path, format_answer_note(qid, solution_body, fields, f"{title}解析"))
            embeds.append(vault_embed(q_path, vault_root))
            manifest_questions.append({
                "number": question["number"],
                "qid": qid,
                "section_index": section_index,
                "question_path": str(q_path),
                "answer_path": str(a_path),
                "question_body_sha256": sha256_text(q_body),
                "solution_body_sha256": sha256_text(solution_body),
                "choice": question["choice"],
                "answer": fields["answer"],
                "answer_source": fields["answer_source"],
                "explanation_char_count": len(normalize_match(fields["explanation"])),
                "detail_markers": fields["detail_markers"],
                "source_start_line": question["source_start_line"],
                "source_solution_line": question["source_solution_line"],
                "source_provenance": provenance or None,
                "pdf_answer_recovery": question["pdf_answer_recovery"],
            })
        write_text(section_note, f"## {section['title']}\n\n" + "\n".join(embeds) + "\n")
    preamble = "\n".join(lines[: sections[0]["start_index"]]).rstrip()
    root_note = graph_root / safe_filename(f"{title}.md", "exam.md")
    write_text(root_note, preamble + "\n\n" + "\n".join(vault_embed(path, vault_root) for path in section_notes) + "\n")
    manifest_path = staging_root / "exam-paper-manifest.json"
    final_audit = staging_root / "final-audit-report.json"
    manifest = {
        "schema_version": 1,
        "stage": "exam-paper-parser",
        "status": "generated",
        "source_pdf": str(source),
        "source_sha256": source_hash,
        "raw_markdown": str(markdown_path),
        "raw_markdown_sha256": raw_hash,
        "vault_root": str(vault_root),
        "graph_root": str(graph_root),
        "staging_root": str(staging_root),
        "root_note": str(root_note),
        "final_audit_report": str(final_audit),
        "registry": str(registry_path),
        "provenance_block_count": len(provenance_blocks),
        "sections": [
            {
                "index": index,
                "title": item["title"],
                "expected_count": item["expected_count"],
                "detected_count": item["detected_count"],
                "note_path": str(section_notes[index]),
            }
            for index, item in enumerate(sections)
        ],
        "questions": manifest_questions,
        "metrics": {
            "question_count": len(manifest_questions),
            "answer_count": len(manifest_questions),
            "section_count": len(sections),
            "asset_count": copied_assets,
            "pdf_answer_recovery_count": sum(1 for item in manifest_questions if item["pdf_answer_recovery"]),
            "llm_calls": 0,
            "adapter_reviews": 0,
            "duration_seconds": round(time.monotonic() - started, 3),
            "ocr_cache_hit": bool((ocr_report or {}).get("cache_hit")),
        },
    }
    write_json(manifest_path, manifest)
    audit = audit_manifest(manifest_path)
    manifest["status"] = audit["status"]
    write_json(manifest_path, manifest)
    return {**audit, "metrics": manifest["metrics"], "root_note": str(root_note)}


def resolve_source(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise ParserError(f"Source is not an existing PDF: {path}")
    return path


def command_run(args: argparse.Namespace) -> dict[str, Any]:
    source = resolve_source(args.source_pdf)
    source_hash = sha256_file(source)
    vault_root = Path(args.vault_root).expanduser().resolve()
    cache_root = Path(args.cache_root).expanduser().resolve() if args.cache_root else vault_root / ".exam-paper-parser" / "cache" / source_hash
    if args.markdown:
        markdown_path = Path(args.markdown).expanduser().resolve()
        asset_root = Path(args.assets_root).expanduser().resolve() if args.assets_root else markdown_path.parent / "images"
        ocr_report = {"cache_hit": True, "raw_markdown": str(markdown_path)}
    else:
        ocr_report = mineru_ocr(source, cache_root, args)
        markdown_path = Path(ocr_report["raw_markdown"])
        asset_root = Path(ocr_report["asset_root"])
    return parse_paper(source, markdown_path, asset_root if asset_root.is_dir() else None, args, ocr_report)


def command_audit(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.manifest).expanduser().resolve()
    if not path.is_file():
        raise ParserError(f"Manifest does not exist: {path}")
    return audit_manifest(path)


def command_batch(args: argparse.Namespace) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    sources = list(dict.fromkeys(str(resolve_source(value)) for value in args.source_pdfs))
    targets: dict[Path, str] = {}
    for source in sources:
        target = output_graph_root(Path(args.output_root).expanduser().resolve(), Path(source).stem)
        if target in targets:
            raise ParserError(f"Batch output collision for {targets[target]} and {source}: {target}")
        targets[target] = source
    def run_one(source: str) -> dict[str, Any]:
        values = argparse.Namespace(**vars(args))
        values.source_pdf = source
        values.markdown = None
        values.assets_root = None
        values.graph_root = None
        values.staging_root = None
        values.title = None
        values.provenance = None
        return command_run(values)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(run_one, source): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                results.append({"source_pdf": source, **future.result()})
            except Exception as exc:
                results.append({"source_pdf": source, "status": "failed", "message": str(exc), "error_type": type(exc).__name__})
    return {
        "schema_version": 1,
        "stage": "exam-paper-parser-batch",
        "status": "passed" if results and all(item.get("status") == "passed" for item in results) else "review_required",
        "paper_count": len(results),
        "passed_count": sum(1 for item in results if item.get("status") == "passed"),
        "results": sorted(results, key=lambda item: item["source_pdf"]),
    }


def add_common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--vault-root", required=True)
    subparser.add_argument("--output-root", required=True)
    subparser.add_argument("--registry")
    subparser.add_argument("--cache-root")
    subparser.add_argument("--env-file")
    subparser.add_argument("--base-url")
    subparser.add_argument("--poll-interval", type=float, default=5.0)
    subparser.add_argument("--max-polls", type=int, default=180)
    subparser.add_argument("--request-timeout", type=float, default=120.0)
    subparser.add_argument("--overwrite", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fast deterministic parser for standardized exam-and-solution PDFs.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("source_pdf")
    add_common(run)
    run.add_argument("--markdown")
    run.add_argument("--assets-root")
    run.add_argument("--provenance")
    run.add_argument("--graph-root")
    run.add_argument("--staging-root")
    run.add_argument("--title")
    batch = commands.add_parser("batch")
    batch.add_argument("source_pdfs", nargs="+")
    add_common(batch)
    batch.add_argument("--jobs", type=int, default=4)
    audit = commands.add_parser("audit")
    audit.add_argument("manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            result = command_run(args)
        elif args.command == "batch":
            result = command_batch(args)
        else:
            result = command_audit(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 2
    except ReviewRequired as exc:
        print(json.dumps({"schema_version": 1, "status": "review_required", "message": str(exc)}, ensure_ascii=False))
        return 2
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

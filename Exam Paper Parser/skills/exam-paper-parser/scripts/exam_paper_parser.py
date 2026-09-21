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
import unicodedata
from urllib import request as urllib_request
from urllib.parse import urlparse, urlsplit
import zipfile

from pypdf import PdfReader, PdfWriter


MAX_PAGES = 200
MAX_BYTES = 200 * 1024 * 1024
ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}
TERMINAL_STATES = {"done", "failed"}
IMAGE_RE = re.compile(r"!\[(?P<alt>[^]]*)\]\((?P<dest>[^)]+)\)")
QUESTION_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[\(（])?(?P<number>\d+)(?:[\)）]|[.．、])\s*"
)
MARKER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:(?:【|\[)(?P<label>答案|解析|分析|详解|解|解一|解二|思路|解答|小问\s*\d+\s*详解)(?:】|\])?[:：]?|(?P<label2>答案|解析|分析|详解|解答)[:：])"
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
    clean = re.sub(r'[/\\:*?"<>|]', '_', path.stem).strip()
    return (clean or fallback) + path.suffix.lower()


def clean_section_title(title: str) -> str:
    cleaned = title.split("：", 1)[0].split(":", 1)[0].strip()
    return cleaned


def normalize_match(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value, flags=re.UNICODE).casefold()


CJK_SUPP_MAP = {
    "⻘": "青", "⻓": "长", "⻔": "门", "⻚": "页", "⻦": "鸟", "⻥": "鱼",
    "⻮": "齿", "⻢": "马", "⻝": "食", "⻎": "辶", "⺶": "羊", "⺼": "肉",
    "⻄": "西", "⾦": "金", "⽊": "木", "⽔": "水", "⽕": "火", "⼟": "土",
    "⼭": "山", "⽉": "月", "⼀": "一", "⾼": "高", "⼆": "二", "⼗": "十",
    "九": "九"
}


def normalize_cjk_text(text: str) -> str:
    translated = text.translate(str.maketrans(CJK_SUPP_MAP))
    return unicodedata.normalize("NFKC", translated)


def extract_title_from_pdf(pdf_path: Path) -> str | None:
    try:
        reader = PdfReader(pdf_path)
        if not reader.pages:
            return None
        text = reader.pages[0].extract_text() or ""
        text = normalize_cjk_text(text)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in lines[:8]:
            clean_l = re.sub(r"\s+", "", line)
            if re.search(r"(?:19|20)\d{2}.*?(?:试卷|试题)", clean_l):
                return clean_l
        first_chunk = re.sub(r"\s+", "", text[:400])
        m = re.search(r"((?:19|20)\d{2}[-~–—]\d{4}学年.*?(?:试卷|试题)(?:（.*?）)?)", first_chunk)
        if m:
            return m.group(1)
    except Exception:
        return None
    return None


def standardize_paper_title(raw_title_or_path: str | Path, pdf_path: Path | None = None) -> str:
    path = Path(raw_title_or_path)
    title = path.stem
    actual_pdf = pdf_path or (path if path.suffix.casefold() == ".pdf" and path.is_file() else None)

    title = normalize_cjk_text(title)

    is_anonymous = bool(re.match(r"^(?:xPad_paper_|paper_|doc_|[a-fA-F0-9_-]{16,})", title))
    if is_anonymous and actual_pdf and actual_pdf.is_file():
        extracted = extract_title_from_pdf(actual_pdf)
        if extracted:
            title = extracted

    title = re.sub(r"_答案分开版本(?:_\d+)?", "", title)
    title = re.sub(r"_解析版(?:_\d+)?", "", title)
    title = re.sub(r"[-_]\d{10,}$", "", title)
    title = re.sub(r"[❖★◆■▲▼●]+", "", title)
    title = re.sub(r"(\d{4})\s*[~～–—_]\s*(\d{4})", r"\1-\2", title)
    title = title.replace("(", "（").replace(")", "）")
    title = re.sub(r"\s+", "", title)
    return title.strip("-_ ")


def analyze_paper_metadata_rules(title: str) -> dict[str, str]:
    meta = {
        "年份": "",
        "学校": "",
        "地区": "",
        "年级": "",
        "学期": "",
        "考试种类": "",
    }
    # 1. 年份
    m_year = re.search(r"(20\d{2}\s*[-~～–—_]\s*20\d{2}|20\d{2})", title)
    if m_year:
        meta["年份"] = re.sub(r"\s*[~～–—_]\s*", "-", m_year.group(1))

    # 2. 年级
    m_grade = re.search(r"(高[一二三]|初[一二三]|七年级|八年级|九年级)", title)
    if m_grade:
        meta["年级"] = m_grade.group(1)

    # 3. 学期
    if re.search(r"[（\(]?上[期学]?[）\)]?|高[一二三]上", title):
        meta["学期"] = "上"
    elif re.search(r"[（\(]?下[期学]?[）\)]?|高[一二三]下", title):
        meta["学期"] = "下"

    # 4. 考试种类
    if "第一次月考" in title or "第1次月考" in title or "一月考" in title:
        meta["考试种类"] = "第一次月考"
    elif "第二次月考" in title or "第2次月考" in title or "二月考" in title:
        meta["考试种类"] = "第二次月考"
    elif "第三次月考" in title or "第3次月考" in title or "三月考" in title:
        meta["考试种类"] = "第三次月考"
    elif "月考" in title:
        m_month = re.search(r"(\d+月份)", title)
        meta["考试种类"] = f"月考（{m_month.group(1)}）" if m_month else "月考"
    elif "期中" in title:
        meta["考试种类"] = "期中"
    elif "期末" in title:
        meta["考试种类"] = "期末"
    elif "开学" in title:
        meta["考试种类"] = "开学考"
    elif "模拟" in title or "一模" in title or "二模" in title or "三模" in title:
        meta["考试种类"] = "模拟考"
    elif "质检" in title or "质量检测" in title or "调研" in title:
        meta["考试种类"] = "质检"
    elif "联考" in title:
        meta["考试种类"] = "联考"
    else:
        meta["考试种类"] = "期中"

    # 5. 地区
    regions = [
        "内蒙古", "呼和浩特", "包头", "赤峰", "乌海", "通辽", "鄂尔多斯",
        "呼伦贝尔", "巴彦淖尔", "乌兰察布", "兴安盟", "锡林郭勒", "阿拉善",
        "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
        "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
        "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "宁夏", "新疆"
    ]
    found_regions = [r for r in regions if r in title]
    if "内蒙古" in found_regions and len(found_regions) > 1:
        other = [r for r in found_regions if r != "内蒙古"][0]
        meta["地区"] = f"内蒙古{other}"
    elif found_regions:
        meta["地区"] = found_regions[0]

    # 6. 学校
    cleaned = title
    if meta["年份"]:
        cleaned = cleaned.replace(meta["年份"], "")
    cleaned = re.sub(r"学年|试卷|数学|（理科）|（文科）|理科|文科|答案分开版本|解析版", "", cleaned)
    school_matches = re.findall(r"((?:[^\s（\(]+?)?(?:[一二三四五六七八九十\d]+中(?:学)?|高级中学|中学|附中|外校|实验学校|名校联盟))", cleaned)
    if school_matches:
        sch = school_matches[-1]
        sch = re.sub(r"^[^\s]*?[区县旗]", "", sch)
        sch = re.sub(r"^内蒙古", "", sch)
        meta["学校"] = sch

    return meta


def call_llm_json(prompt: str, env: dict[str, str] | None = None, system_prompt: str = "") -> dict[str, Any] | None:
    env_map = env or {}
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or env_map.get("OPENAI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or env_map.get("DEEPSEEK_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or env_map.get("LLM_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or env_map.get("DASHSCOPE_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or env_map.get("QWEN_API_KEY")
    )
    if not api_key:
        return None

    base_url = (
        os.environ.get("LLM_BASE_URL")
        or env_map.get("LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or env_map.get("OPENAI_BASE_URL")
    )
    if not base_url:
        if "deepseek" in api_key.lower() or os.environ.get("DEEPSEEK_API_KEY") or env_map.get("DEEPSEEK_API_KEY"):
            base_url = "https://api.deepseek.com/v1"
            model = "deepseek-chat"
        elif os.environ.get("DASHSCOPE_API_KEY") or env_map.get("DASHSCOPE_API_KEY"):
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            model = "qwen-plus"
        else:
            base_url = "https://api.openai.com/v1"
            model = "gpt-4o-mini"
    else:
        model = os.environ.get("LLM_MODEL") or env_map.get("LLM_MODEL") or "deepseek-chat"

    url = f"{base_url.rstrip('/')}/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
    }
    req = urllib_request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            raw_json = m.group(1) if m else content
            return json.loads(raw_json)
    except Exception:
        return None


def analyze_paper_metadata(title: str, env: dict[str, str] | None = None) -> dict[str, str]:
    meta = analyze_paper_metadata_rules(title)
    llm_res = call_llm_json(
        f"请分析以下试卷标题，提取JSON属性：年份、学校、地区、年级、学期、考试种类。\n"
        f"注意：考试种类必须分类为以下之一：期中、期末、第一次月考、第二次月考、第三次月考、月考、开学考、模拟考、质检、联考。\n"
        f"试卷标题：{title}",
        env=env,
        system_prompt="你是一个教育试卷元数据分析专家，请只输出纯JSON对象，包含keys: 年份, 学校, 地区, 年级, 学期, 考试种类。"
    )
    if isinstance(llm_res, dict):
        for k in ["年份", "学校", "地区", "年级", "学期", "考试种类"]:
            val = str(llm_res.get(k, "")).strip()
            if val:
                meta[k] = val
    return meta


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
    if path.suffix.lower() in (".doc", ".docx"):
        return 1
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
    if source.suffix.lower() in (".doc", ".docx"):
        digest = sha256_file(source)[:16]
        return [PdfPart(source, 1, 1, 1, 1, f"exam-{digest}-001")]
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
    
    last_err: Exception | None = None
    for attempt in range(3):
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
            connection.close()
            if 200 <= status < 300:
                return
            raise ParserError(f"MinerU upload failed with HTTP {status}")
        except Exception as exc:
            last_err = exc
            try:
                connection.close()
            except Exception:
                pass
            time.sleep(2.0 * (attempt + 1))
    raise ParserError(f"MinerU upload failed after 3 attempts: {last_err}")


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


MARKER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:【|\[)?(?P<label>答案|解析|分析|详解|解答(?!题)|思路点拨|试题解析|思路分析|小问\s*\d+\s*详解)(?:】|\])?[:：]?"
)
SECTION_KEYWORDS = ("单选题", "多选题", "选择题", "填空题", "解答题", "计算题", "证明题", "应用题")
ORDINAL_RE = re.compile(r"^[一二三四五六七八九十]+[、.．]")


class ParserError(RuntimeError):
    pass


class ReviewRequired(ParserError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def is_section_heading(line: str) -> tuple[bool, str]:
    match = re.match(r"^\s*(?P<hashes>#{1,6})?\s*(?P<title>.+?)\s*$", line)
    if not match:
        return False, ""
    title = match.group("title").strip()
    if any(container in title for container in ("第一部分", "第二部分", "第三部分", "选择题部分", "非选择题部分", "卷I", "卷II", "卷Ⅰ", "卷Ⅱ")):
        return False, ""
    has_keyword = any(keyword in title for keyword in SECTION_KEYWORDS) or bool(re.search(r"第\d+题", title))
    hashes = match.group("hashes") or ""
    authority = len(hashes) >= 2 or ORDINAL_RE.match(title) is not None
    return bool(has_keyword and authority), title


def expected_count(title: str) -> int | None:
    match = re.search(r"本题共\s*(\d+)\s*小题", title)
    return int(match.group(1)) if match else None


def split_inline_markers(text: str) -> str:
    text = re.sub(
        r"(?<!^)[ \t]*(?=(?:【|\[)(?:答案|解析|分析|详解|解答(?!题)|思路点拨|试题解析|思路分析|小问\s*\d+\s*详解)(?:】|\])?[:：]?|(?:答案|解析|分析|详解|解答(?!题))[:：])",
        "\n",
        text,
    )
    text = re.sub(r"(?<=[。．.！!？?）\)])[ \t]*(?=[一二三四五六七八九十]+[、.．])", "\n", text)
    text = re.sub(r"(?<=[。．.！!？?）\)])[ \t]*(?=[\(（]\d{1,2}[\)）][ \t]*[\u4e00-\u9fa5\$])", "\n", text)
    text = re.sub(
        r"(?<!^)[ \t]*(?=(?:(?<=[。\.\!\?！\？\)])|(?<=正确\.)|(?<=错误\.))\s*\d+[.．、][ \t]*(?:[\u4e00-\u9fa5]|\$|[A-Za-z]|\(ND|（))",
        "\n",
        text,
    )
    text = re.sub(
        r"(?<=[。．.！!？?）\)])[ \t]*(?=\d+[.．、][ \t]*[\u4e00-\u9fa5\$])",
        "\n",
        text,
    )
    return text



def marker_name(line: str) -> str | None:
    match = MARKER_RE.match(line)
    if not match:
        return None
    label = match.group("label") or match.group("label2")
    if not label:
        return None
    if label in ("解", "解一", "解二", "解答"):
        return "解析"
    return "详解" if label.endswith("详解") else label


def marker_label(line: str) -> str | None:
    match = MARKER_RE.match(line)
    if not match:
        return None
    return match.group("label") or match.group("label2")


def first_solution_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], 1):
        if marker_name(line):
            return index
    return None


def is_zuodaqu_line(line: str) -> bool:
    clean = re.sub(r"[#\s*：:\-]", "", line)
    return clean in ("作答区", "作答区域", "答题区", "答题区域")


def is_question_line(line: str) -> bool:
    if is_zuodaqu_line(line):
        return False
    match = QUESTION_RE.match(line)
    if not match:
        return False
    number = int(match.group("number"))
    if number > 35 or number < 1:
        return False
    raw_prefix = line[:match.end()].strip()
    rest = line[match.end():].strip()
    if raw_prefix.startswith("(") or raw_prefix.startswith("（") or raw_prefix.startswith("【") or raw_prefix.startswith("["):
        has_options = bool(re.search(r"[\(（][A-D][\)）]|(?<![A-Za-z])[A-D][.．、]", rest))
        has_question_stem = any(rest.startswith(w) for w in ("已知", "若", "在", "设", "函数", "定义", "观察", "某", "直", "圆", "曲线", "如图", "极坐标", "向量", "平面", "本小题", "本题", "答")) or "___" in rest or "（）" in rest or "()" in rest
        if not (has_options or has_question_stem):
            return False
    if any(kw in rest for kw in ("答卷前", "答题卡", "准考证号", "2B 铅笔", "2B铅笔", "答题纸", "作答前", "试卷共", "本场考试", "黑色字迹")):
        return False
    if rest.startswith("=") or rest.startswith("+") or rest.startswith("-"):
        return False
    return True


def repair_missing_question_numbers(markdown: str) -> str:
    lines = markdown.splitlines()
    question_indices = []
    for idx, line in enumerate(lines):
        if is_question_line(line):
            m = QUESTION_RE.match(line)
            question_indices.append((idx, int(m.group("number"))))
    
    if not question_indices:
        return markdown

    repaired_lines = list(lines)

    # Check if Q1 is missing at the start (first question number is > 1)
    first_idx, first_num = question_indices[0]
    if first_num > 1:
        for missing_num in range(1, first_num):
            for target_idx in range(0, first_idx):
                l = repaired_lines[target_idx].strip()
                if l and not l.startswith("#") and not l.startswith("【") and not is_question_line(l):
                    if re.match(r"^[A-D][.．、]\s*", l) and not ("（" in l or "(" in l or ("A." in l and "B." in l)):
                        continue
                    repaired_lines[target_idx] = f"{missing_num}. {l}"
                    break

    question_indices = []
    for idx, line in enumerate(repaired_lines):
        if is_question_line(line):
            m = QUESTION_RE.match(line)
            question_indices.append((idx, int(m.group("number"))))

    for i in range(len(question_indices) - 1):
        idx1, num1 = question_indices[i]
        idx2, num2 = question_indices[i + 1]
        gap = num2 - num1
        if 1 < gap <= 3:
            for step in range(1, gap):
                missing_num = num1 + step
                for target_idx in range(idx1 + 1, idx2):
                    l = repaired_lines[target_idx].strip()
                    if l and not l.startswith("#") and not l.startswith("【") and not is_question_line(l):
                        if re.match(r"^[A-D][.．、]\s*", l) and not ("（" in l or "(" in l or ("A." in l and "B." in l)):
                            continue
                        repaired_lines[target_idx] = f"{missing_num}. {l}"
                        break

    return "\n".join(repaired_lines)


def extract_standalone_answers(markdown: str) -> tuple[dict[int, str], dict[int, str]]:
    answers: dict[int, str] = {}
    solutions: dict[int, str] = {}

    # 1. Choice HTML table
    td_numbers = re.findall(r"<td>\s*(\d{1,2})\s*</td>", markdown)
    td_answers = re.findall(r"<td>\s*([A-D])\s*</td>", markdown)
    if len(td_numbers) > 0 and len(td_numbers) == len(td_answers):
        for num_str, ans_str in zip(td_numbers, td_answers):
            answers[int(num_str)] = ans_str.upper()

    # Only scan answer lines under "# ...答案" or "## 参考答案"
    answer_section_content = ""
    ans_match = re.search(r"(?:\n|^)#+\s*.*?(?:答案|解析).*?\n(?P<ans_body>.*)", markdown, re.DOTALL)
    if ans_match:
        answer_section_content = ans_match.group("ans_body")
    else:
        answer_section_content = markdown

    # 2. Short answer lines
    for line in answer_section_content.splitlines():
        if any(kw in line for kw in ("评分标准", "评阅", "本解答列出", "阅到底")):
            continue
        item_matches = re.finditer(r"(?:^|\s)(?:[\(（])?(?P<num>\d{1,2})(?:[\)）]|[.．、])?\s*(?P<ans>[A-D]|\$[^\$]+\$|[^\.\n]+?)(?=\s+(?:[\(（])?\d{1,2}|\s*\.\s*|\s*$)", line)
        for im in item_matches:
            n = int(im.group("num"))
            ans = im.group("ans").strip().rstrip(".").strip()
            if 1 <= n <= 35 and ans and not ans.startswith("解") and not ans.startswith("本解答") and not ans.startswith("评阅"):
                if n not in answers:
                    answers[n] = ans

    # 3. Question blocks with 【分析】/【解答】/故选/故答案为
    q_blocks = re.split(r"(?:\n|^)(?P<num>\d{1,2})[.．、]?\s*(?=(?:\(\d+\s*分\)|（\d+\s*分）|【分析】|【考点】|【解答】|（本小题|\[解\]))", markdown)
    if len(q_blocks) > 1:
        for i in range(1, len(q_blocks) - 1, 2):
            num = int(q_blocks[i])
            body = q_blocks[i+1].strip()

            if num not in answers:
                choice_m = re.search(r"故选[：:\s]*([A-D])", body)
                if choice_m:
                    answers[num] = choice_m.group(1).upper()
                else:
                    fill_m = re.search(r"故答案为[：:\s]*(.+?)(?=\.|\n|【|$)", body)
                    if fill_m:
                        answers[num] = fill_m.group(1).strip()

            if num not in solutions:
                sol_m = re.search(r"((?:【分析】|【解答】).*?)(?=\n【点评】|\n\d{1,2}[.．、]|\n#+|$)", body, re.DOTALL)
                if sol_m:
                    solutions[num] = sol_m.group(1).strip()

    # 4. Sequential unnumbered 【分析】...【解答】 blocks in document
    seq_blocks = re.findall(r"(【分析】.*?【解答】.*?)(?=\n【分析】|\n##|\s*$)", markdown, re.DOTALL)
    if seq_blocks:
        for idx, b_text in enumerate(seq_blocks, 1):
            if idx not in answers:
                choice_m = re.search(r"故选[：:\s]*([A-D])", b_text)
                if choice_m:
                    answers[idx] = choice_m.group(1).upper()
                else:
                    fill_m = re.search(r"故答案为[：:\s]*(.+?)(?=\.|\n|【|$)", b_text)
                    if fill_m:
                        answers[idx] = fill_m.group(1).strip()

            if idx not in solutions:
                sol_m = re.search(r"((?:【分析】|【解答】).*?)(?=\n【点评】|\n##|\s*$)", b_text, re.DOTALL)
                if sol_m:
                    solutions[idx] = sol_m.group(1).strip()

    # 5. Free response solutions starting with [解] or 【解析】
    sol_matches = re.finditer(r"(?:\n|^)(?P<num>\d{1,2})[.．、]?\s*(?P<body>(?:\[解\]|【解析】).*?)(?=\n\d{1,2}[.．、]?\s*(?:\[解\]|【解析】)|\n##|\s*$)", answer_section_content, re.DOTALL)
    for sm in sol_matches:
        n = int(sm.group("num"))
        b = sm.group("body").strip()
        if 1 <= n <= 35 and b and n not in solutions:
            solutions[n] = b

    return answers, solutions


def parse_sections(markdown: str) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    extracted_answers, extracted_solutions = extract_standalone_answers(markdown)
    markdown = repair_missing_question_numbers(markdown)
    lines: list[str] = []
    source_line_numbers: list[int] = []
    for source_line_number, raw_line in enumerate(markdown.splitlines(), 1):
        if is_zuodaqu_line(raw_line):
            continue
        if re.match(r"^\s*#{1,6}\s*", raw_line):
            lines.append(raw_line)
            source_line_numbers.append(source_line_number)
        else:
            split_lines = split_inline_markers(raw_line).splitlines() or [""]
            for sl in split_lines:
                if not is_zuodaqu_line(sl):
                    lines.append(sl)
                    source_line_numbers.append(source_line_number)
    
    raw_sections: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        matched, title = is_section_heading(line)
        if matched:
            raw_sections.append({
                "title": title,
                "clean_title": clean_section_title(title),
                "heading_line": source_line_numbers[index],
                "start_index": index,
            })
    if not raw_sections:
        raw_sections.append({"title": "一、试卷全图", "clean_title": "一、试卷全图", "heading_line": 1, "start_index": 0})

    # Detect answer boundary (two-part question-answer format)
    seen_titles: set[str] = set()
    q_sections: list[dict[str, Any]] = []
    ans_sections: list[dict[str, Any]] = []
    ans_boundary_index: int | None = None

    for s in raw_sections:
        clean_t = s["clean_title"]
        title_lower = s["title"].lower()
        is_ans_sec = any(kw in clean_t or kw in title_lower for kw in ("参考答案", "答案与解析", "试题解析", "答案及解析"))
        
        if (clean_t in seen_titles or is_ans_sec) and ans_boundary_index is None:
            ans_boundary_index = s["start_index"]
            ans_sections.append(s)
        elif ans_boundary_index is not None:
            ans_sections.append(s)
        else:
            seen_titles.add(clean_t)
            q_sections.append(s)

    if ans_boundary_index is None:
        for idx, line in enumerate(lines):
            if re.match(r"^\s*#{1,6}\s*.*(?:参考答案|答案与解析|试题解析|答案及解析)", line) or re.match(r"^\s*【(?:参考答案|答案与解析|试题解析)】", line):
                ans_boundary_index = idx
                ans_sections.append({
                    "title": line.strip().lstrip("#").strip(),
                    "clean_title": "参考答案",
                    "heading_line": source_line_numbers[idx],
                    "start_index": idx,
                })
                break

    sections = q_sections if q_sections else raw_sections
    
    # Parse answer blocks per answer section
    sec_answers: dict[int, dict[int, str]] = {}
    ans_pat = re.compile(r"^\s*(?:#{1,6}\s*)?(?P<num>\d{1,2})[.．、]\s*(?P<body>.*)")
    
    for a_idx, a_sec in enumerate(ans_sections):
        start = a_sec["start_index"] + 1
        end = ans_sections[a_idx + 1]["start_index"] if a_idx + 1 < len(ans_sections) else len(lines)
        sub_lines = lines[start:end]
        
        ans_starts: list[tuple[int, int]] = []
        for l_idx, l in enumerate(sub_lines):
            m = ans_pat.match(l)
            if m:
                num = int(m.group("num"))
                if 1 <= num <= 35:
                    ans_starts.append((l_idx, num))
        
        sec_answers[a_idx] = {}
        for pos, (l_idx, num) in enumerate(ans_starts):
            b_end = ans_starts[pos + 1][0] if pos + 1 < len(ans_starts) else len(sub_lines)
            body = "\n".join(sub_lines[l_idx:b_end]).strip()
            sec_answers[a_idx][num] = body

    def lookup_answer(sec_idx: int, local_num: int, global_num: int) -> str | None:
        if sec_idx in sec_answers and local_num in sec_answers[sec_idx]:
            return sec_answers[sec_idx][local_num]
        for a_map in sec_answers.values():
            if global_num in a_map:
                return a_map[global_num]
        if len(sec_answers) == 1 and 0 in sec_answers and local_num in sec_answers[0]:
            return sec_answers[0][local_num]
        return None

    def format_solution_from_body(ans_body: str, choice: bool, fill_in: bool = False, q_lines: list[str] | None = None) -> list[str]:
        # Strip leading question number like "1、", "1." or "## 15."
        cleaned = re.sub(r"^\s*(?:#{1,6}\s*)?\d{1,2}[.．、]\s*", "", ans_body.strip()).strip()
        q_text = "\n".join(q_lines or [])

        if choice:
            c_ans = extract_choice_answer(cleaned)
            ans_str = c_ans if c_ans else "详见解析"
        elif fill_in:
            f_ans = extract_fill_answer(cleaned, q_text)
            ans_str = f_ans if f_ans else "详见解析"
        else:
            ans_str = "详见解析"

        # 剥除可能残留的开头的【答案】及行内答案文本（直到换行或下一个【分析】/【解答】/【解析】标记）
        cleaned = re.sub(r"^\s*【答案】.*?(?=(?:\n|【解析】|【分析】|【解答】|$))", "", cleaned).strip()
        # 清理难度标记行（如 难度 | 容易，## 难度 等）
        cleaned = re.sub(r"(?:\n|^)\s*#{0,6}\s*(?:难度\s*\|?|【难度】).*?(?=\n|$)", "", cleaned).strip()

        if cleaned.startswith("【解答】"):
            cleaned = "【解析】" + cleaned[4:].strip()

        if "【解答】" in cleaned and "【解析】" not in cleaned:
            cleaned = cleaned.replace("【解答】", "【解析】")

        if "【解析】" in cleaned or "【分析】" in cleaned:
            return [f"【答案】{ans_str}", cleaned]
        else:
            return [
                f"【答案】{ans_str}",
                "【分析】本题解析推导如下：",
                f"【解析】\n{cleaned}".strip(),
            ]

    questions: list[dict[str, Any]] = []
    global_q_count = 0

    for section_index, section in enumerate(sections):
        end = sections[section_index + 1]["start_index"] if section_index + 1 < len(sections) else (ans_boundary_index if ans_boundary_index else len(lines))
        starts = [index for index in range(section["start_index"] + 1, end) if is_question_line(lines[index])]
        if not starts:
            raise ReviewRequired(f"Section has no numbered questions: {section['title']}")

        first_match = QUESTION_RE.match(lines[starts[0]])
        first_num = int(first_match.group("number")) if first_match else 1
        resets_at_one = (first_num == 1 and global_q_count > 0)

        for position, start in enumerate(starts):
            question_end = starts[position + 1] if position + 1 < len(starts) else end
            block = lines[start:question_end]
            match = QUESTION_RE.match(lines[start])
            local_num = int(match.group("number")) if match else (position + 1)
            global_num = global_q_count + local_num if resets_at_one else local_num

            solution_offset = first_solution_index(block)
            if solution_offset is None:
                question_lines = block
                source_sol_line = source_line_numbers[start]
                ans_body = lookup_answer(section_index, local_num, global_num)
                if ans_body:
                    is_choice = is_choice_question("\n".join(question_lines), section["title"])
                    is_fill = is_fill_in_question("\n".join(question_lines), section["title"])
                    solution_lines = format_solution_from_body(ans_body, is_choice, is_fill, question_lines)
                else:
                    st_ans = extracted_answers.get(local_num) or extracted_answers.get(global_num)
                    st_sol = extracted_solutions.get(local_num) or extracted_solutions.get(global_num)
                    if st_ans or st_sol:
                        ans_str = st_ans if st_ans else "详见解析"
                        sol_str = st_sol if st_sol else ""
                        if "【解答】" in sol_str and "【解析】" not in sol_str:
                            sol_str = sol_str.replace("【解答】", "【解析】")
                        if "【分析】" in sol_str:
                            solution_lines = [f"【答案】{ans_str}", sol_str]
                        else:
                            sol_formatted = sol_str if sol_str.startswith("【解析】") else f"【解析】\n{sol_str}"
                            solution_lines = [f"【答案】{ans_str}", "【分析】本题解析推导如下：", sol_formatted]
                    else:
                        raise ReviewRequired(f"Question {local_num} (global {global_num}) in {section['title']} has no explicit publisher solution marker")
            else:
                question_lines = block[:solution_offset]
                solution_lines = block[solution_offset:]
                source_sol_line = source_line_numbers[start + solution_offset]

            question_lines = [l for l in question_lines if not is_zuodaqu_line(l)]
            clean_q_body = "\n".join(question_lines).strip()
            clean_q_body = re.sub(r"(?:\n|^)\s*#{0,6}\s*作答区[:：]?\s*(?=\n|$)", "", clean_q_body)
            clean_q_body = re.sub(r"(?:\n|^)\s*#{0,6}\s*(?:难度\s*\|?|【难度】).*?(?=\n|$)", "", clean_q_body).rstrip() + "\n"

            questions.append({
                "number": global_num,
                "local_number": local_num,
                "section_index": section_index,
                "source_start_line": source_line_numbers[start],
                "source_solution_line": source_sol_line,
                "question_body": clean_q_body,
                "solution_body": "\n".join(solution_lines).rstrip() + "\n",
            })
        section["end_index"] = end
        section["expected_count"] = expected_count(section["title"])
        section["detected_count"] = len(starts)
        global_q_count = questions[-1]["number"]

    # Deduplicate within same question number if any
    deduped_questions: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    for q in questions:
        num = q["number"]
        if num in seen_numbers:
            for prev_q in deduped_questions:
                if prev_q["number"] == num:
                    if len(q["solution_body"].strip()) > len(prev_q["solution_body"].strip()):
                        prev_q["solution_body"] = q["solution_body"]
                    break
        else:
            seen_numbers.add(num)
            deduped_questions.append(q)

    deduped_questions.sort(key=lambda item: item["number"])
    questions = deduped_questions
    return lines, sections, questions


def pdf_choice_answers(source: Path) -> dict[int, dict[str, Any]]:
    if source.suffix.lower() in (".doc", ".docx"):
        return {}
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


def is_choice_question(body: str, section_title: str = "") -> bool:
    if any(k in section_title for k in ("单选", "多选", "选择题")):
        return True
    values = set(re.findall(r"(?<![A-Za-z])([A-D])[.．、\s]", body))
    if {"A", "B", "C", "D"}.issubset(values):
        return True
    if re.search(r"(?:故\s*选|应\s*选|故答案(?:为|是|选)|本题选)\s*[：:]?\s*\$?\s*[A-D]", body):
        return True
    return False


def is_fill_in_question(body: str, section_title: str = "") -> bool:
    if "填空" in section_title:
        return True
    if "____" in body or "__" in body:
        return True
    return False


def extract_choice_answer(solution_body: str) -> str | None:
    patterns = [
        r"(?:故\s*选|应\s*选|故答案(?:为|是|选)|正确答案(?:为|是|选)|本题选|所以选|选)\s*[：:]?\s*\$?\s*([A-D]+(?:\s*[,，、]\s*[A-D]+)*)\b",
        r"【答案】\s*\$?\s*([A-D]+(?:\s*[,，、]\s*[A-D]+)*)\b",
        r"(?:^|\n)\s*答案\s*[：:]?\s*\$?\s*([A-D]+(?:\s*[,，、]\s*[A-D]+)*)\b",
        r"故选\s*[：:]?\s*\$?\s*([A-D])",
    ]
    for pat in patterns:
        m = re.findall(pat, solution_body, re.IGNORECASE)
        if m:
            raw = m[-1]
            ans = re.sub(r"[\s,，、\$]", "", raw).upper()
            if ans and all(c in "ABCD" for c in ans):
                return ans
    return None


def extract_fill_answer(solution_body: str, question_body: str = "", env: dict[str, str] | None = None) -> str | None:
    def _clean_str(val: str) -> str:
        s = val.strip()
        s = re.sub(r"\s*【点评】.*$", "", s).strip()
        s = re.sub(r"\s*[.。]\s*(\$?)$", r"\1", s).strip()
        return s

    # 1. 故答案为: ...
    m = re.search(r"(?:故答案为|答案为|故答案是|答案是)[：:\s]*(.+?)(?=\n\n|\n[【#]|$)", solution_body)
    if m:
        ans = _clean_str(m.group(1))
        if ans and ans != "详见解析":
            return ans

    # 2. Check for circled proposition true/false conclusion: e.g. ① ... 为真命题，② ... 为假命题
    prop_matches = re.findall(r"([①②③④⑤⑥⑦⑧⑨⑩])[^，。\n]*?为真命题", solution_body)
    if prop_matches and any(k in question_body or k in solution_body for k in ("真命题", "序号")):
        ans = "".join(prop_matches)
        if ans:
            return ans

    # 3. Explicit 【答案】 marker at beginning
    m_top = re.search(r"【答案】\s*(.+?)(?=\n|【|$)", solution_body)
    if m_top:
        ans = m_top.group(1).strip().rstrip(".").rstrip("。").strip()
        if ans and ans != "详见解析":
            return ans

    # 4. 综上所述 / 故 ... 等于 / 值为 ...
    m_val = re.search(r"(?:综上所述|所以|故).*?(?:的值为|等于|方程为|距离是|结果为)[：:\s]*(.+?)(?=\.|\n|$)", solution_body)
    if m_val:
        ans = m_val.group(1).strip().rstrip(".").rstrip("。").strip()
        if ans and len(ans) < 100 and ans != "详见解析":
            return ans

    # 5. Try LLM if configured
    if env or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY"):
        prompt = (
            f"请从以下填空题和解析中提取最终的简明答案（数值、表达式或序号），严禁输出'详见解析'，直接返回答案内容：\n"
            f"题目：\n{question_body}\n\n解析：\n{solution_body}"
        )
        llm_res = call_llm_json(prompt, env=env, system_prompt="你是一名数学阅卷老师。只返回纯文本答案本身，不要有任何多余文字或解释。")
        if isinstance(llm_res, dict) and llm_res.get("answer"):
            return str(llm_res["answer"]).strip()
        elif isinstance(llm_res, str) and llm_res.strip():
            return llm_res.strip()

    return None


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


def solution_fields(
    solution_body: str,
    choice: bool,
    recovered: dict[str, Any] | None,
    fill_in: bool = False,
    question_body: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    lines, markers = marked_chunks(solution_body)
    by_name: dict[str, list[tuple[str, int, int]]] = {}
    for marker in markers:
        by_name.setdefault(marker[0], []).append(marker)
    explicit_answer = content_after_marker(lines, by_name["答案"][0]) if by_name.get("答案") else ""
    compact_explicit = compact_answer(explicit_answer)

    if choice:
        c_ans = extract_choice_answer(solution_body)
        if re.fullmatch(r"[A-F]+", compact_explicit, re.IGNORECASE):
            answer = compact_explicit.upper()
            answer_source = "explicit-answer"
        elif (recovered or {}).get("answer"):
            answer = str(recovered.get("answer", "")).upper()
            answer_source = "pdf-text-recovery"
        elif c_ans:
            answer = c_ans
            answer_source = "explicit-conclusion"
        else:
            raise ReviewRequired(f"Choice question has no valid option answer: {solution_body[:200]}")
    elif fill_in:
        f_ans = extract_fill_answer(solution_body, question_body, env=env)
        if compact_explicit and compact_explicit != "详见解析" and len(compact_explicit) <= 400:
            answer = compact_explicit
            answer_source = "explicit-answer"
        elif (recovered or {}).get("answer"):
            answer = str(recovered.get("answer", "")).strip()
            answer_source = "recovered-answer"
        elif f_ans:
            answer = f_ans
            answer_source = "explicit-conclusion"
        else:
            raise ReviewRequired(f"Fill-in question has no valid answer: {solution_body[:200]}")
    else:
        fill_conclusion = re.search(r"故答案为[：:\s]*(.+?)(?=\.|\n|【|$)", solution_body)
        if fill_conclusion:
            answer = fill_conclusion.group(1).strip()
            answer_source = "explicit-conclusion"
        elif compact_explicit and compact_explicit != "详见解析" and len(compact_explicit) <= 400:
            answer = compact_explicit
            answer_source = "explicit-answer"
        else:
            answer = "详见解析"
            answer_source = "publisher-solution"

    if answer.startswith("为：") or answer.startswith("为:"):
        answer = answer[2:].strip()
    if answer.startswith("故答案为：") or answer.startswith("故答案为:"):
        answer = answer[5:].strip()
    answer = re.sub(r"\s*【点评】.*$", "", answer).strip()
    answer = re.sub(r"\s*[.。]\s*(\$?)$", r"\1", answer).strip()
    if not answer:
        answer = "详见解析" if (not choice and not fill_in) else "无"

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
    if output_root.name == "按年份分类":
        year_match = re.search(r"(?:19|20)\d{2}", title)
        parent = output_root / year_match.group(0) if year_match else output_root
    else:
        parent = output_root
    clean_name = re.sub(r'[/\\:*?"<>|]', '_', title).strip()
    return parent / clean_name


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
    vault_root = Path(manifest["vault_root"])
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    numbers = [int(item["number"]) for item in manifest["questions"]]
    if sorted(numbers) != list(range(1, len(numbers) + 1)):
        errors.append({"kind": "question-ledger", "numbers": numbers})
    for section in manifest["sections"]:
        if section.get("expected_count") is not None and section["expected_count"] != section["detected_count"]:
            warnings.append({"kind": "section-count-mismatch", "section": section["title"]})
    for question in manifest["questions"]:
        q_path = Path(question["question_path"])
        a_path = Path(question["answer_path"])
        if not q_path.is_file() or not a_path.is_file():
            errors.append({"kind": "missing-note", "number": question["number"]})
            continue
        if q_path.parent != graph_root / "questions":
            errors.append({"kind": "unexpected-question-dir", "path": str(q_path)})
        if a_path.parent != graph_root / "questions" / "answers":
            errors.append({"kind": "unexpected-answer-dir", "path": str(a_path)})
        q_text = q_path.read_text(encoding="utf-8")
        a_text = a_path.read_text(encoding="utf-8")
        body_match = re.search(r"<!-- question-source:start -->\n(?P<body>.*?)\n<!-- question-source:end -->", q_text, re.DOTALL)
        if body_match is None or sha256_text(body_match.group("body").rstrip() + "\n") != question["question_body_sha256"]:
            errors.append({"kind": "question-content-drift", "number": question["number"]})
        if q_text.count(f"![[{a_path.stem}]]") != 1 and q_text.count(vault_embed(a_path, vault_root)) != 1:
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
            warnings.append({"kind": "choice-answer", "number": question["number"]})
        if question["choice"] and question["answer_source"] not in {"explicit-answer", "explicit-conclusion", "pdf-text-recovery"}:
            warnings.append({"kind": "choice-answer-source", "number": question["number"]})
        if question["answer_source"] == "pdf-text-recovery" and not question.get("pdf_answer_recovery"):
            warnings.append({"kind": "missing-pdf-answer-evidence", "number": question["number"]})
        if question["explanation_char_count"] < 8 or "本题未单列解析" in a_text:
            warnings.append({"kind": "insubstantial-explanation", "number": question["number"]})
        sec = question.get("section", "")
        is_choice = question.get("choice") or any(k in sec for k in ("选择", "单选", "多选"))
        is_fill = question.get("fill_in") or "填空" in sec
        ans = question.get("answer", "")
        if is_choice or is_fill:
            if not ans or ans == "详见解析":
                errors.append({
                    "kind": "invalid-choice-or-fill-answer",
                    "number": question["number"],
                    "section": sec,
                    "answer": ans,
                })
        for path, text in ((q_path, q_text), (a_path, a_text)):
            for destination in local_image_errors(path, text, graph_root=graph_root):
                errors.append({"kind": "broken-image", "number": question["number"], "destination": destination})
    root_note = Path(manifest["root_note"])
    if not root_note.is_file():
        errors.append({"kind": "missing-root-note"})
    else:
        root_text = root_note.read_text(encoding="utf-8")
        for key in ["年份", "学校", "地区", "年级", "学期", "考试种类"]:
            if f"{key}:" not in root_text:
                errors.append({"kind": "missing-paper-attribute", "key": key})
        for question in manifest["questions"]:
            q_path = Path(question["question_path"])
            if root_text.count(vault_embed(q_path, vault_root)) != 1:
                errors.append({"kind": "question-embed-in-root", "number": question["number"]})
    image_root = graph_root / "images"
    for path in graph_root.rglob("*"):
        if path.is_file() and path.suffix.casefold() == ".canvas":
            errors.append({"kind": "unexpected-canvas", "path": str(path)})
        elif path.is_file() and path.suffix.casefold() not in {".md", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".json"}:
            warnings.append({"kind": "unexpected-output-type", "path": str(path)})
        stem = path.stem if path.is_file() else path.name
        if image_root not in path.parents and any(char in '/\\:*?"<>|' for char in stem):
            errors.append({"kind": "unsafe-generated-path", "path": str(path)})
    for child in graph_root.iterdir():
        if child.is_dir() and child.name not in {"images", "questions", ".staging", ".exam-paper-parser"}:
            errors.append({"kind": "unexpected-subdirectory", "path": str(child)})
    if (graph_root / "questions").is_dir():
        for child in (graph_root / "questions").iterdir():
            if child.is_dir() and child.name != "answers":
                errors.append({"kind": "unexpected-question-subdirectory", "path": str(child)})
    question_notes = list((graph_root / "questions").glob("Q*.md")) if (graph_root / "questions").is_dir() else []
    answer_notes = list((graph_root / "questions" / "answers").glob("Q*A1.md")) if (graph_root / "questions" / "answers").is_dir() else []
    if len(question_notes) != len(manifest["questions"]):
        errors.append({"kind": "question-file-count", "actual": len(question_notes)})
    if len(answer_notes) != len(manifest["questions"]):
        errors.append({"kind": "answer-file-count", "actual": len(answer_notes)})
    if not source.is_file() or sha256_file(source) != manifest["source_sha256"]:
        errors.append({"kind": "source-drift"})
    raw_markdown = Path(manifest["raw_markdown"])
    if not raw_markdown.is_file() or sha256_file(raw_markdown) != manifest["raw_markdown_sha256"]:
        errors.append({"kind": "raw-markdown-drift"})
    result = {
        "schema_version": 1,
        "stage": "final-audit",
        "status": "passed" if not errors else "review_required",
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
    warnings: list[dict[str, Any]] = []
    source_hash = sha256_file(source)
    markdown = markdown_path.read_text(encoding="utf-8-sig")
    raw_hash = sha256_file(markdown_path)
    lines, sections, questions = parse_sections(markdown)
    numbers = [item["number"] for item in questions]
    if sorted(numbers) != list(range(1, len(numbers) + 1)):
        raise ReviewRequired(f"Question ledger is not continuous 1..N: {numbers}")
    for section in sections:
        if section["expected_count"] is not None and section["expected_count"] != section["detected_count"]:
            warnings.append({"kind": "section-count-mismatch", "section": section["title"], "expected": section["expected_count"], "detected": section["detected_count"]})
    title = args.title or standardize_paper_title(source.stem, pdf_path=source)
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
    env_file = resolve_env_file(getattr(args, "env_file", None))
    env = parse_env(env_file)
    paper_meta = analyze_paper_metadata(title, env)

    for question in questions:
        sec_title = sections[question["section_index"]]["title"]
        question["provenance"] = provenance_for(question["question_body"], provenance_blocks)
        question["choice"] = is_choice_question(question["question_body"], sec_title)
        question["fill_in"] = is_fill_in_question(question["question_body"], sec_title)
        recovered = pdf_answers.get(question["number"]) if question["choice"] else None
        question["solution_fields"] = solution_fields(
            question["solution_body"],
            question["choice"],
            recovered,
            fill_in=question["fill_in"],
            question_body=question["question_body"],
            env=env,
        )
        question["pdf_answer_recovery"] = (
            recovered if question["solution_fields"]["answer_source"] == "pdf-text-recovery" else None
        )
        question["identity"] = sha256_text(f"{source_hash}\n{question['number']}\n{question['question_body']}")
    qids = allocate_qids(registry_path, [item["identity"] for item in questions], vault_root)
    copied_assets = copy_assets(asset_root, graph_root)
    
    manifest_questions: list[dict[str, Any]] = []
    manifest_sections: list[dict[str, Any]] = []
    root_note = graph_root / safe_filename(f"{title}.md", "exam.md")
    root_lines: list[str] = [
        "---",
        f'title: "{title}"',
        'type: "exam_paper"',
        f'年份: "{paper_meta.get("年份", "")}"',
        f'学校: "{paper_meta.get("学校", "")}"',
        f'地区: "{paper_meta.get("地区", "")}"',
        f'年级: "{paper_meta.get("年级", "")}"',
        f'学期: "{paper_meta.get("学期", "")}"',
        f'考试种类: "{paper_meta.get("考试种类", "")}"',
        f'question_count: {len(questions)}',
        f'created_at: "{time.strftime("%Y-%m-%d")}"',
        "---",
        "",
        f"# {title}",
        "",
    ]
    
    questions_dir = graph_root / "questions"
    answers_dir = questions_dir / "answers"
    questions_dir.mkdir(parents=True, exist_ok=True)
    answers_dir.mkdir(parents=True, exist_ok=True)

    for section_index, section in enumerate(sections):
        sec_title = clean_section_title(section["title"])
        root_lines.append(f"## {sec_title}\n")
        section_qids: list[str] = []
        for question in [item for item in questions if item["section_index"] == section_index]:
            qid = qids[question["identity"]]
            section_qids.append(qid)
            q_path = questions_dir / f"{qid}.md"
            a_path = answers_dir / f"{qid}A1.md"
            q_body = rebase_images(question["question_body"], 1)
            solution_body = rebase_images(question["solution_body"], 2)
            fields = dict(question["solution_fields"])
            fields["analysis"] = rebase_images(fields["analysis"], 2)
            fields["explanation"] = rebase_images(fields["explanation"], 2)
            provenance = question["provenance"] or {}
            sec_num = question["section_index"] + 1
            local_num = question["local_number"]
            metadata = [
                "---",
                f'question_id: "exam:{source_hash[:12]}:{sec_num}:{local_num}"',
                f'question_number: "{local_num}"',
                f'context_key: "{source_hash[:12]}"',
                f'question_source: "{root_note}"',
                f'source_paper: "[[{title}]]"',
                f'section: "{sec_title}"',
                f'年份: "{paper_meta.get("年份", "")}"',
                f'学校: "{paper_meta.get("学校", "")}"',
                f'地区: "{paper_meta.get("地区", "")}"',
                f'年级: "{paper_meta.get("年级", "")}"',
                f'学期: "{paper_meta.get("学期", "")}"',
                f'考试种类: "{paper_meta.get("考试种类", "")}"',
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
                'answer_handling: "external"',
                '重要程度: "重要"',
                "answer_status: matched",
                "---",
                "<!-- question-source:start -->",
                q_body.rstrip(),
                "<!-- question-source:end -->",
                "",
                f"![[{qid}A1]]",
                "",
            ])
            write_text(q_path, "\n".join(metadata))
            write_text(a_path, format_answer_note(qid, solution_body, fields, f"{title}解析"))
            root_lines.append(vault_embed(q_path, vault_root))
            root_lines.append("")
            manifest_questions.append({
                "number": question["number"],
                "local_number": question["local_number"],
                "question_number": str(question["local_number"]),
                "qid": qid,
                "section_index": section_index,
                "section": sec_title,
                "clean_section": sec_title,
                "question_path": str(q_path),
                "answer_path": str(a_path),
                "question_body_sha256": sha256_text(q_body),
                "solution_body_sha256": sha256_text(solution_body),
                "choice": question["choice"],
                "fill_in": question["fill_in"],
                "answer": fields["answer"],
                "answer_source": fields["answer_source"],
                "explanation_char_count": len(normalize_match(fields["explanation"])),
                "detail_markers": fields["detail_markers"],
                "source_start_line": question["source_start_line"],
                "source_solution_line": question["source_solution_line"],
                "source_provenance": provenance or None,
                "pdf_answer_recovery": question["pdf_answer_recovery"],
            })
        manifest_sections.append({
            "index": section_index,
            "title": section["title"],
            "clean_title": sec_title,
            "expected_count": section.get("expected_count"),
            "detected_count": section.get("detected_count"),
            "qids": section_qids,
        })
    write_text(root_note, "\n".join(root_lines).rstrip() + "\n")
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
        "paper_metadata": paper_meta,
        "final_audit_report": str(final_audit),
        "registry": str(registry_path),
        "provenance_block_count": len(provenance_blocks),
        "sections": manifest_sections,
        "questions": manifest_questions,
        "metrics": {
            "question_count": len(manifest_questions),
            "answer_count": len(manifest_questions),
            "section_count": len(manifest_sections),
            "asset_count": copied_assets,
            "pdf_answer_recovery_count": sum(1 for item in manifest_questions if item["pdf_answer_recovery"]),
            "llm_calls": 0,
            "adapter_reviews": 0,
            "duration_seconds": round(time.monotonic() - started, 3),
            "ocr_cache_hit": bool((ocr_report or {}).get("cache_hit")),
        },
    }
    write_json(manifest_path, manifest)
    audit = audit_manifest(manifest_path, overwrite=args.overwrite)
    manifest["status"] = audit["status"]
    write_json(manifest_path, manifest)
    return {
        "schema_version": 1,
        "stage": "exam-paper-parser",
        "status": audit["status"],
        "manifest": str(manifest_path),
        "graph_root": str(graph_root),
        "root_note": str(root_note),
        "metrics": manifest["metrics"],
    }


def resolve_source(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.casefold() not in (".pdf", ".doc", ".docx"):
        raise ParserError(f"Source is not an existing PDF or Word file: {path}")
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
        source_path = Path(source)
        clean_title = standardize_paper_title(source_path.stem, pdf_path=source_path)
        target = output_graph_root(Path(args.output_root).expanduser().resolve(), clean_title)
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

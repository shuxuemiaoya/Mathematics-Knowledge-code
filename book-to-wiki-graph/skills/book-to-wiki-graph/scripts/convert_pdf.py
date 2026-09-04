#!/usr/bin/env python3
"""Convert a book PDF to source-faithful Markdown with OCR and asset extraction."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse, urlsplit

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

DEFAULT_ENV_FILE = Path("/Users/oven/Documents/Mathematics-Knowledge-code/.env")
DEFAULT_BASE_URL = "https://mineru.net"
MAX_PAGES = 200
MAX_BYTES = 200 * 1024 * 1024
BATCH_SIZE = 50
ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}
TERMINAL_STATES = {"done", "failed"}
IMAGE_LINK_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")
HTML_IMAGE_LINK_RE = re.compile(
    r"""(<img\b[^>]*?\bsrc=["'])([^"']+)(["'])""",
    re.IGNORECASE,
)


class ConversionError(RuntimeError):
    pass


class ConfigurationError(ConversionError):
    pass


class MineruError(ConversionError):
    pass


@dataclass(frozen=True)
class PdfPart:
    path: Path
    index: int
    count: int
    start_page: int
    end_page: int
    data_id: str


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    poll_interval: float
    max_polls: int
    request_timeout: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_settings(args: argparse.Namespace) -> Settings:
    values = parse_env_file(Path(args.env_file).expanduser().resolve())
    api_key = os.environ.get("MINERU_API_KEY") or values.get("MINERU_API_KEY", "")
    if not api_key:
        raise ConfigurationError(
            f"MINERU_API_KEY is missing from the process environment and {args.env_file}"
        )
    base_url = (args.base_url or values.get("MINERU_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    if base_url.endswith("/api/v4"):
        base_url = base_url[: -len("/api/v4")]
    return Settings(
        api_key=api_key,
        base_url=base_url,
        poll_interval=args.poll_interval,
        max_polls=args.max_polls,
        request_timeout=args.request_timeout,
    )


def pdf_page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise ConfigurationError(
            "Book PDF conversion requires pypdf in the selected Python runtime"
        ) from exc
    try:
        count = len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise ConfigurationError(f"Cannot open PDF: {path}: {exc}") from exc
    if count < 1:
        raise ConfigurationError(f"PDF has no pages: {path}")
    return count


def write_pdf_range(source: Path, target: Path, start_page: int, end_page: int) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()
    for page_index in range(start_page - 1, end_page):
        writer.add_page(reader.pages[page_index])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        writer.write(stream)


def fit_ranges_to_size(
    source: Path,
    initial_ranges: list[tuple[int, int]],
    temp_dir: Path,
) -> list[tuple[int, int]]:
    accepted: list[tuple[int, int]] = []
    pending = list(initial_ranges)
    while pending:
        start_page, end_page = pending.pop(0)
        probe = temp_dir / f"probe-{start_page}-{end_page}.pdf"
        write_pdf_range(source, probe, start_page, end_page)
        size = probe.stat().st_size
        probe.unlink(missing_ok=True)
        if size <= MAX_BYTES:
            accepted.append((start_page, end_page))
            continue
        if start_page == end_page:
            raise ConversionError(
                f"Page {start_page} exceeds MinerU's 200 MB per-file limit"
            )
        midpoint = (start_page + end_page) // 2
        pending[0:0] = [(start_page, midpoint), (midpoint + 1, end_page)]
    return accepted


def make_data_id(source: Path, index: int, count: int) -> str:
    digest = hashlib.sha1(
        f"{source.resolve()}:{source.stat().st_size}:{source.stat().st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:16]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.stem).strip("._-") or "book"
    return f"{stem}.{digest}.{index:03d}-of-{count:03d}"[:128]


def prepare_parts(source: Path, temp_dir: Path) -> list[PdfPart]:
    page_count = pdf_page_count(source)
    if page_count <= MAX_PAGES and source.stat().st_size <= MAX_BYTES:
        return [
            PdfPart(
                path=source,
                index=1,
                count=1,
                start_page=1,
                end_page=page_count,
                data_id=make_data_id(source, 1, 1),
            )
        ]
    ranges = [
        (start, min(start + MAX_PAGES - 1, page_count))
        for start in range(1, page_count + 1, MAX_PAGES)
    ]
    ranges = fit_ranges_to_size(source, ranges, temp_dir)
    parts: list[PdfPart] = []
    for index, (start_page, end_page) in enumerate(ranges, start=1):
        part_path = temp_dir / f"{source.stem}.part-{index:03d}.pdf"
        write_pdf_range(source, part_path, start_page, end_page)
        parts.append(
            PdfPart(
                path=part_path,
                index=index,
                count=len(ranges),
                start_page=start_page,
                end_page=end_page,
                data_id=make_data_id(source, index, len(ranges)),
            )
        )
    return parts


def build_payload(parts: list[PdfPart]) -> dict[str, Any]:
    return {
        "files": [
            {
                "name": part.path.name,
                "data_id": part.data_id,
                "is_ocr": True,
            }
            for part in parts
        ],
        "model_version": "vlm",
        "language": "ch",
        "enable_formula": True,
        "enable_table": True,
    }


class MineruClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

    def request_json(
        self,
        method: str,
        url: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request = urllib_request.Request(
            url,
            data=body,
            headers=self.auth_headers,
            method=method,
        )
        try:
            with urllib_request.urlopen(
                request, timeout=self.settings.request_timeout
            ) as response:
                status = response.status
                raw = response.read()
        except urllib_error.HTTPError as exc:
            raise MineruError(f"{action} returned HTTP {exc.code}") from exc
        except urllib_error.URLError as exc:
            raise MineruError(f"{action} failed: {exc.reason}") from exc
        if status != 200:
            raise MineruError(f"{action} returned HTTP {status}")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MineruError(f"{action} returned invalid JSON") from exc
        if parsed.get("code") != 0:
            raise MineruError(
                f"{action} returned MinerU code {parsed.get('code')}: "
                f"{parsed.get('msg', '')}"
            )
        return parsed

    def request_upload_urls(self, parts: list[PdfPart]) -> tuple[str, list[str]]:
        body = self.request_json(
            "POST",
            f"{self.settings.base_url}/api/v4/file-urls/batch",
            "Upload URL request",
            build_payload(parts),
        )
        data = body.get("data") or {}
        batch_id = data.get("batch_id")
        urls = data.get("file_urls") or []
        if not batch_id or len(urls) != len(parts):
            raise MineruError("Upload URL response is missing a batch ID or has a URL-count mismatch")
        return str(batch_id), [str(url) for url in urls]

    def upload(self, url: str, part: PdfPart) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise MineruError(f"Upload URL is invalid for part {part.index}")
        connection_class = (
            http.client.HTTPSConnection
            if parsed.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_class(
            parsed.hostname,
            parsed.port,
            timeout=self.settings.request_timeout,
        )
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        try:
            connection.putrequest("PUT", path)
            connection.putheader("Content-Length", str(part.path.stat().st_size))
            connection.endheaders()
            with part.path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    connection.send(block)
            response = connection.getresponse()
            status = response.status
            response.read()
        except OSError as exc:
            raise MineruError(f"Upload failed for part {part.index}: {exc}") from exc
        finally:
            connection.close()
        if status != 200:
            raise MineruError(
                f"Upload failed for part {part.index}: HTTP {status}"
            )

    def poll(self, batch_id: str) -> list[dict[str, Any]]:
        endpoint = f"{self.settings.base_url}/api/v4/extract-results/batch/{batch_id}"
        for poll_index in range(1, self.settings.max_polls + 1):
            body = self.request_json(
                "GET",
                endpoint,
                "Batch result poll",
            )
            results = (body.get("data") or {}).get("extract_result") or []
            states = [str(item.get("state", "")) for item in results]
            if results and all(state in TERMINAL_STATES for state in states):
                return results
            unknown = [state for state in states if state not in ACTIVE_STATES | TERMINAL_STATES]
            if unknown:
                raise MineruError(f"MinerU returned unknown task states: {unknown}")
            print(
                f"MinerU batch {batch_id}: poll {poll_index}/{self.settings.max_polls}, "
                f"states={states or ['waiting-for-result']}",
                file=sys.stderr,
            )
            time.sleep(self.settings.poll_interval)
        raise MineruError(f"MinerU polling timed out for batch {batch_id}")

    def download(self, url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib_request.Request(url, method="GET")
        try:
            with urllib_request.urlopen(
                request, timeout=self.settings.request_timeout
            ) as response, target.open("wb") as stream:
                if response.status != 200:
                    raise MineruError(
                        f"Result download returned HTTP {response.status}"
                    )
                shutil.copyfileobj(response, stream, length=1024 * 1024)
        except urllib_error.HTTPError as exc:
            raise MineruError(
                f"Result download returned HTTP {exc.code}"
            ) from exc
        except urllib_error.URLError as exc:
            raise MineruError(f"Result download failed: {exc.reason}") from exc


def chunked(parts: list[PdfPart]) -> list[list[PdfPart]]:
    return [parts[index : index + BATCH_SIZE] for index in range(0, len(parts), BATCH_SIZE)]


def safe_member(member: str) -> Path:
    path = Path(member)
    if path.is_absolute() or ".." in path.parts:
        raise ConversionError(f"Unsafe path in MinerU result zip: {member}")
    return path


def image_relative_path(path: Path) -> Path | None:
    lowered = [part.lower() for part in path.parts]
    if "images" not in lowered:
        return None
    index = lowered.index("images")
    remainder = path.parts[index + 1 :]
    return Path(*remainder) if remainder else None


def markdown_asset_relative_path(destination: str) -> Path | None:
    clean_destination = destination.strip().strip("<>")
    parsed = urlparse(clean_destination)
    if parsed.scheme or clean_destination.startswith("#"):
        return None
    normalized = Path(parsed.path.replace("\\", "/"))
    lowered = [part.lower() for part in normalized.parts]
    if "images" not in lowered:
        return None
    index = lowered.index("images")
    remainder = normalized.parts[index + 1 :]
    return Path(*remainder) if remainder else None


def rewrite_markdown_images(content: str, image_map: dict[str, str]) -> str:
    def replace_md(match: re.Match[str]) -> str:
        prefix, dest, suffix = match.group(1), match.group(2), match.group(3)
        rel = markdown_asset_relative_path(dest)
        if rel and str(rel) in image_map:
            return f"{prefix}{image_map[str(rel)]}{suffix}"
        return match.group(0)

    def replace_html(match: re.Match[str]) -> str:
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)
        rel = markdown_asset_relative_path(src)
        if rel and str(rel) in image_map:
            return f"{prefix}{image_map[str(rel)]}{suffix}"
        return match.group(0)

    content = IMAGE_LINK_RE.sub(replace_md, content)
    content = HTML_IMAGE_LINK_RE.sub(replace_html, content)
    return content


def extract_part_result(
    zip_path: Path,
    part: PdfPart,
    extract_dir: Path,
    target_images_dir: Path,
) -> tuple[str, list[Path]]:
    with zipfile.ZipFile(zip_path) as archive:
        members = [safe_member(name) for name in archive.namelist()]
        md_members = [
            member for member in members if member.suffix.lower() == ".md"
        ]
        if not md_members:
            raise ConversionError(f"No Markdown found in result for part {part.index}")
        main_md_member = sorted(md_members, key=lambda m: len(m.parts))[0]
        archive.extractall(extract_dir)

    raw_md_path = extract_dir / main_md_member
    content = raw_md_path.read_text(encoding="utf-8-sig", errors="replace")

    copied_images: list[Path] = []
    image_map: dict[str, str] = {}
    target_images_dir.mkdir(parents=True, exist_ok=True)

    for item in extract_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = image_relative_path(item.relative_to(extract_dir))
        if rel is not None:
            new_name = f"part{part.index:03d}_{rel.name}"
            target_file = target_images_dir / new_name
            shutil.copy2(item, target_file)
            copied_images.append(target_file)
            image_map[str(rel)] = f"images/{new_name}"

    rewritten = rewrite_markdown_images(content, image_map)
    return rewritten, copied_images


def convert_pdf_to_markdown(
    source: Path,
    output_path: Path,
    settings: Settings,
    temp_root: Path | None = None,
) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=temp_root, prefix="pdf-convert-") as temp_str:
        temp_dir = Path(temp_str)
        client = MineruClient(settings)
        parts = prepare_parts(source, temp_dir)
        batches = chunked(parts)

        part_results: dict[int, str] = {}
        all_images: list[Path] = []
        target_images_dir = output_path.parent / "images"

        for batch_index, batch_parts in enumerate(batches, start=1):
            batch_id, upload_urls = client.request_upload_urls(batch_parts)
            for part, url in zip(batch_parts, upload_urls):
                client.upload(url, part)

            results = client.poll(batch_id)
            results_by_data_id = {str(item.get("data_id")): item for item in results}

            for part in batch_parts:
                part_entry = results_by_data_id.get(part.data_id)
                if not part_entry:
                    raise ConversionError(f"MinerU returned no entry for part {part.index}")
                state = part_entry.get("state")
                if state != "done":
                    raise ConversionError(
                        f"MinerU conversion failed for part {part.index}: state={state}, "
                        f"msg={part_entry.get('err_msg', '')}"
                    )
                full_zip_url = part_entry.get("full_zip_url")
                if not full_zip_url:
                    raise ConversionError(f"Missing full_zip_url for part {part.index}")

                zip_dest = temp_dir / f"result-part-{part.index:03d}.zip"
                client.download(full_zip_url, zip_dest)

                part_extract_dir = temp_dir / f"extract-part-{part.index:03d}"
                md_text, images = extract_part_result(
                    zip_dest, part, part_extract_dir, target_images_dir
                )
                part_results[part.index] = md_text
                all_images.extend(images)

        merged_lines: list[str] = []
        for index in sorted(part_results):
            text = part_results[index].strip()
            if text:
                merged_lines.append(text)

        full_markdown = "\n\n".join(merged_lines) + "\n"
        output_path.write_text(full_markdown, encoding="utf-8")

        return {
            "status": "passed",
            "source_pdf": str(source),
            "source_sha256": sha256_file(source),
            "output_markdown": str(output_path),
            "output_sha256": sha256_file(output_path),
            "page_count": pdf_page_count(source),
            "part_count": len(parts),
            "image_count": len(all_images),
            "line_count": len(full_markdown.splitlines()),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Input PDF file")
    parser.add_argument("--output", type=Path, required=True, help="Output Markdown file")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--base-url", type=str)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument("--report", type=Path, help="Save conversion report to JSON")
    args = parser.parse_args()

    settings = load_settings(args)
    report = convert_pdf_to_markdown(args.source, args.output, settings)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

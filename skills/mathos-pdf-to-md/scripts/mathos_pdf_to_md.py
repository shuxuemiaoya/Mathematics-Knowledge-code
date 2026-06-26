from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import fitz
import requests

DEFAULT_ENV_PATH = Path(r"C:\Mathematics-Knowledge\.env")
DEFAULT_BASE_URL = "https://mineru.net"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
DEFAULT_MAX_PARALLEL_TASKS = 10
DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_BYTES = 200 * 1024 * 1024
DEFAULT_POLL_INTERVAL = 10
DEFAULT_MAX_RETRIES = 180
DEFAULT_BATCH_SIZE = 50
SCRIPT_COMMAND = r".\skills\mathos-pdf-to-md\scripts\mathos_pdf_to_md.py"
DONE_STATES = {"done"}
ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}
FAILED_STATES = {"failed"}


class MathosPdfError(Exception):
    pass


class ConfigurationError(MathosPdfError):
    pass


class MineruApiError(MathosPdfError):
    pass


class ConversionError(MathosPdfError):
    pass


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    max_parallel_tasks: int = DEFAULT_MAX_PARALLEL_TASKS
    poll_interval: int = DEFAULT_POLL_INTERVAL
    max_retries: int = DEFAULT_MAX_RETRIES


@dataclass(frozen=True)
class PdfJob:
    source_pdf: Path
    target_md: Path


@dataclass(frozen=True)
class SkippedPdf:
    source_pdf: Path
    target_md: Path
    reason: str


@dataclass(frozen=True)
class PdfPart:
    source_pdf: Path
    upload_path: Path
    data_id: str
    part_index: int
    part_count: int
    start_page: int
    end_page: int
    requires_split: bool


@dataclass(frozen=True)
class ExtractedPart:
    markdown_path: Path
    markdown_text: str
    assets: list[Path]
    asset_count: int
    part_index: int


@dataclass(frozen=True)
class ConversionResult:
    source_pdf: Path
    target_md: Path
    status: str
    parts: int
    assets: int
    message: str = ""
    split_parts: list[dict[str, Any]] = field(default_factory=list)
    zip_paths: list[str] = field(default_factory=list)


def parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_int(values: dict[str, str], key: str, default: int) -> int:
    raw = values.get(key) or os.environ.get(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc


def normalize_base_url(raw_url: str) -> str:
    base_url = raw_url.rstrip("/")
    if base_url.endswith("/api/v4"):
        return base_url[: -len("/api/v4")]
    return base_url


def load_settings(env_path: Path = DEFAULT_ENV_PATH) -> Settings:
    env_values = parse_env_file(env_path)
    api_key = env_values.get("MINERU_API_KEY") or os.environ.get("MINERU_API_KEY", "")
    if not api_key:
        raise ConfigurationError(f"Missing MINERU_API_KEY in {env_path}")
    raw_base_url = env_values.get("BASE_URL") or os.environ.get("BASE_URL") or DEFAULT_BASE_URL
    return Settings(
        api_key=api_key,
        base_url=normalize_base_url(raw_base_url),
        max_parallel_tasks=env_int(env_values, "MAX_PARALLEL_TASKS", DEFAULT_MAX_PARALLEL_TASKS),
        poll_interval=env_int(env_values, "POLL_INTERVAL", DEFAULT_POLL_INTERVAL),
        max_retries=env_int(env_values, "MAX_RETRIES", DEFAULT_MAX_RETRIES),
    )


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def save_config(config: dict[str, Any], config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_output_root(args: argparse.Namespace, config_path: Path = DEFAULT_CONFIG_PATH) -> Path:
    if args.output_root:
        output_root = Path(args.output_root).expanduser().resolve()
        config = load_config(config_path)
        if config.get("default_output_root") != str(output_root):
            config["default_output_root"] = str(output_root)
            save_config(config, config_path)
        return output_root

    config = load_config(config_path)
    remembered = config.get("default_output_root")
    if not remembered:
        raise ConfigurationError("No output root configured. Re-run with --output-root <path>.")

    if not args.yes:
        answer = input(f"Use remembered output root '{remembered}'? Type yes to continue: ").strip().lower()
        if answer != "yes":
            raise ConfigurationError("Output root was not confirmed.")
    return Path(remembered).expanduser().resolve()


def resolve_source_base(args: argparse.Namespace, config_path: Path = DEFAULT_CONFIG_PATH) -> Path:
    if args.source_base:
        source_base = Path(args.source_base).expanduser().resolve()
        config = load_config(config_path)
        if config.get("default_source_base") != str(source_base):
            config["default_source_base"] = str(source_base)
            save_config(config, config_path)
        return source_base

    config = load_config(config_path)
    remembered = config.get("default_source_base")
    if not remembered:
        raise ConfigurationError("No source base configured. Re-run with --source-base <path>.")

    if not args.yes:
        answer = input(f"Use remembered source base '{remembered}'? Type yes to continue: ").strip().lower()
        if answer != "yes":
            raise ConfigurationError("Source base was not confirmed.")
    return Path(remembered).expanduser().resolve()


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def target_markdown_path(source_pdf: Path, source_base: Path, output_root: Path) -> Path:
    source_pdf = source_pdf.resolve()
    source_base = source_base.resolve()
    output_root = output_root.resolve()
    try:
        relative_pdf = source_pdf.relative_to(source_base)
    except ValueError as exc:
        raise ConfigurationError(f"{source_pdf} is not under source base {source_base}") from exc
    return output_root / relative_pdf.with_suffix(".md")


def discover_pdf_jobs(source_path: Path, source_base: Path, output_root: Path) -> tuple[list[PdfJob], list[SkippedPdf]]:
    source_path = source_path.resolve()
    if not source_path.exists():
        raise ConfigurationError(f"Invalid source path: {source_path}")
    if not source_base.exists() or not source_base.is_dir():
        raise ConfigurationError(f"Invalid source base: {source_base}")
    if not is_relative_to(source_path, source_base):
        raise ConfigurationError(f"Source path {source_path} is not under source base {source_base}")

    jobs: list[PdfJob] = []
    skipped: list[SkippedPdf] = []
    if source_path.is_file():
        if source_path.suffix.lower() != ".pdf":
            raise ConfigurationError(f"Source file is not a PDF: {source_path}")
        discovered = [source_path]
    elif source_path.is_dir():
        discovered = sorted(
            source_path.rglob("*"),
            key=lambda item: (len(item.relative_to(source_path).parts), str(item).lower()),
        )
    else:
        raise ConfigurationError(f"Invalid source path: {source_path}")

    for source_pdf in discovered:
        if not source_pdf.is_file() or source_pdf.suffix.lower() != ".pdf":
            continue
        target_md = target_markdown_path(source_pdf, source_base, output_root)
        if target_md.exists():
            skipped.append(SkippedPdf(source_pdf=source_pdf, target_md=target_md, reason="target exists"))
            continue
        jobs.append(PdfJob(source_pdf=source_pdf, target_md=target_md))
    return jobs, skipped


def pdf_page_count(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def write_pdf_part(source_pdf: Path, target_pdf: Path, start_page: int, end_page: int) -> None:
    with fitz.open(source_pdf) as src:
        out = fitz.open()
        out.insert_pdf(src, from_page=start_page - 1, to_page=end_page - 1)
        target_pdf.parent.mkdir(parents=True, exist_ok=True)
        out.save(target_pdf)
        out.close()


def split_ranges_by_size(
    source_pdf: Path,
    ranges: list[tuple[int, int]],
    temp_dir: Path,
    max_bytes: int,
) -> list[tuple[int, int]]:
    accepted: list[tuple[int, int]] = []
    pending = list(ranges)
    while pending:
        start_page, end_page = pending.pop(0)
        probe = temp_dir / f"probe_{start_page}_{end_page}.pdf"
        write_pdf_part(source_pdf, probe, start_page, end_page)
        size = probe.stat().st_size
        probe.unlink(missing_ok=True)
        if size <= max_bytes:
            accepted.append((start_page, end_page))
            continue
        if start_page == end_page:
            raise ConversionError(
                f"Single page {start_page} of {source_pdf} exceeds {max_bytes} bytes"
            )
        midpoint = (start_page + end_page) // 2
        pending.insert(0, (midpoint + 1, end_page))
        pending.insert(0, (start_page, midpoint))
    return accepted


def plan_pdf_parts(
    source_pdf: Path,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    temp_dir: Path | None = None,
) -> list[PdfPart]:
    source_pdf = source_pdf.resolve()
    page_count = pdf_page_count(source_pdf)
    if page_count == 0:
        raise ConversionError(f"Empty PDF: {source_pdf}")
    if page_count <= max_pages and source_pdf.stat().st_size <= max_bytes:
        return [
            PdfPart(
                source_pdf=source_pdf,
                upload_path=source_pdf,
                data_id=make_data_id(source_pdf, 1, 1),
                part_index=1,
                part_count=1,
                start_page=1,
                end_page=page_count,
                requires_split=False,
            )
        ]

    owned_temp: tempfile.TemporaryDirectory[str] | None = None
    if temp_dir is None:
        owned_temp = tempfile.TemporaryDirectory(prefix="mathos-pdf-split-")
        temp_dir = Path(owned_temp.name)
    temp_dir.mkdir(parents=True, exist_ok=True)

    ranges = [
        (start, min(start + max_pages - 1, page_count))
        for start in range(1, page_count + 1, max_pages)
    ]
    ranges = split_ranges_by_size(source_pdf, ranges, temp_dir, max_bytes)
    parts: list[PdfPart] = []
    for index, (start_page, end_page) in enumerate(ranges, start=1):
        upload_path = temp_dir / f"{source_pdf.stem}.part-{index:03d}.pdf"
        write_pdf_part(source_pdf, upload_path, start_page, end_page)
        parts.append(
            PdfPart(
                source_pdf=source_pdf,
                upload_path=upload_path,
                data_id=make_data_id(source_pdf, index, len(ranges)),
                part_index=index,
                part_count=len(ranges),
                start_page=start_page,
                end_page=end_page,
                requires_split=True,
            )
        )
    if owned_temp is not None:
        # Tests and callers that do not pass a temp_dir only inspect metadata. Keep split files
        # unavailable in that mode to avoid leaking temp folders.
        owned_temp.cleanup()
    return parts


def make_data_id(source_pdf: Path, part_index: int, part_count: int) -> str:
    digest = hashlib.sha1(str(source_pdf.resolve()).encode("utf-8")).hexdigest()[:16]
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_pdf.stem).strip("._-") or "pdf"
    return f"{safe_stem}.{digest}.{part_index:03d}-of-{part_count:03d}"[:128]


def build_batch_payload(parts: list[PdfPart]) -> dict[str, Any]:
    return {
        "files": [
            {"name": part.upload_path.name, "data_id": part.data_id, "is_ocr": True}
            for part in parts
        ],
        "model_version": "vlm",
        "language": "ch",
        "enable_formula": True,
        "enable_table": True,
    }


class MineruClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.api_key}",
        }

    def _check_json_response(self, response: requests.Response) -> dict[str, Any]:
        if response.status_code != 200:
            raise MineruApiError(f"MinerU HTTP {response.status_code}")
        data = response.json()
        if data.get("code") != 0:
            raise MineruApiError(f"MinerU API error {data.get('code')}: {data.get('msg')}")
        return data

    def request_upload_urls(self, parts: list[PdfPart]) -> tuple[str, list[str]]:
        response = self.session.post(
            f"{self.settings.base_url}/api/v4/file-urls/batch",
            headers=self.headers,
            json=build_batch_payload(parts),
        )
        data = self._check_json_response(response)
        batch_id = data["data"]["batch_id"]
        urls = data["data"]["file_urls"]
        if len(urls) != len(parts):
            raise MineruApiError("MinerU returned a mismatched upload URL count")
        return batch_id, urls

    def upload_file(self, upload_url: str, path: Path) -> None:
        with path.open("rb") as file:
            response = self.session.put(upload_url, data=file)
        if response.status_code != 200:
            raise MineruApiError(f"Upload failed for {path.name}: HTTP {response.status_code}")

    def poll_batch(self, batch_id: str) -> list[dict[str, Any]]:
        url = f"{self.settings.base_url}/api/v4/extract-results/batch/{batch_id}"
        last_state_signature = ""
        stalled_count = 0
        for _ in range(self.settings.max_retries):
            response = self.session.get(url, headers=self.headers)
            data = self._check_json_response(response)
            results = data["data"].get("extract_result", [])
            states = [item.get("state", "") for item in results]
            state_signature = json.dumps(states, ensure_ascii=False)
            if state_signature == last_state_signature:
                stalled_count += 1
            else:
                stalled_count = 0
                last_state_signature = state_signature
            if stalled_count >= self.settings.max_retries:
                raise MineruApiError(f"Polling stalled for batch {batch_id}")
            if results and all(state in DONE_STATES | FAILED_STATES for state in states):
                return results
            if any(state not in DONE_STATES | FAILED_STATES | ACTIVE_STATES for state in states):
                raise MineruApiError(f"Unexpected MinerU states for batch {batch_id}: {states}")
            time.sleep(self.settings.poll_interval)
        raise MineruApiError(f"Polling timed out for batch {batch_id}")

    def download_zip(self, url: str, target: Path) -> None:
        response = self.session.get(url, stream=True)
        if response.status_code != 200:
            raise MineruApiError(f"Download failed: HTTP {response.status_code}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)


def safe_zip_member(member: str) -> Path:
    path = Path(member)
    if path.is_absolute() or ".." in path.parts:
        raise ConversionError(f"Unsafe zip member path: {member}")
    return path


def rewrite_markdown_asset_links(markdown: str, pdf_stem: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix, path, suffix = match.group(1), match.group(2), match.group(3)
        parsed = urlparse(path)
        if parsed.scheme or path.startswith("#") or path.startswith("images/" + pdf_stem + "/"):
            return match.group(0)
        if path.startswith("images/"):
            new_path = "images/" + pdf_stem + "/" + path[len("images/") :]
            return f"{prefix}{new_path}{suffix}"
        return match.group(0)

    return re.sub(r"(!\[[^\]]*\]\()([^)]+)(\))", replace, markdown)


def extract_mineru_zip(
    zip_path: Path,
    output_md: Path,
    pdf_stem: str,
    artifact_dir: Path,
    part_label: str,
    target_md: Path | None = None,
) -> ExtractedPart:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    artifact_extract_dir = artifact_dir / "extracted" / part_label
    artifact_extract_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Path] = []
    markdown_text: str | None = None

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            safe_path = safe_zip_member(member)
            if member.endswith("/"):
                continue
            if safe_path.name == "full.md":
                markdown_text = archive.read(member).decode("utf-8")
                (artifact_extract_dir / "full.md").write_text(markdown_text, encoding="utf-8")
                continue
            target_artifact = artifact_extract_dir / safe_path
            target_artifact.parent.mkdir(parents=True, exist_ok=True)
            target_artifact.write_bytes(archive.read(member))
            if safe_path.parts and safe_path.parts[0] == "images":
                relative_inside_images = Path(*safe_path.parts[1:])
                dest_parent = target_md.parent if target_md is not None else output_md.parent
                final_asset = dest_parent / "images" / pdf_stem / relative_inside_images
                final_asset.parent.mkdir(parents=True, exist_ok=True)
                final_asset.write_bytes(archive.read(member))
                assets.append(final_asset)

    if markdown_text is None:
        raise ConversionError(f"Missing full.md in {zip_path}")
    markdown_text = rewrite_markdown_asset_links(markdown_text, pdf_stem)
    output_md.write_text(markdown_text, encoding="utf-8")
    return ExtractedPart(
        markdown_path=output_md,
        markdown_text=markdown_text,
        assets=assets,
        asset_count=len(assets),
        part_index=int(part_label.rsplit("-", 1)[-1]) if "-" in part_label else 1,
    )


def merge_markdown_parts(parts: list[ExtractedPart], output_md: Path) -> None:
    ordered = sorted(parts, key=lambda part: part.part_index)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(part.markdown_text.strip() for part in ordered if part.markdown_text.strip())
    output_md.write_text(body + "\n", encoding="utf-8")


def chunked(items: list[PdfPart], size: int) -> list[list[PdfPart]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def convert_job(job: PdfJob, client: MineruClient, artifact_dir: Path) -> ConversionResult:
    with tempfile.TemporaryDirectory(prefix="mathos-pdf-parts-") as temp_name:
        temp_dir = Path(temp_name)
        parts = plan_pdf_parts(job.source_pdf, temp_dir=temp_dir)
        extracted_parts: list[ExtractedPart] = []
        part_lookup = {part.data_id: part for part in parts}
        zip_paths: list[str] = []
        for batch_parts in chunked(parts, DEFAULT_BATCH_SIZE):
            batch_id, upload_urls = client.request_upload_urls(batch_parts)
            for part, upload_url in zip(batch_parts, upload_urls):
                client.upload_file(upload_url, part.upload_path)
            results = client.poll_batch(batch_id)
            for item in results:
                data_id = item.get("data_id")
                part = part_lookup.get(data_id)
                if part is None:
                    raise ConversionError(f"MinerU returned unknown data_id: {data_id}")
                if item.get("state") == "failed":
                    raise ConversionError(item.get("err_msg") or f"MinerU failed {part.upload_path.name}")
                zip_url = item.get("full_zip_url")
                if not zip_url:
                    raise ConversionError(f"MinerU result for {part.upload_path.name} has no full_zip_url")
                zip_path = artifact_dir / "zips" / job.source_pdf.stem / f"part-{part.part_index:03d}.zip"
                client.download_zip(zip_url, zip_path)
                zip_paths.append(str(zip_path))
                part_output = job.target_md
                if part.part_count > 1:
                    part_output = artifact_dir / "parts-md" / job.source_pdf.stem / f"part-{part.part_index:03d}.md"
                part_label = f"part-{part.part_index:03d}"
                asset_namespace = job.source_pdf.stem
                if part.part_count > 1:
                    asset_namespace = f"{job.source_pdf.stem}/{part_label}"
                extracted_parts.append(
                    extract_mineru_zip(
                        zip_path=zip_path,
                        output_md=part_output,
                        pdf_stem=asset_namespace,
                        artifact_dir=artifact_dir,
                        part_label=part_label,
                        target_md=job.target_md,
                    )
                )
        if len(extracted_parts) > 1:
            merge_markdown_parts(extracted_parts, job.target_md)
        asset_count = sum(part.asset_count for part in extracted_parts)
        return ConversionResult(
            source_pdf=job.source_pdf,
            target_md=job.target_md,
            status="converted",
            parts=len(parts),
            assets=asset_count,
            split_parts=[
                {
                    "upload_path": str(part.upload_path),
                    "part_index": part.part_index,
                    "part_count": part.part_count,
                    "start_page": part.start_page,
                    "end_page": part.end_page,
                    "requires_split": part.requires_split,
                    "data_id": part.data_id,
                }
                for part in parts
            ],
            zip_paths=zip_paths,
        )


def masked_settings(settings: Settings) -> dict[str, Any]:
    return {
        "api_key": "***" if settings.api_key else "",
        "base_url": settings.base_url,
        "max_parallel_tasks": settings.max_parallel_tasks,
        "poll_interval": settings.poll_interval,
        "max_retries": settings.max_retries,
    }


def command_arg(value: Path | str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def build_convert_command(source_path: Path, source_base: Path, output_root: Path) -> str:
    return (
        f"python {SCRIPT_COMMAND} convert {command_arg(source_path)} "
        f"--source-base {command_arg(source_base)} "
        f"--output-root {command_arg(output_root)} --yes"
    )


def pdf_file_count(jobs: list[PdfJob], skipped: list[SkippedPdf]) -> int:
    return len(jobs) + len(skipped)


def build_plan_state(
    source_path: Path,
    source_base: Path,
    output_root: Path,
    jobs: list[PdfJob],
    skipped: list[SkippedPdf],
) -> dict[str, Any]:
    source_path = source_path.resolve()
    source_base = source_base.resolve()
    output_root = output_root.resolve()
    return {
        "stage": "pdf-to-md",
        "skill": "skills/mathos-pdf-to-md",
        "source_path": str(source_path),
        "source_base": str(source_base),
        "output_root": str(output_root),
        "counts": {
            "source_pdfs": pdf_file_count(jobs, skipped),
            "pending": len(jobs),
            "skipped": len(skipped),
            "existing_outputs": len(skipped),
        },
        "pending_files": [
            {"source_pdf": str(job.source_pdf), "target_md": str(job.target_md)}
            for job in jobs
        ],
        "skipped_files": [
            {"source_pdf": str(item.source_pdf), "target_md": str(item.target_md), "reason": item.reason}
            for item in skipped
        ],
        "next_command": build_convert_command(source_path, source_base, output_root) if jobs else "",
    }


def is_retryable_failure(failure: dict[str, str]) -> bool:
    message = failure.get("message", "").lower()
    retryable_markers = [
        "proxyerror",
        "remotedisconnected",
        "connectionpool",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "too many requests",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
    ]
    return any(marker in message for marker in retryable_markers)


def build_run_state(
    settings: Settings,
    source_path: Path,
    source_base: Path,
    output_root: Path,
    jobs: list[PdfJob],
    skipped: list[SkippedPdf],
    results: list[ConversionResult],
    failures: list[dict[str, str]],
    record_dir: Path,
) -> dict[str, Any]:
    retryable_failures = [failure for failure in failures if is_retryable_failure(failure)]
    permanent_failures = [failure for failure in failures if not is_retryable_failure(failure)]
    converted = [result for result in results if result.status == "converted"]
    source_path = source_path.resolve()
    source_base = source_base.resolve()
    output_root = output_root.resolve()
    return {
        "stage": "pdf-to-md",
        "skill": "skills/mathos-pdf-to-md",
        "status": "completed" if not failures else "stopped_or_partially_failed",
        "settings": masked_settings(settings),
        "source_path": str(source_path),
        "source_base": str(source_base),
        "output_root": str(output_root),
        "record_dir": str(record_dir),
        "counts": {
            "source_pdfs": pdf_file_count(jobs, skipped),
            "attempted": len(jobs),
            "converted": len(converted),
            "failed": len(failures),
            "skipped": len(skipped),
            "retryable_failures": len(retryable_failures),
            "permanent_failures": len(permanent_failures),
        },
        "outputs": [
            {
                "source_pdf": str(result.source_pdf),
                "target_md": str(result.target_md),
                "parts": result.parts,
                "assets": result.assets,
            }
            for result in converted
        ],
        "skipped_files": [
            {"source_pdf": str(item.source_pdf), "target_md": str(item.target_md), "reason": item.reason}
            for item in skipped
        ],
        "retryable_failures": retryable_failures,
        "permanent_failures": permanent_failures,
        "records": {
            "manifest": str(record_dir / "manifest.json"),
            "failure_ledger": str(record_dir / "failure-ledger.json"),
            "skipped_files": str(record_dir / "skipped-files.json"),
            "artifact_index": str(record_dir / "artifact-index.md"),
            "run_summary": str(record_dir / "run-summary.md"),
            "run_state": str(record_dir / "run-state.json"),
        },
        "next_command": build_convert_command(source_path, source_base, output_root) if failures else "",
    }


def write_run_state(
    record_dir: Path,
    settings: Settings,
    source_path: Path,
    source_base: Path,
    output_root: Path,
    jobs: list[PdfJob],
    skipped: list[SkippedPdf],
    results: list[ConversionResult],
    failures: list[dict[str, str]],
) -> None:
    state = build_run_state(
        settings=settings,
        source_path=source_path,
        source_base=source_base,
        output_root=output_root,
        jobs=jobs,
        skipped=skipped,
        results=results,
        failures=failures,
        record_dir=record_dir,
    )
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "run-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_manifest(
    manifest_path: Path,
    settings: Settings,
    jobs: list[PdfJob],
    skipped: list[SkippedPdf],
    results: list[ConversionResult] | None = None,
    failures: list[dict[str, str]] | None = None,
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "settings": masked_settings(settings),
        "jobs": [
            {"source_pdf": str(job.source_pdf), "target_md": str(job.target_md)}
            for job in jobs
        ],
        "skipped": [
            {"source_pdf": str(item.source_pdf), "target_md": str(item.target_md), "reason": item.reason}
            for item in skipped
        ],
        "results": [
            dataclasses.asdict(result)
            for result in (results or [])
        ],
        "failures": failures or [],
    }
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def run_record_dir(source_dir: Path, records_root: Path = Path("agent-memory/records")) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", source_dir.name).strip("-") or "source"
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return records_root / f"{stamp}-pdf-to-md-{slug}"


def write_run_summary(record_dir: Path, jobs: list[PdfJob], skipped: list[SkippedPdf], results: list[ConversionResult], failures: list[dict[str, str]]) -> None:
    converted = [result for result in results if result.status == "converted"]
    summary = f"""# Run Summary

## Stage

- Name: pdf-to-md
- Skill: skills/mathos-pdf-to-md
- Command or workflow: MinerU local batch upload API

## Status

- Completion status: {"completed" if not failures else "stopped or partially failed"}
- Stop reason: {"none" if not failures else "one or more conversions failed"}

## Counts

- Attempted files: {len(jobs)}
- Converted files: {len(converted)}
- Failed files: {len(failures)}
- Skipped files: {len(skipped)}
- Warning items: 0

## Outputs

- Manifest: `{record_dir / "manifest.json"}`
- Failure ledger: `{record_dir / "failure-ledger.json"}`

## Boundary Reminder

This summary records execution facts and output inventory. It does not judge content correctness.
"""
    (record_dir / "run-summary.md").write_text(summary, encoding="utf-8")


def write_failure_ledger(record_dir: Path, failures: list[dict[str, str]]) -> None:
    data = {
        "stage": "pdf-to-md",
        "skill": "skills/mathos-pdf-to-md",
        "failure_counts": {
            "conversion_failure": len(failures),
            "missing_api_key": 0,
            "api_error": sum(1 for failure in failures if failure.get("category") == "api_error"),
            "missing_output": sum(1 for failure in failures if failure.get("category") == "missing_output"),
        },
        "failed_items": failures,
        "stopped": bool(failures),
        "stop_reason": "one or more conversions failed" if failures else "",
    }
    (record_dir / "failure-ledger.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_skipped_files(record_dir: Path, skipped: list[SkippedPdf]) -> None:
    data = [
        {"source_pdf": str(item.source_pdf), "target_md": str(item.target_md), "reason": item.reason}
        for item in skipped
    ]
    (record_dir / "skipped-files.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_artifact_index(record_dir: Path, results: list[ConversionResult]) -> None:
    lines = [
        "# Artifact Index",
        "",
        "## Outputs",
        "",
    ]
    for result in sorted(results, key=lambda item: str(item.target_md).lower()):
        lines.append(f"- `{result.target_md}`")
        for zip_path in result.zip_paths:
            lines.append(f"  - Zip: `{zip_path}`")
    lines.extend(
        [
            "",
            "## Run Records",
            "",
            f"- Manifest: `{record_dir / 'manifest.json'}`",
            f"- Failure ledger: `{record_dir / 'failure-ledger.json'}`",
            f"- Skipped files: `{record_dir / 'skipped-files.json'}`",
            f"- Run state: `{record_dir / 'run-state.json'}`",
        ]
    )
    (record_dir / "artifact-index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_source_and_outputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    source_arg = args.source or args.source_dir
    if not source_arg:
        raise ConfigurationError("Missing source path. Provide a PDF file or directory.")
    source_path = Path(source_arg).expanduser().resolve()
    source_base = resolve_source_base(args)
    output_root = resolve_output_root(args)
    return source_path, source_base, output_root


def run_plan(args: argparse.Namespace) -> int:
    source_path, source_base, output_root = resolve_source_and_outputs(args)
    jobs, skipped = discover_pdf_jobs(source_path, source_base, output_root)
    state = build_plan_state(source_path, source_base, output_root, jobs, skipped)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def run_conversion(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.env))
    source_path, source_base, output_root = resolve_source_and_outputs(args)
    jobs, skipped = discover_pdf_jobs(source_path, source_base, output_root)
    record_dir = run_record_dir(source_path)
    record_dir.mkdir(parents=True, exist_ok=True)
    results: list[ConversionResult] = []
    failures: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.max_parallel_tasks) as executor:
        future_map = {
            executor.submit(convert_job, job, MineruClient(settings), record_dir): job
            for job in jobs
        }
        for future in concurrent.futures.as_completed(future_map):
            job = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                category = "api_error" if isinstance(exc, MineruApiError) else "conversion_failure"
                failures.append({"source_pdf": str(job.source_pdf), "category": category, "message": str(exc)})

    write_manifest(record_dir / "manifest.json", settings, jobs, skipped, results, failures)
    write_failure_ledger(record_dir, failures)
    write_skipped_files(record_dir, skipped)
    write_artifact_index(record_dir, results)
    write_run_summary(record_dir, jobs, skipped, results, failures)
    write_run_state(record_dir, settings, source_path, source_base, output_root, jobs, skipped, results, failures)
    print(f"Run records: {record_dir}")
    print(f"Attempted: {len(jobs)} Converted: {len(results)} Failed: {len(failures)} Skipped: {len(skipped)}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert PDF directories to Markdown through MinerU.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("source", nargs="?", help="PDF file or directory to inspect.")
    plan.add_argument("--source-dir", help="PDF directory to inspect. Kept for backward compatibility.")
    plan.add_argument("--source-base", help="Ancestor path to strip before mirroring output hierarchy.")
    plan.add_argument("--output-root")
    plan.add_argument("--yes", action="store_true", help="Use remembered roots without interactive prompt.")

    convert = subparsers.add_parser("convert")
    convert.add_argument("source", nargs="?", help="PDF file or directory to convert.")
    convert.add_argument("--source-dir", help="PDF directory to convert. Kept for backward compatibility.")
    convert.add_argument("--source-base", help="Ancestor path to strip before mirroring output hierarchy.")
    convert.add_argument("--output-root")
    convert.add_argument("--env", default=str(DEFAULT_ENV_PATH))
    convert.add_argument("--yes", action="store_true", help="Use remembered output root without interactive prompt.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        return run_plan(args)
    if args.command == "convert":
        return run_conversion(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import hashlib
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
from urllib.parse import urlparse

import fitz
import requests


DEFAULT_ENV_FILE = Path(r"C:\Mathematics-Knowledge\.env")
DEFAULT_BASE_URL = "https://mineru.net"
MAX_PAGES = 200
MAX_BYTES = 200 * 1024 * 1024
BATCH_SIZE = 50
ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}
TERMINAL_STATES = {"done", "failed"}
IMAGE_LINK_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")


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


def resolve_paths(source_arg: str, output_arg: str | None) -> tuple[Path, Path]:
    source = Path(source_arg).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ConfigurationError(f"Source is not an existing PDF: {source}")
    target = (
        Path(output_arg).expanduser().resolve()
        if output_arg
        else source.with_suffix(".md")
    )
    if target.suffix.lower() != ".md":
        raise ConfigurationError(f"Output must use the .md extension: {target}")
    if source == target:
        raise ConfigurationError("Source PDF and target Markdown paths must differ")
    return source, target


def pdf_page_count(path: Path) -> int:
    try:
        with fitz.open(path) as document:
            count = document.page_count
    except Exception as exc:
        raise ConfigurationError(f"Cannot open PDF: {path}: {exc}") from exc
    if count < 1:
        raise ConfigurationError(f"PDF has no pages: {path}")
    return count


def write_pdf_range(source: Path, target: Path, start_page: int, end_page: int) -> None:
    with fitz.open(source) as source_doc:
        output_doc = fitz.open()
        try:
            output_doc.insert_pdf(
                source_doc,
                from_page=start_page - 1,
                to_page=end_page - 1,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            output_doc.save(target)
        finally:
            output_doc.close()


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
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.stem).strip("._-") or "exam"
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
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    @property
    def auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

    def require_success_json(self, response: requests.Response, action: str) -> dict[str, Any]:
        if response.status_code != 200:
            raise MineruError(f"{action} returned HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise MineruError(f"{action} returned invalid JSON") from exc
        if body.get("code") != 0:
            raise MineruError(
                f"{action} returned MinerU code {body.get('code')}: {body.get('msg', '')}"
            )
        return body

    def request_upload_urls(self, parts: list[PdfPart]) -> tuple[str, list[str]]:
        response = self.session.post(
            f"{self.settings.base_url}/api/v4/file-urls/batch",
            headers=self.auth_headers,
            json=build_payload(parts),
            timeout=self.settings.request_timeout,
        )
        body = self.require_success_json(response, "Upload URL request")
        data = body.get("data") or {}
        batch_id = data.get("batch_id")
        urls = data.get("file_urls") or []
        if not batch_id or len(urls) != len(parts):
            raise MineruError("Upload URL response is missing a batch ID or has a URL-count mismatch")
        return str(batch_id), [str(url) for url in urls]

    def upload(self, url: str, part: PdfPart) -> None:
        with part.path.open("rb") as stream:
            response = self.session.put(
                url,
                data=stream,
                timeout=self.settings.request_timeout,
            )
        if response.status_code != 200:
            raise MineruError(
                f"Upload failed for part {part.index}: HTTP {response.status_code}"
            )

    def poll(self, batch_id: str) -> list[dict[str, Any]]:
        endpoint = f"{self.settings.base_url}/api/v4/extract-results/batch/{batch_id}"
        for poll_index in range(1, self.settings.max_polls + 1):
            response = self.session.get(
                endpoint,
                headers=self.auth_headers,
                timeout=self.settings.request_timeout,
            )
            body = self.require_success_json(response, "Batch result poll")
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
        response = self.session.get(
            url,
            stream=True,
            timeout=self.settings.request_timeout,
        )
        if response.status_code != 200:
            raise MineruError(f"Result download returned HTTP {response.status_code}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as stream:
            for block in response.iter_content(chunk_size=1024 * 1024):
                if block:
                    stream.write(block)


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


def markdown_asset_relative_path(destination: str, namespace: str) -> Path | None:
    clean_destination = destination.strip().strip("<>")
    parsed = urlparse(clean_destination)
    if parsed.scheme or clean_destination.startswith("#"):
        return None
    parts = [part for part in parsed.path.replace("\\", "/").split("/") if part not in {"", "."}]
    lowered = [part.lower() for part in parts]
    if "images" not in lowered:
        return None
    image_index = lowered.index("images")
    remainder = parts[image_index + 1 :]
    namespace_parts = [part for part in namespace.replace("\\", "/").split("/") if part]
    if [part.lower() for part in remainder[: len(namespace_parts)]] == [
        part.lower() for part in namespace_parts
    ]:
        remainder = remainder[len(namespace_parts) :]
    return Path(*remainder) if remainder else None


def rewrite_asset_links(markdown: str, namespace: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix, destination, suffix = match.group(1), match.group(2), match.group(3)
        relative = markdown_asset_relative_path(destination, namespace)
        if relative is None:
            return match.group(0)
        normalized_namespace = namespace.replace("\\", "/").strip("/")
        normalized_relative = relative.as_posix()
        return f"{prefix}images/{normalized_namespace}/{normalized_relative}{suffix}"

    return IMAGE_LINK_RE.sub(replace, markdown)


def unresolved_staged_asset_links(
    markdown: str,
    namespace: str,
    staged_asset_root: Path,
) -> list[str]:
    unresolved: list[str] = []
    for match in IMAGE_LINK_RE.finditer(markdown):
        destination = match.group(2)
        clean_destination = destination.strip().strip("<>")
        parsed = urlparse(clean_destination)
        if parsed.scheme or clean_destination.startswith("#"):
            continue
        relative = markdown_asset_relative_path(destination, namespace)
        if relative is None or not (staged_asset_root / relative).is_file():
            unresolved.append(clean_destination)
    return unresolved


def extract_result(
    zip_path: Path,
    namespace: str,
    staged_asset_root: Path,
) -> tuple[str, int]:
    markdown: str | None = None
    asset_count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            member_path = safe_member(member)
            if member.endswith("/"):
                continue
            if member_path.name.lower() == "full.md":
                markdown = archive.read(member).decode("utf-8")
                continue
            relative_image = image_relative_path(member_path)
            if relative_image is None:
                continue
            destination = staged_asset_root / relative_image
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
            asset_count += 1
    if markdown is None:
        raise ConversionError(f"MinerU result has no full.md: {zip_path.name}")
    rewritten_markdown = rewrite_asset_links(markdown, namespace)
    unresolved = unresolved_staged_asset_links(
        rewritten_markdown,
        namespace,
        staged_asset_root,
    )
    if unresolved:
        raise ConversionError(
            "MinerU Markdown contains unresolved local image links after asset extraction: "
            + ", ".join(unresolved)
        )
    return rewritten_markdown, asset_count


def preflight_output(target: Path, asset_root: Path, overwrite: bool) -> None:
    conflicts = [path for path in (target, asset_root) if path.exists()]
    if conflicts and not overwrite:
        joined = ", ".join(str(path) for path in conflicts)
        raise ConfigurationError(f"Output already exists; explicit --overwrite required: {joined}")


def commit_outputs(
    staged_markdown: Path,
    staged_assets: Path,
    target: Path,
    asset_root: Path,
    overwrite: bool,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        target.unlink(missing_ok=True)
        if asset_root.exists():
            shutil.rmtree(asset_root)
    if staged_assets.exists():
        asset_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_assets), str(asset_root))
    shutil.move(str(staged_markdown), str(target))


def validate_coverage(parts: list[PdfPart], page_count: int) -> None:
    expected = 1
    for part in sorted(parts, key=lambda item: item.index):
        if part.start_page != expected or part.end_page < part.start_page:
            raise ConversionError("Split page ranges contain a gap or overlap")
        expected = part.end_page + 1
    if expected != page_count + 1:
        raise ConversionError("Split page ranges do not cover the complete PDF")


def plan_state(source: Path, target: Path) -> dict[str, Any]:
    pages = pdf_page_count(source)
    size = source.stat().st_size
    page_parts = (pages + MAX_PAGES - 1) // MAX_PAGES
    return {
        "stage": "convert-exam-pdf-to-markdown",
        "status": "planned",
        "source_pdf": str(source),
        "source_sha256": sha256_file(source),
        "page_count": pages,
        "size_bytes": size,
        "target_md": str(target),
        "asset_root": str(target.parent / "images" / source.stem),
        "ocr_forced": True,
        "model_version": "vlm",
        "language": "ch",
        "enable_formula": True,
        "enable_table": True,
        "requires_split": pages > MAX_PAGES or size > MAX_BYTES,
        "minimum_part_count": page_parts,
        "output_conflicts": [
            str(path)
            for path in (target, target.parent / "images" / source.stem)
            if path.exists()
        ],
    }


def convert(source: Path, target: Path, args: argparse.Namespace) -> dict[str, Any]:
    original_hash = sha256_file(source)
    page_count = pdf_page_count(source)
    asset_root = target.parent / "images" / source.stem
    preflight_output(target, asset_root, args.overwrite)
    settings = load_settings(args)
    client = MineruClient(settings)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".exam-pdf-to-md-", dir=target.parent) as temp_name:
        temp_dir = Path(temp_name)
        parts = prepare_parts(source, temp_dir / "parts")
        validate_coverage(parts, page_count)
        markdown_parts: dict[int, str] = {}
        total_assets = 0
        staged_assets_base = temp_dir / "final-assets"

        part_by_id = {part.data_id: part for part in parts}
        for batch_number, batch in enumerate(chunked(parts), start=1):
            batch_id, upload_urls = client.request_upload_urls(batch)
            for part, upload_url in zip(batch, upload_urls):
                print(
                    f"Uploading part {part.index}/{part.count} in batch {batch_number}",
                    file=sys.stderr,
                )
                client.upload(upload_url, part)
            for result in client.poll(batch_id):
                data_id = str(result.get("data_id", ""))
                part = part_by_id.get(data_id)
                if part is None:
                    raise ConversionError(f"MinerU returned unknown data_id: {data_id}")
                if result.get("state") == "failed":
                    raise MineruError(
                        f"MinerU failed part {part.index}: {result.get('err_msg', '')}"
                    )
                zip_url = result.get("full_zip_url")
                if not zip_url:
                    raise MineruError(f"MinerU part {part.index} has no full_zip_url")
                zip_path = temp_dir / "zips" / f"part-{part.index:03d}.zip"
                client.download(str(zip_url), zip_path)
                namespace = source.stem
                staged_asset_root = staged_assets_base
                if part.count > 1:
                    namespace = f"{source.stem}/part-{part.index:03d}"
                    staged_asset_root = staged_assets_base / f"part-{part.index:03d}"
                markdown, asset_count = extract_result(
                    zip_path,
                    namespace,
                    staged_asset_root,
                )
                markdown_parts[part.index] = markdown
                total_assets += asset_count

        if len(markdown_parts) != len(parts):
            raise ConversionError("MinerU returned an incomplete set of PDF parts")
        merged = "\n\n".join(
            markdown_parts[index].strip() for index in range(1, len(parts) + 1)
        ).strip()
        if not merged:
            raise ConversionError("MinerU returned empty Markdown")
        staged_markdown = temp_dir / "result.md"
        staged_markdown.write_text(merged + "\n", encoding="utf-8")

        current_hash = sha256_file(source)
        if current_hash != original_hash:
            raise ConversionError("Ordered PDF changed during conversion")
        commit_outputs(
            staged_markdown,
            staged_assets_base,
            target,
            asset_root,
            args.overwrite,
        )

    if not target.is_file() or target.stat().st_size == 0:
        raise ConversionError("Target Markdown was not created or is empty")
    reported_assets = list(asset_root.rglob("*")) if asset_root.exists() else []
    reported_assets = [path for path in reported_assets if path.is_file()]
    if len(reported_assets) != total_assets:
        raise ConversionError("Extracted asset count does not match committed assets")

    return {
        "stage": "convert-exam-pdf-to-markdown",
        "status": "completed",
        "source_pdf": str(source),
        "source_sha256": original_hash,
        "page_count": page_count,
        "size_bytes": source.stat().st_size,
        "target_md": str(target),
        "asset_root": str(asset_root),
        "asset_count": total_assets,
        "ocr_forced": True,
        "model_version": "vlm",
        "language": "ch",
        "enable_formula": True,
        "enable_table": True,
        "part_count": len(parts),
        "parts": [
            {
                "index": part.index,
                "start_page": part.start_page,
                "end_page": part.end_page,
            }
            for part in parts
        ],
        "validation": {
            "source_hash_unchanged": True,
            "page_coverage_complete": True,
            "target_nonempty": True,
            "assets_committed": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert one ordered exam PDF to Markdown with MinerU forced OCR."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "convert"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("source_pdf")
        subparser.add_argument("--output")
    converter = subparsers.choices["convert"]
    converter.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    converter.add_argument("--base-url")
    converter.add_argument("--poll-interval", type=float, default=10.0)
    converter.add_argument("--max-polls", type=int, default=180)
    converter.add_argument("--request-timeout", type=float, default=120.0)
    converter.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source: Path | None = None
    target: Path | None = None
    try:
        source, target = resolve_paths(args.source_pdf, args.output)
        if args.command == "plan":
            state = plan_state(source, target)
        else:
            state = convert(source, target, args)
        print(json.dumps(state, ensure_ascii=False))
        return 0
    except Exception as exc:
        error = {
            "stage": "convert-exam-pdf-to-markdown",
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "source_pdf": str(source) if source else str(args.source_pdf),
            "target_md": str(target) if target else args.output,
            "ocr_forced": True,
        }
        print(json.dumps(error, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

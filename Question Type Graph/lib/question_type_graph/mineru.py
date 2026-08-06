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

from .common import ConfigurationError, GraphError, load_profile, pdf_page_count, safe_name, sha256_file, write_json_atomic


DEFAULT_ENV_FILE = Path("/Users/oven/Documents/Mathematics-Knowledge-code/.env")
DEFAULT_BASE_URL = "https://mineru.net"
MAX_PAGES = 200
MAX_BYTES = 200 * 1024 * 1024
BATCH_SIZE = 50
ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}
TERMINAL_STATES = {"done", "failed"}
IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")
HTML_IMAGE_RE = re.compile(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'])", re.IGNORECASE)


class MineruError(GraphError):
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
    language: str


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def load_settings(args: argparse.Namespace, profile: dict[str, Any]) -> Settings:
    env = parse_env_file(Path(args.env_file).expanduser().resolve())
    api_key = os.environ.get("MINERU_API_KEY") or env.get("MINERU_API_KEY", "")
    if not api_key:
        raise ConfigurationError("MINERU_API_KEY is missing from the environment and configured .env")
    base_url = (args.base_url or env.get("MINERU_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    if base_url.endswith("/api/v4"):
        base_url = base_url[:-7]
    language = args.language or ("ch" if str(profile.get("language", "")).casefold().startswith("zh") else "en")
    return Settings(api_key, base_url, args.poll_interval, args.max_polls, args.request_timeout, language)


def profile_source(profile: dict[str, Any], role: str) -> dict[str, Any]:
    values = [item for item in profile["sources"] if item.get("role") == role]
    if len(values) != 1:
        raise ConfigurationError(f"Profile must contain exactly one source for role {role!r}")
    source = values[0]
    if source.get("kind") != "pdf":
        raise ConfigurationError(f"Source role {role!r} is not a PDF")
    return source


def write_pdf_range(source: Path, target: Path, start_page: int, end_page: int) -> None:
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception as exc:
        raise ConfigurationError("pypdf is required for PDF splitting") from exc
    reader = PdfReader(str(source))
    writer = PdfWriter()
    for index in range(start_page - 1, end_page):
        writer.add_page(reader.pages[index])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        writer.write(stream)


def fit_ranges(source: Path, initial: list[tuple[int, int]], temp: Path) -> list[tuple[int, int]]:
    accepted: list[tuple[int, int]] = []
    pending = list(initial)
    while pending:
        start, end = pending.pop(0)
        probe = temp / f"probe-{start}-{end}.pdf"
        write_pdf_range(source, probe, start, end)
        size = probe.stat().st_size
        probe.unlink(missing_ok=True)
        if size <= MAX_BYTES:
            accepted.append((start, end))
        elif start == end:
            raise GraphError(f"PDF page {start} exceeds MinerU's 200 MB limit")
        else:
            midpoint = (start + end) // 2
            pending[0:0] = [(start, midpoint), (midpoint + 1, end)]
    return accepted


def data_id(source: Path, index: int, count: int) -> str:
    seed = f"{source.resolve()}:{source.stat().st_size}:{source.stat().st_mtime_ns}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.stem).strip("._-") or "source"
    return f"{stem}.{digest}.{index:03d}-of-{count:03d}"[:128]


def prepare_parts(source: Path, temp: Path) -> list[PdfPart]:
    pages = pdf_page_count(source)
    if pages <= MAX_PAGES and source.stat().st_size <= MAX_BYTES:
        return [PdfPart(source, 1, 1, 1, pages, data_id(source, 1, 1))]
    ranges = [(start, min(start + MAX_PAGES - 1, pages)) for start in range(1, pages + 1, MAX_PAGES)]
    ranges = fit_ranges(source, ranges, temp)
    parts: list[PdfPart] = []
    for index, (start, end) in enumerate(ranges, 1):
        target = temp / f"part-{index:03d}.pdf"
        write_pdf_range(source, target, start, end)
        parts.append(PdfPart(target, index, len(ranges), start, end, data_id(source, index, len(ranges))))
    expected = 1
    for part in parts:
        if part.start_page != expected:
            raise GraphError("PDF split contains a page gap or overlap")
        expected = part.end_page + 1
    if expected != pages + 1:
        raise GraphError("PDF split does not cover every page")
    return parts


def build_payload(parts: list[PdfPart], language: str) -> dict[str, Any]:
    return {
        "files": [{"name": part.path.name, "data_id": part.data_id, "is_ocr": True} for part in parts],
        "model_version": "vlm",
        "language": language,
        "enable_formula": True,
        "enable_table": True,
    }


class Client:
    def __init__(self, settings: Settings):
        self.settings = settings

    def json_request(self, method: str, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib_request.Request(
            f"{self.settings.base_url}{endpoint}",
            data=body,
            headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
            method=method,
        )
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                with urllib_request.urlopen(request, timeout=self.settings.request_timeout) as response:
                    raw = response.read()
                    status = response.status
                break
            except urllib_error.HTTPError as exc:
                if exc.code < 500 or attempt == 3:
                    raise MineruError(f"MinerU returned HTTP {exc.code}") from exc
                last_error = exc
            except (urllib_error.URLError, http.client.RemoteDisconnected, TimeoutError, ConnectionError) as exc:
                last_error = exc
                if attempt == 3:
                    reason = getattr(exc, "reason", str(exc))
                    raise MineruError(f"MinerU request failed after retries: {reason}") from exc
            time.sleep(float(attempt))
        else:
            raise MineruError(f"MinerU request failed after retries: {last_error}")
        if status != 200:
            raise MineruError(f"MinerU returned HTTP {status}")
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise MineruError("MinerU returned invalid JSON") from exc
        if value.get("code") != 0:
            raise MineruError(f"MinerU code {value.get('code')}: {value.get('msg', '')}")
        return value

    def upload_urls(self, parts: list[PdfPart]) -> tuple[str, list[str]]:
        value = self.json_request("POST", "/api/v4/file-urls/batch", build_payload(parts, self.settings.language))
        data = value.get("data") or {}
        batch_id, urls = data.get("batch_id"), data.get("file_urls") or []
        if not batch_id or len(urls) != len(parts):
            raise MineruError("Upload URL response is incomplete")
        return str(batch_id), [str(url) for url in urls]

    def upload(self, url: str, part: PdfPart) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise MineruError("MinerU returned an invalid signed upload URL")
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, parsed.port, timeout=self.settings.request_timeout)
        target = parsed.path or "/"
        if parsed.query:
            target += f"?{parsed.query}"
        try:
            connection.putrequest("PUT", target)
            connection.putheader("Content-Length", str(part.path.stat().st_size))
            connection.endheaders()
            with part.path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    connection.send(block)
            response = connection.getresponse()
            status = response.status
            response.read()
        finally:
            connection.close()
        if status != 200:
            raise MineruError(f"Upload failed for part {part.index}: HTTP {status}")

    def poll(self, batch_id: str) -> list[dict[str, Any]]:
        for attempt in range(1, self.settings.max_polls + 1):
            value = self.json_request("GET", f"/api/v4/extract-results/batch/{batch_id}")
            results = (value.get("data") or {}).get("extract_result") or []
            states = [str(item.get("state", "")) for item in results]
            if results and all(state in TERMINAL_STATES for state in states):
                return results
            if any(state not in ACTIVE_STATES | TERMINAL_STATES for state in states):
                raise MineruError(f"Unknown MinerU states: {states}")
            print(f"MinerU poll {attempt}/{self.settings.max_polls}: {states or ['waiting']}", file=sys.stderr)
            time.sleep(self.settings.poll_interval)
        raise MineruError("MinerU polling timed out")

    def download(self, url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib_request.urlopen(urllib_request.Request(url, method="GET"), timeout=self.settings.request_timeout) as response, target.open("wb") as stream:
                if response.status != 200:
                    raise MineruError(f"Result download returned HTTP {response.status}")
                shutil.copyfileobj(response, stream, length=1024 * 1024)
        except urllib_error.URLError as exc:
            raise MineruError(f"Result download failed: {exc.reason}") from exc


def safe_member(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise GraphError(f"Unsafe path in result zip: {value}")
    return path


def local_image_suffix(destination: str) -> Path | None:
    clean = destination.strip().strip("<>")
    parsed = urlparse(clean)
    if parsed.scheme or clean.startswith("#"):
        return None
    parts = [part for part in parsed.path.replace("\\", "/").split("/") if part not in {"", "."}]
    lowered = [part.casefold() for part in parts]
    if "images" not in lowered:
        return None
    index = lowered.index("images")
    return Path(*parts[index + 1:]) if parts[index + 1:] else None


def extract_zip(
    zip_path: Path,
    namespace: str,
    asset_root: Path,
    provenance_root: Path,
) -> tuple[str, int, list[Path]]:
    markdown: str | None = None
    count = 0
    provenance_files: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            path = safe_member(member)
            if member.endswith("/"):
                continue
            if path.name.casefold() == "full.md":
                markdown = archive.read(member).decode("utf-8")
                continue
            if "content_list" in path.name.casefold() and path.suffix.casefold() == ".json":
                destination = provenance_root / f"{len(provenance_files) + 1:03d}-{safe_name(path.name, 'content_list.json')}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))
                provenance_files.append(destination)
                continue
            lowered = [part.casefold() for part in path.parts]
            if "images" not in lowered:
                continue
            index = lowered.index("images")
            relative = Path(*path.parts[index + 1:])
            destination = asset_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
            count += 1
    if markdown is None:
        raise GraphError("MinerU result zip has no full.md")

    def replace(match: re.Match[str]) -> str:
        suffix = local_image_suffix(match.group(2))
        if suffix is None:
            return match.group(0)
        return f"{match.group(1)}images/{namespace}/{suffix.as_posix()}{match.group(3)}"

    return HTML_IMAGE_RE.sub(replace, IMAGE_RE.sub(replace, markdown)), count, provenance_files


def plan(profile_path: Path, role: str) -> dict[str, Any]:
    profile = load_profile(profile_path)
    source = profile_source(profile, role)
    path = Path(source["path"])
    pages = pdf_page_count(path)
    return {
        "schema_version": 1,
        "stage": "question-type-pdf-to-markdown",
        "status": "planned",
        "profile": profile["_profile_path"],
        "role": role,
        "source_pdf": str(path),
        "source_sha256": source["sha256"],
        "page_count": pages,
        "size_bytes": path.stat().st_size,
        "target_md": source["markdown_path"],
        "requires_split": pages > MAX_PAGES or path.stat().st_size > MAX_BYTES,
        "ocr_forced": True,
        "model_version": "vlm",
        "enable_formula": True,
        "enable_table": True,
    }


def convert(profile_path: Path, role: str, args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(profile_path)
    source_meta = profile_source(profile, role)
    source = Path(source_meta["path"])
    target = Path(args.output).resolve() if args.output else Path(source_meta["markdown_path"]).resolve()
    asset_root = target.parent / "images" / role
    provenance_root = target.parent / "provenance" / role
    if (target.exists() or asset_root.exists() or provenance_root.exists()) and not args.overwrite:
        raise ConfigurationError("Conversion output exists; explicit --overwrite required")
    settings = load_settings(args, profile)
    original_hash = source_meta["sha256"]
    checkpoint_path = Path(profile["paths"]["staging_root"]) / f"{role}-mineru-remote-state.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".question-pdf-", dir=target.parent) as temp_name:
        temp = Path(temp_name)
        parts = prepare_parts(source, temp / "parts")
        client = Client(settings)
        markdown_parts: dict[int, str] = {}
        total_assets = 0
        total_provenance = 0
        part_by_id = {part.data_id: part for part in parts}
        for offset in range(0, len(parts), BATCH_SIZE):
            batch = parts[offset:offset + BATCH_SIZE]
            checkpoint = None
            if checkpoint_path.is_file():
                try:
                    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8-sig"))
                except Exception:
                    checkpoint = None
            expected_ids = [part.data_id for part in batch]
            can_resume = bool(
                checkpoint
                and checkpoint.get("status") == "active"
                and checkpoint.get("source_sha256") == original_hash
                and checkpoint.get("data_ids") == expected_ids
                and checkpoint.get("batch_id")
            )
            if can_resume:
                batch_id = str(checkpoint["batch_id"])
                print(f"Resuming MinerU batch for {role}: {batch_id}", file=sys.stderr)
            else:
                batch_id, urls = client.upload_urls(batch)
                for part, url in zip(batch, urls):
                    print(f"Uploading {role} part {part.index}/{part.count}", file=sys.stderr)
                    client.upload(url, part)
                write_json_atomic(
                    checkpoint_path,
                    {
                        "schema_version": 1,
                        "status": "active",
                        "role": role,
                        "source_sha256": original_hash,
                        "batch_id": batch_id,
                        "data_ids": expected_ids,
                    },
                    overwrite=True,
                )
            for result in client.poll(batch_id):
                part = part_by_id.get(str(result.get("data_id", "")))
                if part is None:
                    raise MineruError("MinerU returned an unknown data_id")
                if result.get("state") == "failed":
                    raise MineruError(f"MinerU failed part {part.index}: {result.get('err_msg', '')}")
                url = result.get("full_zip_url")
                if not url:
                    raise MineruError(f"MinerU part {part.index} has no full_zip_url")
                zip_path = temp / "zips" / f"part-{part.index:03d}.zip"
                client.download(str(url), zip_path)
                namespace = role if len(parts) == 1 else f"{role}/part-{part.index:03d}"
                staged_assets = temp / "assets" / ("" if len(parts) == 1 else f"part-{part.index:03d}")
                staged_provenance = temp / "provenance" / f"part-{part.index:03d}"
                markdown, count, provenance_files = extract_zip(
                    zip_path, namespace, staged_assets, staged_provenance
                )
                marker = f"<!-- source-part:{part.index} pages:{part.start_page}-{part.end_page} -->"
                markdown_parts[part.index] = f"{marker}\n\n{markdown.strip()}"
                total_assets += count
                total_provenance += len(provenance_files)
            write_json_atomic(
                checkpoint_path,
                {
                    "schema_version": 1,
                    "status": "downloaded",
                    "role": role,
                    "source_sha256": original_hash,
                    "batch_id": batch_id,
                    "data_ids": expected_ids,
                },
                overwrite=True,
            )
        if len(markdown_parts) != len(parts):
            raise MineruError("MinerU returned incomplete PDF parts")
        merged = "\n\n".join(markdown_parts[index] for index in range(1, len(parts) + 1)).strip() + "\n"
        if not merged.strip():
            raise MineruError("MinerU returned empty Markdown")
        if sha256_file(source) != original_hash:
            raise GraphError("Source PDF changed during conversion")
        if args.overwrite:
            target.unlink(missing_ok=True)
            if asset_root.exists():
                shutil.rmtree(asset_root)
            if provenance_root.exists():
                shutil.rmtree(provenance_root)
        target.write_text(merged, encoding="utf-8", newline="\n")
        staged_base = temp / "assets"
        if staged_base.exists():
            asset_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged_base), str(asset_root))
        staged_provenance_base = temp / "provenance"
        if staged_provenance_base.exists():
            provenance_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged_provenance_base), str(provenance_root))
    provenance_artifacts = [
        {"path": str(path.resolve()), "sha256": sha256_file(path.resolve())}
        for path in sorted(provenance_root.rglob("*.json"))
    ] if provenance_root.exists() else []
    report = {
        "schema_version": 1,
        "stage": "question-type-pdf-to-markdown",
        "status": "completed",
        "profile": profile["_profile_path"],
        "role": role,
        "source_pdf": str(source),
        "source_sha256": original_hash,
        "target_md": str(target),
        "target_sha256": sha256_file(target),
        "page_count": pdf_page_count(source),
        "part_count": len(parts),
        "parts": [{"index": p.index, "start_page": p.start_page, "end_page": p.end_page} for p in parts],
        "asset_count": total_assets,
        "page_provenance": {
            "format": "mineru-content-list",
            "page_index_semantics": "raw MinerU page_idx values are preserved per PDF part",
            "artifact_count": total_provenance,
            "artifacts": provenance_artifacts,
        },
        "ocr_forced": True,
        "model_version": "vlm",
        "language": settings.language,
        "enable_formula": True,
        "enable_table": True,
        "validation": {
            "source_hash_unchanged": True,
            "page_coverage_complete": True,
            "target_nonempty": True,
            "page_block_provenance_preserved": total_provenance > 0,
        },
    }
    if args.report:
        write_json_atomic(Path(args.report), report, overwrite=args.overwrite)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a typed supplementary-book PDF with forced MinerU OCR.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "convert"):
        item = sub.add_parser(command)
        item.add_argument("profile", type=Path)
        item.add_argument("role", choices=["questions", "answers", "combined"])
        item.add_argument("--output")
    convert_parser = sub.choices["convert"]
    convert_parser.add_argument("--report")
    convert_parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    convert_parser.add_argument("--base-url")
    convert_parser.add_argument("--language")
    convert_parser.add_argument("--poll-interval", type=float, default=10.0)
    convert_parser.add_argument("--max-polls", type=int, default=180)
    convert_parser.add_argument("--request-timeout", type=float, default=120.0)
    convert_parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = plan(args.profile, args.role) if args.command == "plan" else convert(args.profile, args.role, args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "question-type-pdf-to-markdown", "status": "failed", "error_type": type(exc).__name__, "message": str(exc), "ocr_forced": True}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Inventory unordered exam images and merge an explicitly evidenced order."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
SCHEMA_VERSION = 1


class SkillError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SkillError(f"Expected a JSON object in {path}")
    return payload


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def collect_images(source_dir: Path, recursive: bool, excluded_dir: Path) -> list[Path]:
    iterator = source_dir.rglob("*") if recursive else source_dir.iterdir()
    images = []
    for path in iterator:
        resolved = path.resolve()
        if not path.is_file() or path.suffix.lower() not in RASTER_EXTENSIONS:
            continue
        if is_within(resolved, excluded_dir):
            continue
        images.append(resolved)
    return sorted(images, key=lambda item: str(item.relative_to(source_dir)).casefold())


def inspect_image(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as source:
            source.verify()
        with Image.open(path) as source:
            exif = source.getexif()
            orientation = exif.get(274)
            capture_time = exif.get(36867) or exif.get(306)
            original_width, original_height = source.size
            transposed = ImageOps.exif_transpose(source)
            width, height = transposed.size
            mode = transposed.mode
            image_format = source.format
    except Exception as exc:
        raise SkillError(f"Cannot decode image {path}: {exc}") from exc

    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "original_width": original_width,
        "original_height": original_height,
        "width": width,
        "height": height,
        "mode": mode,
        "format": image_format,
        "exif_orientation": orientation,
        "exif_capture_time": capture_time,
        "filesystem_modified_utc": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
        "filename_number_tokens": re.findall(r"\d+", path.stem),
    }


def render_contact_sheets(
    records: list[dict[str, Any]],
    source_dir: Path,
    output_dir: Path,
    prefix: str,
    ordered: bool = False,
) -> list[str]:
    columns = 3
    rows = 3
    cell_width = 520
    cell_height = 700
    label_height = 92
    per_sheet = columns * rows
    font = load_font(22)
    small_font = load_font(17)
    outputs: list[str] = []

    for sheet_index, start in enumerate(range(0, len(records), per_sheet), start=1):
        batch = records[start : start + per_sheet]
        sheet = Image.new(
            "RGB",
            (columns * cell_width, rows * cell_height),
            "white",
        )
        draw = ImageDraw.Draw(sheet)

        for offset, record in enumerate(batch):
            row, column = divmod(offset, columns)
            left = column * cell_width
            top = row * cell_height
            source_path = (source_dir / record["relative_path"]).resolve()
            with Image.open(source_path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                thumbnail = ImageOps.contain(
                    image,
                    (cell_width - 24, cell_height - label_height - 24),
                )
            image_left = left + (cell_width - thumbnail.width) // 2
            image_top = top + 10
            sheet.paste(thumbnail, (image_left, image_top))

            sequence = record.get("sequence")
            heading = (
                f"Page {sequence:03d} | {record['image_id']}"
                if ordered and sequence is not None
                else record["image_id"]
            )
            label_top = top + cell_height - label_height
            draw.rectangle(
                (left, label_top, left + cell_width - 1, top + cell_height - 1),
                fill="#f3f4f6",
                outline="#9ca3af",
            )
            draw.text((left + 10, label_top + 6), heading, fill="black", font=font)
            filename = textwrap.shorten(
                record["relative_path"],
                width=48,
                placeholder="...",
            )
            draw.text(
                (left + 10, label_top + 42),
                filename,
                fill="#374151",
                font=small_font,
            )
            draw.rectangle(
                (left, top, left + cell_width - 1, top + cell_height - 1),
                outline="#6b7280",
                width=1,
            )

        output_path = output_dir / f"{prefix}-{sheet_index:03d}.png"
        sheet.save(output_path, format="PNG")
        outputs.append(str(output_path.resolve()))
    return outputs


def inventory_command(args: argparse.Namespace) -> dict[str, Any]:
    source_dir = Path(args.image_folder).resolve()
    work_dir = Path(args.work_dir).resolve()
    if not source_dir.is_dir():
        raise SkillError(f"Image folder does not exist: {source_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)

    image_paths = collect_images(source_dir, args.recursive, work_dir)
    if not image_paths:
        raise SkillError(f"No supported raster images found in {source_dir}")

    records: list[dict[str, Any]] = []
    for index, image_path in enumerate(image_paths, start=1):
        details = inspect_image(image_path)
        records.append(
            {
                "image_id": f"IMG-{index:04d}",
                "relative_path": image_path.relative_to(source_dir).as_posix(),
                **details,
            }
        )

    hash_groups: dict[str, list[str]] = {}
    for record in records:
        hash_groups.setdefault(record["sha256"], []).append(record["image_id"])
    duplicates = [
        {"sha256": digest, "image_ids": image_ids}
        for digest, image_ids in hash_groups.items()
        if len(image_ids) > 1
    ]

    contact_sheets = render_contact_sheets(
        records,
        source_dir,
        work_dir,
        "inventory-contact-sheet",
    )
    inventory_path = work_dir / "inventory.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "recursive": bool(args.recursive),
        "image_count": len(records),
        "images": records,
        "exact_duplicate_groups": duplicates,
        "contact_sheets": contact_sheets,
        "warning": (
            "Inventory and contact-sheet order are inspection aids only, not final page order."
        ),
    }
    write_json(inventory_path, payload)

    template_path = work_dir / "order-manifest.template.json"
    write_json(
        template_path,
        {
            "schema_version": SCHEMA_VERSION,
            "status": "draft",
            "document_pattern": "",
            "content_evidence": [],
            "ambiguities": ["Replace with [] only after resolving every ambiguity."],
            "ordered_images": [],
        },
    )
    return {
        "status": "inventory_complete",
        "image_count": len(records),
        "inventory": str(inventory_path),
        "order_template": str(template_path),
        "contact_sheets": contact_sheets,
        "exact_duplicate_groups": duplicates,
    }


def validate_order(
    inventory: dict[str, Any],
    order: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if inventory.get("schema_version") != SCHEMA_VERSION:
        raise SkillError("Unsupported inventory schema version")
    if order.get("schema_version") != SCHEMA_VERSION:
        raise SkillError("Unsupported order-manifest schema version")
    if order.get("status") != "ready":
        raise SkillError("Order manifest status must be 'ready'")
    if order.get("ambiguities") != []:
        raise SkillError("Order manifest must contain an empty ambiguities list")
    content_evidence = order.get("content_evidence")
    if not isinstance(content_evidence, list) or not any(
        isinstance(item, str) and item.strip() for item in content_evidence
    ):
        raise SkillError("Order manifest requires non-page-number content evidence")

    inventory_records = inventory.get("images")
    ordered_entries = order.get("ordered_images")
    if not isinstance(inventory_records, list) or not inventory_records:
        raise SkillError("Inventory contains no image records")
    if not isinstance(ordered_entries, list):
        raise SkillError("ordered_images must be a list")

    by_id = {record.get("image_id"): record for record in inventory_records}
    if None in by_id or len(by_id) != len(inventory_records):
        raise SkillError("Inventory image IDs are missing or duplicated")

    seen: set[str] = set()
    ordered_records: list[dict[str, Any]] = []
    for position, entry in enumerate(ordered_entries, start=1):
        if not isinstance(entry, dict):
            raise SkillError(f"Order entry {position} must be an object")
        image_id = entry.get("image_id")
        if image_id not in by_id:
            raise SkillError(f"Unknown image ID at position {position}: {image_id}")
        if image_id in seen:
            raise SkillError(f"Duplicate image ID in order manifest: {image_id}")
        seen.add(image_id)
        confidence = entry.get("confidence")
        if confidence not in {"high", "medium"}:
            raise SkillError(
                f"{image_id} confidence must be 'high' or 'medium', not {confidence!r}"
            )
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise SkillError(f"{image_id} requires a content-based ordering reason")
        record = dict(by_id[image_id])
        record["sequence"] = position
        record["confidence"] = confidence
        record["reason"] = reason.strip()
        ordered_records.append(record)

    expected = set(by_id)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise SkillError(f"Order manifest coverage mismatch; missing={missing}, extra={extra}")
    return ordered_records, ordered_entries


def image_for_pdf(source_path: Path) -> Image.Image:
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode in {"RGBA", "LA"} or (
            image.mode == "P" and "transparency" in image.info
        ):
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            return background.convert("RGB")
        return image.convert("RGB")


def merge_command(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise SkillError(
            "ReportLab and pypdf are required; use the Codex bundled Python runtime."
        ) from exc

    inventory_path = Path(args.inventory).resolve()
    order_path = Path(args.order).resolve()
    output_path = Path(args.output).resolve()
    inventory = read_json(inventory_path)
    order = read_json(order_path)
    ordered_records, _ = validate_order(inventory, order)
    source_dir = Path(inventory.get("source_dir", "")).resolve()
    if not source_dir.is_dir():
        raise SkillError(f"Inventory source folder no longer exists: {source_dir}")

    if output_path.exists() and not args.overwrite:
        raise SkillError(f"Output already exists; explicit overwrite required: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    verified_sources: list[dict[str, Any]] = []
    for record in ordered_records:
        source_path = (source_dir / record["relative_path"]).resolve()
        if not is_within(source_path, source_dir):
            raise SkillError(f"Image path escapes source folder: {record['relative_path']}")
        if not source_path.is_file():
            raise SkillError(f"Source image is missing: {source_path}")
        current_hash = sha256_file(source_path)
        if current_hash != record["sha256"]:
            raise SkillError(f"Source image changed after inventory: {source_path}")
        verified_sources.append(
            {
                "sequence": record["sequence"],
                "image_id": record["image_id"],
                "relative_path": record["relative_path"],
                "sha256": current_hash,
                "confidence": record["confidence"],
                "reason": record["reason"],
            }
        )

    temporary_file = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}-",
        suffix=".tmp.pdf",
        dir=output_path.parent,
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()
    try:
        pdf = canvas.Canvas(str(temporary_path), pageCompression=1)
        pdf.setTitle(output_path.stem)
        pdf.setAuthor("Exam Paper Organizer")
        pdf.setSubject("Semantically ordered exam page images")
        for record in ordered_records:
            source_path = (source_dir / record["relative_path"]).resolve()
            image = image_for_pdf(source_path)
            width_px, height_px = image.size
            width_pt = width_px * 72.0 / args.dpi
            height_pt = height_px * 72.0 / args.dpi
            page_scale = min(1.0, 14400.0 / max(width_pt, height_pt))
            width_pt *= page_scale
            height_pt *= page_scale
            stream = io.BytesIO()
            image.save(stream, format="PNG", optimize=True)
            stream.seek(0)
            pdf.setPageSize((width_pt, height_pt))
            pdf.drawImage(
                ImageReader(stream),
                0,
                0,
                width=width_pt,
                height=height_pt,
                preserveAspectRatio=True,
                mask="auto",
            )
            pdf.showPage()
        pdf.save()

        reader = PdfReader(str(temporary_path))
        page_count = len(reader.pages)
        expected_count = len(ordered_records)
        if page_count != expected_count:
            raise SkillError(
                f"PDF page-count mismatch: expected {expected_count}, found {page_count}"
            )
        for record in verified_sources:
            source_path = (source_dir / record["relative_path"]).resolve()
            if sha256_file(source_path) != record["sha256"]:
                raise SkillError(f"Source image changed during merge: {source_path}")
        if output_path.exists() and not args.overwrite:
            raise SkillError(
                f"Output appeared during merge; explicit overwrite required: {output_path}"
            )
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    preview_dir = order_path.parent
    ordered_previews = render_contact_sheets(
        ordered_records,
        source_dir,
        preview_dir,
        "ordered-preview",
        ordered=True,
    )
    report_path = (
        Path(args.report).resolve()
        if args.report
        else order_path.parent / "merge-report.json"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "merged_pending_visual_verification",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "inventory": str(inventory_path),
        "order_manifest": str(order_path),
        "output_pdf": str(output_path),
        "output_sha256": sha256_file(output_path),
        "ordered_image_count": expected_count,
        "page_count": page_count,
        "dpi": args.dpi,
        "ordered_images": verified_sources,
        "ordered_previews": ordered_previews,
        "source_hashes_verified": True,
        "visual_verification_required": True,
    }
    write_json(report_path, report)
    return {
        "status": "merged_pending_visual_verification",
        "output_pdf": str(output_path),
        "output_sha256": report["output_sha256"],
        "page_count": page_count,
        "ordered_image_count": expected_count,
        "merge_report": str(report_path),
        "ordered_previews": ordered_previews,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory and merge semantically ordered exam-page images."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser(
        "inventory",
        help="Hash images and create labeled contact sheets without assuming order.",
    )
    inventory_parser.add_argument("image_folder")
    inventory_parser.add_argument("--work-dir", required=True)
    inventory_parser.add_argument("--recursive", action="store_true")
    inventory_parser.set_defaults(handler=inventory_command)

    merge_parser = subparsers.add_parser(
        "merge",
        help="Validate an evidenced order manifest and create one PDF.",
    )
    merge_parser.add_argument("--inventory", required=True)
    merge_parser.add_argument("--order", required=True)
    merge_parser.add_argument("--output", required=True)
    merge_parser.add_argument("--report")
    merge_parser.add_argument("--dpi", type=float, default=144.0)
    merge_parser.add_argument("--overwrite", action="store_true")
    merge_parser.set_defaults(handler=merge_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if not math.isfinite(getattr(args, "dpi", 1)) or getattr(args, "dpi", 1) <= 0:
            raise SkillError("--dpi must be positive")
        result = args.handler(args)
    except SkillError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

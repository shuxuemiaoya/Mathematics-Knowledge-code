import json
import importlib.util
import sys
import zipfile
from pathlib import Path

import fitz
import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "mathos-pdf-to-md"
    / "scripts"
    / "mathos_pdf_to_md.py"
)
spec = importlib.util.spec_from_file_location("mathos_pdf_to_md", SCRIPT_PATH)
tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["mathos_pdf_to_md"] = tool
spec.loader.exec_module(tool)


def make_pdf(path: Path, pages: int) -> None:
    doc = fitz.open()
    for page_number in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {page_number + 1}")
    doc.save(path)
    doc.close()


def test_mirror_output_path_preserves_hierarchy_and_renames_pdf(tmp_path):
    source_base = tmp_path / "sync"
    source_pdf = source_base / "数学妙呀资料" / "小学" / "六级上册" / "函数.pdf"
    output_root = tmp_path / "vault"
    source_pdf.parent.mkdir(parents=True)
    source_pdf.write_bytes(b"%PDF")

    output_md = tool.target_markdown_path(source_pdf, source_base, output_root)

    assert output_md == output_root / "数学妙呀资料" / "小学" / "六级上册" / "函数.md"


def test_source_outside_source_base_is_rejected(tmp_path):
    with pytest.raises(tool.ConfigurationError, match="source base"):
        tool.target_markdown_path(
            tmp_path / "other" / "a.pdf",
            tmp_path / "sync",
            tmp_path / "vault",
        )


def test_discover_pdf_jobs_recurses_and_skips_existing_markdown(tmp_path):
    source_base = tmp_path / "sync"
    output_root = tmp_path / "vault"
    pending_pdf = source_base / "a" / "pending.pdf"
    done_pdf = source_base / "a" / "done.pdf"
    nested_pdf = source_base / "a" / "b" / "nested.PDF"
    ignored_txt = source_base / "a" / "ignored.txt"
    for path in [pending_pdf, done_pdf, nested_pdf, ignored_txt]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    done_target = tool.target_markdown_path(done_pdf, source_base, output_root)
    done_target.parent.mkdir(parents=True)
    done_target.write_text("already done", encoding="utf-8")

    jobs, skipped = tool.discover_pdf_jobs(source_base, source_base, output_root)

    assert [job.source_pdf.name for job in jobs] == ["pending.pdf", "nested.PDF"]
    assert [item.source_pdf.name for item in skipped] == ["done.pdf"]


def test_discover_pdf_jobs_accepts_single_pdf_and_preserves_source_base_hierarchy(tmp_path):
    source_base = tmp_path / "数学妙呀资料"
    source_pdf = source_base / "小学" / "人教版数学" / "六年级上册" / "2025秋一遍过数学RJ6上.pdf"
    output_root = tmp_path / "Secondary-School-Mathematics-Knowledge-Map"
    source_pdf.parent.mkdir(parents=True)
    source_pdf.write_bytes(b"%PDF")

    jobs, skipped = tool.discover_pdf_jobs(source_pdf, source_base, output_root)

    assert skipped == []
    assert len(jobs) == 1
    assert jobs[0].source_pdf == source_pdf.resolve()
    assert jobs[0].target_md == output_root.resolve() / "小学" / "人教版数学" / "六年级上册" / "2025秋一遍过数学RJ6上.md"


def test_discover_single_pdf_skips_existing_markdown(tmp_path):
    source_base = tmp_path / "数学妙呀资料"
    source_pdf = source_base / "小学" / "人教版数学" / "六年级上册" / "done.pdf"
    output_root = tmp_path / "vault"
    source_pdf.parent.mkdir(parents=True)
    source_pdf.write_bytes(b"%PDF")
    target = output_root / "小学" / "人教版数学" / "六年级上册" / "done.md"
    target.parent.mkdir(parents=True)
    target.write_text("already done", encoding="utf-8")

    jobs, skipped = tool.discover_pdf_jobs(source_pdf, source_base, output_root)

    assert jobs == []
    assert len(skipped) == 1
    assert skipped[0].target_md == target.resolve()


def test_resolve_source_base_uses_remembered_config(tmp_path):
    config_path = tmp_path / "config.json"
    source_base = tmp_path / "数学妙呀资料"
    tool.save_config({"default_source_base": str(source_base)}, config_path)
    args = type("Args", (), {"source_base": None, "yes": True})()

    assert tool.resolve_source_base(args, config_path) == source_base.resolve()


def test_load_env_reads_mineru_key_without_returning_other_secret_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MINERU_API_KEY=secret-token\nBASE_URL=https://example.test\nMAX_PARALLEL_TASKS=7\n",
        encoding="utf-8",
    )

    settings = tool.load_settings(env_path)

    assert settings.api_key == "secret-token"
    assert settings.base_url == "https://example.test"
    assert settings.max_parallel_tasks == 7


def test_load_env_normalizes_mineru_api_v4_base_url(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MINERU_API_KEY=secret-token\nBASE_URL=https://mineru.net/api/v4\n",
        encoding="utf-8",
    )

    settings = tool.load_settings(env_path)

    assert settings.base_url == "https://mineru.net"


def test_default_config_path_lives_in_skill_root():
    assert tool.DEFAULT_CONFIG_PATH == SCRIPT_PATH.parents[1] / "config.json"


def test_plan_pdf_parts_splits_by_page_limit(tmp_path):
    pdf = tmp_path / "long.pdf"
    make_pdf(pdf, 201)

    parts = tool.plan_pdf_parts(pdf, max_pages=200, max_bytes=200 * 1024 * 1024)

    assert [(part.start_page, part.end_page) for part in parts] == [(1, 200), (201, 201)]
    assert all(part.requires_split for part in parts)


def test_build_batch_payload_forces_ocr_and_default_mineru_options(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    part = tool.PdfPart(
        source_pdf=pdf,
        upload_path=pdf,
        data_id="abc",
        part_index=1,
        part_count=1,
        start_page=1,
        end_page=1,
        requires_split=False,
    )

    payload = tool.build_batch_payload([part])

    assert payload["model_version"] == "vlm"
    assert payload["language"] == "ch"
    assert payload["enable_formula"] is True
    assert payload["enable_table"] is True
    assert payload["files"] == [{"name": "a.pdf", "data_id": "abc", "is_ocr": True}]


def test_extract_mineru_zip_renames_full_md_and_rewrites_asset_links(tmp_path):
    zip_path = tmp_path / "result.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("full.md", "# Title\n\n![](images/pic.png)\n")
        archive.writestr("images/pic.png", b"img")
        archive.writestr("middle.json", "{}")
    output_md = tmp_path / "vault" / "unit" / "函数.md"
    artifact_dir = tmp_path / "records"

    result = tool.extract_mineru_zip(
        zip_path=zip_path,
        output_md=output_md,
        pdf_stem="函数",
        artifact_dir=artifact_dir,
        part_label="part-001",
    )

    assert output_md.read_text(encoding="utf-8") == "# Title\n\n![](images/函数/pic.png)\n"
    assert (output_md.parent / "images" / "函数" / "pic.png").read_bytes() == b"img"
    assert result.markdown_path == output_md
    assert result.asset_count == 1


def test_merge_markdown_parts_preserves_order_and_assets(tmp_path):
    output_md = tmp_path / "vault" / "book.md"
    output_md.parent.mkdir(parents=True)
    first = tool.ExtractedPart(
        markdown_path=tmp_path / "part1.md",
        markdown_text="first",
        assets=[],
        asset_count=0,
        part_index=1,
    )
    second = tool.ExtractedPart(
        markdown_path=tmp_path / "part2.md",
        markdown_text="second",
        assets=[],
        asset_count=0,
        part_index=2,
    )

    tool.merge_markdown_parts([second, first], output_md)

    assert output_md.read_text(encoding="utf-8") == "first\n\nsecond\n"


def test_extract_split_part_can_namespace_assets_by_part(tmp_path):
    zip_path = tmp_path / "result.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("full.md", "![](images/pic.png)\n")
        archive.writestr("images/pic.png", b"img")
    output_md = tmp_path / "records" / "part.md"

    result = tool.extract_mineru_zip(
        zip_path=zip_path,
        output_md=output_md,
        pdf_stem="函数/part-001",
        artifact_dir=tmp_path / "records",
        part_label="part-001",
    )

    assert result.markdown_text == "![](images/函数/part-001/pic.png)\n"


def test_write_manifest_masks_api_key(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    settings = tool.Settings(
        api_key="secret-token",
        base_url="https://mineru.net",
        max_parallel_tasks=10,
        poll_interval=1,
        max_retries=2,
    )

    tool.write_manifest(manifest_path, settings, jobs=[], skipped=[])

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "secret-token" not in manifest_path.read_text(encoding="utf-8")
    assert data["settings"]["api_key"] == "***"


def test_build_plan_state_reports_counts_and_next_command(tmp_path):
    source_base = tmp_path / "source"
    source_path = source_base / "小学"
    output_root = tmp_path / "vault"
    pending_pdf = source_path / "a.pdf"
    done_pdf = source_path / "done.pdf"
    for pdf in [pending_pdf, done_pdf]:
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF")
    done_target = output_root / "小学" / "done.md"
    done_target.parent.mkdir(parents=True)
    done_target.write_text("done", encoding="utf-8")
    jobs, skipped = tool.discover_pdf_jobs(source_path, source_base, output_root)

    state = tool.build_plan_state(source_path, source_base, output_root, jobs, skipped)

    assert state["counts"] == {
        "source_pdfs": 2,
        "pending": 1,
        "skipped": 1,
        "existing_outputs": 1,
    }
    assert state["pending_files"][0]["source_pdf"] == str(pending_pdf.resolve())
    assert "--source-base" in state["next_command"]
    assert str(source_base.resolve()) in state["next_command"]


def test_write_run_state_groups_retryable_failures_and_next_command(tmp_path):
    source_base = tmp_path / "source"
    source_path = source_base / "小学"
    output_root = tmp_path / "vault"
    pdf = source_path / "a.pdf"
    target_md = output_root / "小学" / "a.md"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF")
    job = tool.PdfJob(pdf.resolve(), target_md.resolve())
    record_dir = tmp_path / "records"
    settings = tool.Settings(api_key="secret-token", max_parallel_tasks=1)
    failures = [
        {
            "source_pdf": str(pdf.resolve()),
            "category": "conversion_failure",
            "message": "ProxyError: RemoteDisconnected",
        },
        {
            "source_pdf": str(source_path / "bad.pdf"),
            "category": "conversion_failure",
            "message": "missing full.md",
        },
    ]

    tool.write_run_state(
        record_dir=record_dir,
        settings=settings,
        source_path=source_path,
        source_base=source_base,
        output_root=output_root,
        jobs=[job],
        skipped=[],
        results=[],
        failures=failures,
    )

    state = json.loads((record_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["settings"]["api_key"] == "***"
    assert state["counts"]["failed"] == 2
    assert state["counts"]["retryable_failures"] == 1
    assert state["retryable_failures"][0]["source_pdf"] == str(pdf.resolve())
    assert state["permanent_failures"][0]["message"] == "missing full.md"
    assert "convert" in state["next_command"]

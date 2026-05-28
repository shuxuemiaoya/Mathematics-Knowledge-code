import pytest

from math_knowledge_tools.mineru.batch_parser.file_utils import get_output_paths, merge_md_files


def test_get_output_paths_falls_back_without_escaping_out_dir(tmp_path):
    batch_root = tmp_path / "batch"
    source_dir = batch_root / "chapter"
    source_dir.mkdir(parents=True)
    pdf_path = source_dir / "lesson.pdf"
    docx_path = source_dir / "lesson.docx"
    pdf_path.write_bytes(b"%PDF-1.4")
    docx_path.write_bytes(b"docx")

    out_dir = tmp_path / "knowledge"
    unrelated_base = tmp_path / "other-source-root"
    unrelated_base.mkdir()

    output_md, output_images = get_output_paths(
        str(docx_path),
        str(unrelated_base),
        str(out_dir),
        fallback_root=str(batch_root),
    )

    assert output_md == str(out_dir / "chapter" / "lesson_docx.md")
    assert output_images == str(out_dir / "chapter" / "images")


def test_get_output_paths_rejects_source_outside_base_without_fallback(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside" / "a.pdf"
    outside.parent.mkdir()
    outside.write_bytes(b"%PDF-1.4")

    with pytest.raises(ValueError):
        get_output_paths(str(outside), str(base), str(tmp_path / "out"))


def test_merge_md_files_rewrites_chunk_image_names(tmp_path):
    extract_a = tmp_path / "extract_a"
    extract_b = tmp_path / "extract_b"
    for extract in (extract_a, extract_b):
        (extract / "images").mkdir(parents=True)

    md_a = extract_a / "full.md"
    md_b = extract_b / "full.md"
    md_a.write_text("![a](images/a.png)", encoding="utf-8")
    md_b.write_text("![b](images/b.png)", encoding="utf-8")
    (extract_a / "images" / "a.png").write_bytes(b"a")
    (extract_b / "images" / "b.png").write_bytes(b"b")

    output_md = tmp_path / "out" / "merged.md"
    merge_md_files(
        [(str(md_a), str(extract_a)), (str(md_b), str(extract_b))],
        str(output_md),
        str(tmp_path / "out" / "images"),
    )

    merged = output_md.read_text(encoding="utf-8")
    assert "images/chunk_000_a.png" in merged
    assert "images/chunk_001_b.png" in merged
    assert (tmp_path / "out" / "images" / "chunk_000_a.png").exists()
    assert (tmp_path / "out" / "images" / "chunk_001_b.png").exists()

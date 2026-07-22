from pathlib import Path
import argparse
import importlib.util
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "mathos-pdf-to-md" / "scripts" / "mathos_pdf_to_md.py"

spec = importlib.util.spec_from_file_location("mathos_pdf_to_md", SCRIPT_PATH)
pdf_to_md = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["mathos_pdf_to_md"] = pdf_to_md
spec.loader.exec_module(pdf_to_md)


def test_convert_does_not_write_agent_memory_records(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source" / "book.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF-1.4\n")
    output_root = tmp_path / "out"
    target = output_root / "book.md"
    job = pdf_to_md.PdfJob(source_pdf=source, target_md=target)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pdf_to_md, "load_settings", lambda env: pdf_to_md.Settings(api_key="test-key"))
    monkeypatch.setattr(pdf_to_md, "discover_pdf_jobs", lambda source_path, source_base, output_root_arg: ([job], []))

    def fake_convert_job(job_arg, client, artifact_dir):
        assert "agent-memory" not in artifact_dir.parts
        job_arg.target_md.parent.mkdir(parents=True, exist_ok=True)
        job_arg.target_md.write_text("# converted\n", encoding="utf-8")
        return pdf_to_md.ConversionResult(
            source_pdf=job_arg.source_pdf,
            target_md=job_arg.target_md,
            status="converted",
            parts=1,
            assets=0,
        )

    monkeypatch.setattr(pdf_to_md, "convert_job", fake_convert_job)

    args = argparse.Namespace(
        source=str(source),
        source_dir=None,
        source_base=str(source.parent),
        output_root=str(output_root),
        env=str(tmp_path / ".env"),
        yes=True,
    )

    assert pdf_to_md.run_conversion(args) == 0

    captured = capsys.readouterr()
    assert "Run records:" not in captured.out
    state = json.loads(captured.out)
    assert state["counts"]["converted"] == 1
    assert state["outputs"][0]["target_md"] == str(target)
    assert not (tmp_path / "agent-memory" / "records").exists()

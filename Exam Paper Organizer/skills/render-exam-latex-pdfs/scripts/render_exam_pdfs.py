from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_PAPER = "ExamPaper（题解整合版）.md"
DEFAULT_SOLUTIONS = "ExamPaper（题解整合版）（解析版）.md"


class RenderError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(value: str | None, folder: Path, default_name: str) -> Path:
    if value is None:
        return (folder / default_name).resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = folder / candidate
    return candidate.resolve()


def require_source(path: Path, label: str) -> None:
    if not path.is_file():
        raise RenderError(f"Missing {label} Markdown source: {path}")
    if path.suffix.lower() != ".md":
        raise RenderError(f"{label} source is not Markdown: {path}")
    if path.stat().st_size == 0:
        raise RenderError(f"{label} Markdown source is empty: {path}")


def run_process(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def write_log(path: Path, command: list[str], output: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered_command = subprocess.list2cmdline(command)
    path.write_text(f"COMMAND\n{rendered_command}\n\nOUTPUT\n{output}", encoding="utf-8")


def pandoc_to_latex(
    pandoc: str,
    source: Path,
    tex_output: Path,
    template: Path,
    lua_filter: Path,
    folder: Path,
    log_dir: Path,
) -> dict[str, Any]:
    resource_paths = [source.parent, folder]
    images = folder / "images"
    if images.is_dir():
        resource_paths.append(images)

    command = [
        pandoc,
        str(source),
        "--from=markdown+raw_html+raw_tex+tex_math_dollars+fenced_divs+link_attributes",
        "--to=latex",
        "--standalone",
        f"--template={template}",
        f"--lua-filter={lua_filter}",
        f"--resource-path={os.pathsep.join(str(path) for path in resource_paths)}",
        "--wrap=preserve",
        f"--output={tex_output}",
    ]
    result = run_process(command, source.parent)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    log_path = log_dir / f"{source.stem}.pandoc.log"
    if result.returncode != 0:
        write_log(log_path, command, output)
        raise RenderError(f"Pandoc failed for {source}; see {log_path}")
    if not tex_output.is_file() or tex_output.stat().st_size == 0:
        raise RenderError(f"Pandoc reported success but did not create LaTeX output: {tex_output}")
    return {
        "command": command,
        "returncode": result.returncode,
        "log": str(log_path) if log_path.exists() else None,
    }


def xelatex_to_pdf(
    xelatex: str,
    source: Path,
    tex_source: Path,
    pdf_output: Path,
    output_dir: Path,
    log_dir: Path,
) -> dict[str, Any]:
    combined_output: list[str] = []
    commands: list[list[str]] = []
    log_path = log_dir / f"{source.stem}.xelatex.log"

    with tempfile.TemporaryDirectory(prefix=".latex-build-", dir=output_dir) as temporary:
        build_dir = Path(temporary)
        returncode = 0
        for pass_number in (1, 2):
            command = [
                xelatex,
                "-enable-installer",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "-synctex=0",
                f"-output-directory={build_dir}",
                str(tex_source),
            ]
            commands.append(command)
            result = run_process(command, source.parent)
            returncode = result.returncode
            combined_output.append(
                f"PASS {pass_number}\n"
                + "\n".join(part for part in (result.stdout, result.stderr) if part)
            )
            if returncode != 0:
                break

        write_log(log_path, commands[-1], "\n\n".join(combined_output))
        if returncode != 0:
            raise RenderError(f"XeLaTeX failed for {tex_source}; see {log_path}")

        built_pdf = build_dir / f"{tex_source.stem}.pdf"
        if not built_pdf.is_file() or built_pdf.stat().st_size == 0:
            raise RenderError(f"XeLaTeX reported success but did not create a PDF for {tex_source}")
        shutil.copy2(built_pdf, pdf_output)

    return {
        "commands": commands,
        "returncode": 0,
        "log": str(log_path),
    }


def read_page_count(pdfinfo: str | None, pdf_path: Path) -> int | None:
    if not pdfinfo:
        return None
    result = run_process([pdfinfo, str(pdf_path)], pdf_path.parent)
    if result.returncode != 0:
        return None
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def build_edition(
    label: str,
    source: Path,
    template: Path,
    lua_filter: Path,
    folder: Path,
    output_dir: Path,
    log_dir: Path,
    pandoc: str,
    xelatex: str,
    pdfinfo: str | None,
) -> dict[str, Any]:
    original_hash = sha256(source)
    tex_output = output_dir / f"{source.stem}.tex"
    pdf_output = output_dir / f"{source.stem}.pdf"

    pandoc_result = pandoc_to_latex(
        pandoc,
        source,
        tex_output,
        template,
        lua_filter,
        folder,
        log_dir,
    )
    xelatex_result = xelatex_to_pdf(
        xelatex,
        source,
        tex_output,
        pdf_output,
        output_dir,
        log_dir,
    )

    final_hash = sha256(source)
    if final_hash != original_hash:
        raise RenderError(f"Source hash changed during rendering: {source}")

    page_count = read_page_count(pdfinfo, pdf_output)
    if page_count is not None and page_count <= 0:
        raise RenderError(f"Generated PDF has no pages: {pdf_output}")

    return {
        "edition": label,
        "status": "completed",
        "source": str(source),
        "source_sha256_before": original_hash,
        "source_sha256_after": final_hash,
        "source_unchanged": True,
        "template": str(template),
        "tex": str(tex_output),
        "pdf": str(pdf_output),
        "pdf_bytes": pdf_output.stat().st_size,
        "page_count": page_count,
        "pandoc": pandoc_result,
        "xelatex": xelatex_result,
        "visual_qa": "required",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render reformatted exam Markdown and its solution edition as distinct LaTeX/PDF documents."
    )
    parser.add_argument("folder", help="Folder containing the exam Markdown files and images folder.")
    parser.add_argument("--paper", help="Paper-edition Markdown path; defaults to ExamPaper（题解整合版）.md.")
    parser.add_argument(
        "--solutions",
        help="Solutions-edition Markdown path; defaults to ExamPaper（题解整合版）（解析版）.md.",
    )
    parser.add_argument(
        "--edition",
        choices=("both", "paper", "solutions"),
        default="both",
        help="Render both editions by default, or one explicitly selected edition.",
    )
    parser.add_argument("--output-dir", help="Output directory; defaults to <folder>/latex-output.")
    parser.add_argument("--check", action="store_true", help="Validate inputs and dependencies without writing files.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of existing .tex and .pdf outputs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary: dict[str, Any] = {
        "stage": "render-exam-latex-pdfs",
        "status": "failed",
        "editions": [],
        "errors": [],
    }

    try:
        folder = Path(args.folder).expanduser().resolve()
        if not folder.is_dir():
            raise RenderError(f"Input folder does not exist: {folder}")

        skill_dir = Path(__file__).resolve().parents[1]
        assets_dir = skill_dir / "assets"
        lua_filter = skill_dir / "scripts" / "exam_layout.lua"
        templates = {
            "paper": assets_dir / "exam-paper-template.tex",
            "solutions": assets_dir / "exam-solutions-template.tex",
        }
        sources = {
            "paper": resolve_path(args.paper, folder, DEFAULT_PAPER),
            "solutions": resolve_path(args.solutions, folder, DEFAULT_SOLUTIONS),
        }
        selected_labels = ["paper", "solutions"] if args.edition == "both" else [args.edition]

        for label in selected_labels:
            require_source(sources[label], label)
            if not templates[label].is_file():
                raise RenderError(f"Missing {label} LaTeX template: {templates[label]}")
        if not lua_filter.is_file():
            raise RenderError(f"Missing Pandoc layout filter: {lua_filter}")

        pandoc = shutil.which("pandoc")
        xelatex = shutil.which("xelatex")
        pdfinfo = shutil.which("pdfinfo.exe") or shutil.which("pdfinfo")
        if not pandoc:
            raise RenderError("Pandoc is unavailable on PATH.")
        if not xelatex:
            raise RenderError("XeLaTeX is unavailable on PATH.")

        output_dir_value = Path(args.output_dir).expanduser() if args.output_dir else folder / "latex-output"
        if not output_dir_value.is_absolute():
            output_dir_value = folder / output_dir_value
        output_dir = output_dir_value.resolve()
        log_dir = output_dir / "logs"

        planned = []
        conflicts = []
        for label in selected_labels:
            source = sources[label]
            tex_output = output_dir / f"{source.stem}.tex"
            pdf_output = output_dir / f"{source.stem}.pdf"
            planned.append(
                {
                    "edition": label,
                    "source": str(source),
                    "source_sha256": sha256(source),
                    "template": str(templates[label]),
                    "tex": str(tex_output),
                    "pdf": str(pdf_output),
                }
            )
            conflicts.extend(str(path) for path in (tex_output, pdf_output) if path.exists())

        summary.update(
            {
                "folder": str(folder),
                "output_dir": str(output_dir),
                "tools": {"pandoc": pandoc, "xelatex": xelatex, "pdfinfo": pdfinfo},
                "planned": planned,
                "existing_outputs": conflicts,
            }
        )

        if args.check:
            summary["status"] = "ready" if not conflicts or args.overwrite else "blocked"
            if conflicts and not args.overwrite:
                summary["errors"].append("Existing output gate; rerun with explicit overwrite permission.")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if summary["status"] == "ready" else 2

        if conflicts and not args.overwrite:
            raise RenderError("Existing output gate: " + "; ".join(conflicts))

        output_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        failed = False
        for label in selected_labels:
            try:
                result = build_edition(
                    label,
                    sources[label],
                    templates[label],
                    lua_filter,
                    folder,
                    output_dir,
                    log_dir,
                    pandoc,
                    xelatex,
                    pdfinfo,
                )
                summary["editions"].append(result)
            except Exception as exc:  # Continue so the two editions remain failure-isolated.
                failed = True
                summary["editions"].append(
                    {
                        "edition": label,
                        "status": "failed",
                        "source": str(sources[label]),
                        "template": str(templates[label]),
                        "error": str(exc),
                    }
                )
                summary["errors"].append(str(exc))

        summary["status"] = "failed" if failed else "completed"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if failed else 0
    except Exception as exc:
        summary["errors"].append(str(exc))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

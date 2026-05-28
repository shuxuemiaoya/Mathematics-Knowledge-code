import argparse

from .md_formatter.cli import run_formatter
from .mineru.cli import run_batch_parser


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mathematics knowledge-base automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    format_parser = subparsers.add_parser("format", help="Format Markdown files")
    format_parser.add_argument("--dir", required=True, help="Directory containing Markdown files")
    format_parser.add_argument(
        "--mode",
        required=True,
        choices=["textbook", "exercise", "yishu", "bishua", "all_exercises"],
    )
    format_parser.add_argument("--backup", action="store_true")
    format_parser.add_argument("--dry-run", action="store_true")

    mineru_parser = subparsers.add_parser("mineru", help="Convert PDFs/DOCX files with MinerU")
    mineru_parser.add_argument("root_dir")
    mineru_parser.add_argument("--out-dir")
    mineru_parser.add_argument("--base-src-dir")
    mineru_parser.add_argument(
        "--format",
        choices=["none", "textbook", "exercise", "yishu", "bishua", "all_exercises"],
        default="none",
    )

    args = parser.parse_args(argv)

    if args.command == "format":
        ok = run_formatter(args.dir, args.mode, backup=args.backup, dry_run=args.dry_run)
    else:
        from .mineru.config import DEFAULT_KNOWLEDGE_BASE_DIR, DEFAULT_SOURCE_MATERIALS_DIR

        ok = run_batch_parser(
            args.root_dir,
            args.out_dir or DEFAULT_KNOWLEDGE_BASE_DIR,
            args.base_src_dir or DEFAULT_SOURCE_MATERIALS_DIR,
            args.format,
        )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import os

from ..md_formatter.cli import run_formatter
from .batch_parser.file_utils import scan_directory
from .batch_parser.processor import Processor
from .config import (
    DEFAULT_KNOWLEDGE_BASE_DIR,
    DEFAULT_SOURCE_MATERIALS_DIR,
    MINERU_API_KEY,
    get_logger,
)


logger = get_logger()


def build_parser():
    parser = argparse.ArgumentParser(description="Batch convert PDF/DOCX files to Markdown with MinerU")
    parser.add_argument(
        "root_dir",
        type=str,
        help="Root directory to recursively scan for PDF and DOCX files.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=DEFAULT_KNOWLEDGE_BASE_DIR,
        help="Output directory for processed Markdown files.",
    )
    parser.add_argument(
        "--base-src-dir",
        type=str,
        default=DEFAULT_SOURCE_MATERIALS_DIR,
        help="Base source directory used to calculate the relative output path.",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["none", "textbook", "exercise", "yishu", "bishua", "all_exercises"],
        default="none",
        help="Post-processing formatter to run on the output directory.",
    )
    return parser


def run_batch_parser(root_dir, out_dir, base_src_dir, formatter_mode="none"):
    root_dir = os.path.abspath(root_dir)
    base_src_dir = os.path.abspath(base_src_dir)
    if not os.path.isdir(root_dir):
        logger.error(f"Error: Directory '{root_dir}' does not exist.")
        return False

    if not MINERU_API_KEY:
        logger.error("MINERU_API_KEY is not configured. Set it in .env or the environment.")
        return False

    logger.info(f"Scanning directory: {root_dir}")
    tasks = scan_directory(root_dir)

    if not tasks:
        logger.info("No PDF or DOCX files found.")
        return True

    logger.info(f"Found {len(tasks)} files to process.")

    processor = Processor(root_dir, out_dir, base_src_dir, tasks)
    processor.run()

    if formatter_mode != "none":
        # 计算本次任务实际的根输出目录，避免格式化整个知识库
        try:
            rel_root = os.path.relpath(root_dir, base_src_dir)
            if rel_root == os.pardir or rel_root.startswith(os.pardir + os.sep):
                actual_out_dir = out_dir
            else:
                actual_out_dir = os.path.join(out_dir, rel_root)
        except ValueError:
            actual_out_dir = out_dir
            
        logger.info(f"Running post-processing formatter '{formatter_mode}' on {actual_out_dir}...")
        return run_formatter(actual_out_dir, formatter_mode, backup=False)

    return True


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    ok = run_batch_parser(args.root_dir, args.out_dir, args.base_src_dir, args.format)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

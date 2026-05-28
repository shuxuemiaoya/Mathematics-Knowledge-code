import argparse
import sys
import os

# Add parent directory to sys.path to allow importing common config and core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import get_logger
from batch_parser.file_utils import scan_directory
from batch_parser.processor import Processor
from md_formatter.cli import run_formatter

logger = get_logger()

def main():
    parser = argparse.ArgumentParser(description="MinerU Batch Document Parser")
    parser.add_argument(
        "root_dir",
        type=str,
        help="Root directory to recursively scan for PDF and DOCX files."
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=r"C:\mygithub\Secondary-School-Mathematics-Knowledge-Map",
        help="Output directory for the processed files."
    )
    parser.add_argument(
        "--base-src-dir",
        type=str,
        default=r"C:\code\BaiduSyncdisk\数学妙呀资料",
        help="Base source directory used to calculate the relative path."
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["none", "textbook", "exercise", "yishu", "bishua", "all_exercises"],
        default="none",
        help="Post-processing formatter to run on the output directory."
    )
    
    args = parser.parse_args()
    
    root_dir = os.path.abspath(args.root_dir)
    if not os.path.isdir(root_dir):
        logger.error(f"Error: Directory '{root_dir}' does not exist.")
        sys.exit(1)
        
    logger.info(f"Scanning directory: {root_dir}")
    tasks = scan_directory(root_dir)
    
    if not tasks:
        logger.info("No PDF or DOCX files found.")
        return
        
    logger.info(f"Found {len(tasks)} files to process.")
    
    processor = Processor(root_dir, args.out_dir, args.base_src_dir, tasks)
    processor.run()
    
    if args.format != "none":
        logger.info(f"Running post-processing formatter '{args.format}' on output directory...")
        run_formatter(args.out_dir, args.format, backup=False)

if __name__ == "__main__":
    main()

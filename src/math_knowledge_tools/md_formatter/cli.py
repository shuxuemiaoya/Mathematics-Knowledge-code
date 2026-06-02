import argparse
from pathlib import Path
from .logger import get_logger
from .textbook import TextbookFormatter
from .exercise import ExerciseFormatter
from .renjiao_textbook import RenjiaoTextbookFormatter

logger = get_logger()

def main(argv=None):
    parser = argparse.ArgumentParser(description="Markdown formatter for the mathematics knowledge base")
    parser.add_argument("--dir", type=str, required=True, help="Directory containing markdown files")
    parser.add_argument("--mode", type=str, required=True,
                        choices=["textbook", "exercise", "yishu", "bishua", "all_exercises", "renjiao-textbook"],
                        help="Formatting mode: textbook | exercise | yishu | bishua | all_exercises | renjiao-textbook")
    parser.add_argument("--backup", action="store_true", help="Create .bak files before modifying")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change without writing them")
    
    args = parser.parse_args(argv)
    return 0 if run_formatter(args.dir, args.mode, args.backup, dry_run=args.dry_run) else 1

def run_formatter(dir_path: str, mode: str, backup: bool = False, dry_run: bool = False):
    root = Path(dir_path).expanduser().resolve()
    logger.info(f"Starting formatter on {root} with mode={mode}, dry_run={dry_run}")
    
    if not root.exists() or not root.is_dir():
        logger.error(f"Invalid directory: {root}")
        return False
        
    if mode == "textbook":
        formatter = TextbookFormatter()
    elif mode == "exercise":
        formatter = ExerciseFormatter(variant="default")
    elif mode == "yishu":
        formatter = ExerciseFormatter(variant="yishu")
    elif mode == "bishua":
        formatter = ExerciseFormatter(variant="bishua")
    elif mode == "all_exercises":
        formatter = ExerciseFormatter(variant="all")
    elif mode == "renjiao-textbook":
        formatter = RenjiaoTextbookFormatter()
    else:
        logger.error(f"Unknown mode: {mode}")
        return False

    processed_count = 0
    updated_count = 0
    
    for p in root.rglob("*.md"):
        if any(part.startswith('.') for part in p.parts):
            continue
            
        processed_count += 1
        success = formatter.process_file(p, backup=backup, dry_run=dry_run)
        if success:
            updated_count += 1
            
    action = "would update" if dry_run else "updated"
    logger.info(f"Formatting complete. Processed {processed_count} files, {action} {updated_count} files.")
    return True

if __name__ == "__main__":
    raise SystemExit(main())

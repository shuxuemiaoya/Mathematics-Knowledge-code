import argparse
from pathlib import Path
from .logger import get_logger
from .textbook import TextbookFormatter
from .exercise import ExerciseFormatter

logger = get_logger()

def main():
    parser = argparse.ArgumentParser(description="Enterprise Markdown Formatter")
    parser.add_argument("--dir", type=str, required=True, help="Directory containing markdown files")
    parser.add_argument("--mode", type=str, required=True,
                        choices=["textbook", "exercise", "yishu", "bishua", "all_exercises"],
                        help="Formatting mode: textbook | exercise | yishu | bishua | all_exercises")
    parser.add_argument("--backup", action="store_true", help="Create .bak files before modifying")
    
    args = parser.parse_args()
    return run_formatter(args.dir, args.mode, args.backup)

def run_formatter(dir_path: str, mode: str, backup: bool = False):
    root = Path(dir_path).expanduser().resolve()
    logger.info(f"Starting formatter on {root} with mode={mode}")
    
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
    else:
        logger.error(f"Unknown mode: {mode}")
        return False

    processed_count = 0
    updated_count = 0
    
    for p in root.rglob("*.md"):
        if any(part.startswith('.') for part in p.parts):
            continue
            
        processed_count += 1
        success = formatter.process_file(p, backup=backup)
        if success:
            updated_count += 1
            
    logger.info(f"Formatting complete. Processed {processed_count} files, updated {updated_count} files.")
    return True

if __name__ == "__main__":
    main()

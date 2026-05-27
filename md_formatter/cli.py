import argparse
from pathlib import Path
from .logger import get_logger
from .textbook import TextbookFormatter
from .exercise import ExerciseFormatter

logger = get_logger()

def main():
    parser = argparse.ArgumentParser(description="Enterprise Markdown Formatter")
    parser.add_argument("--dir", type=str, help="Directory containing markdown files")
    parser.add_argument("--mode", type=str, choices=["textbook", "exercise", "yishu", "bishua", "all_exercises"], help="Formatting mode")
    parser.add_argument("--backup", action="store_true", help="Create .bak files before modifying")
    
    args = parser.parse_args()
    
    target_dir = args.dir
    target_mode = args.mode
    
    if not target_dir:
        target_dir = input("请输入要修改的文件所在的目录: ").strip()
        
    if not target_mode:
        print("\n请选择要修改的文件类型:")
        print("1. 教科书 (textbook)")
        print("2. 练习册：一书 (yishu)")
        print("3. 练习册：必刷 (bishua)")
        print("4. 默认/其他练习册 (exercise)")
        print("5. 全部练习册 (all_exercises)")
        mode_input = input("请输入编号或模式名 (默认 1): ").strip()
        
        mode_map = {
            "1": "textbook",
            "2": "yishu",
            "3": "bishua",
            "4": "exercise",
            "5": "all_exercises",
            "": "textbook"
        }
        target_mode = mode_map.get(mode_input, mode_input)
        
    return run_formatter(target_dir, target_mode, args.backup)

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

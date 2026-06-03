import cProfile
import pstats
from mathos.formatter.cli import run_formatter

def main():
    print("Starting profile...")
    file_path = r"C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\总复习\专题\高考数学秘密\浙大优辅《高中数学新体系 导数的秘密》.md"
    mode = "zheda_youfu"
    profiler = cProfile.Profile()
    profiler.enable()
    
    run_formatter(file_path, mode, backup=False, dry_run=True)
    
    profiler.disable()
    stats = pstats.Stats(profiler).sort_stats('tottime')
    stats.print_stats(30)

if __name__ == "__main__":
    main()

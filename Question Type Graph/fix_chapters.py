import re
import shutil
from pathlib import Path

# Mapping of sections to their proper chapters based on standard textbook & TOC
# Chapter 1: 空间向量与立体几何 (1.1 - 1.4, 第一章素养检测, 第一章高考强化, 专题1)
# Chapter 2: 直线和圆的方程 (2.1 - 2.5, 第二章素养检测, 第二章高考强化, 专题2 - 专题4)
# Chapter 3: 圆锥曲线的方程 (3.1 - 3.3, 第三章素养检测, 第三章高考强化, 专题5 - 专题9)
# Chapter 4: 综合专项/模块测试 (专练1, 专练2, 模块综合测试)

base_dir = Path("/Users/oven/Documents/ovenmathmap/高中/课堂同步/教辅/必刷题/2027版 必刷题 数学选择性必修第一册RJA")
c1_dir = base_dir / "01_第一章"

chap1_target = base_dir / "01_第一章_空间向量与立体几何"
chap2_target = base_dir / "02_第二章_直线和圆的方程"
chap3_target = base_dir / "03_第三章_圆锥曲线的方程"
chap4_target = base_dir / "04_综合专练与模块测试"

print("Done planning")

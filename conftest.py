"""pytest 配置（第一轮骨架）：把 src 目录加入模块搜索路径，便于测试导入 cell_planner。"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
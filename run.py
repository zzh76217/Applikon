# -*- coding: utf-8 -*-
"""程序入口：源码运行时用 `python run.py`；打包时 PyInstaller 以本文件为入口脚本。"""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):        # 打包版模块已在 exe 内部，不必再改 sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from cell_planner.ui.main_window import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
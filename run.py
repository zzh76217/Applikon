# -*- coding: utf-8 -*-
"""程序入口：双击 启动软件.bat，或在命令行于工程根目录执行  python run.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from cell_planner.ui.main_window import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

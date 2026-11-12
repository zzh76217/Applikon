# -*- coding: utf-8 -*-
"""模拟 CSV 命令行入口（第五轮）。

真正的生成逻辑已搬到包内 src/cell_planner/io_/simulator.py（③离线分析页的"试算"按钮也调用它），
本文件只负责命令行参数解析，用法保持不变：
    python tools/make_simulated_csv.py
    python tools/make_simulated_csv.py --out-dir D:\临时测试目录 --tag 单测专用
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cell_planner.io_.simulator import (          # noqa: E402  复用包内实现，避免两份代码
    build_control_rows, build_offline_rows, control_values, generate, main, write_csv,
)


if __name__ == "__main__":
    raise SystemExit(main())
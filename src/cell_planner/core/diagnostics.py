# -*- coding: utf-8 -*-
"""诊断输出与随包资源查找（第六轮打包必需）。
1) 打包成 windowed 的 .exe 后没有控制台，sys.stdout / sys.stderr 都是 None，
   原代码里的 sys.stderr.write 会"出错时再崩一次"。本模块统一处理：有控制台就照常打印，
   并且无论有没有控制台，都追加写一份到 程序目录/logs/软件运行日志.txt，
   让不懂代码的用户能把日志文件直接发给开发者。
2) bundled_asset() 负责找随包资源（图标等）：优先程序目录，其次 onefile 解包的临时目录。
日志目录名/文件名/大小上限来自 config 的 app_info 段；只有当 config 本身读不出来时
（正是最需要写日志的时刻）才退回到下面的文件名默认值——它们是文件名，不是工艺参数。
本模块不参与任何工艺计算。
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from cell_planner.core.config_loader import APP_ROOT

_FALLBACK_LOG_DIR = "logs"
_FALLBACK_LOG_FILE = "软件运行日志.txt"
_FALLBACK_LOG_MAX_MB = 5


def _log_settings() -> Tuple[str, str, int]:
    """(日志目录名, 日志文件名, 轮转上限字节) —— 优先 config.app_info。"""
    dir_name, file_name, max_mb = _FALLBACK_LOG_DIR, _FALLBACK_LOG_FILE, _FALLBACK_LOG_MAX_MB
    try:
        from cell_planner.core.config_loader import get_config
        info = get_config().get("app_info") or {}
        dir_name = str(info.get("log_dir") or dir_name)
        file_name = str(info.get("log_file") or file_name)
        max_mb = int(info.get("log_max_mb") or max_mb)
    except Exception:
        pass                      # 配置读不出来时仍要能写日志
    return dir_name, file_name, max_mb


def log_dir(root: Optional[Path] = None) -> Path:
    dir_name, _f, _m = _log_settings()
    return (root or APP_ROOT) / dir_name


def log_file(root: Optional[Path] = None) -> Path:
    dir_name, file_name, _m = _log_settings()
    return (root or APP_ROOT) / dir_name / file_name


def _rotate_if_needed(path: Path, max_bytes: int) -> None:
    try:
        if path.is_file() and path.stat().st_size > max_bytes:
            old = path.with_name(path.stem + ".old" + path.suffix)
            os.replace(path, old)
    except OSError:
        pass          # 日志写不进去绝不能连累主程序


def write_diagnostic(text: str, level: str = "提示", root: Optional[Path] = None) -> Optional[Path]:
    """把一段诊断文字写到控制台（若有）并追加到日志文件；返回日志文件路径或 None。
    任何 IO 失败都静默忽略——诊断是附属功能，不允许引发新异常。"""
    _d, _f, max_mb = _log_settings()
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    frozen = "打包版" if getattr(sys, "frozen", False) else "源码版"
    block = "[%s][%s][%s] %s" % (stamp, level, frozen, str(text).rstrip())
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.write(block + "\n")
        except Exception:
            pass
    try:
        path = log_file(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(path, max_mb * 1024 * 1024)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(block + "\n")
        return path
    except Exception:
        return None


def bundled_asset(relative: str) -> Optional[Path]:
    """查找随包资源（如图标）：优先程序目录（用户可替换），其次 onefile 解包出来的临时目录。"""
    candidates = []
    if not getattr(sys, "frozen", False):
        candidates.append(APP_ROOT / relative)
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / relative)
    candidates.append(APP_ROOT / relative)
    for cand in candidates:
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None
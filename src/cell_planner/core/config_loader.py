# -*- coding: utf-8 -*-
"""配置加载：全部阈值、默认参数、硬件限值只允许来自 config/config.yaml。
严禁在业务代码中硬编码工艺参数（AGENTS.md 硬约束 2）。

第六轮（打包 .exe）路径规则：
- 源码运行：根目录 = 工程根（本文件往上三层），配置在 config/config.yaml。
- 打包运行：根目录 = exe 所在目录（不是 onefile 的临时解包目录！），
  这样模板库、列名映射、开机配置单、配方都落在用户看得见、下次还在的地方。
- 打包版首次启动时，会把内置的默认 config.yaml 释放到 exe 同目录的 config 文件夹下，
  之后你直接编辑那个文件即可改参数；若所在目录只读（如 Program Files），
  则退回读内置副本运行，并在界面里提示配置不可写。
"""
from __future__ import annotations

import functools
import shutil
import sys
from pathlib import Path
from typing import Optional

import yaml

# ---------- 运行模式与根目录 ----------
IS_FROZEN = bool(getattr(sys, "frozen", False))
RUN_MODE = "打包版" if IS_FROZEN else "源码版"


def _resolve_app_root() -> Path:
    """程序根目录：打包版取 exe 所在目录，源码版取工程根。"""
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


APP_ROOT = _resolve_app_root()
PROJECT_ROOT = APP_ROOT          # 兼容既有引用名（各模块都从这里派生 data/ 下的路径）
CONFIG_DIR = APP_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _bundled_config_file() -> Optional[Path]:
    """打包时内置的默认配置（onefile 解包到临时目录），源码运行时返回 None。"""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    candidate = Path(base) / "config" / "config.yaml"
    return candidate if candidate.is_file() else None


def ensure_external_config() -> Path:
    """确保 exe 同目录有一份可编辑的 config.yaml，返回实际使用的配置文件路径。
    优先用外部文件；外部缺失但有内置副本时释放一份出来；释放失败就用内置只读副本。"""
    if CONFIG_FILE.is_file():
        return CONFIG_FILE
    bundled = _bundled_config_file()
    if bundled is None:
        raise FileNotFoundError(
            "找不到配置文件：{0}\n请把 config.yaml 放到该位置后重新启动软件。".format(CONFIG_FILE)
        )
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundled, CONFIG_FILE)
        return CONFIG_FILE
    except OSError:
        return bundled


def config_source() -> str:
    """当前配置文件位置（界面/日志用，方便用户知道自己在改哪一份）。"""
    try:
        return str(ensure_external_config())
    except FileNotFoundError:
        return str(CONFIG_FILE)


@functools.lru_cache(maxsize=1)
def get_config() -> dict:
    """读取并缓存配置；修改 config.yaml 后重启程序（或在②页点"保存并生效"）生效。"""
    path = ensure_external_config()
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("配置文件格式错误（顶层必须是键值映射）：" + str(path))
    return cfg


def reload_config() -> dict:
    """强制重新读取配置（测试与②页写回后用）。"""
    get_config.cache_clear()
    return get_config()
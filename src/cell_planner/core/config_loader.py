# -*- coding: utf-8 -*-
"""配置加载：全部阈值、默认参数、硬件限值只允许来自 config/config.yaml。
严禁在业务代码中硬编码工艺参数（AGENTS.md 硬约束 2）。
第六轮打包后配置路径可能变化，届时在此处适配（sys._MEIPASS），当前按工程根解析。"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"


@functools.lru_cache(maxsize=1)
def get_config() -> dict:
    """读取并缓存配置；修改 config.yaml 后重启程序生效。"""
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError("配置文件缺失，请联系开发者：" + str(CONFIG_FILE))
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("配置文件格式错误（顶层必须是键值映射）：" + str(CONFIG_FILE))
    return cfg


def reload_config() -> dict:
    """强制重新读取配置（测试用）。"""
    get_config.cache_clear()
    return get_config()

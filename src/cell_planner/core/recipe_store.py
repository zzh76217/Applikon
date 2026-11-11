# -*- coding: utf-8 -*-
"""轻量配方存取（第三轮）：把"批次配置"页的全部输入参数按名字保存/调出/删除。
存储为 data/recipes/*.json（每个配方一个文件，人类可读、可直接拷贝备份）。
注意：这不是模块 4 的 SQLite 模板库（第五轮实现），二者互不影响：
配方 = 界面输入参数快照；模板 = 第五轮的实验方案模板与多批次对比。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from cell_planner.core.config_loader import PROJECT_ROOT, get_config

RECIPE_VERSION = 1
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def recipes_dir(directory: Optional[Path] = None, cfg: Optional[dict] = None) -> Path:
    if directory is not None:
        return Path(directory)
    cfg = cfg or get_config()
    return PROJECT_ROOT / str(cfg["recipes"]["dir"])


def _safe_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("配方名称不能为空，请在输入框中先填写名称。")
    if len(name) > 60:
        raise ValueError("配方名称过长（最多 60 个字符），请精简后再保存。")
    if name in (".", "..") or _BAD_CHARS.search(name):
        raise ValueError('配方名称不能包含这些字符：\\ / : * ? " < > |，请换一个名称（中文可以用）。')
    return name


def _recipe_path(name: str, directory: Path) -> Path:
    return directory / (_safe_name(name) + ".json")


def save_recipe(name: str, params: dict, directory: Optional[Path] = None) -> Path:
    """保存（同名覆盖）一个配方文件，返回文件路径。"""
    d = recipes_dir(directory=directory)
    d.mkdir(parents=True, exist_ok=True)
    p = _recipe_path(name, d)
    payload = {
        "配方": _safe_name(name),
        "版本": RECIPE_VERSION,
        "保存时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "参数": params,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def list_recipes(directory: Optional[Path] = None) -> List[str]:
    """按名称排序返回现有配方名。"""
    d = recipes_dir(directory=directory)
    if not d.is_dir():
        return []
    return sorted(f.stem for f in d.glob("*.json"))


def load_recipe(name: str, directory: Optional[Path] = None) -> dict:
    """读取配方并返回其参数字典；文件不存在或损坏时抛中文错误。"""
    d = recipes_dir(directory=directory)
    p = _recipe_path(name, d)
    if not p.is_file():
        raise ValueError("找不到配方文件：" + str(p))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("配方文件已损坏（JSON 解析失败）：" + str(p) + "，错误：" + str(exc)) from exc
    params = data.get("参数")
    if not isinstance(params, dict):
        raise ValueError("配方文件缺少『参数』字段，无法载入：" + str(p))
    return params


def delete_recipe(name: str, directory: Optional[Path] = None) -> None:
    d = recipes_dir(directory=directory)
    p = _recipe_path(name, d)
    if not p.is_file():
        raise ValueError("找不到要删除的配方：" + _safe_name(name))
    p.unlink()

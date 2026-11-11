# -*- coding: utf-8 -*-
"""config.yaml 原位回写工具（第三轮"硬件配置"页使用）。
设计目标：只修改指定键路径上的标量值，其余所有行（含全部中文注释）原样保留。
实现方式：逐行扫描 + 缩进栈追踪键路径；命中目标键时替换冒号后的值，保留行尾注释。
安全限制：不支持改写行内映射 { a: 1 } 与行内列表 [1, 2]（遇到即抛中文错误，拒写不损坏文件）。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from cell_planner.core.config_loader import CONFIG_FILE, reload_config

_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_]+):(.*)$")


def _format_value(value) -> str:
    """把 Python 值格式化成 YAML 标量文本。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = ("%.10f" % value).rstrip("0")
        if text.endswith("."):
            text += "0"
        return text
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # 双引号字符串是合法 YAML
    raise ValueError("不支持写入的配置值类型：%r" % (value,))


def _split_value_comment(rest: str) -> Tuple[str, str]:
    """把冒号后的内容拆成 (值部分, 注释部分)。注释以" # "或行尾" #"界定（值里若含 # 会被判为行内注释起始而拒写保护）。"""
    idx = rest.find("#")
    if idx == -1:
        return rest, ""
    return rest[:idx], rest[idx:]


def set_yaml_values(text: str, updates: Dict[Tuple[str, ...], object]) -> str:
    """返回应用 updates 后的新配置文件文本（纯函数，便于单元测试）。
    updates 的键是键路径元组，如 ("hardware", "min_working_volume_ml")；值是最终写入的标量。"""
    if not updates:
        return text
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    stack: list[Tuple[int, str]] = []      # (缩进, 键名)
    hit: set[Tuple[str, ...]] = set()
    for i, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY_RE.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        key = m.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = tuple(k for _, k in stack) + (key,)
        if path in updates:
            value_raw, comment = _split_value_comment(m.group(3))
            if "{" in value_raw or "[" in value_raw:
                raise ValueError(
                    "配置项 %s 使用了行内写法，硬件配置页仅支持逐行标量修改，请勿手改本行为 { } 或 [ ] 形式。" % " → ".join(path))
            lines[i] = m.group(1) + key + ": " + _format_value(updates[path]) + \
                (("  " + comment) if comment else "")
            hit.add(path)
        stack.append((indent, key))
    missing = set(updates) - hit
    if missing:
        names = "、".join(" → ".join(p) for p in sorted(missing))
        raise ValueError("配置文件中找不到以下配置项，已拒绝保存以防止误写：" + names)
    return newline.join(lines) + (newline if text.endswith(("\n", "\r\n")) else "")


def update_config_file(updates: Dict[Tuple[str, ...], object],
                       config_path: Optional[Path] = None,
                       backup: bool = True) -> Path:
    """把 updates 写回 config.yaml：先备份 .bak，再原位替换，最后重载缓存使新阈值立即生效。"""
    path = Path(config_path) if config_path is not None else CONFIG_FILE
    if not path.is_file():
        raise FileNotFoundError("配置文件缺失：" + str(path))
    text = path.read_text(encoding="utf-8")
    new_text = set_yaml_values(text, updates)   # 校验失败会抛错，原文件保持不变
    if backup:
        shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(new_text, encoding="utf-8", newline="")
    if config_path is None:
        reload_config()
    return path

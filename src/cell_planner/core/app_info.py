# -*- coding: utf-8 -*-
"""软件身份信息与界面文案渲染（第六轮）。
窗口标题、"你的文件都在这里"提示条的文字模板都放在 config.app_info 里，
本模块只负责把模板渲染成最终字符串——纯函数，不依赖 Qt，便于单元测试。
严禁把界面文案写死在代码里（AGENTS.md 硬约束 1、2）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional


def app_info(cfg: Mapping) -> dict:
    """取 app_info 段；缺失时返回空字典（调用方必须能容忍空配置）。"""
    info = cfg.get("app_info") if cfg else None
    return info if isinstance(info, dict) else {}


def window_title(cfg: Mapping, mode: str) -> str:
    """渲染窗口标题。模板占位符：{name} {version} {round_label} {mode}。
    mode 由调用方传入「打包版」或「源码版」，配置文件里不写死。"""
    info = app_info(cfg)
    fields = {
        "name": str(info.get("name", "")),
        "version": str(info.get("version", "")),
        "round_label": str(info.get("round_label", "")),
        "mode": str(mode),
    }
    template = str(info.get("title_template") or "{name} {version}")
    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError):
        return "%s（%s）" % (fields["name"], fields["mode"])


def tab_titles(cfg: Mapping, count: int) -> list:
    """①–⑥ 页签名称，来自 config.app_info.tab_titles。
    配置缺失、类型不对或条数不够时，返回的列表用空字符串占位，由界面按顺序补内置兜底名。
    放在 config 的原因：打包成 .exe 后在窄屏/高缩放的实验电脑上页签会被挤出窗口，
    用户自己把名字改短就能解决，不必重新打包。"""
    raw = app_info(cfg).get("tab_titles")
    if not isinstance(raw, list):
        return []
    out = []
    for i in range(count):
        item = raw[i] if i < len(raw) else ""
        out.append(str(item).strip() if item is not None else "")
    return out


def locations_text(cfg: Mapping, *, config_path: object, data_dir: Optional[Path],
                   log_path: Optional[Path], manual_path: Optional[Path]) -> str:
    """渲染"你的文件都在这里"一行。模板占位符：{config} {data} {log} {manual}。
    任一路径拿不到就整行留空，宁可不显示也不显示错误路径。"""
    info = app_info(cfg)
    template = str(info.get("locations_template") or "")
    if not template:
        return ""
    paths = {
        "config": str(config_path) if config_path else "",
        "data": str(data_dir) if data_dir else "",
        "log": str(log_path) if log_path else "",
        "manual": str(manual_path) if manual_path else "",
    }
    if not paths["config"] or not paths["data"]:
        return ""
    try:
        return template.format(**paths)
    except (KeyError, IndexError, ValueError):
        return ""


def manual_path(cfg: Mapping, root: Path) -> Optional[Path]:
    """说明书文件名来自 config，返回 程序目录/说明书 的完整路径。"""
    name = str(app_info(cfg).get("manual_file") or "").strip()
    return (Path(root) / name) if name else None
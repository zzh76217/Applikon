# -*- coding: utf-8 -*-
"""模块 5：SOP 防呆引导（第五轮）。

检查条目全部来自 config.yaml 的 sop.stages（阶段名/条目文字都不写进代码），
界面按本模块渲染复选框，导出"确认单"CSV 时逐条标注 已确认 / 未确认。
本模块不联网、不读写设备，只落地本地文件。
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from cell_planner.core.config_loader import get_config

CONFIRMED = "已确认"
NOT_CONFIRMED = "未确认"
CSV_HEADER = ["阶段", "序号", "检查项", "是否已确认"]


# ---------------------------------------------------------------- 配置读取
def _cfg(cfg: Optional[dict]) -> dict:
    """只有 cfg is None 才回退全局配置；传空字典视为"配置缺失"，必须报中文错误。"""
    return get_config() if cfg is None else cfg


def sop_config(cfg: Optional[dict] = None) -> dict:
    cfg = _cfg(cfg)
    sop = cfg.get("sop") if isinstance(cfg, dict) else None
    if not isinstance(sop, dict) or not sop.get("stages"):
        raise ValueError("config.yaml 里缺少 sop 段（或 sop.stages 为空），无法生成 SOP 检查清单。"
                         "请补齐配置后重新打开软件。")
    return sop


def stages(cfg: Optional[dict] = None) -> List[dict]:
    """返回 [{key, name, items:[文字]}]，条目顺序与 config 一致。"""
    out: List[dict] = []
    for i, st in enumerate(sop_config(cfg)["stages"], start=1):
        name = str(st.get("name") or "").strip()
        key = str(st.get("key") or "").strip()
        items = [str(x).strip() for x in (st.get("items") or []) if str(x).strip()]
        if not name or not key:
            raise ValueError("config.yaml 的 sop.stages 第 %d 阶段缺少 name 或 key，请补全。" % i)
        if not items:
            raise ValueError("config.yaml 的 sop.stages 阶段「%s」里没有任何检查条目，请补全。" % name)
        if any(o["key"] == key for o in out):
            raise ValueError("config.yaml 的 sop.stages 里有重复的 key：%s，请改成不同值。" % key)
        out.append({"key": key, "name": name, "items": items})
    return out


def item_id(stage_key: str, index: int) -> str:
    """勾选项的稳定 id，界面用 "<stage_key>:<序号>" 记状态。"""
    return "%s:%d" % (stage_key, int(index))


def all_items(cfg: Optional[dict] = None) -> List[dict]:
    """扁平化条目清单：[{id, stage_key, stage_name, index, text}]。"""
    rows: List[dict] = []
    for st in stages(cfg):
        for i, text in enumerate(st["items"], start=1):
            rows.append({"id": item_id(st["key"], i), "stage_key": st["key"],
                         "stage_name": st["name"], "index": i, "text": text})
    return rows


def total_items(cfg: Optional[dict] = None) -> int:
    return len(all_items(cfg))


def require_all_checked(cfg: Optional[dict] = None) -> bool:
    return bool(sop_config(cfg).get("require_all_checked_for_export"))


def reset_on_new_batch(cfg: Optional[dict] = None) -> bool:
    return bool(sop_config(cfg).get("reset_on_new_batch", True))


# ---------------------------------------------------------------- 进度与校验
def _as_set(checked: Optional[Iterable[str]]) -> set:
    if not checked:
        return set()
    if isinstance(checked, (set, frozenset)):
        return set(checked)
    if isinstance(checked, dict):                       # 允许传 {id: True}
        return {str(k) for k, v in checked.items() if v}
    return {str(x) for x in checked}


def progress(checked: Optional[Iterable[str]], cfg: Optional[dict] = None) -> dict:
    """按阶段统计勾选进度（界面进度条/状态栏用）。"""
    got = _as_set(checked)
    stage_rows: List[dict] = []
    done_all = 0
    total_all = 0
    for st in stages(cfg):
        total = len(st["items"])
        done = sum(1 for i in range(1, total + 1) if item_id(st["key"], i) in got)
        done_all += done
        total_all += total
        stage_rows.append({"key": st["key"], "name": st["name"], "done": done, "total": total,
                           "all_done": done == total,
                           "text": "%s：已勾选 %d/%d 项%s" % (st["name"], done, total,
                                                             "" if done == total else "（还有 %d 项未确认）" % (total - done))})
    return {"stages": stage_rows, "done": done_all, "total": total_all,
            "all_done": done_all == total_all,
            "text": "总体进度：已勾选 %d/%d 项" % (done_all, total_all)}


def unchecked_items(checked: Optional[Iterable[str]], cfg: Optional[dict] = None) -> List[dict]:
    got = _as_set(checked)
    return [row for row in all_items(cfg) if row["id"] not in got]


def export_gate(checked: Optional[Iterable[str]], cfg: Optional[dict] = None) -> Tuple[bool, str]:
    """导出前的闸门：config.sop.require_all_checked_for_export 决定是否必须全部勾选。"""
    missing = unchecked_items(checked, cfg)
    if not missing:
        return True, "全部 %d 项均已确认，可以导出。" % total_items(cfg)
    if require_all_checked(cfg):
        return False, ("还有 %d 项未勾选确认（例如「%s」），按 config.sop.require_all_checked_for_export=true "
                       "的要求，SOP 确认单暂不能导出。" % (len(missing), missing[0]["text"]))
    return True, ("提醒：还有 %d 项未勾选确认，导出的确认单里这些条目会标注为「%s」，请人工复核后再执行。"
                  % (len(missing), NOT_CONFIRMED))


# ---------------------------------------------------------------- 导出
def build_rows(checked: Optional[Iterable[str]], cfg: Optional[dict] = None) -> List[List[str]]:
    """确认单表格行：未勾选项也必须出现（标"未确认"），否则等于漏项。"""
    got = _as_set(checked)
    rows: List[List[str]] = []
    for row in all_items(cfg):
        rows.append([row["stage_name"], str(row["index"]), row["text"],
                     CONFIRMED if row["id"] in got else NOT_CONFIRMED])
    return rows


def disclaimer_lines(checked: Optional[Iterable[str]], cfg: Optional[dict] = None) -> List[List[str]]:
    cfg = _cfg(cfg)
    prog = progress(checked, cfg)
    sop = sop_config(cfg)
    title = str(sop.get("report_title") or "SOP 防呆引导确认单")
    return [
        ["标题", title],
        ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["勾选进度", "%s；%s" % (prog["text"], "全部已确认" if prog["all_done"] else "尚有未确认项")],
        ["操作人", ""],
        ["第二人复核", ""],
        ["免责说明", "本清单只是操作提示，不替代经本实验室批准的正式 SOP 文件；"
                     "关键步骤（灭菌参数、接种体积、MFC 设定）仍需第二人复核。"
                     "本软件不连接、不控制 my-Control 硬件。"],
    ]


def export_csv(path, checked: Optional[Iterable[str]], cfg: Optional[dict] = None,
               force: bool = False) -> Path:
    """导出 SOP 确认单 CSV（编码取 config.sop.export.csv_encoding）。被闸门拦下时抛中文提示。"""
    cfg = _cfg(cfg)
    ok, message = export_gate(checked, cfg)
    if not ok and not force:
        raise ValueError(message)
    enc = str(sop_config(cfg)["export"]["csv_encoding"])
    p = Path(path)
    if str(p.parent):
        p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding=enc, newline="") as fh:
        w = csv.writer(fh)
        for line in disclaimer_lines(checked, cfg):
            w.writerow(line)
        w.writerow([])
        w.writerow(CSV_HEADER)
        for row in build_rows(checked, cfg):
            w.writerow(row)
        w.writerow([])
        if not ok or message:
            w.writerow(["导出提示", message])
    return p


def sheet_text(checked: Optional[Iterable[str]], cfg: Optional[dict] = None) -> str:
    """纯文本版确认单（一键复制到剪贴板/微信用），不写文件。"""
    lines: List[str] = []
    for line in disclaimer_lines(checked, cfg):
        lines.append("%s：%s" % (line[0], line[1]) if line[1] else line[0] + "：")
    lines.append("")
    lines.append("　".join(CSV_HEADER))
    for row in build_rows(checked, cfg):
        lines.append("%s　%s　%s　%s" % (row[0], row[1], row[2], row[3]))
    lines.append("")
    ok, message = export_gate(checked, cfg)
    lines.append(message)
    return "\n".join(lines)
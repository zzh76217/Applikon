# -*- coding: utf-8 -*-
"""列名映射（第五轮，答复#8）。

逻辑字段清单与候选列名全部来自 config.column_mapping；用户在"列名映射"页把逻辑字段
对应到真实 CSV 的列名后，保存到 data/column_mapping.json（UTF-8 JSON，人类可读可手改）。
真实 my-Control 导出文件到手前，这里只按"通用格式"提供候选列名做自动匹配。
本模块不含任何工艺阈值（阈值集中在 do_alarm / metabolite_limits / harvest_hint）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from cell_planner.core.config_loader import PROJECT_ROOT, get_config

MAPPING_VERSION = 1
DATASET_CONTROL = "control"
DATASET_OFFLINE = "offline"
DATASET_BOTH = "both"

DATASET_LABEL = {
    DATASET_CONTROL: "控制数据（my-Control 运行导出）",
    DATASET_OFFLINE: "离线取样数据（细胞计数 / 糖乳酸）",
    DATASET_BOTH: "两类文件都需要",
}

# 列名归一化时要抹掉的分隔符与单位符号（技术细节，不是工艺参数）
_SEP_RE = re.compile(r"[\s_\-\[\]\(\)\{\}/\\%.,;:+*=]+")


def normalize(text, cfg: Optional[dict] = None) -> str:
    """列名归一化：去掉空格与常见分隔符；默认忽略大小写（由 config 控制）。"""
    cfg = cfg or get_config()
    s = _SEP_RE.sub("", str(text if text is not None else ""))
    if not bool(cfg["column_mapping"].get("auto_match_case_sensitive", False)):
        s = s.casefold()
    return s


def fields(cfg: Optional[dict] = None) -> List[dict]:
    """逻辑字段清单（顺序即界面表格顺序），全部来自 config。"""
    cfg = cfg or get_config()
    raw = cfg["column_mapping"].get("logical_fields")
    if not isinstance(raw, list) or not raw:
        raise ValueError("配置缺少 column_mapping.logical_fields 字段清单，请检查 config/config.yaml。")
    out: List[dict] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("key"):
            raise ValueError("column_mapping.logical_fields 里有条目缺少 key，请检查 config/config.yaml。")
        out.append({
            "key": str(item["key"]),
            "label": str(item.get("label") or item["key"]),
            "unit": str(item.get("unit") or ""),
            "dataset": str(item.get("dataset") or DATASET_BOTH),
            "required": bool(item.get("required")),
            "candidates": [str(c) for c in (item.get("candidates") or [])],
        })
    return out


def fields_for(kind: str, cfg: Optional[dict] = None) -> List[dict]:
    kind = str(kind or "").strip()
    if kind not in (DATASET_CONTROL, DATASET_OFFLINE):
        raise ValueError("未知的数据类型：" + str(kind) + "（只支持 control=控制数据 / offline=离线取样）")
    return [f for f in fields(cfg) if f["dataset"] in (kind, DATASET_BOTH)]


def mapping_path(cfg: Optional[dict] = None) -> Path:
    cfg = cfg or get_config()
    return PROJECT_ROOT / str(cfg["column_mapping"]["mapping_file"])


def section_key(kind: str) -> str:
    return "控制数据" if kind == DATASET_CONTROL else "离线取样"


def blank_mapping(kind: str, cfg: Optional[dict] = None) -> Dict[str, str]:
    return {f["key"]: "" for f in fields_for(kind, cfg)}


def load_all(path: Optional[Path] = None, cfg: Optional[dict] = None) -> dict:
    """读取映射文件；文件不存在时返回空结构（首次使用不算错误）。"""
    cfg = cfg or get_config()
    p = Path(path) if path is not None else mapping_path(cfg)
    result = {DATASET_CONTROL: {}, DATASET_OFFLINE: {}}
    if not p.is_file():
        return result
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("列名映射文件无法读取或已损坏：" + str(p) + "，原因：" + str(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("列名映射文件格式错误（顶层必须是对象）：" + str(p))
    for kind in (DATASET_CONTROL, DATASET_OFFLINE):
        sec = data.get(section_key(kind))
        if isinstance(sec, dict):
            result[kind] = {str(k): str(v) for k, v in sec.items()}
    return result


def save_all(control: Dict[str, str], offline: Dict[str, str],
             path: Optional[Path] = None, cfg: Optional[dict] = None) -> Path:
    cfg = cfg or get_config()
    p = Path(path) if path is not None else mapping_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "说明": "列名映射：把逻辑字段对应到你实际 CSV 里的列名；留空表示该字段不使用。改完可直接用记事本另存。",
        "版本": MAPPING_VERSION,
        "保存时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        section_key(DATASET_CONTROL): {str(k): str(v) for k, v in (control or {}).items()},
        section_key(DATASET_OFFLINE): {str(k): str(v) for k, v in (offline or {}).items()},
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def auto_match(header: List[str], kind: str, cfg: Optional[dict] = None) -> Dict[str, str]:
    """按候选列名自动匹配表头：归一化后完全相同=3 分，包含=2 分；取最高分，同分取最靠前的列；匹配不到留空。"""
    cfg = cfg or get_config()
    header = [str(h) for h in (header or [])]
    norm_header = [normalize(h, cfg) for h in header]
    mapping: Dict[str, str] = {}
    for f in fields_for(kind, cfg):
        best_score, best_idx = 0, -1
        for cand in f["candidates"]:
            nc = normalize(cand, cfg)
            if not nc:
                continue
            for idx, nh in enumerate(norm_header):
                if not nh:
                    continue
                if nh == nc:
                    score = 3
                elif nc in nh:
                    score = 2
                else:
                    continue
                if score > best_score:
                    best_score, best_idx = score, idx
                elif score == best_score and best_score > 0 and idx < best_idx:
                    best_idx = idx
        mapping[f["key"]] = header[best_idx] if best_idx >= 0 else ""
    return mapping


def validate_mapping(mapping: Optional[Dict[str, str]], header: List[str], kind: str,
                     cfg: Optional[dict] = None) -> List[dict]:
    """返回 [{level, text}]：必需字段未映射 / 映射列不存在 = error；同一列被多个字段使用 = warn。"""
    cfg = cfg or get_config()
    header = [str(h) for h in (header or [])]
    in_header = set(header)
    used: Dict[str, List[str]] = {}
    msgs: List[dict] = []
    for f in fields_for(kind, cfg):
        col = str((mapping or {}).get(f["key"], "") or "").strip()
        if not col:
            if f["required"]:
                msgs.append({"level": "error",
                             "text": "必需字段『%s』还没有指定对应的列，请到④列名映射页选择。" % f["label"]})
            continue
        if col not in in_header:
            msgs.append({"level": "error",
                         "text": "字段『%s』映射的列『%s』在该文件表头里找不到，请重新选择列名。" % (f["label"], col)})
            continue
        used.setdefault(col, []).append(f["label"])
    for col, labels in used.items():
        if len(labels) > 1:
            msgs.append({"level": "warn",
                         "text": "列『%s』被多个字段同时使用（%s），请确认是否映射错了。" % (col, "、".join(labels))})
    return msgs
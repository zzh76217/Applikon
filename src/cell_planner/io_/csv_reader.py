# -*- coding: utf-8 -*-
"""my-Control Web UI 导出 CSV 的通用解析器（第五轮，答复#8）。

格式约定全部来自 config.csv_import：
  encoding（首选 UTF-8）+ encoding_fallbacks、delimiter=逗号、header_row=1（首行列名）、
  datetime_iso_format=YYYY-MM-DD HH:MM:SS（另配常见等价写法兜底）、max_rows 行数上限。
列名与逻辑字段的对应关系来自"列名映射"页（data/column_mapping.json），未配置时按候选列名自动匹配。

设计原则：
1. 只负责"把文件读成表"，不做任何工艺判断（判断在 core/analysis.py）。
2. 任何无法解析的单元格一律变成 None 并汇总成中文提示，绝不让界面崩溃。
3. 时间轴统一换算成"相对小时"（第一有效时间点为 0），并按时间升序排列。
4. 模拟数据（SIMULATED）在这里识别，界面必须据此显示醒目警告（答复#8）。
"""
from __future__ import annotations

import csv as _csv
import io as _io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cell_planner.core import column_mapping as cmap
from cell_planner.core.config_loader import get_config

SIMULATED_BANNER = "⚠️ 这是模拟数据（SIMULATED），仅供软件测试，不得用于真实批次决策！"

# 空值/占位符写法（技术细节，不是工艺参数）
_NULL_TOKENS = {"", "-", "--", "na", "n/a", "nan", "null", "none", "/", "?"}
_NUM_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


@dataclass
class RawTable:
    """一次原始读取的结果（未做列映射）。"""

    path: str = ""
    header: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    encoding_used: str = ""
    warnings: List[str] = field(default_factory=list)
    is_simulated: bool = False
    simulated_reason: str = ""

    @property
    def n_rows(self) -> int:
        return len(self.rows)


@dataclass
class Dataset:
    """映射 + 时间轴之后的可用数据集，供 analysis 模块使用。"""

    path: str = ""
    kind: str = ""
    header: List[str] = field(default_factory=list)
    mapping: Dict[str, str] = field(default_factory=dict)
    n_rows: int = 0
    n_points: int = 0
    t_hours: List[float] = field(default_factory=list)
    series: Dict[str, List[Optional[float]]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    is_simulated: bool = False
    simulated_reason: str = ""
    time_is_relative_numeric: bool = False

    # ---------- 便捷取数 ----------
    def values(self, key: str) -> List[Optional[float]]:
        return list(self.series.get(key, []))

    def has(self, key: str) -> bool:
        return any(v is not None for v in self.series.get(key, []))

    def pairs(self, key: str) -> List[Tuple[float, float]]:
        """(相对小时, 数值) 序列，自动跳过缺失值与无时间戳的行。"""
        seq = self.series.get(key) or []
        out: List[Tuple[float, float]] = []
        for i, t in enumerate(self.t_hours):
            if i >= len(seq):
                break
            v = seq[i]
            if t is None or v is None:
                continue
            out.append((float(t), float(v)))
        return out

    def first_valid(self, key: str) -> Optional[float]:
        for v in self.series.get(key) or []:
            if v is not None:
                return v
        return None

    def last_valid(self, key: str) -> Optional[float]:
        vals = [v for v in (self.series.get(key) or []) if v is not None]
        return vals[-1] if vals else None

    def field_label(self, key: str) -> str:
        for f in cmap.fields():
            if f["key"] == key:
                return f["label"]
        return key


def to_float(text) -> Optional[float]:
    """单元格文本 → float。空值/占位符/无法解析一律 None（由调用方汇总提示）。"""
    s = str(text if text is not None else "").strip()
    if not s or s.casefold() in _NULL_TOKENS:
        return None
    s = s.replace(" ", "").replace(",", "")
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_time(text, cfg: Optional[dict] = None) -> Optional[datetime]:
    """按 config 的 ISO 格式 + 等价写法解析时间；失败返回 None。"""
    cfg = cfg or get_config()
    imp = cfg["csv_import"]
    s = str(text if text is not None else "").strip()
    if not s or s.casefold() in _NULL_TOKENS:
        return None
    fmts = [str(imp.get("datetime_iso_format", "%Y-%m-%d %H:%M:%S"))]
    fmts += [str(x) for x in (imp.get("time_format_fallbacks") or [])]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _read_text(path: Path, cfg: dict) -> Tuple[str, str, List[str]]:
    """按 config 首选编码读取文本，失败时依次尝试 encoding_fallbacks。"""
    imp = cfg["csv_import"]
    prefer = str(imp.get("encoding", "utf-8"))
    order = [prefer] + [str(x) for x in (imp.get("encoding_fallbacks") or [])]
    raw_bytes = path.read_bytes()
    warns: List[str] = []
    for i, enc in enumerate(order):
        try:
            text = raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if i > 0:
            warns.append("文件不是首选编码 %s，已改用 %s 读取，请打开确认中文没有乱码。" % (prefer, enc))
        if text.startswith("\ufeff"):
            text = text[1:]
        return text.replace("\r\n", "\n").replace("\r", "\n"), enc, warns
    raise ValueError("无法识别文件编码（已尝试：%s）。请在 my-Control Web UI 导出时选 UTF-8，"
                     "或先用记事本打开后『另存为 → 编码 UTF-8』再导入。" % "、".join(order))


def _detect_simulated(path: Path, header: List[str], rows: List[List[str]], cfg: dict) -> Tuple[bool, str]:
    sim = cfg.get("simulation") or {}
    marker_value = str(sim.get("marker_value", "")).strip().upper()
    marker_column = str(sim.get("marker_column", "")).strip()
    prefix = str(sim.get("filename_prefix", "")).strip().upper()
    reasons: List[str] = []
    if prefix and prefix in path.name.upper():
        reasons.append("文件名带 %s 标记" % prefix)
    if marker_column and marker_column in header:
        j = header.index(marker_column)
        for r in rows[:50]:
            if j < len(r) and str(r[j]).strip().upper() == marker_value:
                reasons.append("每行的『%s』列都标着 %s" % (marker_column, marker_value))
                break
    if marker_value:
        for cell in header:
            if marker_value in str(cell).upper():
                reasons.append("表头里有 %s 字样（列『%s』）" % (marker_value, cell))
                break
    return bool(reasons), "；".join(reasons)


def read_raw_table(path, cfg: Optional[dict] = None) -> RawTable:
    """把 CSV 读成表头 + 文本行（不做列映射）。读不出来的情况一律抛中文 ValueError。"""
    cfg = cfg or get_config()
    imp = cfg["csv_import"]
    p = Path(path)
    if not p.is_file():
        raise ValueError("找不到要导入的文件：" + str(p) + "，请确认文件还在原来的位置。")
    if p.suffix.lower() not in (".csv", ".txt"):
        raise ValueError("只能导入 .csv 或 .txt 文件，当前文件类型是：" + p.suffix)
    text, enc_used, warns = _read_text(p, cfg)
    delim = str(imp.get("delimiter", ","))
    try:
        rows = list(_csv.reader(_io.StringIO(text), delimiter=delim))
    except (_csv.Error, UnicodeError) as exc:
        raise ValueError("CSV 解析失败：" + str(exc) + "（文件：" + str(p) + "）") from exc
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        raise ValueError("文件是空的或只有空行：" + str(p))

    header_row = max(int(imp.get("header_row", 1) or 1), 1)
    if header_row > 1:
        if len(rows) <= header_row - 1:
            raise ValueError("按配置跳过前 %d 行后没有数据了，请检查 config 的 csv_import.header_row。" % (header_row - 1))
        warns.append("已按 config.csv_import.header_row 跳过前 %d 行。" % (header_row - 1))
        rows = rows[header_row - 1:]

    header = [str(c).strip() for c in rows[0]]
    if not any(header):
        raise ValueError("第一行（列名行）是空的，无法识别列名：" + str(p))
    dup = [c for c in set(header) if header.count(c) > 1]
    if dup:
        warns.append("表头里有重复列名（%s），同名列只会用到最左边那一列。" % "、".join(sorted(dup)))

    body = rows[1:]
    ncol = len(header)
    fixed: List[List[str]] = []
    ragged = 0
    for r in body:
        cells = [str(c) for c in r]
        if len(cells) == ncol:
            fixed.append(cells)
        else:
            ragged += 1
            fixed.append((cells + [""] * ncol)[:ncol])
    if ragged:
        warns.append("有 %d 行的列数和表头（%d 列）对不上，已按表头自动补齐或截断，请核对文件是否被手工编辑过。" % (ragged, ncol))

    max_rows = int(imp.get("max_rows", 0) or 0)
    if max_rows and len(fixed) > max_rows:
        raise ValueError("数据行数 %d 超过单次导入上限 %d（config.csv_import.max_rows）。"
                         "请先在 my-Control Web UI 里把时间范围缩小后重新导出。" % (len(fixed), max_rows))

    is_sim, sim_reason = _detect_simulated(p, header, fixed, cfg)
    return RawTable(path=str(p), header=header, rows=fixed, encoding_used=enc_used,
                    warnings=warns, is_simulated=is_sim, simulated_reason=sim_reason)


def _build_time_axis(rows: List[List[str]], col_index: Optional[int], ds: Dataset, cfg: dict) -> List[Optional[float]]:
    n = len(rows)
    if col_index is None:
        ds.errors.append("没有指定『时间戳』对应的列，无法做随时间变化的分析。请到④列名映射页指定时间列。")
        return [None] * n
    cells = [r[col_index] if col_index < len(r) else "" for r in rows]
    stamps = [parse_time(c, cfg) for c in cells]
    ok = [s for s in stamps if s is not None]
    if len(ok) >= max(1, int(n * 0.5)):
        base = min(ok)
        ds.time_is_relative_numeric = False
        if len(ok) < n:
            ds.warnings.append("有 %d 行的时间戳不是可识别的时间格式（应为 %s），这些行已跳过。"
                               % (n - len(ok), cfg["csv_import"].get("datetime_iso_format", "YYYY-MM-DD HH:MM:SS")))
        return [((s - base).total_seconds() / 3600.0) if s is not None else None for s in stamps]

    if bool(cfg["csv_import"].get("numeric_time_allowed", True)):
        nums = [to_float(c) for c in cells]
        valid = [v for v in nums if v is not None]
        if len(valid) >= max(1, int(n * 0.5)):
            base = min(valid)
            ds.time_is_relative_numeric = True
            ds.warnings.append("时间列不是日期时间格式，已按『数值＝相对小时』当作时间轴处理。"
                               "如果那一列实际是秒或别的单位，请在 my-Control 导出时选时间戳列。")
            return [(v - base) if v is not None else None for v in nums]

    ds.errors.append("时间列既不是可识别的日期时间（应为 %s 这类 ISO 写法），也不是数值，无法建立时间轴。"
                     % str(cfg["csv_import"].get("datetime_iso_format", "YYYY-MM-DD HH:MM:SS")))
    return [None] * n


def load_dataset(path, kind: str, mapping: Optional[Dict[str, str]] = None,
                 cfg: Optional[dict] = None, auto_match_when_empty: bool = True) -> Dataset:
    """读取 + 映射 + 建时间轴。任何失败都写进 ds.errors / ds.warnings，不抛异常（界面据此提示）。"""
    cfg = cfg or get_config()
    ds = Dataset(path=str(path), kind=kind)
    try:
        raw = read_raw_table(path, cfg)
    except ValueError as exc:
        ds.errors.append(str(exc))
        return ds
    except OSError as exc:
        ds.errors.append("文件读取失败：" + str(exc))
        return ds

    ds.header = raw.header
    ds.n_rows = raw.n_rows
    ds.warnings.extend(raw.warnings)
    if raw.is_simulated:
        ds.is_simulated = True
        ds.simulated_reason = raw.simulated_reason
        ds.warnings.append(SIMULATED_BANNER + "（识别依据：" + raw.simulated_reason + "）")

    use: Dict[str, str] = {str(k): str(v).strip() for k, v in (mapping or {}).items()}
    if auto_match_when_empty and not any(use.values()):
        use = cmap.auto_match(raw.header, kind, cfg)
        matched = sum(1 for v in use.values() if v)
        ds.warnings.append("没有保存过列名映射，已按候选列名自动匹配（成功 %d / 共 %d 个字段）。"
                           "如果匹配不对，请到④列名映射页手动指定并保存。" % (matched, len(use)))
    ds.mapping = use

    for msg in cmap.validate_mapping(use, raw.header, kind, cfg):
        if msg["level"] == "error":
            ds.errors.append(msg["text"])
        else:
            ds.warnings.append(msg["text"])

    index: Dict[str, int] = {}
    for key, col in use.items():
        if col and col in raw.header:
            index[key] = raw.header.index(col)

    ds.t_hours = _build_time_axis(raw.rows, index.get("time"), ds, cfg)
    keep = [i for i, t in enumerate(ds.t_hours) if t is not None]
    if len(keep) < len(ds.t_hours):
        ds.warnings.append("共有 %d 行没有有效时间戳，已从分析中剔除。" % (len(ds.t_hours) - len(keep)))
    order = sorted(keep, key=lambda i: ds.t_hours[i])
    if any(ds.t_hours[order[j]] < ds.t_hours[order[j - 1]] for j in range(1, len(order))):
        pass  # 排序后必然升序，这里只负责提示原始顺序是否乱过
    if any(ds.t_hours[i] is not None for i in range(len(ds.t_hours))):
        raw_order = [t for t in ds.t_hours if t is not None]
        if any(raw_order[j] < raw_order[j - 1] for j in range(1, len(raw_order))):
            ds.warnings.append("文件里的时间顺序不是从早到晚，已自动按时间升序排列后再分析。")
    ds.t_hours = [ds.t_hours[i] for i in order]
    ds.n_points = len(ds.t_hours)

    for key, j in index.items():
        if key == "time":
            continue
        vals = [to_float(raw.rows[i][j]) if j < len(raw.rows[i]) else None for i in range(len(raw.rows))]
        n_bad = sum(1 for v in vals if v is None)
        if n_bad:
            ds.warnings.append("字段『%s』有 %d 个数据点是空值或无法解析的文本，已跳过这些点。"
                               % (ds.field_label(key), n_bad))
        ds.series[key] = [vals[i] for i in order]

    if not any(ds.series.get(k) for k in index if k != "time"):
        ds.errors.append("按当前列名映射没有取到任何有效数值，请到④列名映射页检查列名是否对应正确。")
    return ds
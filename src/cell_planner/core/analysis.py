# -*- coding: utf-8 -*-
"""模块 3 离线分析（第五轮）：生长曲线与 μ、DO 偏差报警与消耗速率外推、代谢警戒、收获建议、批次摘要。

阈值全部来自 config（do_alarm / metabolite_limits / harvest_hint / analysis），本文件不写死工艺数值：
  公式 6（requirements 3.2）  μ = (ln X2 - ln X1) / (t2 - t1)   —— 本模块 t 用小时，μ 单位 1/小时，×24 得 1/天
  答复#7  DO 低于设定点 deviation_yellow_points 个百分点：持续 >=15 分钟 → 🟡，>=30 分钟 → 🔴；DO < 20% 立即 🔴
  答复#10 葡萄糖 黄 <2、红 <0.5、补糖目标 2-4 g/L；乳酸 黄 >2、红 >4 g/L；界面同显 g/L 与 mmol/L
  收获建议 活率 <80% 且密度下降 → 提示收获
所有函数对非法输入抛中文 ValueError，或在 analyze() 里被降级为警告文本，严禁让界面崩溃。
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from cell_planner.core.config_loader import get_config
from cell_planner.core.validators import LEVEL_ERROR, LEVEL_PASS, LEVEL_WARN

LEVEL_NONE = "none"          # 仅用于"这一格没有数据"的灰色显示，不是校验级别
LEVEL_ICON = {LEVEL_PASS: "✅", LEVEL_WARN: "🟡", LEVEL_ERROR: "🔴", LEVEL_NONE: "⚪"}

HOURS_PER_DAY = 24.0


# ---------------------------------------------------------------- 基础工具
def _clean_pairs(pairs: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """过滤 None / 非有限值，并按时间升序排序。"""
    out: List[Tuple[float, float]] = []
    for item in pairs or []:
        try:
            t, v = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(t) and math.isfinite(v):
            out.append((t, v))
    out.sort(key=lambda x: x[0])
    return out


def _linreg(xs: Sequence[float], ys: Sequence[float]) -> Tuple[float, float, float]:
    """最小二乘拟合 y = a + b·x，返回 (截距 a, 斜率 b, R²)。点数不足或 x 全相同 → 中文 ValueError。"""
    n = len(xs)
    if n != len(ys) or n < 2:
        raise ValueError("拟合至少需要 2 个数据点，当前只有 %d 个。" % n)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        raise ValueError("所有数据点的时间都相同，无法做回归（请检查时间列是否只有一个时刻）。")
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 if ss_tot <= 0 else 1.0 - ss_res / ss_tot
    return a, b, r2


def _median_gap(pts: List[Tuple[float, float]], default: float) -> float:
    gaps = sorted((pts[i][0] - pts[i - 1][0]) for i in range(1, len(pts)))
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return default
    mid = len(gaps) // 2
    return gaps[mid] if len(gaps) % 2 else 0.5 * (gaps[mid - 1] + gaps[mid])


# ---------------------------------------------------------------- 公式 6：比生长速率
def mu_between_hours(x1: float, t1_h: float, x2: float, t2_h: float) -> float:
    """公式 6：μ = (ln X2 − ln X1) / (t2 − t1)，时间用小时 → 返回 1/小时。"""
    for name, val in (("前一个时间点的细胞密度", x1), ("后一个时间点的细胞密度", x2)):
        if val is None or (isinstance(val, float) and not math.isfinite(val)):
            raise ValueError("%s不是有效数字，无法计算 μ。" % name)
        if float(val) <= 0:
            raise ValueError("%s必须大于 0（细胞密度不能是 0 或负数），当前值：%s" % (name, val))
    if t2_h is None or t1_h is None:
        raise ValueError("计算 μ 需要两个时间点，当前时间缺失（请检查 CSV 的时间列）。")
    dt = float(t2_h) - float(t1_h)
    if dt <= 0:
        raise ValueError("后一个时间点必须晚于前一个时间点（当前时间差 %s 小时）。" % _num(dt))
    return (math.log(float(x2)) - math.log(float(x1))) / dt


def _num(x: Optional[float]) -> str:
    if x is None:
        return "—"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return "%.3g" % x


def mu_segments(pairs: Sequence[Tuple[float, float]]) -> List[dict]:
    """相邻采样点逐段 μ（公式 6）。返回按时间排序的段列表。"""
    pts = _clean_pairs(pairs)
    rows: List[dict] = []
    for i in range(1, len(pts)):
        t1, x1 = pts[i - 1]
        t2, x2 = pts[i]
        if t2 <= t1 or x1 <= 0 or x2 <= 0:
            continue
        mu_h = (math.log(x2) - math.log(x1)) / (t2 - t1)
        rows.append({
            "t1_h": t1, "t2_h": t2, "x1": x1, "x2": x2,
            "mu_per_hour": mu_h, "mu_per_day": mu_h * HOURS_PER_DAY,
            "doubling_time_hours": (math.log(2.0) / mu_h) if mu_h > 0 else None,
        })
    return rows


def _log_rates(pts: List[Tuple[float, float]]) -> List[Tuple[int, float]]:
    """相邻点的 ln X 瞬时变化率，返回 [(左点下标, 1/小时)]（公式 6 的微分形式）。"""
    out: List[Tuple[int, float]] = []
    for i in range(1, len(pts)):
        dt = pts[i][0] - pts[i - 1][0]
        if dt <= 0:
            continue
        out.append((i - 1, (math.log(pts[i][1]) - math.log(pts[i - 1][1])) / dt))
    return out


def exponential_window(pairs: Sequence[Tuple[float, float]], cfg: Optional[dict] = None) -> List[Tuple[float, float]]:
    """指数期窗口（纯数据驱动）：取"瞬时生长率 >= 容差 x 最大瞬时生长率"的最长连续采样段。
    容差是无量纲算法参数，来自 config.analysis.exponential_rate_tolerance，不是工艺阈值。"""
    cfg = cfg or get_config()
    tol = float(cfg["analysis"]["exponential_rate_tolerance"])
    pts = [p for p in _clean_pairs(pairs) if p[1] > 0]
    rates = _log_rates(pts)
    pos = [r for _, r in rates if r > 0]
    if len(pts) < 2 or not pos:
        return []
    thresh = tol * max(pos)
    ok = set()
    for i, r in rates:
        if r >= thresh:
            ok.update((i, i + 1))
    best: List[Tuple[float, float]] = []
    cur: List[Tuple[float, float]] = []
    for i in range(len(pts)):
        if i in ok:
            cur.append(pts[i])
        else:
            if len(cur) > len(best):
                best = cur
            cur = []
    if len(cur) > len(best):
        best = cur
    return best


def fit_growth_mu(pairs: Sequence[Tuple[float, float]], cfg: Optional[dict] = None) -> dict:
    """对数期拟合：对 ln X ~ t 做线性回归，斜率即 μ（1/小时，x24 得 1/天）。
    回归窗口优先取指数期窗口；点数不足时退回"密度上升到峰值"的整段（并说明原因）。"""
    cfg = cfg or get_config()
    min_n = int(cfg["analysis"]["growth_fit_min_points"])
    pts = [p for p in _clean_pairs(pairs) if p[1] > 0]
    if len(pts) < 2:
        raise ValueError("有效的细胞密度数据点不足 2 个，无法计算比生长速率 μ。")
    peak_i = max(range(len(pts)), key=lambda i: pts[i][1])
    info = {"n_points_total": len(pts), "peak_time_h": pts[peak_i][0], "peak_density": pts[peak_i][1]}
    win = exponential_window(pts, cfg)
    kind = "指数期窗口（瞬时生长率 >= 容差 x 最大瞬时生长率的最长连续段）"
    if len(win) < min_n:
        win = pts[: peak_i + 1]
        kind = "密度上升到峰值的全部点（指数期窗口点数不足，退回整段上升期）"
    if len(win) < min_n:
        return dict(info, ok=False, mu_per_hour=None, mu_per_day=None, doubling_time_hours=None,
                    r_squared=None, n_points_used=len(win), window_kind="—",
                    reason="上升段只有 %d 个点，少于 config.analysis.growth_fit_min_points 要求的 %d 个点，"
                           "不做对数期回归（逐段 μ 仍然可用）。" % (len(win), min_n))
    a, b, r2 = _linreg([t for t, _ in win], [math.log(x) for _, x in win])
    return dict(info, ok=True, mu_per_hour=b, mu_per_day=b * HOURS_PER_DAY,
                doubling_time_hours=(math.log(2.0) / b) if b > 0 else None, r_squared=r2, intercept=a,
                n_points_used=len(win), window_hours=[win[0][0], win[-1][0]], window_kind=kind,
                reason="对数期 ln X 对 t 线性回归（公式 6 的连续形式）；μ 单位 1/小时，x24 得 1/天。")


# ---------------------------------------------------------------- 答复#7：DO 报警
@dataclass
class AlarmEvent:
    level: str            # LEVEL_WARN / LEVEL_ERROR
    kind: str             # "deviation" 偏差持续 / "absolute" 绝对红线
    start_h: float
    end_h: float
    duration_minutes: float
    threshold: float
    min_value: float
    note: str

    @property
    def level_icon(self) -> str:
        return LEVEL_ICON.get(self.level, "")


def _runs_below(pts: List[Tuple[float, float]], threshold: float, max_gap_h: float) -> List[Tuple[int, int]]:
    """返回连续低于阈值的 (起始索引, 结束索引) 区间；采样间隔超过 max_gap_h 视为断开。"""
    runs: List[Tuple[int, int]] = []
    i = 0
    n = len(pts)
    while i < n:
        if pts[i][1] <= threshold:
            j = i
            while j + 1 < n and pts[j + 1][1] <= threshold and (pts[j + 1][0] - pts[j][0]) <= max_gap_h:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def do_alarm_scan(t_hours: Sequence[Optional[float]], values: Sequence[Optional[float]],
                  do_setpoint_percent: float, cfg: Optional[dict] = None) -> List[AlarmEvent]:
    """按答复#7 扫描 DO：偏差持续超阈值 → 🟡/🔴；跌破绝对红线 → 立即 🔴。"""
    cfg = cfg or get_config()
    da = cfg["do_alarm"]
    dev = float(da["deviation_yellow_points"])
    yellow_min = float(da["deviation_yellow_minutes"])
    red_min = float(da["deviation_red_minutes"])
    abs_red = float(da["absolute_red_percent"])
    setpoint = float(do_setpoint_percent)
    pts = _clean_pairs(list(zip(t_hours, values)))
    if len(pts) < 2:
        raise ValueError("DO 数据点不足 2 个，无法做报警扫描（请检查时间列与 DO 列的映射）。")
    gap_fallback_h = float(da["gap_default_hours"])      # 答复：断档阈值集中在 config，不写死
    gap_factor = float(da["gap_max_factor"])
    gap_default = _median_gap(pts, default=gap_fallback_h)
    max_gap_h = gap_default * gap_factor if gap_default > 0 else gap_fallback_h
    threshold = setpoint - dev
    events: List[AlarmEvent] = []
    for i, j in _runs_below(pts, threshold, max_gap_h):
        span = (pts[j][0] - pts[i][0]) * 60.0
        low = min(v for _, v in pts[i: j + 1])
        if span >= red_min:
            level = LEVEL_ERROR
            why = "持续 %s 分钟 ≥ 红线 %s 分钟" % (_num(span), _num(red_min))
        elif span >= yellow_min:
            level = LEVEL_WARN
            why = "持续 %s 分钟 ≥ 黄线 %s 分钟" % (_num(span), _num(yellow_min))
        else:
            continue
        events.append(AlarmEvent(level=level, kind="deviation", start_h=pts[i][0], end_h=pts[j][0],
                                 duration_minutes=span, threshold=threshold, min_value=low,
                                 note="DO 低于设定点 %s%% 至少 %s 个百分点（阈值 %s%%）：%s"
                                      % (_num(setpoint), _num(dev), _num(threshold), why)))
    for i, j in _runs_below(pts, abs_red, max_gap_h):
        span = (pts[j][0] - pts[i][0]) * 60.0
        low = min(v for _, v in pts[i: j + 1])
        events.append(AlarmEvent(level=LEVEL_ERROR, kind="absolute", start_h=pts[i][0], end_h=pts[j][0],
                                 duration_minutes=span, threshold=abs_red, min_value=low,
                                 note="绝对红线：DO 实测 %s%% 低于 %s%%，立即报警（答复#7）"
                                      % (_num(low), _num(abs_red))))
    events.sort(key=lambda e: (e.start_h, 0 if e.kind == "absolute" else 1))
    return events


def do_alarm_summary(events: Sequence[AlarmEvent]) -> dict:
    n_red = sum(1 for e in events if e.level == LEVEL_ERROR and e.kind == "deviation")
    n_yellow = sum(1 for e in events if e.level == LEVEL_WARN)
    n_abs = sum(1 for e in events if e.kind == "absolute")
    dev_minutes = sum(e.duration_minutes for e in events if e.kind == "deviation")
    abs_minutes = sum(e.duration_minutes for e in events if e.kind == "absolute")
    longest = max((e.duration_minutes for e in events if e.kind == "deviation"), default=0.0)
    return {
        "n_events": len(events), "n_red": n_red, "n_yellow": n_yellow, "n_absolute_red": n_abs,
        "deviation_minutes": dev_minutes, "absolute_red_minutes": abs_minutes,
        "longest_deviation_minutes": longest,
    }


def do_extrapolation(t_hours: Sequence[Optional[float]], values: Sequence[Optional[float]],
                     do_setpoint_percent: float, cfg: Optional[dict] = None) -> dict:
    """DO 消耗速率外推：用最近 lookback_hours 的线性斜率，估算还需多久跌破偏差阈值 / 绝对红线。
    只作信息展示（不做红黄判定，判定仍由 do_alarm_scan 负责）。"""
    cfg = cfg or get_config()
    ex = cfg["analysis"]["do_extrapolation"]
    lookback = float(ex["lookback_hours"])
    min_n = int(ex["min_points"])
    da = cfg["do_alarm"]
    dev = float(da["deviation_yellow_points"])
    abs_red = float(da["absolute_red_percent"])
    pts = _clean_pairs(list(zip(t_hours, values)))
    if not pts:
        return {"ok": False, "note": "没有可用的 DO 数据，无法外推。"}
    t_end = pts[-1][0]
    window = [p for p in pts if p[0] >= t_end - lookback]
    if len(window) < min_n:
        return {"ok": False, "window_hours": lookback,
                "note": "最近 %s 小时内只有 %s 个 DO 数据点（少于 config 要求的 %d 个），不做外推。"
                        % (_num(lookback), _num(len(window)), min_n)}
    a, b, r2 = _linreg([t for t, _ in window], [v for _, v in window])
    last_v = window[-1][1]
    threshold = float(do_setpoint_percent) - dev
    if b >= 0:
        return {"ok": False, "slope_percent_per_hour": b, "last_value": last_v, "r_squared": r2,
                "n_points": len(window), "window_hours": [window[0][0], window[-1][0]],
                "note": "最近窗口内 DO 没有下降趋势（斜率 %s %%/h），不需要外推预警。" % _num(b)}
    def minutes_to(target: float) -> float:
        if last_v <= target:
            return 0.0
        return (last_v - target) / (-b) * 60.0
    return {
        "ok": True, "slope_percent_per_hour": b, "last_value": last_v, "r_squared": r2,
        "n_points": len(window), "window_hours": [window[0][0], window[-1][0]],
        "threshold_deviation_percent": threshold, "minutes_to_deviation": minutes_to(threshold),
        "absolute_red_percent": abs_red, "minutes_to_absolute_red": minutes_to(abs_red),
        "note": "线性外推，只用于提前干预提示，不是 my-Control 硬件报警。",
    }


# ---------------------------------------------------------------- 答复#10：代谢警戒
def mw_g_per_mol(kind: str, cfg: Optional[dict] = None) -> float:
    """分子量：乳酸取 metabolite_limits.lactate_mw_g_mol，葡萄糖取 unit_constants.glucose_mw_g_mol。"""
    cfg = cfg or get_config()
    kind = str(kind or "").strip().lower()
    if kind in ("lactate", "lac", "乳酸"):
        return float(cfg["metabolite_limits"]["lactate_mw_g_mol"])
    if kind in ("glucose", "glc", "葡萄糖"):
        return float(cfg["unit_constants"]["glucose_mw_g_mol"])
    raise ValueError("不认识的要换算物质：" + str(kind))


def g_per_l_to_mmol_per_l(value_g_l: float, mw_g_mol: float) -> float:
    """g/L → mmol/L = g/L ÷ 分子量 × 1000（答复#10）。"""
    if value_g_l is None:
        raise ValueError("浓度为空，无法换算 mmol/L。")
    if mw_g_mol <= 0:
        raise ValueError("分子量必须大于 0（请检查 config 里的 metabolite_limits / unit_constants）。")
    return float(value_g_l) / float(mw_g_mol) * 1000.0


def glucose_flag(value: Optional[float], cfg: Optional[dict] = None) -> dict:
    cfg = cfg or get_config()
    gl = cfg["metabolite_limits"]["glucose_g_l"]
    red = float(gl["red_below"])
    yellow = float(gl["yellow_below"])
    lo, hi = [float(x) for x in gl["target_range"]]
    if value is None:
        return {"level": LEVEL_NONE, "text": "没有葡萄糖数据"}
    v = float(value)
    if v < red:
        return {"level": LEVEL_ERROR, "text": "🔴 葡萄糖 %s g/L < 红线 %s g/L：已耗竭，必须立即补糖" % (_num(v), _num(red))}
    if v < yellow:
        return {"level": LEVEL_WARN, "text": "🟡 葡萄糖 %s g/L < 黄线 %s g/L：提示补糖（目标 %s–%s g/L）"
                % (_num(v), _num(yellow), _num(lo), _num(hi))}
    if v <= hi:
        return {"level": LEVEL_PASS, "text": "✅ 葡萄糖 %s g/L 在补糖目标区间 %s–%s g/L" % (_num(v), _num(lo), _num(hi))}
    return {"level": LEVEL_PASS, "text": "✅ 葡萄糖 %s g/L 高于目标区间上限 %s g/L（目前充足）" % (_num(v), _num(hi))}


def lactate_flag(value: Optional[float], cfg: Optional[dict] = None) -> dict:
    cfg = cfg or get_config()
    lc = cfg["metabolite_limits"]["lactate_g_l"]
    yellow = float(lc["yellow_above"])
    red = float(lc["red_above"])
    if value is None:
        return {"level": LEVEL_NONE, "text": "没有乳酸数据"}
    v = float(value)
    if v > red:
        return {"level": LEVEL_ERROR, "text": "🔴 乳酸 %s g/L > 红线 %s g/L：副产物明显积累，需人工复核补料/换液策略"
                % (_num(v), _num(red))}
    if v > yellow:
        return {"level": LEVEL_WARN, "text": "🟡 乳酸 %s g/L > 黄线 %s g/L：开始积累，建议关注" % (_num(v), _num(yellow))}
    return {"level": LEVEL_PASS, "text": "✅ 乳酸 %s g/L 未超过黄线 %s g/L" % (_num(v), _num(yellow))}


def metabolite_rows(t_hours: Sequence[Optional[float]], glucose: Sequence[Optional[float]],
                    lactate: Sequence[Optional[float]], cfg: Optional[dict] = None) -> List[dict]:
    """逐取样点的代谢评估行（同显 g/L 与 mmol/L）。"""
    cfg = cfg or get_config()
    mw_g = mw_g_per_mol("glucose", cfg)
    mw_l = mw_g_per_mol("lactate", cfg)
    rows: List[dict] = []
    n = len(t_hours)
    for i in range(n):
        t = t_hours[i]
        if t is None:
            continue
        g = glucose[i] if i < len(glucose) else None
        l = lactate[i] if i < len(lactate) else None
        gf = glucose_flag(g, cfg)
        lf = lactate_flag(l, cfg)
        worst = LEVEL_PASS
        for lv in (gf["level"], lf["level"]):
            if lv == LEVEL_ERROR:
                worst = LEVEL_ERROR
            elif lv == LEVEL_WARN and worst != LEVEL_ERROR:
                worst = LEVEL_WARN
        rows.append({
            "t_h": float(t),
            "glucose_g_l": g,
            "glucose_mmol_l": (g_per_l_to_mmol_per_l(g, mw_g) if g is not None else None),
            "glucose_level": gf["level"], "glucose_text": gf["text"],
            "lactate_g_l": l,
            "lactate_mmol_l": (g_per_l_to_mmol_per_l(l, mw_l) if l is not None else None),
            "lactate_level": lf["level"], "lactate_text": lf["text"],
            "level": worst,
        })
    return rows


# ---------------------------------------------------------------- 收获建议
def harvest_advice(density_pairs: Sequence[Tuple[float, float]],
                   viability_pairs: Sequence[Tuple[float, float]], cfg: Optional[dict] = None) -> dict:
    """requirements 模块3 / 答复：活率 <80% 且密度下降 → 提示收获。"""
    cfg = cfg or get_config()
    th = float(cfg["harvest_hint"]["viability_below_percent"])
    via = _clean_pairs(viability_pairs)
    den = _clean_pairs(density_pairs)
    if not via:
        return {"level": LEVEL_NONE, "text": "没有活率数据（离线取样表里缺少活率列或没映射上），无法给出收获建议。"}
    last_via = via[-1][1]
    declining = len(den) >= 2 and den[-1][1] < den[-2][1]
    t_last = via[-1][0]
    if last_via < th and declining:
        return {"level": LEVEL_WARN,
                "text": "🟡 建议收获：活率 %s%% 已低于阈值 %s%%，且细胞密度从 %s 降到 %s ×10⁶ cells/mL（第 %s 小时）。"
                        % (_num(last_via), _num(th), _num(den[-2][1]), _num(den[-1][1]), _num(t_last))}
    if last_via < th:
        return {"level": LEVEL_WARN,
                "text": "🟡 需人工确认：活率 %s%% 已低于阈值 %s%%，但细胞密度还没明显下降，可继续观察 1 个取样点。"
                        % (_num(last_via), _num(th))}
    if declining:
        return {"level": LEVEL_PASS,
                "text": "✅ 暂不提示收获：密度已从 %s 降到 %s ×10⁶ cells/mL，但活率 %s%% 仍高于阈值 %s%%，"
                        "请结合代谢指标判断。" % (_num(den[-2][1]), _num(den[-1][1]), _num(last_via), _num(th))}
    return {"level": LEVEL_PASS,
            "text": "✅ 暂不提示收获：活率 %s%% ≥ 阈值 %s%%，细胞密度仍在上升或持平。" % (_num(last_via), _num(th))}


# ---------------------------------------------------------------- 总分析入口
def _merge_warnings(ds_list, res: dict) -> None:
    for ds in ds_list:
        if ds is None:
            continue
        for w in ds.warnings:
            if w not in res["warnings"]:
                res["warnings"].append(w)
        for e in ds.errors:
            if e not in res["errors"]:
                res["errors"].append(e)


def analyze(control=None, offline=None, do_setpoint_percent: Optional[float] = None,
            cfg: Optional[dict] = None) -> dict:
    """把两个 Dataset（可为 None）跑一遍完整分析。任何子任务失败都只降级为中文提示。"""
    cfg = cfg or get_config()
    res: dict = {
        "metrics": {}, "mu_fit": {}, "mu_segments": [], "do_events": [], "do_summary": {},
        "do_extrapolation": {}, "metabolite_rows": [], "harvest": {"level": LEVEL_NONE, "text": "未做分析"},
        "warnings": [], "errors": [], "is_simulated": False, "notes": [],
        "generated_at": "",
    }
    _merge_warnings([control, offline], res)
    if control is not None and offline is not None:
        res["is_simulated"] = bool(control.is_simulated or offline.is_simulated)
    elif control is not None:
        res["is_simulated"] = bool(control.is_simulated)
    elif offline is not None:
        res["is_simulated"] = bool(offline.is_simulated)

    if do_setpoint_percent is None:
        do_setpoint_percent = float(cfg["process_defaults"]["do_percent"]["set"])
        res["notes"].append("DO 设定点取 config.process_defaults.do_percent.set = %s%%（界面可改）" % _num(do_setpoint_percent))

    # ---- 生长曲线
    den_pairs = offline.pairs("cell_density_mcells_ml") if offline is not None else []
    via_pairs = offline.pairs("viability_percent") if offline is not None else []
    if len(den_pairs) >= 2:
        try:
            res["mu_segments"] = mu_segments(den_pairs)
            res["mu_fit"] = fit_growth_mu(den_pairs, cfg)
        except (ValueError, ZeroDivisionError) as exc:
            res["errors"].append("生长曲线分析失败：" + str(exc))
    else:
        res["notes"].append("没有足够的细胞密度采样点（离线取样 CSV 里需要映射『细胞密度』列且有 2 个以上点），跳过 μ 计算。")

    # ---- DO 报警
    if control is not None and control.has("do_percent"):
        try:
            res["do_events"] = do_alarm_scan(control.t_hours, control.values("do_percent"),
                                             float(do_setpoint_percent), cfg)
            res["do_summary"] = do_alarm_summary(res["do_events"])
            res["do_extrapolation"] = do_extrapolation(control.t_hours, control.values("do_percent"),
                                                       float(do_setpoint_percent), cfg)
        except (ValueError, ZeroDivisionError) as exc:
            res["errors"].append("DO 报警分析失败：" + str(exc))
    else:
        res["notes"].append("没有 DO 时间序列（未导入控制数据 CSV，或 DO 列没映射上），跳过 DO 报警分析。")

    # ---- 代谢
    if offline is not None:
        n = offline.n_points
        res["metabolite_rows"] = metabolite_rows(offline.t_hours,
                                                 (offline.values("glucose_g_l") + [None] * n)[:n],
                                                 (offline.values("lactate_g_l") + [None] * n)[:n], cfg)
    res["harvest"] = harvest_advice(den_pairs, via_pairs, cfg)

    # ---- 批次摘要（字段名与 config.template_library.compare_fields 对齐）
    res["metrics"] = build_metrics(control, offline, res, cfg)
    res["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return res


def _peak(values: Sequence[Optional[float]]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    return max(vals) if vals else None


def build_metrics(control=None, offline=None, res: Optional[dict] = None, cfg: Optional[dict] = None) -> dict:
    """批次关键参数摘要（供批次对比表与报告导出使用；缺数据一律 None，显示为 —）。"""
    cfg = cfg or get_config()
    res = res or {}
    m: dict = {
        "peak_density_mcells_ml": None, "peak_viability_percent": None,
        "mu_max_per_day": None, "doubling_time_hours": None,
        "glucose_min_g_l": None, "lactate_max_g_l": None,
        "do_yellow_minutes": None, "n_do_alarms": None,
        "days_observed": None, "is_simulated": bool((res.get("is_simulated") or False)),
        "density_start_mcells_ml": None, "glucose_consumed_g_l": None, "lactate_produced_g_l": None,
        "do_min_percent": None, "do_mean_percent": None, "ph_mean": None, "temp_mean_c": None, "rpm_mean": None,
        "n_control_points": (control.n_points if control is not None else 0),
        "n_offline_points": (offline.n_points if offline is not None else 0),
        "peak_day_hours": None,
    }
    if offline is not None:
        den = offline.pairs("cell_density_mcells_ml")
        via = offline.pairs("viability_percent")
        if den:
            m["peak_density_mcells_ml"] = _peak([v for _, v in den])
            m["density_start_mcells_ml"] = den[0][1]
            m["peak_day_hours"] = max(den, key=lambda p: p[1])[0]
        if via:
            m["peak_viability_percent"] = _peak([v for _, v in via])
        g = [v for v in offline.values("glucose_g_l") if v is not None]
        l = [v for v in offline.values("lactate_g_l") if v is not None]
        if g:
            m["glucose_min_g_l"] = min(g)
            m["glucose_consumed_g_l"] = g[0] - min(g)
        if l:
            m["lactate_max_g_l"] = max(l)
            m["lactate_produced_g_l"] = max(l) - l[0]
        if offline.t_hours:
            m["days_observed"] = max(offline.t_hours) / HOURS_PER_DAY
    fit = res.get("mu_fit") or {}
    segs = res.get("mu_segments") or []
    seg_pos = [s["mu_per_day"] for s in segs if s.get("mu_per_day") is not None and s["mu_per_day"] > 0]
    if seg_pos:
        m["mu_max_per_day"] = max(seg_pos)
    elif fit.get("ok"):
        m["mu_max_per_day"] = fit.get("mu_per_day")
    if m["mu_max_per_day"]:
        m["doubling_time_hours"] = math.log(2.0) / (m["mu_max_per_day"] / HOURS_PER_DAY)
    ds_sum = res.get("do_summary") or {}
    if ds_sum:
        m["do_yellow_minutes"] = ds_sum.get("deviation_minutes")
        m["n_do_alarms"] = ds_sum.get("n_events")
    if control is not None:
        do = [v for v in control.values("do_percent") if v is not None]
        if do:
            m["do_min_percent"] = min(do)
            m["do_mean_percent"] = sum(do) / len(do)
        if control.t_hours and m["days_observed"] is None:
            m["days_observed"] = max(control.t_hours) / HOURS_PER_DAY
        for key, slot in (("ph", "ph_mean"), ("temperature_c", "temp_mean_c"), ("agitation_rpm", "rpm_mean")):
            vals = [v for v in control.values(key) if v is not None]
            if vals:
                m[slot] = sum(vals) / len(vals)
    return m


def metric_label(key: str, cfg: Optional[dict] = None) -> str:
    cfg = cfg or get_config()
    for item in cfg["template_library"]["compare_fields"]:
        if str(item.get("key")) == key:
            return str(item.get("label") or key)
    _extra = {
        "density_start_mcells_ml": "起始细胞密度 (×10⁶ cells/mL)",
        "glucose_consumed_g_l": "累计耗糖 (g/L)",
        "lactate_produced_g_l": "累计产乳酸 (g/L)",
        "do_min_percent": "DO 最低值 (%)",
        "do_mean_percent": "DO 平均值 (%)",
        "ph_mean": "pH 平均值",
        "temp_mean_c": "温度平均值 (°C)",
        "rpm_mean": "搅拌转速平均值 (rpm)",
        "n_control_points": "控制数据点数",
        "n_offline_points": "离线取样点数",
        "peak_day_hours": "密度峰值时刻 (h)",
    }
    return _extra.get(key, key)


def report_sections(res: dict, cfg: Optional[dict] = None) -> List[Tuple[str, List[str], List[List[str]]]]:
    """把分析结果整理成 [(小节标题, 表头, 行)]，供界面表格与报告 CSV 导出复用。"""
    cfg = cfg or get_config()
    m = res.get("metrics") or {}
    sections: List[Tuple[str, List[str], List[List[str]]]] = []
    rows = []
    for key in [str(x["key"]) for x in cfg["template_library"]["compare_fields"]] + \
               ["density_start_mcells_ml", "glucose_consumed_g_l", "lactate_produced_g_l",
                "do_min_percent", "do_mean_percent", "ph_mean", "temp_mean_c", "rpm_mean",
                "n_control_points", "n_offline_points", "peak_day_hours"]:
        if key in m:
            rows.append([metric_label(key, cfg), fmt_metric(key, m.get(key), cfg)])
    sections.append(("批次关键参数摘要", ["指标", "数值"], rows))

    alarm_rows = []
    for e in res.get("do_events") or []:
        alarm_rows.append([LEVEL_ICON.get(e.level, ""), "偏差持续" if e.kind == "deviation" else "绝对红线",
                           _num(e.start_h), _num(e.end_h), _num(e.duration_minutes), _num(e.min_value), e.note])
    sections.append(("DO 报警事件（答复#7）", ["级别", "类型", "起始(h)", "结束(h)", "持续(分钟)", "最低DO(%)", "说明"], alarm_rows))

    metab_rows = []
    for r in res.get("metabolite_rows") or []:
        metab_rows.append([_num(r["t_h"]), _num(r["glucose_g_l"]), _num2(r["glucose_mmol_l"]),
                           LEVEL_ICON.get(r["glucose_level"], ""),
                           _num(r["lactate_g_l"]), _num2(r["lactate_mmol_l"]), LEVEL_ICON.get(r["lactate_level"], ""),
                           r["glucose_text"], r["lactate_text"]])
    sections.append(("代谢趋势与警戒线（答复#10）",
                     ["时刻(h)", "葡萄糖(g/L)", "葡萄糖(mmol/L)", "糖级别", "乳酸(g/L)", "乳酸(mmol/L)", "酸级别", "糖说明", "酸说明"],
                     metab_rows))

    seg_rows = []
    for s in res.get("mu_segments") or []:
        seg_rows.append([_num(s["t1_h"]), _num(s["t2_h"]), _num(s["x1"]), _num(s["x2"]),
                         _num4(s["mu_per_day"]), _num(s["doubling_time_hours"])])
    sections.append(("逐段比生长速率 μ（公式 6）", ["t1(h)", "t2(h)", "X1(×10⁶/mL)", "X2(×10⁶/mL)", "μ(1/天)", "倍增时间(h)"], seg_rows))

    fit = res.get("mu_fit") or {}
    fit_rows = []
    if fit:
        fit_rows = [
            ["是否完成回归", "是" if fit.get("ok") else "否"],
            ["对数期数据点数", _num(fit.get("n_points_used"))],
            ["回归窗口", str(fit.get("window_kind") or "—")],
            ["μ (1/小时)", _num4(fit.get("mu_per_hour"))],
            ["μ (1/天)", _num4(fit.get("mu_per_day"))],
            ["倍增时间 (小时)", _num(fit.get("doubling_time_hours"))],
            ["拟合 R²", _num4(fit.get("r_squared"))],
            ["说明 / 原因", str(fit.get("reason") or "")],
        ]
    sections.append(("对数期 μ 回归", ["项目", "结果"], fit_rows))

    ex = res.get("do_extrapolation") or {}
    ex_rows = []
    if ex:
        ex_rows = [
            ["DO 斜率 (%/h)", _num4(ex.get("slope_percent_per_hour"))],
            ["最近一点 DO (%)", _num(ex.get("last_value"))],
            ["预计跌破偏差阈值(分钟)", _num(ex.get("minutes_to_deviation"))],
            ["预计跌破绝对红线(分钟)", _num(ex.get("minutes_to_absolute_red"))],
            ["说明", str(ex.get("note") or "")],
        ]
    sections.append(("DO 消耗速率外推（仅提示）", ["项目", "结果"], ex_rows))

    har = res.get("harvest") or {}
    sections.append(("收获建议", ["级别", "说明"],
                     [[LEVEL_ICON.get(har.get("level"), ""), str(har.get("text") or "")]]))
    return sections


# ---------------------------------------------------------------- 分析报告导出
def report_disclaimer_lines(res: dict, cfg: Optional[dict] = None) -> List[List[str]]:
    """报告抬头信息行（标题/生成时间/数据来源/免责声明），导出 CSV 与界面横幅共用。"""
    cfg = cfg or get_config()
    lines: List[List[str]] = [["报告标题", str(cfg["analysis"].get("report_title") or "离线批次分析报告")]]
    lines.append(["生成时间", str(res.get("generated_at") or "")])
    if res.get("is_simulated"):
        lines.append(["数据来源", str(cfg["csv_import"]["simulator_output_marker"])
                      + " —— 模拟测试数据，不得用于真实批次决策，不得混入交付物"])
    else:
        lines.append(["数据来源", "用户导入的 my-Control 导出文件（离线分析，本软件不连接设备）"])
    lines.append(["免责声明", "本报告仅供规划参考，正式决策需人工复核；本软件不连接、不控制 my-Control 硬件。"])
    return lines


def export_report_csv(res: dict, path, cfg: Optional[dict] = None) -> Path:
    """把分析结果写成一份 CSV 报告（编码取 config.analysis.report_export.csv_encoding，默认 utf-8-sig）。"""
    cfg = cfg or get_config()
    enc = str(cfg["analysis"]["report_export"]["csv_encoding"])
    p = Path(path)
    if str(p.parent):
        p.parent.mkdir(parents=True, exist_ok=True)
    sections = report_sections(res, cfg)
    notes = []
    for key in ("warnings", "notes", "errors"):
        for text in res.get(key) or []:
            notes.append([{"warnings": "提示", "notes": "说明", "errors": "失败项"}[key], str(text)])
    if notes:
        sections = sections + [("数据质量提示", ["类型", "内容"], notes)]
    with open(p, "w", encoding=enc, newline="") as fh:
        w = csv.writer(fh)
        for line in report_disclaimer_lines(res, cfg):
            w.writerow(line)
        w.writerow([])
        for title, header, rows in sections:
            w.writerow([title])
            w.writerow(list(header))
            for r in rows:
                w.writerow(list(r))
            w.writerow([])
    return p


def _num2(x: Optional[float]) -> str:
    return "—" if x is None else "%.2f" % float(x)


def _num4(x: Optional[float]) -> str:
    return "—" if x is None else "%.4g" % float(x)


def fmt_metric(key: str, value, cfg: Optional[dict] = None) -> str:
    """摘要数值的中文显示（None → —）。"""
    if value is None:
        return "—"
    if key == "is_simulated":
        return "是（SIMULATED 模拟数据）" if value else "否（真实数据）"
    if isinstance(value, bool):
        return "是" if value else "否"
    if key in ("n_control_points", "n_offline_points", "n_do_alarms"):
        return str(int(value))
    return _num2(value)
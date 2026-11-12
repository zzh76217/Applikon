"""模拟 CSV 生成器（第五轮 · 模块 3 离线分析的测试夹具与界面试算功能）。

作用：在拿不到 my-Control 真实导出文件之前，生成两份"格式与真实导出一致"的 CSV，
让③离线分析页与④列名映射页可以被完整测试，也让零代码用户能立刻试算界面功能。

输出的每一行都带 SIMULATED 标记列，文件名以 SIMULATED 开头，解析器会识别并在界面挂红条；
这些数据是测试构造值（见 config.yaml 的 simulation 段），**不得用于真实批次决策，也不得混入交付物**。
"""
from __future__ import annotations

import argparse
import math
from datetime import datetime, timedelta
from pathlib import Path

from cell_planner.core import formulas
from cell_planner.core.config_loader import PROJECT_ROOT, get_config


def _sim(cfg: dict) -> dict:
    return cfg["simulation"]


def control_values(cfg: dict) -> dict:
    """控制数据每行的"设备读数"：气流量必须由第三节公式 3-5 算出，不手填数字。"""
    pd = cfg["process_defaults"]
    hw = cfg["hardware"]
    sim = _sim(cfg)
    v_work = float(cfg["ui_defaults"]["working_volume_ml"])
    vvm = float(pd["aeration_vvm"]["set"])
    q_air = formulas.air_flow_ml_min(vvm, v_work)
    q_o2 = formulas.o2_flow_ml_min(q_air, float(pd["o2_ratio_percent"]["set"]))
    q_co2 = formulas.co2_flow_ml_min(q_air, float(pd["co2_ratio_percent"]["set"]))
    do_set = float(pd["do_percent"]["set"])
    dev = float(cfg["do_alarm"]["deviation_yellow_points"])
    abs_red = float(cfg["do_alarm"]["absolute_red_percent"])
    return {
        "v_work_ml": v_work,
        "temperature_c": float(pd["temp_growth_c"]["set"]),
        "ph": float(pd["ph_setpoint"]["set"]),
        "do_base": do_set,
        "do_relative_level": do_set - dev - 5.0,     # 低于设定点 dev+5 个百分点：必定越过偏差阈值
        "do_absolute_level": max(abs_red - 5.0, 0.0),  # 跌破绝对红线
        "agitation_rpm": float(pd["agitation_rpm"]["set"]),
        "air_ml_min": q_air,
        "o2_ml_min": q_o2,
        "co2_ml_min": q_co2,
        "mfc_air_max": float(hw["mfc_max_ml_min"]["air"]),
        "mfc_co2_max": float(hw["mfc_max_ml_min"]["co2"]),
        "marker": str(sim["marker_value"]),
        "marker_column": str(sim["marker_column"]),
    }


def build_control_rows(cfg: dict, t0: datetime) -> list:
    """5 分钟一个点、共 days 天；在 config 指定的三个时刻构造 DO 跌落（报黄 / 报红 / 绝对红线）。"""
    sim, da = _sim(cfg), cfg["do_alarm"]
    val = control_values(cfg)
    step_h = float(sim["control_interval_minutes"]) / 60.0
    total_h = float(sim["days"]) * 24.0
    dips = [
        (float(sim["do_dip_yellow_start_hours"]), float(sim["do_dip_yellow_minutes"]), val["do_relative_level"]),
        (float(sim["do_dip_red_start_hours"]), float(sim["do_dip_red_minutes"]), val["do_relative_level"]),
        (float(sim["do_absolute_red_start_hours"]), float(sim["do_absolute_red_minutes"]), val["do_absolute_level"]),
    ]
    header = list(cfg["simulation"]["columns"]["control"])
    rows = []
    n = int(round(total_h / step_h)) + 1
    for i in range(n):
        t_h = i * step_h
        do = val["do_base"] + 0.5 * math.sin(t_h)          # 平稳期：在设定点附近 ±0.5 波动
        for start_h, minutes, level in dips:
            if start_h <= t_h <= start_h + minutes / 60.0:
                do = level
        if do > val["mfc_air_max"] or val["air_ml_min"] > val["mfc_air_max"]:
            raise ValueError("模拟参数与 MFC 量程冲突，请检查 config.hardware 与 config.ui_defaults")
        rows.append([
            (t0 + timedelta(hours=t_h)).strftime(cfg["csv_import"]["datetime_iso_format"]),
            "%.1f" % val["temperature_c"],
            "%.2f" % val["ph"],
            "%.1f" % do,
            "%.0f" % val["agitation_rpm"],
            "%.1f" % val["air_ml_min"],
            "%.1f" % val["o2_ml_min"],
            "%.1f" % val["co2_ml_min"],
            val["marker"],
        ])
    if len(header) != len(rows[0]):
        raise ValueError("config.simulation.columns.control 列数与生成行数不一致（应为 %d 列）" % len(rows[0]))
    return header, rows


def _density_at(t_h: float, x0: float, mu_per_day: float, peak: float, decline_h: float) -> float:
    """指数上升到峰值，之后线性下降（下降斜率固定为每小时损失峰值的 25% / 下降时长）。"""
    t_peak_h = math.log(peak / x0) / mu_per_day * 24.0
    if t_h <= t_peak_h:
        return min(peak, x0 * math.exp(mu_per_day * t_h / 24.0))
    frac = 0.0 if decline_h <= 0 else min(1.0, (t_h - t_peak_h) / decline_h)
    return max(0.0, peak * (1.0 - 0.25 * frac))


def build_offline_rows(cfg: dict, t0: datetime) -> list:
    """每 offline_interval_days 天取样一次：密度、活率、葡萄糖、乳酸（构造值来自 config.simulation）。"""
    sim = _sim(cfg)
    step_h = float(sim["offline_interval_days"]) * 24.0
    total_h = float(sim["days"]) * 24.0
    x0 = float(sim["initial_density_mcells_ml"])
    mu = float(sim["mu_max_per_day"])
    peak = float(sim["peak_density_mcells_ml"])
    decline_h = float(sim["decline_days_after_peak"]) * 24.0
    v0, v1 = float(sim["viability_start_percent"]), float(sim["viability_end_percent"])
    g0, g1 = float(sim["glucose_start_g_l"]), float(sim["glucose_end_g_l"])
    l0, l1 = float(sim["lactate_start_g_l"]), float(sim["lactate_end_g_l"])
    header = list(sim["columns"]["offline"])
    rows = []
    n = int(round(total_h / step_h)) + 1
    for i in range(n):
        t_h = i * step_h
        frac = 0.0 if total_h <= 0 else t_h / total_h
        rows.append([
            (t0 + timedelta(hours=t_h)).strftime(cfg["csv_import"]["datetime_iso_format"]),
            "%.2f" % _density_at(t_h, x0, mu, peak, decline_h),
            "%.1f" % (v0 + (v1 - v0) * frac),
            "%.2f" % (g0 + (g1 - g0) * frac),
            "%.2f" % (l0 + (l1 - l0) * frac),
            str(sim["marker_value"]),
        ])
    if len(header) != len(rows[0]):
        raise ValueError("config.simulation.columns.offline 列数与生成行数不一致（应为 %d 列）" % len(rows[0]))
    return header, rows


def write_csv(path: Path, header: list, rows: list, cfg: dict) -> Path:
    enc = str(cfg["csv_import"].get("encoding", "utf-8"))
    line_sep = "\r\n"
    with open(path, "w", encoding=enc, newline="") as fh:
        fh.write(",".join(str(h) for h in header) + line_sep)
        for r in rows:
            fh.write(",".join(str(c) for c in r) + line_sep)
    return path


def generate(out_dir=None, tag: str = "", cfg: dict = None) -> list:
    """生成两份模拟 CSV，返回文件路径列表。"""
    cfg = cfg or get_config()
    sim = _sim(cfg)
    stamp = str(tag).strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(out_dir) if out_dir else (PROJECT_ROOT / str(sim["out_dir"]))
    base.mkdir(parents=True, exist_ok=True)
    prefix = str(sim["filename_prefix"])
    t0 = datetime(2026, 1, 1, 0, 0, 0)          # 固定起点，保证每次生成结果一致（便于回归测试）
    files = []
    for kind, cn_name in (("control", "控制数据"), ("offline", "离线取样")):
        header, rows = (build_control_rows(cfg, t0) if kind == "control"
                        else build_offline_rows(cfg, t0))
        path = base / ("%s_%s_%s.csv" % (prefix, cn_name, stamp))
        files.append(write_csv(path, header, rows, cfg))
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成带 SIMULATED 标记的测试用 CSV（不是真实数据）")
    ap.add_argument("--out-dir", dest="out_dir", default=None, help="输出目录，默认取 config simulation.out_dir")
    ap.add_argument("--tag", dest="tag", default="", help="文件名后缀，默认用当前时间")
    args = ap.parse_args(argv)
    cfg = get_config()
    print("=" * 78)
    print("⚠️  本脚本输出的是【模拟数据 SIMULATED】：仅供软件测试与演示，")
    print("    严禁当成真实批次数据使用，严禁混入交付物！真实数据请从 my-Control Web UI 导出。")
    print("=" * 78)
    try:
        files = generate(args.out_dir, args.tag, cfg)
    except (ValueError, OSError) as exc:
        print("生成失败：" + str(exc))
        return 1
    val = control_values(cfg)
    print("控制数据：V_work=%s mL，Q_air=%s mL/min，Q_O2=%s mL/min，Q_CO2=%s mL/min（均由公式 3-5 计算）"
          % (val["v_work_ml"], round(val["air_ml_min"], 1), round(val["o2_ml_min"], 1),
             round(val["co2_ml_min"], 1)))
    for f in files:
        print("已生成 → %s（%d 行数据 + 1 行表头）" % (f, sum(1 for _ in open(f, encoding="utf-8")) - 1))
    print("下一步：打开软件③离线分析页，把这两个文件分别选为「控制数据」与「离线取样数据」即可。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
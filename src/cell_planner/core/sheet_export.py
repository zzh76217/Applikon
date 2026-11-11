# -*- coding: utf-8 -*-
"""开机配置单导出（第三轮）：把一次"计算并校验"的结果整理成表格行，一键导出 CSV。
CSV 用 config 里的 setup_sheet_export.csv_encoding（默认 utf-8-sig，Excel/WPS 双击打开不乱码）。
所有阈值与备注文字来自 config 与校验结果，本模块不新增工艺数值。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Optional

from cell_planner.core.config_loader import get_config
from cell_planner.core.validators import LEVEL_ERROR, LEVEL_PASS, LEVEL_WARN, RuleResult, SetupInputs

HEADER = ["分类", "项目", "数值", "单位", "依据/备注"]

_LEVEL_TEXT = {LEVEL_PASS: "通过", LEVEL_WARN: "警告", LEVEL_ERROR: "错误"}

DISCLAIMER = "本配置单由规划软件自动生成，仅供规划参考，正式上机前必须由操作人员人工复核。"


def _fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return ("%.2f" % x).rstrip("0").rstrip(".")


def build_sheet_rows(inp: SetupInputs, v_base_ml: float, v_af_ml: float,
                     cell_line: str, medium: str, results: List[RuleResult],
                     cfg: Optional[dict] = None) -> List[List[str]]:
    """生成配置单的表格行（含表头行）。行结构 = HEADER 的 5 列。"""
    cfg = cfg or get_config()
    ap = cfg["alkali_pump"]
    hw = cfg["hardware"]
    frac = cfg["sampling"]["max_cumulative_fraction_of_working"]
    rows: List[List[str]] = [list(HEADER)]

    rows.append(["基本信息", "细胞株", cell_line or "（未填写）", "", "界面输入"])
    rows.append(["基本信息", "培养基类型", medium or "（未填写）", "", "界面输入"])
    rows.append(["基本信息", "反应器型号", str(hw.get("reactor_model", "")), "", "config：hardware.reactor_model"])

    rows.append(["体积", "目标工作体积 V_work", _fmt(inp.v_work_ml), "mL", "界面输入"])
    rows.append(["体积", "接种体积 V_seed", _fmt(inp.v_seed_ml), "mL", "公式1：V_work×CD_inoc÷CD_seed"])
    rows.append(["体积", "碱液预留 V_base", _fmt(v_base_ml), "mL", "占工作体积比例（界面输入）"])
    rows.append(["体积", "消泡剂 V_antifoam", _fmt(v_af_ml), "mL", "占工作体积比例（界面输入）"])
    rows.append(["体积", "培养基补液 V_medium", _fmt(inp.v_medium_ml), "mL", "公式2：V_work−V_seed−V_base−V_antifoam"])

    rows.append(["通气", "通气强度 vvm", _fmt(inp.vvm), "vvm", "界面输入"])
    rows.append(["通气", "Air 流量 Q_air", _fmt(inp.q_air_ml_min), "mL/min", "公式3：vvm×V_work"])
    rows.append(["通气", "O2 流量 Q_O2", _fmt(inp.q_o2_ml_min), "mL/min", "公式4：Q_air×%s%%" % _fmt(inp.o2_ratio_percent)])
    rows.append(["通气", "CO2 流量 Q_CO2", _fmt(inp.q_co2_ml_min), "mL/min", "公式5：Q_air×%s%%" % _fmt(inp.co2_ratio_percent)])

    rows.append(["控制设定点", "搅拌初始转速", _fmt(inp.rpm), "rpm", "界面输入"])
    rows.append(["控制设定点", "生长阶段温度", _fmt(inp.temp_growth_c), "°C", "界面输入"])
    if inp.temp_expression_c is not None:
        rows.append(["控制设定点", "表达阶段温度", _fmt(inp.temp_expression_c), "°C", "界面输入（已启用降温）"])
    rows.append(["控制设定点", "pH 设定点", _fmt(inp.ph_setpoint), "", "界面输入"])
    rows.append(["控制设定点", "DO 设定点", _fmt(inp.do_percent), "%", "界面输入"])
    rows.append(["控制设定点", "培养周期", _fmt(inp.culture_days), "天", "界面输入"])

    rows.append(["密度", "种子液浓度 CD_seed", _fmt(inp.cd_seed_mcells_ml), "×10⁶ cells/mL", "界面输入"])
    rows.append(["密度", "目标接种密度 CD_inoc", _fmt(inp.cd_inoc_mcells_ml), "×10⁶ cells/mL", "界面输入"])

    rows.append(["取样", "计划累计取样体积", _fmt(inp.sampling_total_ml), "mL",
                 "R17 上限 = 工作体积×%s%%" % _fmt(frac * 100.0)])
    rows.append(["加液", "碱泵流量系数建议", _fmt(ap["max_rate_ml_per_min_per_L"]), "mL/(min·L)",
                 "config：alkali_pump；" + str(ap["note"])])

    n_err = sum(1 for r in results if r.level == LEVEL_ERROR)
    n_warn = sum(1 for r in results if r.level == LEVEL_WARN)
    rows.append(["校验汇总", "统计", "错误 %d 项 / 警告 %d 项 / 通过 %d 项" % (
        n_err, n_warn, len(results) - n_err - n_warn), "",
        "存在错误项时禁止按此配置上机" if n_err else "无错误项；警告项需人工确认"])
    for r in results:
        rows.append(["校验明细", "%s %s" % (r.rule_id, r.name), _LEVEL_TEXT[r.level], "", r.message])

    rows.append(["声明", "免责声明", DISCLAIMER, "", "AGENTS.md 硬约束 6"])
    return rows


def export_sheet_csv(path, rows: List[List[str]], cfg: Optional[dict] = None) -> Path:
    """把配置单行写入 CSV 文件（编码取 config，默认 utf-8-sig）。"""
    cfg = cfg or get_config()
    encoding = str(cfg["setup_sheet_export"].get("csv_encoding", "utf-8-sig"))
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding=encoding, newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)
    return p

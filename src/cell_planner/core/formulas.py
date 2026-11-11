# -*- coding: utf-8 -*-
"""
核心计算公式 —— 全部数值参数由调用方从 config 传入，本模块不写死工艺数值。
requirements.md 3.2 节（第二轮实现公式 1-5）：
  公式 1 接种体积：   V_seed   = V_work * CD_inoc / CD_seed
  公式 2 培养基体积： V_medium = V_work - V_seed - V_base - V_antifoam
  公式 3 通气量：     Q_air    = vvm * V_work            （mL/min）
  公式 4 O2 流量：    Q_O2     = Q_air * O2_ratio        （比例按百分数数值传入）
  公式 5 CO2 流量：   Q_CO2    = Q_air * CO2_ratio
开发提示词文档 §四(四) 补充公式（第四轮实现）：
  补充公式 A 总需细胞数：     N_total = V_work * CD_inoc            （单位：×10⁶ cells）
  补充公式 B 搅拌启动建议：   按工作体积分段给初始转速建议（分段表来自 config，仅建议，仍受 R05 校验）
  补充公式 C 表观剪切速率：   γ ≈ k * N，N = rpm / 60（转/秒），k 为无量纲叶轮常数（来自 config；k 为 null 时上层须防御式提示，不得崩溃）
不在本模块的公式：公式 6 μ 与公式 8 PEC（第五轮分析模块）、公式 7 ε（由校验器 R06 处理）。
单位约定：体积 mL、流量 mL/min、浓度统一 x10^6 cells/mL、比例传百分数数值（10 即 10%）。
非法输入一律抛中文 ValueError，由界面层捕获提示，严禁静默返回错误数字。
"""
from __future__ import annotations

import math

_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def inoculum_volume_ml(v_work_ml: float, cd_inoc_mcells_ml: float, cd_seed_mcells_ml: float) -> float:
    """公式 1：接种体积 V_seed = V_work * CD_inoc / CD_seed（mL）。"""
    if v_work_ml <= 0:
        raise ValueError("目标工作体积必须大于 0 mL")
    if cd_inoc_mcells_ml <= 0:
        raise ValueError("目标接种密度必须大于 0（x10^6 cells/mL）")
    if cd_seed_mcells_ml <= 0:
        raise ValueError("种子液浓度必须大于 0（x10^6 cells/mL）")
    return v_work_ml * cd_inoc_mcells_ml / cd_seed_mcells_ml


def medium_volume_ml(v_work_ml: float, v_seed_ml: float, v_base_ml: float, v_antifoam_ml: float) -> float:
    """公式 2：培养基体积 V_medium = V_work - V_seed - V_base - V_antifoam（mL，可为负，由 R08 报错）。"""
    for name, val in (
        ("目标工作体积", v_work_ml),
        ("接种体积", v_seed_ml),
        ("碱液预留体积", v_base_ml),
        ("消泡剂预留体积", v_antifoam_ml),
    ):
        if val < 0:
            raise ValueError(name + "不能为负数：" + str(val))
    return v_work_ml - v_seed_ml - v_base_ml - v_antifoam_ml


def air_flow_ml_min(vvm: float, v_work_ml: float) -> float:
    """公式 3：Air 流量 Q_air = vvm * V_work（mL/min）。"""
    if vvm <= 0:
        raise ValueError("通气量 vvm 必须大于 0")
    if v_work_ml <= 0:
        raise ValueError("目标工作体积必须大于 0 mL")
    return vvm * v_work_ml


def o2_flow_ml_min(q_air_ml_min: float, o2_ratio_percent: float) -> float:
    """公式 4：O2 流量 = Q_air * O2 补充比例（mL/min）。"""
    return _flow_from_ratio(q_air_ml_min, o2_ratio_percent, "O2 补充比例")


def co2_flow_ml_min(q_air_ml_min: float, co2_ratio_percent: float) -> float:
    """公式 5：CO2 流量 = Q_air * CO2 配比（mL/min）。"""
    return _flow_from_ratio(q_air_ml_min, co2_ratio_percent, "CO2 配比")


def _flow_from_ratio(q_air_ml_min: float, ratio_percent: float, name: str) -> float:
    if q_air_ml_min < 0:
        raise ValueError("Air 流量不能为负数")
    if ratio_percent < 0:
        raise ValueError(name + "不能为负数")
    return q_air_ml_min * ratio_percent / 100.0


def total_cells_millions(v_work_ml: float, cd_inoc_mcells_ml: float) -> float:
    """补充公式 A：总需细胞数 N_total = V_work * CD_inoc，返回单位固定为 ×10⁶ cells。
    （例：2000 mL × 0.4 ×10⁶ cells/mL = 800 ×10⁶ cells，即 8.0×10⁸ 个细胞。
    提示词文档算例把结果误写成 8.0 × 10⁶ cells，按物理正确的单位换算实现，见 README 第四轮决策。）"""
    if v_work_ml <= 0:
        raise ValueError("目标工作体积必须大于 0 mL")
    if cd_inoc_mcells_ml <= 0:
        raise ValueError("目标接种密度必须大于 0（x10^6 cells/mL）")
    return v_work_ml * cd_inoc_mcells_ml


def scientific_cn(value: float, digits: int = 1) -> str:
    """把大数格式化成中文上标科学计数法，如 8.0×10⁸；仅用于展示，不参与计算。"""
    if value == 0:
        return "0"
    exp = math.floor(math.log10(abs(value)))
    mantissa = value / (10.0 ** exp)
    return ("%." + str(digits) + "f") % mantissa + "×10" + str(exp).translate(_SUPERSCRIPT)


def agitation_start_rpm_suggestion(v_work_ml: float, bands: list) -> float:
    """补充公式 B：按工作体积分段返回搅拌启动建议转速（rpm）。
    bands 来自 config 的 agitation_start_suggestion.bands_ml，自上而下匹配第一个
    满足 v_work_ml <= max_ml 的段；max_ml 为 null 表示"以上"兜底段。"""
    if v_work_ml <= 0:
        raise ValueError("目标工作体积必须大于 0 mL")
    if not bands:
        raise ValueError("配置缺少 agitation_start_suggestion.bands_ml 分段表，请在硬件配置或 config.yaml 补充")
    for band in bands:
        max_ml = band.get("max_ml")
        if max_ml is None or v_work_ml <= float(max_ml):
            return float(band["rpm"])
    raise ValueError("搅拌建议分段表未覆盖工作体积 " + str(v_work_ml) + " mL，请在 config 补充兜底段（max_ml: null）")


def shear_gamma_per_s(rpm: float, impeller_constant_k) -> float:
    """补充公式 C：表观剪切速率估算 γ ≈ k * N，N = rpm / 60（转/秒），γ 单位 1/s。
    k 为无量纲叶轮常数，只能来自 config（mixing_physics.impeller_constant_k）。
    k 为 null 时抛中文 ValueError —— 上层界面须按"黄色提示、不崩溃"处理（同叶轮直径 D 缺参数模式）。
    注意：γ 为经验估算，仅用于相对比较，不是实测剪切力。"""
    if impeller_constant_k is None:
        raise ValueError("缺少叶轮常数 k，无法估算剪切速率 γ，请在 config.yaml 的 mixing_physics.impeller_constant_k 补充后自动生效")
    if impeller_constant_k <= 0:
        raise ValueError("叶轮常数 k 必须大于 0，当前值：" + str(impeller_constant_k))
    if rpm < 0:
        raise ValueError("搅拌转速不能为负数，当前值：" + str(rpm))
    return impeller_constant_k * rpm / 60.0

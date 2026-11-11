# -*- coding: utf-8 -*-
"""
requirements.md 第 3.2 节核心计算公式 —— 第二轮实现公式 1-5：
  公式 1 接种体积：   V_seed   = V_work * CD_inoc / CD_seed
  公式 2 培养基体积： V_medium = V_work - V_seed - V_base - V_antifoam
  公式 3 通气量：     Q_air    = vvm * V_work            （mL/min）
  公式 4 O2 流量：    Q_O2     = Q_air * O2_ratio        （比例按百分数数值传入）
  公式 5 CO2 流量：   Q_CO2    = Q_air * CO2_ratio
不在本模块的公式：公式 6 μ（第四轮）、公式 7 ε（由校验器 R06 处理）、公式 8 γ（暂缓）。
单位约定：体积 mL、流量 mL/min、浓度统一 x10^6 cells/mL、比例传百分数数值（10 即 10%）。
"""
from __future__ import annotations


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

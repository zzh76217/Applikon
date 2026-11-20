# -*- coding: utf-8 -*-
"""
requirements.md 第五节校验规则 —— 第三轮起全部 18 条（R01-R18）落地。
所有阈值来自 config/config.yaml（get_config），本文件不写死任何工艺数值。
R06 特殊处理（用户 2026-11-11 定案）：叶轮直径 D 为 null 时不计算 ε，
第四轮补强：D 已填但工作体积 ≤ 0 或直径 ≤ 0 时，返回红/黄并说明原因，严禁除零崩溃。
封版轮（2026-11-20）：R05 改三档（<下限红、下限~谨慎区边界黄、边界~上限绿），并在小体积段并列显示
R06 红线反解出的"转速事实上限"；R06 在推荐区上限~黄线之间的文案更正为"高于推荐区上限但未达黄线"。
R15 合并答复#5 的三类密度检查：CD_seed>CD_inoc、CD_seed 上限报红、反应器起始密度合理区间报黄。
输出黄色警告"叶轮直径参数缺失，无法计算剪切力，请后续在配置中补充"，严禁报错崩溃。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from cell_planner.core.config_loader import get_config

LEVEL_PASS = "pass"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"

LEVEL_ICON = {LEVEL_PASS: "✅ 通过", LEVEL_WARN: "🟡 警告", LEVEL_ERROR: "🔴 错误"}

MISSING_D_MSG = "⚠️ 缺少叶轮直径参数，无法计算剪切力，请后续在配置中补充（可查设备铭牌）"


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    name: str
    level: str
    message: str

    @property
    def display(self) -> str:
        return LEVEL_ICON[self.level]


@dataclass(frozen=True)
class SetupInputs:
    """一次"计算并校验"所需的全部数值（由界面层收集后传入）。"""

    v_work_ml: float
    v_seed_ml: float
    v_medium_ml: float
    q_air_ml_min: float
    q_o2_ml_min: float
    q_co2_ml_min: float
    rpm: float
    temp_growth_c: float
    temp_expression_c: Optional[float]
    ph_setpoint: float
    do_percent: float
    o2_ratio_percent: float
    co2_ratio_percent: float
    cd_inoc_mcells_ml: float
    cd_seed_mcells_ml: float
    vvm: float
    culture_days: float
    sampling_total_ml: float


def _n(x: float) -> str:
    """提示文本用的紧凑数字格式（整数不带小数点）。"""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return ("%.2f" % x).rstrip("0").rstrip(".")


def _eps_n(x: float) -> str:
    """ε 专用数字格式：小于 0.01 W/kg 时保留三位小数，避免界面上出现"ε ≈ 0 W/kg"这种误导写法。"""
    if 0 < abs(x) < 0.01:
        return ("%.3f" % x).rstrip("0").rstrip(".")
    return _n(x)


def run_validation(inp: SetupInputs, cfg: Optional[dict] = None) -> List[RuleResult]:
    """按 R01→R18 顺序逐条校验，返回结果列表。"""
    cfg = cfg or get_config()
    return [fn(inp, cfg) for fn in (
        rule_r01, rule_r02, rule_r03, rule_r04, rule_r05, rule_r06,
        rule_r07, rule_r08, rule_r09, rule_r10, rule_r11, rule_r12, rule_r13,
        rule_r14, rule_r15, rule_r16, rule_r17, rule_r18,
    )]


def rule_r01(inp: SetupInputs, cfg: dict) -> RuleResult:
    hw = cfg["hardware"]
    lo, hi = hw["min_working_volume_ml"], hw["max_working_volume_ml"]
    v = inp.v_work_ml
    if lo <= v <= hi:
        return RuleResult("R01", "工作体积范围", LEVEL_PASS,
                          "工作体积 %s mL，位于 %s–%s mL 允许范围内。" % (_n(v), _n(lo), _n(hi)))
    return RuleResult("R01", "工作体积范围", LEVEL_ERROR,
                      "工作体积 %s mL 超出 %s–%s mL（my-Control 3L 硬件限制），请修正后重新计算。" % (_n(v), _n(lo), _n(hi)))


def _rule_mfc(rule_id, name, label, q, limit, level_on_fail):
    if q <= limit:
        return RuleResult(rule_id, name, LEVEL_PASS,
                          "%s %s mL/min，未超过 MFC 量程 %s mL/min。" % (label, _n(q), _n(limit)))
    return RuleResult(rule_id, name, level_on_fail,
                      "%s %s mL/min 超过 MFC 量程上限 %s mL/min，硬件无法执行，请降低通气量或比例。" % (label, _n(q), _n(limit)))


def rule_r02(inp: SetupInputs, cfg: dict) -> RuleResult:
    return _rule_mfc("R02", "Air 流量不超量程", "Air 流量", inp.q_air_ml_min,
                     cfg["hardware"]["mfc_max_ml_min"]["air"], LEVEL_ERROR)


def rule_r03(inp: SetupInputs, cfg: dict) -> RuleResult:
    return _rule_mfc("R03", "O2 流量不超量程", "O2 流量", inp.q_o2_ml_min,
                     cfg["hardware"]["mfc_max_ml_min"]["o2"], LEVEL_ERROR)


def rule_r04(inp: SetupInputs, cfg: dict) -> RuleResult:
    return _rule_mfc("R04", "CO2 流量不超量程", "CO2 流量", inp.q_co2_ml_min,
                     cfg["hardware"]["mfc_max_ml_min"]["co2"], LEVEL_ERROR)


def _rpm_at_epsilon(inp: SetupInputs, cfg: dict, eps_target: float):
    """R06 公式的解析逆：反算"比功率达到 eps_target 时对应的搅拌转速"（rpm）。

    ε = Np·N³·D⁵ ÷ V（ρ 在 P 与 ε 中相消），N = rpm×2π÷60
    → rpm = 60÷(2π) × (ε×V ÷ (Np×D⁵))^(1/3)。
    参数缺失或不合理（D=null、D≤0、V≤0）时返回 None，由调用方省略提示，严禁抛异常。
    """
    mp = cfg["mixing_physics"]
    d = mp.get("impeller_diameter_m")
    np_ = mp.get("power_number_np")
    if not d or not np_ or d <= 0 or np_ <= 0 or inp.v_work_ml <= 0:
        return None
    v_m3 = inp.v_work_ml / 1000000.0
    cube = eps_target * v_m3 / (np_ * (d ** 5))
    if cube <= 0:
        return None
    return (60.0 / (2.0 * math.pi)) * (cube ** (1.0 / 3.0))


def _r05_fact_cap_hint(inp: SetupInputs, cfg: dict) -> str:
    """封版轮拍板#3：工作体积落在 config 指定区间（出厂 600–1000 mL）时，
    R05 提示里并列显示该体积下 ε 红线的反解转速（=该段"事实上限"），
    消除"R05 要求够快 / R06 要求够慢"把用户两头卡死的问题。区间与阈值全部取自 config。"""
    rng = cfg["process_defaults"]["agitation_rpm"]
    band = rng.get("fact_cap_volume_ml")
    if not band or len(band) != 2:
        return ""
    v_lo, v_hi = band
    if not (v_lo <= inp.v_work_ml <= v_hi):
        return ""
    red = cfg["mixing_physics"]["epsilon_red_w_kg"]
    cap = _rpm_at_epsilon(inp, cfg, red)
    if cap is None:
        return ""
    cap_shown = math.floor(cap * 10.0 + 1e-9) / 10.0   # 向下取整到 0.1 rpm：提示里的上限值本身必须不越红线
    return ("本体积段（%s–%s mL）受 R06 剪切红线 ε = %s W/kg 限制，转速事实上限约 %s rpm，"
            "请把转速控制在 %s–%s rpm 之间；此段以 R06 的实际判定为准，R05 与 R06 不再互相卡。"
            % (_n(v_lo), _n(v_hi), _n(red), _n(cap_shown), _n(rng["min"]), _n(cap_shown)))


def rule_r05(inp: SetupInputs, cfg: dict) -> RuleResult:
    """封版轮拍板#3 改的三档：低于下限 = 🔴 拦截；下限到谨慎边界之间 = 🟡 黄（注意沉降与混合不足）；
    谨慎边界到上限 = 🟢 通过；超过上限维持原来的 🟡 黄（需人工确认）。"""
    rng = cfg["process_defaults"]["agitation_rpm"]
    lo, hi = rng["min"], rng["max"]
    caution = rng.get("caution_below_rpm", lo)
    hint = _r05_fact_cap_hint(inp, cfg)
    if inp.rpm < lo:
        return RuleResult("R05", "搅拌转速范围", LEVEL_ERROR,
                          "转速 %s rpm 低于允许下限 %s rpm，混合不足与细胞沉降风险高，禁止使用该配置，请提高转速。%s"
                          % (_n(inp.rpm), _n(lo), hint))
    if inp.rpm > hi:
        return RuleResult("R05", "搅拌转速范围", LEVEL_WARN,
                          "转速 %s rpm 超出 %s–%s rpm（CHO 剪切敏感），可继续但需人工确认。%s"
                          % (_n(inp.rpm), _n(lo), _n(hi), hint))
    if inp.rpm < caution:
        return RuleResult("R05", "搅拌转速范围", LEVEL_WARN,
                          "转速 %s rpm 处于 %s–%s rpm 谨慎区，小体积注意沉降与混合不足，请人工确认罐内混合是否均匀。%s"
                          % (_n(inp.rpm), _n(lo), _n(caution), hint))
    return RuleResult("R05", "搅拌转速范围", LEVEL_PASS,
                      "转速 %s rpm，位于 %s–%s rpm 推荐范围。%s"
                      % (_n(inp.rpm), _n(caution), _n(hi), hint))


def rule_r06(inp: SetupInputs, cfg: dict) -> RuleResult:
    mp = cfg["mixing_physics"]
    d = mp.get("impeller_diameter_m")
    if d is None:
        return RuleResult("R06", "能量耗散率（剪切安全）", LEVEL_WARN, MISSING_D_MSG)
    if inp.v_work_ml <= 0:
        return RuleResult("R06", "能量耗散率（剪切安全）", LEVEL_ERROR,
                          "工作体积必须大于 0 mL，无法计算能量耗散率 ε，请先修正 R01 的工作体积输入。")
    if d <= 0:
        return RuleResult("R06", "能量耗散率（剪切安全）", LEVEL_WARN,
                          "叶轮直径配置值 " + str(d) + " m 不合理（应大于 0），无法计算 ε，请在硬件配置页或 config.yaml 修正。")
    rho = mp["broth_density_kg_m3"]
    np_ = mp["power_number_np"]
    red = mp["epsilon_red_w_kg"]
    yellow = mp["epsilon_yellow_w_kg"]
    rec_lo, rec_hi = mp["epsilon_recommended_w_kg"]
    n_rad_s = inp.rpm * 2.0 * math.pi / 60.0
    v_m3 = inp.v_work_ml / 1000000.0
    power_w = np_ * rho * (n_rad_s ** 3) * (d ** 5)
    eps = power_w / (rho * v_m3)
    txt = "比功率 ε ≈ %s W/kg（红线 %s、黄线 %s、推荐区 %s–%s W/kg）。" % (
        _eps_n(eps), _n(red), _n(yellow), _n(rec_lo), _n(rec_hi))
    if eps > red:
        return RuleResult("R06", "能量耗散率（剪切安全）", LEVEL_ERROR, "超过红线，禁止使用该配置！" + txt)
    if eps > yellow:
        return RuleResult("R06", "能量耗散率（剪切安全）", LEVEL_WARN, "接近剪切红线，建议降速并人工复核。" + txt)
    # 封版轮拍板#4：0.04 < ε ≤ 0.05 这一段原文案写成"低于推荐区"是反话，已更正为"高于推荐区上限但未达黄线"
    if rec_lo <= eps <= rec_hi:
        note = "处于推荐区。"
    elif eps > rec_hi:
        note = "高于推荐区上限但未达黄线，建议按低速复核。"
    else:
        note = "低于推荐区，剪切安全但混合可能偏弱。"
    return RuleResult("R06", "能量耗散率（剪切安全）", LEVEL_PASS, note + txt)


def rule_r07(inp: SetupInputs, cfg: dict) -> RuleResult:
    if 0 < inp.v_seed_ml < inp.v_work_ml:
        return RuleResult("R07", "接种体积合理性", LEVEL_PASS,
                          "接种体积 %s mL，大于 0 且小于工作体积 %s mL。" % (_n(inp.v_seed_ml), _n(inp.v_work_ml)))
    return RuleResult("R07", "接种体积合理性", LEVEL_ERROR,
                      "接种体积 %s mL 必须大于 0 且小于工作体积 %s mL，请检查种子液浓度与目标接种密度。" % (_n(inp.v_seed_ml), _n(inp.v_work_ml)))


def rule_r08(inp: SetupInputs, cfg: dict) -> RuleResult:
    if inp.v_medium_ml > 0:
        return RuleResult("R08", "培养基体积合理性", LEVEL_PASS,
                          "培养基补液体积 %s mL，大于 0。" % _n(inp.v_medium_ml))
    return RuleResult("R08", "培养基体积合理性", LEVEL_ERROR,
                      "培养基补液体积 %s mL 不为正数，说明接种体积+碱液+消泡剂已挤占全部工作体积，请缩小各项预留比例。" % _n(inp.v_medium_ml))


def _rule_range(rule_id, name, label, value, rng, unit, digits=1):
    lo, hi = rng["min"], rng["max"]
    fmt = "%" + ("." + str(digits) + "f" if digits else "s")
    if lo <= value <= hi:
        return RuleResult(rule_id, name, LEVEL_PASS,
                          ("%s设定点 " + fmt + " %s，位于 %s–%s 推荐范围。") % (label, value, unit, _n(lo), _n(hi)))
    return RuleResult(rule_id, name, LEVEL_WARN,
                      ("%s设定点 " + fmt + " %s 超出 %s–%s，可继续但需人工确认。") % (label, value, unit, _n(lo), _n(hi)))


def rule_r09(inp: SetupInputs, cfg: dict) -> RuleResult:
    return _rule_range("R09", "DO 设定点范围", "DO", inp.do_percent,
                       cfg["process_defaults"]["do_percent"], "%")


def rule_r10(inp: SetupInputs, cfg: dict) -> RuleResult:
    return _rule_range("R10", "pH 设定点范围", "pH", inp.ph_setpoint,
                       cfg["process_defaults"]["ph_setpoint"], "", digits=2)


def rule_r11(inp: SetupInputs, cfg: dict) -> RuleResult:
    tg = cfg["process_defaults"]["temp_growth_c"]
    te = cfg["process_defaults"]["temp_expression_c"]
    lo, hi = min(tg["min"], te["min"]), max(tg["max"], te["max"])
    temps = [("生长阶段", inp.temp_growth_c)]
    if inp.temp_expression_c is not None:
        temps.append(("表达阶段", inp.temp_expression_c))
    bad = [(stage, v) for stage, v in temps if v < lo or v > hi]
    if not bad:
        shown = "、".join("%s %s °C" % (s, _n(v)) for s, v in temps)
        return RuleResult("R11", "温度设定点范围", LEVEL_PASS,
                          "%s，位于 %s–%s °C 允许范围。" % (shown, _n(lo), _n(hi)))
    shown = "、".join("%s %s °C" % (s, _n(v)) for s, v in bad)
    return RuleResult("R11", "温度设定点范围", LEVEL_WARN,
                      "%s 超出 %s–%s °C，可继续但需人工确认。" % (shown, _n(lo), _n(hi)))


def rule_r12(inp: SetupInputs, cfg: dict) -> RuleResult:
    hi = cfg["process_defaults"]["o2_ratio_percent"]["max"]
    if inp.o2_ratio_percent <= hi:
        return RuleResult("R12", "O2 补充比例上限", LEVEL_PASS,
                          "O2 补充比例 %s%%，不超过上限 %s%%。" % (_n(inp.o2_ratio_percent), _n(hi)))
    return RuleResult("R12", "O2 补充比例上限", LEVEL_WARN,
                      "O2 补充比例 %s%% 超过上限 %s%%，需人工确认气体安全后再继续。" % (_n(inp.o2_ratio_percent), _n(hi)))


def rule_r13(inp: SetupInputs, cfg: dict) -> RuleResult:
    hi = cfg["process_defaults"]["co2_ratio_percent"]["max"]
    if inp.co2_ratio_percent <= hi:
        return RuleResult("R13", "CO2 配比上限", LEVEL_PASS,
                          "CO2 配比 %s%%，不超过上限 %s%%。" % (_n(inp.co2_ratio_percent), _n(hi)))
    return RuleResult("R13", "CO2 配比上限", LEVEL_WARN,
                      "CO2 配比 %s%% 超过上限 %s%%，pH 控制与安全性需人工确认。" % (_n(inp.co2_ratio_percent), _n(hi)))


def rule_r14(inp: SetupInputs, cfg: dict) -> RuleResult:
    """R14：通气量对应 vvm 在推荐范围（0.05-0.1，取自 config）。"""
    rng = cfg["process_defaults"]["aeration_vvm"]
    lo, hi = rng["min"], rng["max"]
    v = inp.vvm
    if lo <= v <= hi:
        return RuleResult("R14", "通气量 vvm 推荐区间", LEVEL_PASS,
                          "vvm = %s，位于推荐区间 %s–%s。" % (_n(v), _n(lo), _n(hi)))
    return RuleResult("R14", "通气量 vvm 推荐区间", LEVEL_WARN,
                      "vvm = %s 超出推荐区间 %s–%s，可能供氧不足或起泡/剪切风险增加，需人工确认。" % (_n(v), _n(lo), _n(hi)))


def rule_r15(inp: SetupInputs, cfg: dict) -> RuleResult:
    """R15：种子液浓度必须大于目标接种密度（否则无法稀释接种，🔴）；
    并合并答复#5：CD_seed 超上限报红、反应器起始密度超出合理区间报黄。"""
    di = cfg["density_input"]
    cd_seed = inp.cd_seed_mcells_ml
    cd_inoc = inp.cd_inoc_mcells_ml
    seed_red = di["seed_conc_red_max_mcells_ml"]
    y_lo, y_hi = di["reactor_initial_density_yellow_range_mcells_ml"]
    # hard_max（界面输入上限 20）由配置页自旋框封顶实现（答复#5），R15 内不再判（先被 CD_seed 红线拦截，属不可达分支）
    if cd_seed <= cd_inoc:
        return RuleResult("R15", "种子/接种密度合理性", LEVEL_ERROR,
                          "种子液浓度 %s 不高于目标接种密度 %s（×10⁶ cells/mL），无法稀释接种，请核对细胞计数结果。" % (_n(cd_seed), _n(cd_inoc)))
    if cd_seed > seed_red:
        return RuleResult("R15", "种子/接种密度合理性", LEVEL_ERROR,
                          "种子液浓度 %s ×10⁶ cells/mL 超过典型上限 %s（摇瓶/种子罐收获浓度通常 1–5），疑似计数错误，禁止按此配置上机。" % (_n(cd_seed), _n(seed_red)))
    inoc = cfg["process_defaults"]["inoculum_density_mcells_ml"]
    if inoc["min"] <= cd_inoc <= inoc["max"]:
        return RuleResult("R15", "种子/接种密度合理性", LEVEL_PASS,
                          "种子液浓度 %s > 目标接种密度 %s（×10⁶ cells/mL），接种密度处于工艺推荐范围 %s–%s。" % (_n(cd_seed), _n(cd_inoc), _n(inoc["min"]), _n(inoc["max"])))
    if cd_inoc < y_lo or cd_inoc > y_hi:
        return RuleResult("R15", "种子/接种密度合理性", LEVEL_WARN,
                          "反应器起始密度 %s ×10⁶ cells/mL 超出常见合理区间 %s–%s，可继续但需人工确认。" % (_n(cd_inoc), _n(y_lo), _n(y_hi)))
    return RuleResult("R15", "种子/接种密度合理性", LEVEL_PASS,
                      "种子液浓度 %s > 目标接种密度 %s（×10⁶ cells/mL），且均在合理区间内。" % (_n(cd_seed), _n(cd_inoc)))


def rule_r16(inp: SetupInputs, cfg: dict) -> RuleResult:
    """R16：曝气方式必须为烧结曝气头 —— 界面强制提示（🟡），禁止选 L 型管直吹。"""
    sp = str(cfg["hardware"].get("sparger_required") or "")
    if sp != "sintered":
        return RuleResult("R16", "曝气方式强制提示", LEVEL_ERROR,
                          "配置中 sparger_required 不是 sintered，与 my-Control 3L 手册（多孔陶瓷/金属烧结曝气头，约 15 μm）不符，请修正硬件配置。")
    return RuleResult("R16", "曝气方式强制提示", LEVEL_WARN,
                      "强制提示：曝气必须使用烧结曝气头（约 15 μm），严禁 L 型管直吹！上机前请人工核对实际安装的曝气头类型。")


def rule_r17(inp: SetupInputs, cfg: dict) -> RuleResult:
    """R17：计划累计取样体积不超过工作体积的规定百分比。"""
    frac = cfg["sampling"]["max_cumulative_fraction_of_working"]
    limit = frac * inp.v_work_ml
    v = inp.sampling_total_ml
    if v <= limit + 1e-9:
        return RuleResult("R17", "累计取样体积上限", LEVEL_PASS,
                          "计划累计取样 %s mL，不超过工作体积的 %s%%（上限 %s mL）。" % (_n(v), _n(frac * 100.0), _n(limit)))
    return RuleResult("R17", "累计取样体积上限", LEVEL_WARN,
                      "计划累计取样 %s mL 超过工作体积的 %s%%（上限 %s mL），可能明显损耗培养体系，需人工确认取样计划。" % (_n(v), _n(frac * 100.0), _n(limit)))


def rule_r18(inp: SetupInputs, cfg: dict) -> RuleResult:
    """R18：培养周期在推荐范围内（7–14 天，取自 config）。"""
    rng = cfg["process_defaults"]["culture_days"]
    lo, hi = rng["min"], rng["max"]
    d = inp.culture_days
    if lo <= d <= hi:
        return RuleResult("R18", "培养周期范围", LEVEL_PASS,
                          "培养周期 %s 天，位于 %s–%s 天推荐范围。" % (_n(d), _n(lo), _n(hi)))
    return RuleResult("R18", "培养周期范围", LEVEL_WARN,
                      "培养周期 %s 天超出 %s–%s 天推荐范围，营养/污染风险增加，需人工确认。" % (_n(d), _n(lo), _n(hi)))

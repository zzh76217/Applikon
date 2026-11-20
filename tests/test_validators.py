# -*- coding: utf-8 -*-
"""校验规则 R01-R18 单元测试（第三轮起覆盖 requirements.md 第五节全部 18 条）。
边界值全部从 config/config.yaml 推导，测试代码不写死工艺数值；
期望的 级别（通过/警告/错误）取自 requirements.md 第五节规则表的"级别"列。
第四轮追加：R06 非法体积/非法直径防护与"极端输入 18 条全跑不崩溃"测试。
第八轮（2026-11-20）：用户查定叶轮直径 D = 0.052 m 写入 config，R06 从"缺参数固定黄"
变成真实 ε 判定；"D 为 null 走黄色防御分支"改为显式注入 null 复现，防御路径不得失守。
封版轮（2026-11-20 续）：R05 下限 80→60 并改三档（红拦/黄提示/绿通过），小体积段在 R05 里
并列显示 R06 红线反解出的转速事实上限；补充公式 B 分档 80/100/120→60/70/80；
R06 在推荐区上限~黄线之间的文案更正为「高于推荐区上限但未达黄线」。"""
import copy
import math

import pytest

from cell_planner.core import validators
from cell_planner.core.config_loader import get_config

CFG = get_config()


def make_inputs(**overrides):
    """构造一组基于 requirements 3.3 算例的基准输入（除 R06 因 ε≈0.076 W/kg 超黄线必为黄色外
    其余全绿；叶轮直径 D=0.052 m 已于第八轮填入 config），再按用例覆盖个别字段。"""
    pd = CFG["process_defaults"]
    base = dict(
        v_work_ml=2000.0,
        v_seed_ml=266.6666667,
        v_medium_ml=1691.3333,
        q_air_ml_min=200.0,
        q_o2_ml_min=20.0,
        q_co2_ml_min=20.0,
        rpm=pd["agitation_rpm"]["set"],
        temp_growth_c=pd["temp_growth_c"]["set"],
        temp_expression_c=None,
        ph_setpoint=pd["ph_setpoint"]["set"],
        do_percent=pd["do_percent"]["set"],
        o2_ratio_percent=pd["o2_ratio_percent"]["set"],
        co2_ratio_percent=pd["co2_ratio_percent"]["set"],
        cd_inoc_mcells_ml=pd["inoculum_density_mcells_ml"]["set"],
        cd_seed_mcells_ml=3.0,
        vvm=pd["aeration_vvm"]["set"],
        culture_days=pd["culture_days"]["set"],
        sampling_total_ml=float(CFG["ui_defaults"]["sampling_total_ml"]),
    )
    base.update(overrides)
    return validators.SetupInputs(**base)


def run_one(rule_id, inp):
    results = {r.rule_id: r for r in validators.run_validation(inp, CFG)}
    return results[rule_id]


class TestScope:
    """第三轮范围控制：恰好实现 R01-R18 全部 18 条，不缺不多。"""

    def test_exact_rule_ids_r01_to_r18(self):
        ids = [r.rule_id for r in validators.run_validation(make_inputs(), CFG)]
        assert ids == ["R%02d" % i for i in range(1, 19)]

    def test_baseline_expected_warnings_are_r06_and_r16(self):
        res = validators.run_validation(make_inputs(), CFG)
        warn_ids = sorted(r.rule_id for r in res if r.level == validators.LEVEL_WARN)
        assert warn_ids == ["R06", "R16"]   # R06=ε 超黄线（第八轮起为实算）、R16=曝气方式强制提示，均属预期
        assert sum(1 for r in res if r.level == validators.LEVEL_ERROR) == 0

    def test_baseline_no_error(self):
        res = validators.run_validation(make_inputs(), CFG)
        assert all(r.level != validators.LEVEL_ERROR for r in res)

    def test_all_messages_are_chinese(self):
        for r in validators.run_validation(make_inputs(), CFG):
            assert any("\u4e00" <= ch <= "\u9fff" for ch in r.message), r.rule_id


class TestR06MissingDiameter:
    """第一轮答复#3 定下的防御分支：D 为 null → 黄色警告并说明原因，不得崩溃。

    第八轮出厂 config 已填入 D=0.052 m，所以这里必须显式注入 null 来复现该分支，
    而不是依赖出厂值 —— 防御路径以后仍然不许失守。"""

    def test_warns_when_diameter_null(self):
        cfg = copy.deepcopy(CFG)
        cfg["mixing_physics"]["impeller_diameter_m"] = None
        results = {x.rule_id: x for x in validators.run_validation(make_inputs(), cfg)}
        r = results["R06"]
        assert r.level == validators.LEVEL_WARN
        assert "叶轮直径" in r.message
        assert "W/kg" not in r.message   # 缺 D 时不应给出 ε 数值

    def test_computes_epsilon_when_diameter_given(self):
        cfg = copy.deepcopy(CFG)
        cfg["mixing_physics"]["impeller_diameter_m"] = 0.06   # 仅用于验证"有 D 时能走通计算路径"
        results = {x.rule_id: x for x in validators.run_validation(make_inputs(), cfg)}
        r06 = results["R06"]
        assert r06.level in (validators.LEVEL_PASS, validators.LEVEL_WARN, validators.LEVEL_ERROR)
        assert "W/kg" in r06.message


class TestR06WithFactoryDiameter:
    """第八轮：用户拍板 D = 0.052 m（=52 mm）写入 config，R06 必须真算 ε。

    ε 的期望值按 requirements.md 第三节公式独立复算：P = Np·ρ·N³·D⁵，ε = P ÷ (ρ·V)；
    手算过程与逐体积对照表见 docs/第八轮验收说明.md（未在测试里迁就被测代码）。"""

    def test_factory_diameter_is_52_mm(self):
        assert CFG["mixing_physics"]["impeller_diameter_m"] == pytest.approx(0.052, rel=1e-9), \
            "出厂叶轮直径应为 0.052 m（= 52 mm，用户 2026-11-20 拍板）"
        assert CFG["mixing_physics"]["power_number_np"] == pytest.approx(0.35, rel=1e-9)
        assert CFG["mixing_physics"]["impeller_constant_k"] is None   # k 维持不动

    def test_epsilon_matches_independent_hand_computation(self):
        mp = CFG["mixing_physics"]
        d = mp["impeller_diameter_m"]
        rho = mp["broth_density_kg_m3"]
        n_rad_s = 100.0 * 2.0 * math.pi / 60.0          # 出厂默认 100 rpm
        power_w = mp["power_number_np"] * rho * n_rad_s ** 3 * d ** 5
        eps = power_w / (rho * 2000.0 / 1e6)            # 出厂算例 2.0 L
        assert eps == pytest.approx(0.0764, rel=1e-3), "2.0 L / 100 rpm 的 ε 应约等于 0.0764 W/kg"
        assert mp["epsilon_yellow_w_kg"] < eps <= mp["epsilon_red_w_kg"]   # 黄档：不拦导出

    def test_r06_now_reports_a_number_instead_of_missing_d(self):
        r = run_one("R06", make_inputs())
        assert r.level == validators.LEVEL_WARN
        assert "0.1" in r.message and "W/kg" in r.message
        assert "缺少叶轮直径" not in r.message

    def _hand_eps(self, rpm, v_ml=2000.0):
        """按 requirements.md 第三节公式独立复算：P = Np·ρ·N³·D⁵，ε = P ÷ (ρ·V)。"""
        mp = CFG["mixing_physics"]
        n_rad_s = rpm * 2.0 * math.pi / 60.0
        power_w = mp["power_number_np"] * mp["broth_density_kg_m3"] * n_rad_s ** 3 * mp["impeller_diameter_m"] ** 5
        return power_w / (mp["broth_density_kg_m3"] * v_ml / 1e6)

    def _hand_level(self, eps):
        mp = CFG["mixing_physics"]
        if eps > mp["epsilon_red_w_kg"]:
            return validators.LEVEL_ERROR
        if eps > mp["epsilon_yellow_w_kg"]:
            return validators.LEVEL_WARN
        return validators.LEVEL_PASS

    def test_validator_tiers_follow_hand_computed_epsilon(self):
        """扫一圈转速：软件 R06 的判级必须与手算 ε 落在同一档（ε ∝ N³，110 rpm 起应报红禁止）。"""
        for rpm in (50.0, 64.0, 70.0, 80.0, 86.0, 90.0, 100.0, 109.0, 110.0, 120.0, 150.0):
            eps = self._hand_eps(rpm)
            assert run_one("R06", make_inputs(rpm=rpm)).level == self._hand_level(eps), \
                "rpm=%s 时判级与手算 ε=%.4f 不一致" % (rpm, eps)
        assert self._hand_eps(200.0) == pytest.approx(self._hand_eps(100.0) * 8.0, rel=1e-12)

    def test_message_shows_the_same_number_as_hand_computation(self):
        """R06 文案里给用户的 ε 数值必须与手算一致（界面按两位小数显示，故用绝对容差）。"""
        for rpm, v_ml in ((100.0, 2000.0), (120.0, 2400.0), (80.0, 1000.0), (70.0, 1800.0)):
            r = run_one("R06", make_inputs(rpm=rpm, v_work_ml=v_ml))
            shown = float(r.message.split("\u03b5 \u2248 ")[1].split(" W/kg")[0])
            assert shown == pytest.approx(self._hand_eps(rpm, v_ml), abs=0.005), r.message

    def test_factory_default_case_is_warn_not_missing_param(self):
        """出厂算例（2.0 L / 100 rpm）：黄档、不拦导出，且必须带上红线/黄线/推荐区三个参照数。"""
        r = run_one("R06", make_inputs())
        assert r.level == validators.LEVEL_WARN
        for token in ("0.1", "0.05", "0.02", "0.04"):
            assert token in r.message, "R06 文案缺少阈值参照 " + token

    def test_wording_between_recommended_and_yellow_is_corrected(self):
        """封版轮拍板#4：0.04 < ε ≤ 0.05 这段判绿，但文案不得再写成"低于推荐区"（原为反话）。
        转速由该区间中点反解得到，不在测试里写死。"""
        mp = CFG["mixing_physics"]
        rec_hi, yellow = mp["epsilon_recommended_w_kg"][1], mp["epsilon_yellow_w_kg"]
        mid = (rec_hi + yellow) / 2.0
        v_ml = 2000.0
        # 反解公式：ε = Np·N³·D⁵ ÷ V(m³)，体积必须用 m³
        rpm = (60.0 / (2.0 * math.pi)) * ((mid * v_ml / 1e6) / (mp["power_number_np"] * mp["impeller_diameter_m"] ** 5)) ** (1.0 / 3.0)
        eps = self._hand_eps(rpm, v_ml)
        assert rec_hi < eps <= yellow, "取样点必须落在推荐区上限与黄线之间，ε=%.4f" % eps
        r = run_one("R06", make_inputs(rpm=rpm))
        assert r.level == validators.LEVEL_PASS
        assert "高于推荐区上限但未达黄线" in r.message, r.message
        assert "低于推荐区" not in r.message, r.message

    def test_wording_below_recommended_keeps_low_note_and_no_zero_display(self):
        """低于推荐区仍写"低于推荐区"；ε < 0.01 W/kg 不得显示成 0（封版轮修的显示瑕疵）。"""
        r = run_one("R06", make_inputs(rpm=40.0))
        assert r.level == validators.LEVEL_PASS
        assert "低于推荐区" in r.message, r.message
        assert "高于推荐区上限" not in r.message
        assert "ε ≈ 0 W/kg" not in r.message, "极小 ε 不能显示为 0"
        assert "ε ≈ 0.005" in r.message, r.message


class TestR01:
    def test_below_min_error(self):
        lo = CFG["hardware"]["min_working_volume_ml"]
        assert run_one("R01", make_inputs(v_work_ml=lo - 1)).level == validators.LEVEL_ERROR

    def test_above_max_error(self):
        hi = CFG["hardware"]["max_working_volume_ml"]
        assert run_one("R01", make_inputs(v_work_ml=hi + 1)).level == validators.LEVEL_ERROR

    def test_boundaries_pass(self):
        hw = CFG["hardware"]
        for v in (hw["min_working_volume_ml"], hw["max_working_volume_ml"]):
            assert run_one("R01", make_inputs(v_work_ml=v)).level == validators.LEVEL_PASS


class TestR02R03R04MfcLimits:
    @pytest.mark.parametrize("rule,field", [("R02", "q_air_ml_min"), ("R03", "q_o2_ml_min"), ("R04", "q_co2_ml_min")])
    def test_at_limit_pass_and_above_error(self, rule, field):
        mfc = CFG["hardware"]["mfc_max_ml_min"]
        gas = {"R02": "air", "R03": "o2", "R04": "co2"}[rule]
        limit = mfc[gas]
        assert run_one(rule, make_inputs(**{field: limit})).level == validators.LEVEL_PASS
        assert run_one(rule, make_inputs(**{field: limit + 1})).level == validators.LEVEL_ERROR


class TestR05Rpm:
    """封版轮（2026-11-20 拍板#3）：R05 从「越界仅警告」改为三档 ——
    < 下限 = 红拦；下限~谨慎边界（config caution_below_rpm）= 黄；
    谨慎边界~上限 = 绿；超上限维持黄。边界全部从 config 推导，不在测试里写死工艺数值。"""

    def test_below_min_is_error_not_warn(self):
        lo = CFG["process_defaults"]["agitation_rpm"]["min"]
        r = run_one("R05", make_inputs(rpm=lo - 1))
        assert r.level == validators.LEVEL_ERROR
        assert "禁止使用该配置" in r.message

    def test_high_warn(self):
        hi = CFG["process_defaults"]["agitation_rpm"]["max"]
        assert run_one("R05", make_inputs(rpm=hi + 1)).level == validators.LEVEL_WARN

    def test_in_range_pass(self):
        assert run_one("R05", make_inputs()).level == validators.LEVEL_PASS

    def test_factory_limits_are_sealed_values(self):
        rng = CFG["process_defaults"]["agitation_rpm"]
        assert rng["min"] == 60, "R05 下限应为拍板#3 的 60 rpm（未放宽到 40-50）"
        assert rng["max"] == 150, "上限维持 requirements.md 第 3.1 节的 150 rpm"
        assert rng["caution_below_rpm"] == 80, "黄档上界应为原推荐下限 80 rpm"


class TestR05SealBoundaries:
    """用户点名的三条边界（59 / 60 / 74 rpm）+ 80 绿档；
    以及「600-1000 mL 段在 R05 提示里并列显示 R06 红线反解转速」的新行为与逆公式自洽性。"""

    @staticmethod
    def _backsolve_rpm(v_ml, eps):
        """独立复算 R06 公式的逆：rpm = 60/(2π) × (ε·V ÷ (Np·D⁵))^(1/3)。"""
        mp = CFG["mixing_physics"]
        return (60.0 / (2.0 * math.pi)) * ((eps * v_ml / 1e6) / (mp["power_number_np"] * mp["impeller_diameter_m"] ** 5)) ** (1.0 / 3.0)

    def test_59_error_60_warn_74_warn_80_pass(self):
        rng = CFG["process_defaults"]["agitation_rpm"]
        assert (rng["min"], rng["caution_below_rpm"]) == (60, 80)
        assert run_one("R05", make_inputs(rpm=59.0)).level == validators.LEVEL_ERROR, "59 rpm 必须红拦"
        assert run_one("R05", make_inputs(rpm=60.0)).level == validators.LEVEL_WARN, "60 rpm 起进入黄档"
        r74 = run_one("R05", make_inputs(rpm=74.0))
        assert r74.level == validators.LEVEL_WARN, "74 rpm 仍在黄档"
        assert "小体积注意沉降与混合不足" in r74.message, r74.message
        assert run_one("R05", make_inputs(rpm=80.0)).level == validators.LEVEL_PASS, "80 rpm 起绿"

    def test_fact_cap_listed_in_small_volume_band(self):
        band = CFG["process_defaults"]["agitation_rpm"]["fact_cap_volume_ml"]
        red = CFG["mixing_physics"]["epsilon_red_w_kg"]
        lo = CFG["process_defaults"]["agitation_rpm"]["min"]
        for v_ml in (band[0], 800.0, band[1]):
            cap = self._backsolve_rpm(v_ml, red)
            shown = ("%.1f" % (math.floor(cap * 10.0 + 1e-9) / 10.0)).rstrip("0").rstrip(".")
            msg = run_one("R05", make_inputs(rpm=74.0, v_work_ml=v_ml)).message
            assert ("转速事实上限约 %s rpm" % shown) in msg, (v_ml, msg)
            assert ("请把转速控制在 %d–%s rpm 之间" % (lo, shown)) in msg, (v_ml, msg)
            eps_back = (CFG["mixing_physics"]["power_number_np"] * (cap * 2.0 * math.pi / 60.0) ** 3
                        * CFG["mixing_physics"]["impeller_diameter_m"] ** 5 / (v_ml / 1e6))
            assert eps_back == pytest.approx(red, rel=1e-9), "R05 引用的反解转速与 R06 公式不自洽"
        assert self._backsolve_rpm(600.0, red) == pytest.approx(73.2, abs=0.05), "600 mL 红线转速应约 73.2 rpm（第八轮手算表）"

    def test_fact_cap_hidden_outside_band(self):
        band = CFG["process_defaults"]["agitation_rpm"]["fact_cap_volume_ml"]
        msg = run_one("R05", make_inputs(rpm=74.0, v_work_ml=band[1] + 1000.0)).message
        assert "转速事实上限" not in msg, msg

    def test_fact_cap_silent_when_diameter_missing(self):
        """防御：D 被改回 null 时，R05 不得崩溃，也不得编造一个上限数字。"""
        cfg = copy.deepcopy(CFG)
        cfg["mixing_physics"]["impeller_diameter_m"] = None
        r = validators.rule_r05(make_inputs(rpm=74.0, v_work_ml=600.0), cfg)
        assert r.level == validators.LEVEL_WARN
        assert "转速事实上限" not in r.message


class TestR07R08Volumes:
    def test_zero_seed_volume_error(self):
        assert run_one("R07", make_inputs(v_seed_ml=0.0)).level == validators.LEVEL_ERROR

    def test_seed_equals_work_error(self):
        assert run_one("R07", make_inputs(v_seed_ml=2000.0, v_work_ml=2000.0)).level == validators.LEVEL_ERROR

    def test_negative_medium_error(self):
        assert run_one("R08", make_inputs(v_medium_ml=-5.0)).level == validators.LEVEL_ERROR

    def test_zero_medium_error(self):
        assert run_one("R08", make_inputs(v_medium_ml=0.0)).level == validators.LEVEL_ERROR


class TestR09R10R11Setpoints:
    def test_do_below_warn(self):
        lo = CFG["process_defaults"]["do_percent"]["min"]
        assert run_one("R09", make_inputs(do_percent=lo - 1)).level == validators.LEVEL_WARN

    def test_ph_above_warn(self):
        hi = CFG["process_defaults"]["ph_setpoint"]["max"]
        assert run_one("R10", make_inputs(ph_setpoint=hi + 0.01)).level == validators.LEVEL_WARN

    def test_temp_below_warn(self):
        r11 = CFG["process_defaults"]
        lo = min(r11["temp_growth_c"]["min"], r11["temp_expression_c"]["min"])
        assert run_one("R11", make_inputs(temp_growth_c=lo - 0.5)).level == validators.LEVEL_WARN

    def test_temp_expression_checked_when_enabled(self):
        r11 = CFG["process_defaults"]
        hi = max(r11["temp_growth_c"]["max"], r11["temp_expression_c"]["max"])
        assert run_one("R11", make_inputs(temp_expression_c=hi + 0.5)).level == validators.LEVEL_WARN

    def test_temp_expression_ignored_when_disabled(self):
        assert run_one("R11", make_inputs(temp_expression_c=None)).level == validators.LEVEL_PASS


class TestR12R13GasRatios:
    def test_o2_ratio_above_max_warn(self):
        hi = CFG["process_defaults"]["o2_ratio_percent"]["max"]
        assert run_one("R12", make_inputs(o2_ratio_percent=hi + 1)).level == validators.LEVEL_WARN

    def test_co2_ratio_above_max_warn(self):
        hi = CFG["process_defaults"]["co2_ratio_percent"]["max"]
        assert run_one("R13", make_inputs(co2_ratio_percent=hi + 1)).level == validators.LEVEL_WARN

    def test_o2_ratio_zero_pass(self):
        assert run_one("R12", make_inputs(o2_ratio_percent=0.0)).level == validators.LEVEL_PASS


class TestR14Vvm:
    def test_below_recommended_warn(self):
        lo = CFG["process_defaults"]["aeration_vvm"]["min"]
        assert run_one("R14", make_inputs(vvm=lo / 2)).level == validators.LEVEL_WARN

    def test_above_recommended_warn(self):
        hi = CFG["process_defaults"]["aeration_vvm"]["max"]
        assert run_one("R14", make_inputs(vvm=hi * 2)).level == validators.LEVEL_WARN

    def test_in_range_pass(self):
        assert run_one("R14", make_inputs()).level == validators.LEVEL_PASS


class TestR15Density:
    """R15：CD_seed 必须大于 CD_inoc（🔴）；并合并答复#5 的浓度检查。"""

    def test_seed_not_above_inoc_error(self):
        pd = CFG["process_defaults"]
        inoc = pd["inoculum_density_mcells_ml"]["set"]
        assert run_one("R15", make_inputs(cd_seed_mcells_ml=inoc, cd_inoc_mcells_ml=inoc)).level == validators.LEVEL_ERROR

    def test_seed_below_inoc_error(self):
        assert run_one("R15", make_inputs(cd_seed_mcells_ml=0.5, cd_inoc_mcells_ml=1.0)).level == validators.LEVEL_ERROR

    def test_seed_above_red_max_error(self):
        red = CFG["density_input"]["seed_conc_red_max_mcells_ml"]
        assert run_one("R15", make_inputs(cd_seed_mcells_ml=red + 1)).level == validators.LEVEL_ERROR

    def test_inoc_below_common_band_warn(self):
        inoc_min = CFG["process_defaults"]["inoculum_density_mcells_ml"]["min"]
        assert run_one("R15", make_inputs(cd_inoc_mcells_ml=inoc_min / 2.0)).level == validators.LEVEL_WARN

    def test_inoc_recommended_default_pass(self):
        """requirements 3.1 默认接种密度 0.4 低于常见区间 0.5，但属工艺推荐范围，应通过。"""
        assert run_one("R15", make_inputs()).level == validators.LEVEL_PASS

    def test_inoc_above_common_band_warn(self):
        hi = CFG["density_input"]["reactor_initial_density_yellow_range_mcells_ml"][1]
        seed_red = CFG["density_input"]["seed_conc_red_max_mcells_ml"]
        # 起始密度高于常见区间上限（但低于界面输入上限 20，且 CD_seed 仍大于它、不超红线）
        assert run_one("R15", make_inputs(cd_inoc_mcells_ml=hi + 1, cd_seed_mcells_ml=seed_red - 0.5)).level == validators.LEVEL_WARN


class TestR16Sparger:
    def test_forced_hint_always_warn(self):
        """requirements 第五节：R16 为界面强制提示（🟡），任何配置下都必须出现。"""
        r = run_one("R16", make_inputs())
        assert r.level == validators.LEVEL_WARN
        assert "曝气头" in r.message and "L 型管" in r.message


class TestR17Sampling:
    def test_at_limit_pass(self):
        frac = CFG["sampling"]["max_cumulative_fraction_of_working"]
        v_work = CFG["ui_defaults"]["working_volume_ml"]
        assert run_one("R17", make_inputs(v_work_ml=v_work, sampling_total_ml=frac * v_work)).level == validators.LEVEL_PASS

    def test_above_limit_warn(self):
        frac = CFG["sampling"]["max_cumulative_fraction_of_working"]
        v_work = CFG["ui_defaults"]["working_volume_ml"]
        assert run_one("R17", make_inputs(v_work_ml=v_work, sampling_total_ml=frac * v_work + 1)).level == validators.LEVEL_WARN


class TestR18CultureDays:
    def test_below_range_warn(self):
        lo = CFG["process_defaults"]["culture_days"]["min"]
        assert run_one("R18", make_inputs(culture_days=lo - 1)).level == validators.LEVEL_WARN

    def test_above_range_warn(self):
        hi = CFG["process_defaults"]["culture_days"]["max"]
        assert run_one("R18", make_inputs(culture_days=hi + 1)).level == validators.LEVEL_WARN

    def test_default_pass(self):
        assert run_one("R18", make_inputs()).level == validators.LEVEL_PASS


class TestR06IllegalVolumeGuard:
    """第四轮防呆：D 已填但工作体积 ≤0 时，R06 必须返回 🔴 并说明原因，严禁除零崩溃。"""

    @staticmethod
    def _cfg_with_d():
        cfg2 = copy.deepcopy(CFG)
        cfg2["mixing_physics"]["impeller_diameter_m"] = 0.105
        return cfg2

    def test_zero_volume_with_diameter_gives_error_not_crash(self):
        r = validators.rule_r06(make_inputs(v_work_ml=0.0), self._cfg_with_d())
        assert r.level == validators.LEVEL_ERROR
        assert "工作体积" in r.message

    def test_negative_volume_with_diameter_gives_error(self):
        r = validators.rule_r06(make_inputs(v_work_ml=-5.0), self._cfg_with_d())
        assert r.level == validators.LEVEL_ERROR

    def test_nonpositive_diameter_warns_not_crash(self):
        cfg2 = copy.deepcopy(CFG)
        cfg2["mixing_physics"]["impeller_diameter_m"] = 0.0
        r = validators.rule_r06(make_inputs(), cfg2)
        assert r.level == validators.LEVEL_WARN
        assert "叶轮直径" in r.message


class TestExtremeInputsNoCrash:
    """第四轮约束：全 0 / 负数 / 超大等非法输入下，run_validation 仍须返回 18 条结果且不抛异常
    （界面数字框虽已限制范围，但配方 JSON、手改 config 等路径仍可能带入极端值）。"""

    EXTREMES = [
        dict(v_work_ml=0.0, v_seed_ml=0.0, v_medium_ml=0.0, q_air_ml_min=0.0,
             q_o2_ml_min=0.0, q_co2_ml_min=0.0, cd_inoc_mcells_ml=0.0,
             cd_seed_mcells_ml=0.0, vvm=0.0, culture_days=0.0,
             sampling_total_ml=0.0, rpm=0.0),
        dict(v_work_ml=-100.0, v_seed_ml=-1.0, v_medium_ml=-50.0, q_air_ml_min=-10.0,
             q_o2_ml_min=-1.0, q_co2_ml_min=-1.0, rpm=-50.0, cd_inoc_mcells_ml=-1.0,
             cd_seed_mcells_ml=-1.0, vvm=-0.1, culture_days=-3.0, sampling_total_ml=-5.0),
        dict(v_work_ml=9999999.0, v_seed_ml=9999999.0, v_medium_ml=0.0,
             q_air_ml_min=9999999.0, q_o2_ml_min=9999999.0, q_co2_ml_min=9999999.0,
             rpm=9999.0, cd_inoc_mcells_ml=99.0, cd_seed_mcells_ml=99.0, vvm=5.0,
             culture_days=365.0, sampling_total_ml=999999.0),
    ]

    def test_run_validation_never_crashes(self):
        for over in self.EXTREMES:
            results = validators.run_validation(make_inputs(**over), CFG)
            assert len(results) == 18
            assert all(r.message for r in results)

    def test_run_validation_never_crashes_with_diameter(self):
        cfg2 = copy.deepcopy(CFG)
        cfg2["mixing_physics"]["impeller_diameter_m"] = 0.105
        for over in self.EXTREMES:
            results = validators.run_validation(make_inputs(**over), cfg2)
            assert len(results) == 18
            assert all(r.message for r in results)

# -*- coding: utf-8 -*-
"""校验规则 R01-R18 单元测试（第三轮起覆盖 requirements.md 第五节全部 18 条）。
边界值全部从 config/config.yaml 推导，测试代码不写死工艺数值；
期望的 级别（通过/警告/错误）取自 requirements.md 第五节规则表的"级别"列。"""
import copy

import pytest

from cell_planner.core import validators
from cell_planner.core.config_loader import get_config

CFG = get_config()


def make_inputs(**overrides):
    """构造一组基于 requirements 3.3 算例的基准输入（除 R06 因缺叶轮直径必为黄色外其余全绿），
    再按用例覆盖个别字段。"""
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
        assert warn_ids == ["R06", "R16"]   # 缺叶轮直径 + 曝气方式强制提示，均属预期

    def test_baseline_no_error(self):
        res = validators.run_validation(make_inputs(), CFG)
        assert all(r.level != validators.LEVEL_ERROR for r in res)

    def test_all_messages_are_chinese(self):
        for r in validators.run_validation(make_inputs(), CFG):
            assert any("\u4e00" <= ch <= "\u9fff" for ch in r.message), r.rule_id


class TestR06MissingDiameter:
    """用户定案：D 为 null → 黄色警告并说明原因，不得崩溃。"""

    def test_warns_when_diameter_null(self):
        assert CFG["mixing_physics"]["impeller_diameter_m"] is None
        r = run_one("R06", make_inputs())
        assert r.level == validators.LEVEL_WARN
        assert "叶轮直径" in r.message

    def test_computes_epsilon_when_diameter_given(self):
        cfg = copy.deepcopy(CFG)
        cfg["mixing_physics"]["impeller_diameter_m"] = 0.06   # 仅用于验证"有 D 时能走通计算路径"
        results = {x.rule_id: x for x in validators.run_validation(make_inputs(), cfg)}
        r06 = results["R06"]
        assert r06.level in (validators.LEVEL_PASS, validators.LEVEL_WARN, validators.LEVEL_ERROR)
        assert "W/kg" in r06.message


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
    def test_low_warn(self):
        lo = CFG["process_defaults"]["agitation_rpm"]["min"]
        assert run_one("R05", make_inputs(rpm=lo - 1)).level == validators.LEVEL_WARN

    def test_high_warn(self):
        hi = CFG["process_defaults"]["agitation_rpm"]["max"]
        assert run_one("R05", make_inputs(rpm=hi + 1)).level == validators.LEVEL_WARN

    def test_in_range_pass(self):
        assert run_one("R05", make_inputs()).level == validators.LEVEL_PASS


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

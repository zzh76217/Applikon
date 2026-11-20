# -*- coding: utf-8 -*-
"""第三节公式单元测试（第二轮）。
核心断言的期望值直接取自 requirements.md 3.3 算例，不自编期望值：
  V_work=2000 mL, CD_inoc=0.4, CD_seed=3.0  =>  V_seed=266.7 mL
  vvm=0.1, V_work=2000 mL                    =>  Q_air=200 mL/min, Q_O2=20 mL/min（O2 比例 10%）
其余断言仅验证公式恒等关系与输入防护，不引入新的数值期望。
浮点比较一律使用 pytest.approx。
第四轮追加：开发提示词文档 §四(四) 的 2.0 L 算例（N_total=800 ×10⁶ cells、Q_CO2=30 mL/min @15%），
以及补充公式 B（搅拌启动建议转速）与补充公式 C（γ≈k×N）的恒等关系与非法输入防护测试。"""
import pytest

from cell_planner.core.config_loader import get_config
from cell_planner.core.formulas import (
    agitation_start_rpm_suggestion,
    air_flow_ml_min,
    co2_flow_ml_min,
    inoculum_volume_ml,
    medium_volume_ml,
    o2_flow_ml_min,
    scientific_cn,
    shear_gamma_per_s,
    total_cells_millions,
)


class TestRequirementsExamples:
    """requirements.md 3.3 算例（约束①：期望值逐字来自需求文档）。"""

    def test_example_v_seed(self):
        v_seed = inoculum_volume_ml(v_work_ml=2000.0, cd_inoc_mcells_ml=0.4, cd_seed_mcells_ml=3.0)
        assert v_seed == pytest.approx(266.7, abs=0.05)

    def test_example_q_air(self):
        q_air = air_flow_ml_min(vvm=0.1, v_work_ml=2000.0)
        assert q_air == pytest.approx(200.0)

    def test_example_q_o2(self):
        q_air = air_flow_ml_min(vvm=0.1, v_work_ml=2000.0)
        q_o2 = o2_flow_ml_min(q_air_ml_min=q_air, o2_ratio_percent=10.0)
        assert q_o2 == pytest.approx(20.0)


class TestFormulaIdentities:
    """恒等关系断言：只验证公式自身的数学一致性，不编造期望数值。"""

    def test_medium_volume_conservation(self):
        v_work, v_seed, v_base, v_af = 2000.0, 266.6666667, 40.0, 2.0
        v_medium = medium_volume_ml(v_work, v_seed, v_base, v_af)
        assert v_medium + v_seed + v_base + v_af == pytest.approx(v_work)

    def test_seed_flow_proportional_to_ratio(self):
        q_air = air_flow_ml_min(0.1, 2000.0)
        assert o2_flow_ml_min(q_air, 10.0) == pytest.approx(q_air * 0.10)
        assert co2_flow_ml_min(q_air, 25.0) == pytest.approx(q_air * 0.25)

    def test_zero_ratio_gives_zero_flow(self):
        q_air = air_flow_ml_min(0.05, 1000.0)
        assert o2_flow_ml_min(q_air, 0.0) == pytest.approx(0.0)
        assert co2_flow_ml_min(q_air, 0.0) == pytest.approx(0.0)


class TestInputGuards:
    """非法输入必须抛中文 ValueError，而不是返回错误数字。"""

    def test_nonpositive_cd_seed_raises(self):
        with pytest.raises(ValueError, match="大于 0"):
            inoculum_volume_ml(2000.0, 0.4, 0.0)

    def test_nonpositive_v_work_raises(self):
        with pytest.raises(ValueError):
            air_flow_ml_min(0.1, 0.0)

    def test_negative_ratio_raises(self):
        with pytest.raises(ValueError, match="不能为负数"):
            o2_flow_ml_min(200.0, -5.0)

    def test_negative_volumes_in_medium_raises(self):
        with pytest.raises(ValueError, match="不能为负数"):
            medium_volume_ml(2000.0, -1.0, 0.0, 0.0)


class TestPromptDocExample:
    """开发提示词文档 §四(四) 算例（第四轮，约束①：期望值逐字取自文档）。
    输入：V_work=2000 mL、CD_inoc=0.4e6、CD_seed=3.0e6、vvm=0.1、O2 10%、CO2 15%。
    期望：V_seed=266.7 mL；N_total=800 ×10⁶ cells；Q_air=200 mL/min；Q_O2=20 mL/min；Q_CO2=30 mL/min。
    注：文档把 N_total 误写为 "8.0 × 10⁶ cells"，属单位笔误
    （2000 mL × 0.4×10⁶ cells/mL = 8.0×10⁸ cells = 800 ×10⁶ cells）；
    本测试按物理正确的单位换算断言 800（×10⁶），决策记录见 README 第四轮。"""

    def test_doc_example_v_seed(self):
        assert inoculum_volume_ml(2000.0, 0.4, 3.0) == pytest.approx(266.7, abs=0.05)

    def test_doc_example_n_total(self):
        assert total_cells_millions(2000.0, 0.4) == pytest.approx(800.0)

    def test_doc_example_q_air(self):
        assert air_flow_ml_min(0.1, 2000.0) == pytest.approx(200.0)

    def test_doc_example_q_o2(self):
        assert o2_flow_ml_min(air_flow_ml_min(0.1, 2000.0), 10.0) == pytest.approx(20.0)

    def test_doc_example_q_co2(self):
        assert co2_flow_ml_min(air_flow_ml_min(0.1, 2000.0), 15.0) == pytest.approx(30.0)

    def test_doc_example_n_total_scientific_display(self):
        assert scientific_cn(total_cells_millions(2000.0, 0.4) * 1000000.0) == "8.0×10⁸"


class TestTotalCellsGuards:
    def test_zero_volume_raises_chinese(self):
        with pytest.raises(ValueError, match="工作体积"):
            total_cells_millions(0.0, 0.4)

    def test_zero_density_raises_chinese(self):
        with pytest.raises(ValueError, match="接种密度"):
            total_cells_millions(2000.0, 0.0)


class TestAgitationStartSuggestion:
    """补充公式 B：分段阈值从 config 读取。
    封版轮（2026-11-20 拍板#2＝方案 A）把旧经验分档 80/100/120 rpm 下调为 60/70/80 rpm，
    原因是 D=0.052 m 落地后旧值会让 1200 mL/100 rpm、2000 mL/120 rpm 直接撞 R06 剪切红线；
    新分档同时保证不低于 R05 拦截下限 60 rpm（否则软件自己的建议值会被软件自己拦红）。"""

    @staticmethod
    def _bands():
        return get_config()["agitation_start_suggestion"]["bands_ml"]

    def test_bands_are_the_sealed_values(self):
        bands = self._bands()
        assert [b["max_ml"] for b in bands] == [1000, 1800, None]
        assert [b["rpm"] for b in bands] == [60, 70, 80], "分档应为封版轮拍板#2 的 60/70/80 rpm"

    def test_large_volume_suggests_80(self):
        assert agitation_start_rpm_suggestion(2000.0, self._bands()) == pytest.approx(80.0)

    def test_small_volume_suggests_60(self):
        assert agitation_start_rpm_suggestion(800.0, self._bands()) == pytest.approx(60.0)

    def test_boundary_1000ml_uses_lower_band(self):
        assert agitation_start_rpm_suggestion(1000.0, self._bands()) == pytest.approx(60.0)
        assert agitation_start_rpm_suggestion(1000.5, self._bands()) == pytest.approx(70.0)

    def test_boundary_1800ml(self):
        assert agitation_start_rpm_suggestion(1800.0, self._bands()) == pytest.approx(70.0)
        assert agitation_start_rpm_suggestion(1801.0, self._bands()) == pytest.approx(80.0)

    def test_zero_volume_raises(self):
        with pytest.raises(ValueError, match="工作体积"):
            agitation_start_rpm_suggestion(0.0, self._bands())

    def test_empty_bands_raises_chinese(self):
        with pytest.raises(ValueError, match="分段"):
            agitation_start_rpm_suggestion(2000.0, [])


class TestShearGamma:
    """补充公式 C：γ ≈ k × N（N = rpm/60 转/秒）。k 目前没有参考值（答复#3 延用），
    以下数值断言只是验证公式实现正确性的恒等关系，不是工艺参数期望值。"""

    def test_gamma_identity_with_placeholder_k(self):
        assert shear_gamma_per_s(120.0, 10.0) == pytest.approx(20.0)

    def test_gamma_scales_linearly_with_rpm(self):
        assert shear_gamma_per_s(120.0, 4.0) == pytest.approx(2 * shear_gamma_per_s(60.0, 4.0))

    def test_missing_k_raises_chinese(self):
        with pytest.raises(ValueError, match="叶轮常数 k"):
            shear_gamma_per_s(120.0, None)

    def test_nonpositive_k_raises_chinese(self):
        with pytest.raises(ValueError, match="叶轮常数 k 必须大于 0"):
            shear_gamma_per_s(120.0, 0.0)

    def test_negative_rpm_raises_chinese(self):
        with pytest.raises(ValueError, match="不能为负数"):
            shear_gamma_per_s(-10.0, 5.0)

    def test_current_config_k_is_null_defended(self):
        """第四轮现状：config 的 impeller_constant_k 仍为 null，调用必抛中文异常，
        界面层据此显示黄色警告而不是崩溃（冒烟测试覆盖界面侧）。"""
        mp = get_config()["mixing_physics"]
        if mp.get("shear_gamma_enabled") and mp.get("impeller_constant_k") is None:
            with pytest.raises(ValueError, match="叶轮常数 k"):
                shear_gamma_per_s(100.0, mp.get("impeller_constant_k"))


class TestScientificDisplay:
    def test_scientific_cn_8e8(self):
        assert scientific_cn(8.0e8) == "8.0×10⁸"

    def test_scientific_cn_zero(self):
        assert scientific_cn(0.0) == "0"

    def test_scientific_cn_266_7(self):
        assert scientific_cn(266.7) == "2.7×10²"

    def test_scientific_cn_negative_exponent(self):
        assert scientific_cn(2.0e-3) == "2.0×10⁻³"

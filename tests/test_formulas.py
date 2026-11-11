# -*- coding: utf-8 -*-
"""第三节公式单元测试（第二轮）。
核心断言的期望值直接取自 requirements.md 3.3 算例，不自编期望值：
  V_work=2000 mL, CD_inoc=0.4, CD_seed=3.0  =>  V_seed=266.7 mL
  vvm=0.1, V_work=2000 mL                    =>  Q_air=200 mL/min, Q_O2=20 mL/min（O2 比例 10%）
其余断言仅验证公式恒等关系与输入防护，不引入新的数值期望。
浮点比较一律使用 pytest.approx。"""
import pytest

from cell_planner.core.formulas import (
    air_flow_ml_min,
    co2_flow_ml_min,
    inoculum_volume_ml,
    medium_volume_ml,
    o2_flow_ml_min,
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

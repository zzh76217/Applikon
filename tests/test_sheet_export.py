# -*- coding: utf-8 -*-
"""开机配置单 CSV 导出测试（第三轮）。
核心数值期望值取自 requirements.md 3.3 算例：V_work=2000, CD_inoc=0.4, CD_seed=3.0, vvm=0.1, O2=10%
  => V_seed=266.7 mL、Q_air=200 mL/min、Q_O2=20 mL/min（浮点显示为 266.67/200/20）。
"""
import copy
import csv

import pytest

from cell_planner.core import formulas, sheet_export, validators
from cell_planner.core.config_loader import get_config

CFG = get_config()


def build_case_a():
    pd = CFG["process_defaults"]
    v_work, cd_inoc, cd_seed = 2000.0, 0.4, 3.0
    v_seed = formulas.inoculum_volume_ml(v_work, cd_inoc, cd_seed)
    v_base = v_work * CFG["liquid_additives"]["base_fraction_of_working"]["default"]
    v_af = v_work * CFG["liquid_additives"]["antifoam_fraction_of_working"]["default"]
    v_medium = formulas.medium_volume_ml(v_work, v_seed, v_base, v_af)
    q_air = formulas.air_flow_ml_min(pd["aeration_vvm"]["set"], v_work)
    q_o2 = formulas.o2_flow_ml_min(q_air, pd["o2_ratio_percent"]["set"])
    q_co2 = formulas.co2_flow_ml_min(q_air, pd["co2_ratio_percent"]["set"])
    inp = validators.SetupInputs(
        v_work_ml=v_work, v_seed_ml=v_seed, v_medium_ml=v_medium,
        q_air_ml_min=q_air, q_o2_ml_min=q_o2, q_co2_ml_min=q_co2,
        rpm=pd["agitation_rpm"]["set"], temp_growth_c=pd["temp_growth_c"]["set"],
        temp_expression_c=None, ph_setpoint=pd["ph_setpoint"]["set"],
        do_percent=pd["do_percent"]["set"], o2_ratio_percent=pd["o2_ratio_percent"]["set"],
        co2_ratio_percent=pd["co2_ratio_percent"]["set"],
        cd_inoc_mcells_ml=cd_inoc, cd_seed_mcells_ml=cd_seed,
        vvm=pd["aeration_vvm"]["set"], culture_days=pd["culture_days"]["set"],
        sampling_total_ml=float(CFG["ui_defaults"]["sampling_total_ml"]),
    )
    results = validators.run_validation(inp, CFG)
    return inp, v_base, v_af, results


def row_of(rows, item):
    for r in rows:
        if r[1] == item:
            return r
    raise AssertionError("配置单中找不到项目：" + item)


class TestBuildRows:
    def test_header_and_disclaimer(self):
        inp, v_base, v_af, results = build_case_a()
        rows = sheet_export.build_sheet_rows(inp, v_base, v_af, "CHO-DG44", "CD 培养基", results, CFG)
        assert rows[0] == sheet_export.HEADER
        assert any(sheet_export.DISCLAIMER in r for r in rows[-2:] ), "末两行内必须包含人工复核免责声明"

    def test_case_a_values_match_requirements_example(self):
        inp, v_base, v_af, results = build_case_a()
        rows = sheet_export.build_sheet_rows(inp, v_base, v_af, "CHO-DG44", "CD 培养基", results, CFG)
        assert float(row_of(rows, "接种体积 V_seed")[2]) == pytest.approx(266.7, abs=0.05)
        assert float(row_of(rows, "Air 流量 Q_air")[2]) == pytest.approx(200.0)
        assert float(row_of(rows, "O2 流量 Q_O2")[2]) == pytest.approx(20.0)
        assert float(row_of(rows, "培养基补液 V_medium")[2]) == pytest.approx(1691.33, abs=0.01)

    def test_all_18_rules_written(self):
        inp, v_base, v_af, results = build_case_a()
        rows = sheet_export.build_sheet_rows(inp, v_base, v_af, "CHO-DG44", "CD 培养基", results, CFG)
        detail = [r for r in rows if r[0] == "校验明细"]
        assert len(detail) == 18
        assert detail[0][1].startswith("R01") and detail[-1][1].startswith("R18")

    def test_alkali_pump_note_included(self):
        inp, v_base, v_af, results = build_case_a()
        rows = sheet_export.build_sheet_rows(inp, v_base, v_af, "CHO-DG44", "CD 培养基", results, CFG)
        r = row_of(rows, "碱泵流量系数建议")
        assert CFG["alkali_pump"]["note"] in r[4]
        assert float(r[2]) == pytest.approx(CFG["alkali_pump"]["max_rate_ml_per_min_per_L"])


class TestExportCsv:
    def test_utf8_sig_bom_and_roundtrip(self, tmp_path):
        inp, v_base, v_af, results = build_case_a()
        rows = sheet_export.build_sheet_rows(inp, v_base, v_af, "CHO-DG44", "CD 培养基", results, CFG)
        out = tmp_path / "开机配置单.csv"
        sheet_export.export_sheet_csv(out, rows, CFG)
        raw = out.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), "CSV 必须带 BOM（utf-8-sig），否则 Excel 打开中文乱码"
        with open(out, "r", encoding=CFG["setup_sheet_export"]["csv_encoding"], newline="") as fh:
            read_back = list(csv.reader(fh))
        assert read_back == [[str(c) for c in row] for row in rows]


class TestRound4Rows:
    """第四轮新增行：总需细胞数 N_total（补充公式A）、搅拌启动建议转速（补充公式B）、
    剪切速率估算 γ（补充公式C，k 缺值时必须写"无法计算"而不是崩溃）。
    N_total 期望值 800（×10⁶ cells）逐字取自提示词文档 §四(四) 算例。"""

    @staticmethod
    def _rows_for(cfg=None):
        inp, v_base, v_af, results = build_case_a()
        return sheet_export.build_sheet_rows(inp, v_base, v_af, "CHO-DG44", "CD 培养基",
                                             results, cfg or CFG), inp

    def test_n_total_row_matches_doc_example(self):
        rows, _ = self._rows_for()
        r = row_of(rows, "总需细胞数 N_total")
        assert r[2] == "800"
        assert r[3] == CFG["total_cells"]["display_unit"]
        assert "8.0×10⁸" in r[4]

    def test_agitation_suggestion_row_2000ml(self):
        rows, _ = self._rows_for()
        assert row_of(rows, "搅拌启动建议转速")[2] == "120"

    def test_shear_row_defends_missing_k(self):
        mp = CFG["mixing_physics"]
        if not mp.get("shear_gamma_enabled") or mp.get("impeller_constant_k") is not None:
            pytest.skip("仅在第四轮当前配置（启用 γ 展示且 k=null）下验证缺 k 防护")
        rows, _ = self._rows_for()
        r = row_of(rows, "剪切速率估算 γ")
        assert "叶轮常数 k" in r[2]

    def test_shear_row_computes_when_k_provided(self):
        cfg2 = copy.deepcopy(CFG)
        cfg2["mixing_physics"]["shear_gamma_enabled"] = True
        cfg2["mixing_physics"]["impeller_constant_k"] = 10.0
        rows, inp = self._rows_for(cfg2)
        r = row_of(rows, "剪切速率估算 γ")
        expected = 10.0 * inp.rpm / 60.0  # 恒等关系（k=10 为占位值，非工艺期望值）
        assert float(r[2]) == pytest.approx(expected, abs=0.01)  # 配置单数值列按 2 位小数显示

    def test_shear_row_hidden_when_disabled(self):
        cfg2 = copy.deepcopy(CFG)
        cfg2["mixing_physics"]["shear_gamma_enabled"] = False
        rows, _ = self._rows_for(cfg2)
        assert all(r[1] != "剪切速率估算 γ" for r in rows)

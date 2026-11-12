# -*- coding: utf-8 -*-
"""模拟 CSV 生成器 + ③离线分析端到端测试（第五轮 · 模块 3）。

要点：
- 模拟数据的"工艺阈值"全部读 config，生成参数读 config.simulation，绝不在测试里自编结论；
- 唯一允许的字面期望值来自 requirements.md 3.3 算例（Q_air=200 mL/min、Q_O2=20 mL/min）；
- 所有文件写在 pytest 的 tmp_path 里，不污染工程 data/ 目录（答复#8：模拟数据不得混入交付物）。
"""
import csv
import sys
from pathlib import Path

import pytest

from cell_planner.core import analysis as an
from cell_planner.core import formulas
from cell_planner.core.config_loader import get_config
from cell_planner.io_ import csv_reader as rd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_simulated_csv as mk  # noqa: E402

CFG = get_config()
SIM = CFG["simulation"]
DA = CFG["do_alarm"]
GL = CFG["metabolite_limits"]["glucose_g_l"]
LC = CFG["metabolite_limits"]["lactate_g_l"]
V_WORK = float(CFG["ui_defaults"]["working_volume_ml"])
VVM = float(CFG["process_defaults"]["aeration_vvm"]["set"])
O2_PCT = float(CFG["process_defaults"]["o2_ratio_percent"]["set"])
CO2_PCT = float(CFG["process_defaults"]["co2_ratio_percent"]["set"])
DEV = float(DA["deviation_yellow_points"])
ABS_RED = float(DA["absolute_red_percent"])
MARKER_COL = str(SIM["marker_column"])
MARKER = str(SIM["marker_value"])
PREFIX = str(SIM["filename_prefix"])


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    out = tmp_path_factory.mktemp("simcsv")
    files = mk.generate(out_dir=out, tag="ut", cfg=CFG)
    return out, files


def read_rows(path):
    with open(path, "r", encoding=str(CFG["csv_import"]["encoding"]), newline="") as fh:
        return list(csv.reader(fh))


# ---------------------------------------------------------------- 生成器本身
def test_generate_makes_two_clearly_marked_files(pair):
    out, files = pair
    assert len(files) == 2
    for f in files:
        assert f.parent == out
        assert f.name.startswith(PREFIX + "_"), f.name        # 文件名必须显式 SIMULATED
        assert f.suffix == ".csv"


def test_header_matches_config_and_every_row_carries_marker(pair):
    out, files = pair
    expected = {"control": list(SIM["columns"]["control"]), "offline": list(SIM["columns"]["offline"])}
    for f, kind in zip(files, ("control", "offline")):
        rows = read_rows(f)
        assert rows[0] == expected[kind]                       # 首行列名（答复#8 通用格式）
        col = rows[0].index(MARKER_COL)
        assert all(r[col] == MARKER for r in rows[1:]), kind   # 每一行都要标注
        assert len(rows) > 1


def test_first_column_is_iso_datetime(pair):
    out, files = pair
    fmt = str(CFG["csv_import"]["datetime_iso_format"])
    rows = read_rows(files[0])
    import datetime as dt
    parsed = dt.datetime.strptime(rows[1][0], fmt)             # 解析不抛错即符合 ISO 约定
    assert parsed.year >= 2000


def test_generation_is_reproducible(tmp_path):
    a = mk.generate(out_dir=tmp_path / "a", tag="ut", cfg=CFG)
    b = mk.generate(out_dir=tmp_path / "b", tag="ut", cfg=CFG)
    for fa, fb in zip(a, b):
        assert fa.name == fb.name
        assert fa.read_bytes() == fb.read_bytes()


# ---------------------------------------------------------------- 解析器对接
def test_load_dataset_recognises_simulated_and_has_no_errors(pair):
    out, files = pair
    ctrl = rd.load_dataset(files[0], "control", cfg=CFG)
    off = rd.load_dataset(files[1], "offline", cfg=CFG)
    for ds in (ctrl, off):
        assert ds.is_simulated is True
        assert MARKER in ds.simulated_reason
        assert ds.errors == []
        assert ds.n_points > 0
    n_ctrl = int(round(float(SIM["days"]) * 24.0 / (float(SIM["control_interval_minutes"]) / 60.0))) + 1
    n_off = int(round(float(SIM["days"]) / float(SIM["offline_interval_days"]))) + 1
    assert ctrl.n_points == n_ctrl
    assert off.n_points == n_off
    assert ctrl.t_hours[0] == pytest.approx(0.0)
    assert ctrl.t_hours[-1] == pytest.approx(float(SIM["days"]) * 24.0, rel=1e-6)


def test_control_gas_flows_match_requirements_case(pair):
    """交叉验证第三节公式 3-5 与 3.3 算例（2 L / 0.1 vvm → 200 mL/min，O2 10% → 20 mL/min）。"""
    out, files = pair
    ctrl = rd.load_dataset(files[0], "control", cfg=CFG)
    expect_air = formulas.air_flow_ml_min(VVM, V_WORK)
    expect_o2 = formulas.o2_flow_ml_min(expect_air, O2_PCT)
    expect_co2 = formulas.co2_flow_ml_min(expect_air, CO2_PCT)
    assert expect_air == pytest.approx(200.0)                  # requirements 3.3
    assert expect_o2 == pytest.approx(20.0)                    # requirements 3.3
    for field, want in (("air_ml_min", expect_air), ("o2_ml_min", expect_o2),
                        ("co2_ml_min", expect_co2)):
        vals = [v for v in ctrl.values(field) if v is not None]
        assert vals, field
        assert all(v == pytest.approx(want) for v in vals), field


def test_simulated_input_cannot_be_mistaken_for_real_data(tmp_path, pair):
    """改名去掉 SIMULATED 前缀后，仍要靠标记列识别出来；两者都没有时不得谎称真实数据。"""
    out, files = pair
    renamed = tmp_path / "控制数据_改名.csv"
    renamed.write_bytes(files[0].read_bytes())
    ds = rd.load_dataset(renamed, "control", cfg=CFG)
    assert ds.is_simulated is True                             # 每行标记列仍被识别
    clean = tmp_path / "真实数据.csv"
    rows = read_rows(files[0])
    idx = rows[0].index(MARKER_COL)
    with open(clean, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerows([r[:idx] + r[idx + 1:] for r in rows])     # 去掉标记列
    ds2 = rd.load_dataset(clean, "control", cfg=CFG)
    assert ds2.is_simulated is False
    assert ds2.errors == []


# ---------------------------------------------------------------- 完整分析链路
@pytest.fixture(scope="module")
def analysed(pair):
    out, files = pair
    ctrl = rd.load_dataset(files[0], "control", cfg=CFG)
    off = rd.load_dataset(files[1], "offline", cfg=CFG)
    return an.analyze(ctrl, off, cfg=CFG), off


def test_do_alarm_events_match_config_dips(analysed):
    res, off = analysed
    events = res["do_events"]
    assert res["errors"] == []
    assert len(events) == 3
    yellow_min = float(SIM["do_dip_yellow_minutes"])
    red_min = float(SIM["do_dip_red_minutes"])
    kinds = [(e.kind, e.level) for e in events]
    assert kinds == [("deviation", an.LEVEL_WARN), ("deviation", an.LEVEL_ERROR), ("absolute", an.LEVEL_ERROR)]
    assert events[0].start_h == pytest.approx(float(SIM["do_dip_yellow_start_hours"]), abs=0.1)
    assert events[0].duration_minutes == pytest.approx(yellow_min, abs=1.0)
    assert events[1].duration_minutes == pytest.approx(red_min, abs=1.0)
    assert events[0].threshold == pytest.approx(float(CFG["process_defaults"]["do_percent"]["set"]) - DEV)
    assert events[2].threshold == pytest.approx(ABS_RED)
    assert events[2].min_value < ABS_RED
    s = res["do_summary"]
    assert (s["n_yellow"], s["n_red"], s["n_absolute_red"]) == (1, 1, 1)
    assert s["deviation_minutes"] == pytest.approx(yellow_min + red_min, abs=2.0)


def test_metabolites_cross_both_warning_lines(analysed):
    res, off = analysed
    m = res["metrics"]
    assert m["glucose_min_g_l"] < float(GL["red_below"])        # 构造值跨过红线（config.simulation）
    assert m["lactate_max_g_l"] > float(LC["red_above"])
    rows = res["metabolite_rows"]
    assert rows
    assert rows[-1]["glucose_level"] == an.LEVEL_ERROR         # 末点糖耗竭 → 红
    assert rows[-1]["lactate_level"] == an.LEVEL_ERROR         # 末点乳酸超红线 → 红
    assert rows[0]["glucose_level"] == an.LEVEL_PASS           # 起点 8 g/L 高于目标上限，仍算通过
    assert rows[-1]["level"] == an.LEVEL_ERROR                 # 行级取两者最差
    assert rows[-1]["lactate_mmol_l"] > rows[0]["lactate_mmol_l"]
    # mmol/L 换算必须用 config 分子量（答复#10：乳酸 MW 90.08）
    mw_l = float(CFG["metabolite_limits"]["lactate_mw_g_mol"])
    assert rows[-1]["lactate_mmol_l"] == pytest.approx(rows[-1]["lactate_g_l"] / mw_l * 1000.0, rel=1e-3)
    mw_g = float(CFG["unit_constants"]["glucose_mw_g_mol"])
    assert rows[-1]["glucose_mmol_l"] == pytest.approx(rows[-1]["glucose_g_l"] / mw_g * 1000.0, rel=1e-3)


def test_growth_fit_recovers_config_mu(analysed):
    """公式 6 端到端：模拟数据用 config.simulation.mu_max_per_day 生成，回归必须能反解出来。"""
    res, off = analysed
    fit = res["mu_fit"]
    assert fit["ok"] is True, fit.get("reason")
    assert fit["mu_per_day"] == pytest.approx(float(SIM["mu_max_per_day"]), rel=0.05)
    assert fit["r_squared"] > 0.99
    assert res["metrics"]["doubling_time_hours"] == pytest.approx(
        __import__("math").log(2.0) / (float(SIM["mu_max_per_day"]) / 24.0), rel=0.05)
    peak = float(SIM["peak_density_mcells_ml"])
    assert peak * 0.9 <= res["metrics"]["peak_density_mcells_ml"] <= peak   # 逐日取样，峰值只能≤真实峰值


def test_harvest_hint_triggers_on_config_viability(analysed):
    res, off = analysed
    assert res["harvest"]["level"] == an.LEVEL_WARN
    assert str(int(float(CFG["harvest_hint"]["viability_below_percent"]))) in res["harvest"]["text"]
    assert res["is_simulated"] is True
    assert res["generated_at"]


def test_report_sections_and_csv_export(analysed, tmp_path):
    res, off = analysed
    secs = an.report_sections(res)
    assert len(secs) == 7
    assert secs[0][0] == "批次关键参数摘要"
    head = an.report_disclaimer_lines(res, CFG)
    assert any(MARKER in " ".join(row) for row in head), head      # 模拟数据必须在抬头显式标注
    path = tmp_path / "分析报告.csv"
    out = an.export_report_csv(res, path, cfg=CFG)
    enc = str(CFG["analysis"]["report_export"]["csv_encoding"])
    text = Path(out).read_text(encoding=enc)
    assert MARKER in text
    assert "批次关键参数摘要" in text
    assert "需人工复核" in text                                    # AGENTS.md 硬约束 6
    assert "收获建议" in text
    assert Path(out).read_bytes().startswith(b"\xef\xbb\xbf")   # utf-8-sig 有 BOM，Excel 双击不乱码
    # 空结果也不能崩（用户可能只导入了一半数据）
    empty = an.export_report_csv({"metrics": {}, "generated_at": ""}, tmp_path / "空报告.csv", CFG)
    assert empty.exists()
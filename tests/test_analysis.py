# -*- coding: utf-8 -*-
"""离线分析核心算法单元测试（第五轮 · 模块 3）。
期望值来源只有两类，绝不自编工艺结论：
  1) requirements.md 3.2 公式 6：μ = (ln X2 − ln X1) / (t2 − t1)，以及 ln2/μ = 倍增时间；
  2) config.yaml 里用户拍板的阈值（do_alarm / metabolite_limits / harvest_hint / analysis），
     测试先把阈值读出来，再构造"刚好跨过阈值"的数据来断言分级结果。
浮点比较一律 pytest.approx。"""
import math

import pytest

from cell_planner.core import analysis as an
from cell_planner.core.config_loader import get_config
from cell_planner.io_.csv_reader import Dataset

CFG = get_config()
DA = CFG["do_alarm"]
DEV = float(DA["deviation_yellow_points"])
YELLOW_MIN = float(DA["deviation_yellow_minutes"])
RED_MIN = float(DA["deviation_red_minutes"])
ABS_RED = float(DA["absolute_red_percent"])
SETPOINT = float(CFG["process_defaults"]["do_percent"]["set"])
THRESHOLD = SETPOINT - DEV
GL = CFG["metabolite_limits"]["glucose_g_l"]
LC = CFG["metabolite_limits"]["lactate_g_l"]
HARVEST_VIA = float(CFG["harvest_hint"]["viability_below_percent"])
MIN_FIT_POINTS = int(CFG["analysis"]["growth_fit_min_points"])
STEP_H = 1.0 / 60.0          # 1 分钟采样间隔（技术设定，不是工艺参数）


def mk_series(n_minutes, fn):
    t = [i * STEP_H for i in range(n_minutes + 1)]
    return t, [fn(x) for x in t]


def mk_dataset(kind, **series):
    ds = Dataset(path="内存构造.csv", kind=kind)
    keys = [k for k in series if k != "t"]
    ds.t_hours = list(series["t"])
    ds.n_points = len(ds.t_hours)
    for k in keys:
        ds.series[k] = list(series[k])
    return ds


class TestFormula6Mu:
    """requirements 3.2 公式 6。"""

    def test_mu_between_hours_is_ln_ratio_over_dt(self):
        got = an.mu_between_hours(1.0, 0.0, 2.0, 24.0)
        assert got == pytest.approx(math.log(2.0) / 24.0)

    def test_mu_between_hours_fourfold_in_48h(self):
        got = an.mu_between_hours(0.4, 0.0, 1.6, 48.0)
        assert got == pytest.approx(math.log(4.0) / 48.0)

    def test_mu_between_hours_requires_forward_time(self):
        """公式 6 的 t2 必须晚于 t1：时间倒序要报中文错误，不能给出符号相反的 μ。"""
        forward = an.mu_between_hours(1.0, 0.0, 2.0, 24.0)
        assert forward == pytest.approx(math.log(2.0) / 24.0)
        with pytest.raises(ValueError, match="必须晚于"):
            an.mu_between_hours(2.0, 24.0, 1.0, 0.0)

    @pytest.mark.parametrize("x1,x2,t1,t2", [(0.0, 1.0, 0.0, 24.0), (1.0, -2.0, 0.0, 24.0),
                                             (1.0, 2.0, 5.0, 5.0), (None, 2.0, 0.0, 24.0)])
    def test_mu_between_hours_rejects_illegal_input(self, x1, x2, t1, t2):
        with pytest.raises(ValueError):
            an.mu_between_hours(x1, t1, x2, t2)

    def test_mu_segments_matches_formula6(self):
        pts = [(0.0, 1.0), (24.0, 2.0), (48.0, 2.0)]
        segs = an.mu_segments(pts)
        assert len(segs) == len(pts) - 1
        assert segs[0]["mu_per_hour"] == pytest.approx(math.log(2.0) / 24.0)
        assert segs[0]["mu_per_day"] == pytest.approx(segs[0]["mu_per_hour"] * 24.0)
        assert segs[0]["doubling_time_hours"] == pytest.approx(24.0)
        assert segs[1]["mu_per_hour"] == pytest.approx(0.0)
        assert segs[1]["doubling_time_hours"] is None

    def test_mu_segments_skips_missing_and_bad_points(self):
        """中间点为空值时跳过该点，用前后两点组成 1 段；点太少则返回空列表。"""
        segs = an.mu_segments([(0.0, 1.0), (24.0, None), (48.0, 2.0)])
        assert len(segs) == 1
        assert segs[0]["t1_h"] == pytest.approx(0.0)
        assert segs[0]["t2_h"] == pytest.approx(48.0)
        assert segs[0]["mu_per_hour"] == pytest.approx(math.log(2.0) / 48.0)
        assert an.mu_segments([]) == []
        assert an.mu_segments([(0.0, 1.0)]) == []
        assert an.mu_segments([(0.0, 1.0), (24.0, -3.0)]) == []


class TestLogPhaseFit:
    """对数期回归：纯指数数据的斜率必须还原出输入 μ（公式 6 的连续形式）。"""

    @pytest.mark.parametrize("mu_per_day", [0.3, 0.5, 0.8])
    def test_fit_recovers_exponential_rate(self, mu_per_day):
        x0 = 0.5
        pts = [(i * 24.0, x0 * math.exp(mu_per_day * i)) for i in range(6)]
        fit = an.fit_growth_mu(pts, CFG)
        assert fit["ok"] is True
        assert fit["mu_per_day"] == pytest.approx(mu_per_day, rel=1e-6)
        assert fit["doubling_time_hours"] == pytest.approx(math.log(2.0) / (mu_per_day / 24.0))
        assert fit["r_squared"] == pytest.approx(1.0)

    def test_exponential_window_drops_plateau_phase(self):
        mu_per_day = 0.6
        rising = [(i * 24.0, 0.5 * math.exp(mu_per_day * i)) for i in range(5)]
        plateau = [(i * 24.0, rising[-1][1]) for i in range(5, 8)]
        fit = an.fit_growth_mu(rising + plateau, CFG)
        assert fit["ok"] is True
        assert fit["window_hours"][1] <= rising[-1][0]
        assert fit["n_points_used"] <= len(rising) + 1
        assert fit["mu_per_day"] == pytest.approx(mu_per_day, rel=0.05)

    def test_too_few_points_degrades_instead_of_crashing(self):
        pts = [(0.0, 1.0), (24.0, 1.6), (48.0, 1.6), (72.0, 1.6)]
        fit = an.fit_growth_mu(pts, CFG)
        assert fit["ok"] is False
        assert str(MIN_FIT_POINTS) in fit["reason"]

    def test_insufficient_points_raise_chinese_error(self):
        with pytest.raises(ValueError, match="不足"):
            an.fit_growth_mu([(0.0, 1.0)])
        with pytest.raises(ValueError):
            an.fit_growth_mu([])


class TestDoAlarmScan:
    """答复#7：低于设定点 dev 个百分点，持续黄线分钟报黄、红线分钟报红；跌破绝对红线立即报红。"""

    def test_stable_do_has_no_event(self):
        t, v = mk_series(int(RED_MIN * 4), lambda x: SETPOINT + 0.4 * math.sin(x))
        assert an.do_alarm_scan(t, v, SETPOINT, CFG) == []

    def test_just_below_yellow_duration_is_not_reported(self):
        minutes = int(YELLOW_MIN - 1)
        t, v = mk_series(minutes + 2, lambda x: (THRESHOLD - 1.0) if 1.0 <= x * 60.0 < 1.0 + minutes else SETPOINT)
        assert an.do_alarm_scan(t, v, SETPOINT, CFG) == []

    def test_yellow_duration_reports_warn(self):
        minutes = int(YELLOW_MIN + 1)
        dip_start, dip_end = 1.0, 1.0 + minutes
        t, v = mk_series(int(dip_end) + 2,
                         lambda x: (THRESHOLD - 1.0) if dip_start <= x * 60.0 <= dip_end else SETPOINT)
        events = an.do_alarm_scan(t, v, SETPOINT, CFG)
        assert [e.level for e in events] == [an.LEVEL_WARN]
        assert events[0].kind == "deviation"
        assert events[0].duration_minutes == pytest.approx(minutes)
        assert events[0].threshold == pytest.approx(THRESHOLD)

    def test_red_duration_reports_error(self):
        minutes = int(RED_MIN + 1)
        dip_start, dip_end = 2.0, 2.0 + minutes
        t, v = mk_series(int(dip_end) + 2,
                         lambda x: (THRESHOLD - 1.0) if dip_start <= x * 60.0 <= dip_end else SETPOINT)
        events = an.do_alarm_scan(t, v, SETPOINT, CFG)
        assert [e.level for e in events] == [an.LEVEL_ERROR]
        assert events[0].duration_minutes == pytest.approx(minutes)

    def test_absolute_red_line_reports_immediately(self):
        t = [0.0, STEP_H, 2 * STEP_H, 3 * STEP_H]
        v = [SETPOINT, ABS_RED - 1.0, ABS_RED - 1.0, SETPOINT]
        events = an.do_alarm_scan(t, v, SETPOINT, CFG)
        absolute = [e for e in events if e.kind == "absolute"]
        assert absolute and absolute[0].level == an.LEVEL_ERROR
        assert absolute[0].threshold == pytest.approx(ABS_RED)

    def test_isolated_dips_are_split_by_sampling_gap(self):
        """每隔很久出现一个低点：单点时长 0 < 黄线分钟，不应报为报警（避免误报）。"""
        t, v = [], []
        for i, only_low in enumerate((True, False, False, True, False, False)):
            t.append(i * 6 * STEP_H * 60)
            v.append(THRESHOLD - 1.0 if only_low else SETPOINT)
        assert [e for e in an.do_alarm_scan(t, v, SETPOINT, CFG) if e.kind == "deviation"] == []

    def test_missing_values_are_skipped(self):
        """空值/非数字点被剔除；剔除处形成采样缺口，缺口前的短段（<黄线分钟）不误报。"""
        minutes = int(YELLOW_MIN + RED_MIN + 10)
        t, v = mk_series(minutes, lambda x: (THRESHOLD - 1.0) if x * 60.0 >= 3 else SETPOINT)
        v[7] = None
        v[8] = "不是数字"
        t[9] = None
        events = an.do_alarm_scan(t, v, SETPOINT, CFG)
        assert [e.kind for e in events] == ["deviation"]
        assert events[0].start_h == pytest.approx(10 * STEP_H)      # 第 10 分钟起才是第二段
        assert events[0].duration_minutes == pytest.approx(minutes - 10, rel=1e-6)
        assert events[0].level in (an.LEVEL_WARN, an.LEVEL_ERROR)

    def test_too_few_points_raises_chinese_error(self):
        with pytest.raises(ValueError, match="不足"):
            an.do_alarm_scan([0.0], [50.0], SETPOINT, CFG)
        with pytest.raises(ValueError):
            an.do_alarm_scan([], [], SETPOINT, CFG)

    def test_summary_counts_events(self):
        minutes = int(RED_MIN + 1)
        t, v = mk_series(minutes + 10,
                         lambda x: (THRESHOLD - 1.0) if x * 60.0 < minutes else SETPOINT)
        events = an.do_alarm_scan(t, v, SETPOINT, CFG)
        s = an.do_alarm_summary(events)
        assert s["n_events"] == len(events) == 1
        assert s["n_red"] == 1 and s["n_yellow"] == 0 and s["n_absolute_red"] == 0
        assert s["deviation_minutes"] == pytest.approx(minutes, rel=1e-6)
        assert s["longest_deviation_minutes"] == pytest.approx(minutes, rel=1e-6)
        assert s["absolute_red_minutes"] == pytest.approx(0.0)
        assert an.do_alarm_summary([])["n_events"] == 0


class TestDoExtrapolation:
    def test_linear_decline_minutes_to_threshold(self):
        lookback = float(CFG["analysis"]["do_extrapolation"]["lookback_hours"])
        slope = 2.0                       # 每小时下降 2 个百分点（技术构造值）
        n_h = int(lookback) + 6
        t, v = mk_series(n_h * 60, lambda x: 80.0 - slope * x)
        out = an.do_extrapolation(t, v, SETPOINT, CFG)
        assert out["ok"] is True
        last_v = v[-1]
        assert out["slope_percent_per_hour"] == pytest.approx(-slope, abs=0.05)
        assert out["threshold_deviation_percent"] == pytest.approx(THRESHOLD)
        assert out["minutes_to_deviation"] == pytest.approx((last_v - THRESHOLD) / slope * 60.0, rel=0.05)

    def test_already_below_threshold_is_zero(self):
        t = [0.0, 1.0, 2.0, 3.0]
        v = [THRESHOLD + 1, THRESHOLD - 1, THRESHOLD - 2, THRESHOLD - 3]
        out = an.do_extrapolation(t, v, SETPOINT, CFG)
        assert out["ok"] is True
        assert out["minutes_to_deviation"] == 0.0

    def test_no_data_returns_note(self):
        out = an.do_extrapolation([0.0, 1.0], [None, None], SETPOINT, CFG)
        assert out["ok"] is False
        assert out["note"]

    def test_rising_do_is_reported_as_not_declining(self):
        """最近窗口内 DO 在上升 → 不外推，只给中文说明（不得凭空给出倒计时）。"""
        t, v = mk_series(240, lambda x: 40.0 + x / 60.0)
        out = an.do_extrapolation(t, v, SETPOINT, CFG)
        assert out["ok"] is False
        assert "没有下降趋势" in out["note"]
        assert out["slope_percent_per_hour"] >= 0
        assert "minutes_to_deviation" not in out


class TestMetaboliteLimits:
    """答复#10：葡萄糖黄 <2、红 <0.5，目标 2–4；乳酸黄 >2、红 >4；同时给 mmol/L。"""

    def test_glucose_three_levels_from_config_thresholds(self):
        red, yellow = float(GL["red_below"]), float(GL["yellow_below"])
        lo, hi = [float(x) for x in GL["target_range"]]
        assert an.glucose_flag(red * 0.5, CFG)["level"] == an.LEVEL_ERROR
        assert an.glucose_flag((red + yellow) / 2.0, CFG)["level"] == an.LEVEL_WARN
        assert an.glucose_flag((lo + hi) / 2.0, CFG)["level"] == an.LEVEL_PASS
        assert an.glucose_flag(hi * 3, CFG)["level"] == an.LEVEL_PASS

    def test_lactate_three_levels_from_config_thresholds(self):
        yellow, red = float(LC["yellow_above"]), float(LC["red_above"])
        assert an.lactate_flag(red * 1.5, CFG)["level"] == an.LEVEL_ERROR
        assert an.lactate_flag((yellow + red) / 2.0, CFG)["level"] == an.LEVEL_WARN
        assert an.lactate_flag(yellow * 0.5, CFG)["level"] == an.LEVEL_PASS

    def test_missing_metabolite_value_is_neutral(self):
        assert an.glucose_flag(None, CFG)["level"] == an.LEVEL_NONE
        assert an.lactate_flag(None, CFG)["level"] == an.LEVEL_NONE

    def test_illegal_metabolite_value_does_not_crash(self):
        assert an.glucose_flag(-1.0, CFG)["level"] == an.LEVEL_ERROR
        assert an.lactate_flag(-1.0, CFG)["level"] == an.LEVEL_PASS

    def test_mw_comes_from_config(self):
        assert an.mw_g_per_mol("lactate", CFG) == pytest.approx(float(CFG["metabolite_limits"]["lactate_mw_g_mol"]))
        assert an.mw_g_per_mol("glucose", CFG) == pytest.approx(float(CFG["unit_constants"]["glucose_mw_g_mol"]))
        assert an.mw_g_per_mol("葡萄糖", CFG) == an.mw_g_per_mol("glucose", CFG)
        with pytest.raises(ValueError, match="不认识"):
            an.mw_g_per_mol("乙醇")

    def test_g_per_l_to_mmol_identity(self):
        mw = an.mw_g_per_mol("lactate", CFG)
        assert an.g_per_l_to_mmol_per_l(1.0, mw) == pytest.approx(1000.0 / mw)
        assert an.g_per_l_to_mmol_per_l(2.0, mw) == pytest.approx(2.0 * 1000.0 / mw)

    def test_conversion_guards(self):
        with pytest.raises(ValueError, match="分子量"):
            an.g_per_l_to_mmol_per_l(1.0, 0.0)
        with pytest.raises(ValueError, match="为空"):
            an.g_per_l_to_mmol_per_l(None, 90.08)

    def test_metabolite_rows_show_both_units_and_worst_level(self):
        gl = float(GL["red_below"]) * 0.5
        lc = float(LC["red_above"]) * 1.5
        rows = an.metabolite_rows([0.0, 24.0], [gl, None], [lc, None], CFG)
        assert len(rows) == 2
        r0 = rows[0]
        assert r0["glucose_mmol_l"] == pytest.approx(gl / an.mw_g_per_mol("glucose", CFG) * 1000.0)
        assert r0["lactate_mmol_l"] == pytest.approx(lc / an.mw_g_per_mol("lactate", CFG) * 1000.0)
        assert r0["level"] == an.LEVEL_ERROR
        assert rows[1]["glucose_level"] == an.LEVEL_NONE


class TestHarvestAdvice:
    def test_low_viability_and_declining_density(self):
        via = [(0.0, HARVEST_VIA + 5), (24.0, HARVEST_VIA - 5)]
        den = [(0.0, 15.0), (24.0, 12.0)]
        got = an.harvest_advice(den, via, CFG)
        assert got["level"] == an.LEVEL_WARN
        assert "建议收获" in got["text"]

    def test_low_viability_without_decline_asks_manual_check(self):
        got = an.harvest_advice([(0.0, 12.0), (24.0, 15.0)], [(0.0, HARVEST_VIA - 5)], CFG)
        assert got["level"] == an.LEVEL_WARN
        assert "人工确认" in got["text"]

    def test_good_viability_is_pass(self):
        got = an.harvest_advice([(0.0, 12.0), (24.0, 15.0)], [(0.0, HARVEST_VIA + 10)], CFG)
        assert got["level"] == an.LEVEL_PASS

    def test_no_viability_data_is_neutral(self):
        got = an.harvest_advice([(0.0, 1.0), (24.0, 2.0)], [], CFG)
        assert got["level"] == an.LEVEL_NONE
        assert got["text"]


class TestAnalyzeEntry:
    def make(self):
        minutes = int(RED_MIN + 1)
        t_c, do = mk_series(minutes + 4,
                            lambda x: (THRESHOLD - 1.0) if 2.0 <= x * 60.0 <= 2.0 + minutes else SETPOINT)
        control = mk_dataset("control", t=t_c, do_percent=do,
                             temperature_c=[37.0] * len(t_c), ph=[7.05] * len(t_c))
        mu = 0.5
        t_off = [i * 24.0 for i in range(6)]
        offline = mk_dataset("offline", t=t_off,
                             cell_density_mcells_ml=[0.5 * math.exp(mu * i) for i in range(6)],
                             viability_percent=[99.0, 98.0, 95.0, 90.0, HARVEST_VIA - 1.0, HARVEST_VIA - 3.0],
                             glucose_g_l=[6.0, 4.0, float(GL["yellow_below"]) / 2, float(GL["red_below"]) / 2, 0.2, 0.1],
                             lactate_g_l=[0.5, 1.0, float(LC["yellow_above"]) / 2, float(LC["red_above"]) * 1.2, 4.0, 4.5])
        return control, offline

    def test_full_analysis(self):
        control, offline = self.make()
        res = an.analyze(control, offline, SETPOINT, CFG)
        assert res["errors"] == []
        assert res["metrics"]["peak_density_mcells_ml"] == pytest.approx(max(offline.values("cell_density_mcells_ml")))
        assert res["metrics"]["glucose_min_g_l"] == pytest.approx(min(offline.values("glucose_g_l")))
        assert res["metrics"]["lactate_max_g_l"] == pytest.approx(max(offline.values("lactate_g_l")))
        assert res["metrics"]["do_min_percent"] == pytest.approx(min(control.values("do_percent")))
        assert res["mu_fit"]["mu_per_day"] == pytest.approx(0.5, rel=0.05)
        assert res["do_summary"]["n_red"] >= 1
        assert res["harvest"]["level"] == an.LEVEL_WARN
        assert res["generated_at"]

    def test_do_setpoint_defaults_from_config(self):
        control, offline = self.make()
        res = an.analyze(control, offline, None, CFG)
        assert any("process_defaults" in n for n in res["notes"])

    def test_simulated_flag_propagates(self):
        control, _ = self.make()
        control.is_simulated = True
        res = an.analyze(control, None, SETPOINT, CFG)
        assert res["is_simulated"] is True
        assert res["metrics"]["is_simulated"] is True

    def test_no_datasets_does_not_crash(self):
        res = an.analyze(None, None, SETPOINT, CFG)
        assert res["metrics"]["n_control_points"] == 0
        assert res["harvest"]["level"] == an.LEVEL_NONE
        assert res["do_events"] == []

    def test_errors_are_passed_through(self):
        control, _ = self.make()
        control.errors.append("时间列既不是可识别的日期时间")
        res = an.analyze(control, None, SETPOINT, CFG)
        assert "时间列既不是可识别的日期时间" in res["errors"]

    def test_all_none_columns_degrade(self):
        control = mk_dataset("control", t=[0.0, 1.0, 2.0], do_percent=[None, None, None])
        res = an.analyze(control, None, SETPOINT, CFG)
        assert res["do_events"] == []
        assert res["metrics"]["do_min_percent"] is None

    def test_metric_labels_come_from_config(self):
        keys = [str(x["key"]) for x in CFG["template_library"]["compare_fields"]]
        for key in keys:
            assert an.metric_label(key, CFG)

    def test_report_sections_shape(self):
        control, offline = self.make()
        res = an.analyze(control, offline, SETPOINT, CFG)
        sections = an.report_sections(res, CFG)
        assert len(sections) >= 5
        for title, header, rows in sections:
            assert title and header and all(len(r) == len(header) for r in rows)
        assert any("DO 报警" in s[0] for s in sections)
        assert any("代谢" in s[0] for s in sections)
        assert any("μ" in s[0] for s in sections)

    def test_report_sections_survives_empty_result(self):
        sections = an.report_sections({"metrics": {}, "notes": []}, CFG)
        assert sections and all(isinstance(s[0], str) for s in sections)


class TestDoAlarmGapFromConfig:
    """DO 事件"断档"判定的两个阈值来自 config.do_alarm（gap_default_hours / gap_max_factor），代码不写死。"""

    LOW = THRESHOLD - 1.0
    SPAN_H = YELLOW_MIN / 60.0 / 3.0                      # 每段内部只有黄线时长的 1/3（5 分钟）

    def _series(self):
        gap_h = float(DA["gap_default_hours"]) * float(DA["gap_max_factor"]) + 0.5
        t = [0.0, self.SPAN_H, self.SPAN_H + gap_h, self.SPAN_H + gap_h + self.SPAN_H]
        return t, [self.LOW] * 4, gap_h

    def test_gap_keys_exist(self):
        assert float(DA["gap_default_hours"]) > 0.0
        assert float(DA["gap_max_factor"]) >= 1.0

    def test_gap_beyond_config_factor_splits_event(self):
        """缺口大于"中位取样间隔 × 倍数" → 事件被拆断，两段各 5 分钟，都不到黄线时长 → 不报警。"""
        t, v, gap_h = self._series()
        assert an.do_alarm_scan(t, v, SETPOINT, CFG) == []

    def test_raising_config_factor_merges_event(self):
        """把同一个 config 里的倍数放大（其余不动）→ 缺口被允许 → 合并成一段 85 分钟 → 报红。"""
        t, v, gap_h = self._series()
        cfg2 = dict(CFG)
        da2 = dict(CFG["do_alarm"])
        da2["gap_max_factor"] = (gap_h + self.SPAN_H) / self.SPAN_H
        cfg2["do_alarm"] = da2
        events = an.do_alarm_scan(t, v, SETPOINT, cfg2)
        assert [e.level for e in events] == [an.LEVEL_ERROR]
        assert events[0].duration_minutes == pytest.approx((t[-1] - t[0]) * 60.0)
        assert events[0].duration_minutes > RED_MIN

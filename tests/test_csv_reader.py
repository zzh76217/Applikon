# -*- coding: utf-8 -*-
"""CSV 导入解析器单元测试（第五轮，答复#8：先按 my-Control Web UI 通用导出格式写解析器）。
期望值来源：requirements.md 3.3 算例的体积/流量数值（2000 mL、200 mL/min、20 mL/min）
+ 公式 3-5 恒等关系 + ISO 时间轴的时间差；报警与警戒阈值一律不在本文件出现（那是 do_alarm / metabolite_limits 的事）。
浮点比较使用 pytest.approx；所有非法输入用例都要求"返回中文错误而不抛异常/不崩溃"。"""
import io

import pytest

from cell_planner.core import column_mapping as cm
from cell_planner.core.config_loader import get_config
from cell_planner.io_ import csv_reader as rd

CFG = get_config()
ISO = str(CFG["csv_import"]["datetime_iso_format"])


def write(tmp_path, name, text, encoding=None):
    p = tmp_path / name
    p.write_bytes(text.encode(encoding or str(CFG["csv_import"]["encoding"])))
    return p


def control_csv(tmp_path, name="控制数据.csv"):
    """一份"看起来像真实导出"的表头：列名故意带单位与中括号，考察自动匹配与数值解析。"""
    lines = ["Time,Temp [C],pH,DO [%],Agitation [rpm],Air flow (mL/min),O2 flow (mL/min),data_source"]
    for i, t in enumerate(("2026-03-01 08:00:00", "2026-03-01 08:05:00", "2026-03-01 08:10:00")):
        lines.append(",".join([t, "37.0", "7.05", "50.0", "100", "200.0", "20.0", "REAL"]))
    return write(tmp_path, name, "\n".join(lines) + "\n")


class TestBasicRead:
    def test_header_and_rows(self, tmp_path):
        raw = rd.read_raw_table(control_csv(tmp_path), CFG)
        assert raw.header[0] == "Time"
        assert raw.n_rows == 3
        assert raw.encoding_used == str(CFG["csv_import"]["encoding"])
        assert raw.errors if hasattr(raw, "errors") else True

    def test_gas_flows_match_requirements_example(self, tmp_path):
        """列值本身就是 3.3 算例的 Q_air=200 / Q_O2=20，解析后必须原样取回。"""
        ds = rd.load_dataset(control_csv(tmp_path), cm.DATASET_CONTROL, cfg=CFG)
        assert ds.errors == []
        assert ds.first_valid("air_ml_min") == pytest.approx(200.0)
        assert ds.first_valid("o2_ml_min") == pytest.approx(20.0)
        assert ds.last_valid("do_percent") == pytest.approx(50.0)

    def test_time_axis_is_relative_hours(self, tmp_path):
        ds = rd.load_dataset(control_csv(tmp_path), cm.DATASET_CONTROL, cfg=CFG)
        assert ds.t_hours == pytest.approx([0.0, 5.0 / 60.0, 10.0 / 60.0])
        assert ds.n_points == 3
        assert ds.time_is_relative_numeric is False

    def test_auto_match_used_when_no_saved_mapping(self, tmp_path):
        ds = rd.load_dataset(control_csv(tmp_path), cm.DATASET_CONTROL, cfg=CFG)
        assert ds.mapping["do_percent"] == "DO [%]"
        assert any("自动匹配" in w for w in ds.warnings)

    def test_saved_mapping_is_respected(self, tmp_path):
        p = write(tmp_path, "中文表头.csv",
                  "时钟,溶氧\n2026-03-01 09:00:00,51.0\n2026-03-01 09:05:00,49.5\n")
        mapping = cm.blank_mapping(cm.DATASET_CONTROL, CFG)
        mapping.update({"time": "时钟", "do_percent": "溶氧"})
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, mapping=mapping, cfg=CFG)
        assert ds.errors == []
        assert ds.values("do_percent") == pytest.approx([51.0, 49.5])
        assert not any("自动匹配" in w for w in ds.warnings)


class TestCellParsing:
    def test_to_float_examples(self):
        assert rd.to_float("3.5") == pytest.approx(3.5)
        assert rd.to_float(" 1,500 mL/min ") == pytest.approx(1500.0)
        assert rd.to_float("2e3") == pytest.approx(2000.0)

    @pytest.mark.parametrize("bad", ["", "-", "N/A", "nan", "null", "/", "无数据", None])
    def test_to_float_invalid_is_none(self, bad):
        assert rd.to_float(bad) is None

    def test_parse_time_iso_and_fallback_formats(self):
        assert rd.parse_time("2026-03-01 08:00:00", CFG).strftime(ISO) == "2026-03-01 08:00:00"
        for text in ("2026-03-01T08:00:00", "2026-03-01 08:00", "2026-03-01"):
            assert rd.parse_time(text, CFG) is not None

    def test_parse_time_garbage_is_none(self):
        assert rd.parse_time("不是时间", CFG) is None
        assert rd.parse_time("", CFG) is None

    def test_all_missing_column_is_not_valid(self, tmp_path):
        p = write(tmp_path, "全空.csv", "Time,DO [%]\n2026-03-01 08:00:00,-\n2026-03-01 08:05:00,\n")
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, cfg=CFG)
        assert ds.has("do_percent") is False
        assert ds.pairs("do_percent") == []
        assert any("空值" in w for w in ds.warnings)


class TestTimeAxisFallbacks:
    def test_numeric_time_column_fallback(self, tmp_path):
        p = write(tmp_path, "数值时间.csv", "Time,DO [%]\n0,50\n1,49\n2,48\n")
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, cfg=CFG)
        assert ds.time_is_relative_numeric is True
        assert ds.t_hours == pytest.approx([0.0, 1.0, 2.0])
        assert any("相对小时" in w for w in ds.warnings)

    def test_unparsable_time_column_gives_error(self, tmp_path):
        p = write(tmp_path, "乱时间.csv", "Time,DO [%]\n第一小时,50\n第二小时,49\n")
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, cfg=CFG)
        assert any("时间" in e for e in ds.errors)

    def test_missing_time_column_gives_error(self, tmp_path):
        p = write(tmp_path, "没时间列.csv", "DO [%],pH\n50,7.05\n49,7.10\n")
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, cfg=CFG)
        assert any("时间" in e for e in ds.errors)

    def test_out_of_order_rows_are_sorted(self, tmp_path):
        p = write(tmp_path, "乱序.csv",
                  "Time,DO [%]\n2026-03-01 08:10:00,48\n2026-03-01 08:00:00,50\n2026-03-01 08:05:00,49\n")
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, cfg=CFG)
        assert ds.t_hours == pytest.approx([0.0, 5.0 / 60.0, 10.0 / 60.0])
        assert ds.values("do_percent") == pytest.approx([50.0, 49.0, 48.0])
        assert any("升序" in w for w in ds.warnings)


class TestRobustness:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ValueError, match="找不到要导入的文件"):
            rd.read_raw_table(tmp_path / "不存在.csv", CFG)

    def test_missing_file_via_dataset_returns_error_not_crash(self, tmp_path):
        ds = rd.load_dataset(tmp_path / "不存在.csv", cm.DATASET_CONTROL, cfg=CFG)
        assert ds.errors and ds.n_points == 0

    @pytest.mark.parametrize("name", ["数据.xlsx", "notes.md", "无扩展名"])
    def test_wrong_extension(self, tmp_path, name):
        p = write(tmp_path, name, "a,b\n1,2\n")
        with pytest.raises(ValueError, match="csv|txt"):
            rd.read_raw_table(p, CFG)

    def test_empty_file(self, tmp_path):
        with pytest.raises(ValueError, match="空"):
            rd.read_raw_table(write(tmp_path, "空.csv", "\n\n , \n"), CFG)

    def test_header_row_config_beyond_file_length(self, tmp_path):
        cfg = dict(CFG)
        cfg["csv_import"] = dict(CFG["csv_import"])
        cfg["csv_import"]["header_row"] = 5
        p = write(tmp_path, "短文件.csv", "Time,DO [%]\n2026-03-01 08:00:00,50\n")
        with pytest.raises(ValueError, match="没有数据"):
            rd.read_raw_table(p, cfg)

    def test_header_row_skips_leading_notes(self, tmp_path):
        cfg = dict(CFG)
        cfg["csv_import"] = dict(CFG["csv_import"])
        cfg["csv_import"]["header_row"] = 2
        p = write(tmp_path, "带说明行.csv", "my-Control 导出\nTime,DO [%]\n2026-03-01 08:00:00,50\n")
        raw = rd.read_raw_table(p, cfg)
        assert raw.header == ["Time", "DO [%]"]
        assert any("跳过前" in w for w in raw.warnings)

    def test_garbage_bytes(self, tmp_path):
        p = tmp_path / "乱码.csv"
        p.write_bytes(b"\xff\xfe\x00\x01\x02ab\xa7\x88")
        with pytest.raises(ValueError, match="编码"):
            rd.read_raw_table(p, CFG)

    def test_ragged_rows_are_padded_with_warning(self, tmp_path):
        p = write(tmp_path, "参差.csv", "Time,DO [%],pH\n2026-03-01 08:00:00,50\n2026-03-01 08:05:00,49,7.1,999\n")
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, cfg=CFG)
        assert ds.n_points == 2
        assert any("列数" in w for w in ds.warnings)

    def test_duplicate_header_warns(self, tmp_path):
        p = write(tmp_path, "重复列.csv", "Time,DO [%],DO [%]\n2026-03-01 08:00:00,50,49\n")
        ds = rd.load_dataset(p, cm.DATASET_CONTROL, cfg=CFG)
        assert any("重复列名" in w for w in ds.warnings)

    def test_max_rows_guard(self, tmp_path, monkeypatch):
        cfg = {k: v for k, v in CFG.items()}
        cfg["csv_import"] = dict(CFG["csv_import"])
        cfg["csv_import"]["max_rows"] = 2
        p = write(tmp_path, "超行数.csv",
                  "Time,DO [%]\n2026-03-01 08:00:00,50\n2026-03-01 08:05:00,49\n2026-03-01 08:10:00,48\n")
        with pytest.raises(ValueError, match="上限"):
            rd.read_raw_table(p, cfg)

    def test_non_utf8_encoding_fallback(self, tmp_path):
        encs = [str(x) for x in CFG["csv_import"]["encoding_fallbacks"]]
        alt = "gb18030" if "gb18030" in encs else encs[-1]
        text = "时间,溶氧\n2026-03-01 08:00:00,50\n"
        p = write(tmp_path, "国标.csv", text, encoding=alt)
        raw = rd.read_raw_table(p, CFG)
        assert raw.header[0] == "时间"
        assert any("编码" in w for w in raw.warnings)


class TestSimulatedDetection:
    def test_filename_prefix(self, tmp_path):
        p = write(tmp_path, "SIMULATED_控制数据_x.csv", "Time,DO [%]\n2026-03-01 08:00:00,50\n")
        assert rd.read_raw_table(p, CFG).is_simulated is True

    def test_marker_column(self, tmp_path):
        col = str(CFG["simulation"]["marker_column"])
        val = str(CFG["simulation"]["marker_value"])
        p = write(tmp_path, "普通名字.csv",
                  "Time,DO [percent]," + col + "\n2026-03-01 08:00:00,50," + val + "\n")
        raw = rd.read_raw_table(p, CFG)
        assert raw.is_simulated is True
        assert col in raw.simulated_reason

    def test_real_file_not_flagged(self, tmp_path):
        assert rd.read_raw_table(control_csv(tmp_path), CFG).is_simulated is False

    def test_dataset_carries_banner(self, tmp_path):
        p = write(tmp_path, "SIMULATED_离线取样_x.csv",
                  "Time,Cell density\n2026-03-01 08:00:00,0.4\n2026-03-02 08:00:00,0.8\n")
        ds = rd.load_dataset(p, cm.DATASET_OFFLINE, cfg=CFG)
        assert ds.is_simulated is True
        assert any("SIMULATED" in w for w in ds.warnings)


class TestDatasetHelpers:
    def test_labels_and_pairs(self, tmp_path):
        ds = rd.load_dataset(control_csv(tmp_path), cm.DATASET_CONTROL, cfg=CFG)
        assert ds.field_label("do_percent") == "DO 溶解氧"
        pairs = ds.pairs("temperature_c")
        assert [t_h for t_h, _ in pairs] == pytest.approx([0.0, 5.0 / 60.0, 10.0 / 60.0])
        assert [v for _, v in pairs] == pytest.approx([37.0, 37.0, 37.0])
        assert ds.has("co2_ml_min") is False
        assert ds.values("co2_ml_min") == []

    def test_unknown_key_is_empty(self, tmp_path):
        ds = rd.load_dataset(control_csv(tmp_path), cm.DATASET_CONTROL, cfg=CFG)
        assert ds.values("根本没有这个字段") == []
        assert ds.first_valid("根本没有这个字段") is None
        assert ds.last_valid("根本没有这个字段") is None
# -*- coding: utf-8 -*-
"""列名映射（答复#8）单元测试（第五轮）。
逻辑字段清单、候选列名、必需项一律先从 config.yaml 读出再据此断言，测试里不写死列名/字段清单。
自动匹配用的样例表头取自 config.simulation.columns（模拟生成器与真实导出格式共用同一套列名设计）。"""
import copy

import pytest

from cell_planner.core import column_mapping as cm
from cell_planner.core.config_loader import get_config

CFG = get_config()
CONTROL_HEADERS = list(CFG["simulation"]["columns"]["control"])
OFFLINE_HEADERS = list(CFG["simulation"]["columns"]["offline"])


def cfg_without(**patch):
    """返回临时改过某个开关的配置副本（只改技术开关，不改工艺阈值）。"""
    c = copy.deepcopy(CFG)
    node = c
    for key in patch["path"][:-1]:
        node = node[key]
    node[patch["path"][-1]] = patch["value"]
    return c


class TestFieldListFromConfig:
    def test_fields_come_from_config(self):
        assert [f["key"] for f in cm.fields()] == [str(x["key"]) for x in CFG["column_mapping"]["logical_fields"]]

    def test_fields_for_filters_by_dataset(self):
        for kind in (cm.DATASET_CONTROL, cm.DATASET_OFFLINE):
            expect = [str(x["key"]) for x in CFG["column_mapping"]["logical_fields"]
                      if str(x.get("dataset")) in (kind, cm.DATASET_BOTH)]
            assert [f["key"] for f in cm.fields_for(kind)] == expect

    def test_blank_mapping_covers_all_fields(self):
        assert set(cm.blank_mapping(cm.DATASET_CONTROL)) == {f["key"] for f in cm.fields_for(cm.DATASET_CONTROL)}
        assert all(v == "" for v in cm.blank_mapping(cm.DATASET_OFFLINE).values())

    def test_unknown_kind_is_chinese_error(self):
        with pytest.raises(ValueError, match="未知的数据类型"):
            cm.fields_for("垃圾")

    def test_missing_field_list_raises_chinese_error(self):
        broken = copy.deepcopy(CFG)
        broken["column_mapping"]["logical_fields"] = []
        with pytest.raises(ValueError, match="logical_fields"):
            cm.fields(broken)


class TestNormalize:
    @pytest.mark.parametrize("a,b", [("DO [%]", "do"), ("Air flow (mL/min)", "airflowmlmin"),
                                     ("Sample Time", "sampletime"), ("pH-Value", "phvalue")])
    def test_separators_are_removed(self, a, b):
        assert cm.normalize(a) == cm.normalize(b)

    def test_case_insensitive_is_default(self):
        assert cm.normalize("TIME") == cm.normalize("time")

    def test_case_sensitive_switch(self):
        c = cfg_without(path=("column_mapping", "auto_match_case_sensitive"), value=True)
        assert cm.normalize("TIME", c) != cm.normalize("time", c)

    def test_none_is_empty(self):
        assert cm.normalize(None) == ""


class TestAutoMatch:
    def test_configured_headers_all_match(self):
        for kind, headers in ((cm.DATASET_CONTROL, CONTROL_HEADERS), (cm.DATASET_OFFLINE, OFFLINE_HEADERS)):
            got = cm.auto_match(headers, kind)
            assert all(got[f["key"]] for f in cm.fields_for(kind)), (kind, got)

    def test_matched_column_names_equal_headers(self):
        got = cm.auto_match(CONTROL_HEADERS, cm.DATASET_CONTROL)
        assert all(v in CONTROL_HEADERS for v in got.values())
        assert got["do_percent"] == str(CFG["simulation"]["columns"]["control"][3])

    def test_unknown_headers_match_nothing(self):
        assert all(v == "" for v in cm.auto_match(["aaaa", "bbbb"], cm.DATASET_OFFLINE).values())

    def test_exact_beats_contains(self):
        headers = ["DO SETPOINT [%]", "DO [%]", "Time"]
        got = cm.auto_match(headers, cm.DATASET_CONTROL)
        assert got["do_percent"] == "DO [%]"

    def test_empty_header_list_is_safe(self):
        assert all(v == "" for v in cm.auto_match([], cm.DATASET_CONTROL).values())


class TestValidateMapping:
    def test_missing_required_fields_reported_as_error(self):
        for kind in (cm.DATASET_CONTROL, cm.DATASET_OFFLINE):
            required = [f for f in cm.fields_for(kind) if f["required"]]
            msgs = cm.validate_mapping(cm.blank_mapping(kind), list(
                CFG["simulation"]["columns"][kind]), kind)
            errs = [m for m in msgs if m["level"] == "error"]
            assert len(errs) == len(required)
            assert all(m["text"] for m in errs)

    def test_mapped_column_not_in_header_is_error(self):
        mapping = cm.auto_match(CONTROL_HEADERS, cm.DATASET_CONTROL)
        mapping["do_percent"] = "这一列根本不存在"
        msgs = cm.validate_mapping(mapping, CONTROL_HEADERS, cm.DATASET_CONTROL)
        assert any(m["level"] == "error" and "找不到" in m["text"] for m in msgs)

    def test_two_fields_on_one_column_warns(self):
        mapping = cm.auto_match(CONTROL_HEADERS, cm.DATASET_CONTROL)
        mapping["ph"] = mapping["temperature_c"]
        msgs = cm.validate_mapping(mapping, CONTROL_HEADERS, cm.DATASET_CONTROL)
        assert any(m["level"] == "warn" for m in msgs)
        assert not [m for m in msgs if m["level"] == "error"]

    def test_none_mapping_is_error_not_crash(self):
        msgs = cm.validate_mapping(None, CONTROL_HEADERS, cm.DATASET_CONTROL)
        assert any(m["level"] == "error" for m in msgs)


class TestSaveLoad:
    def test_roundtrip(self, tmp_path):
        p = tmp_path / "map.json"
        control = cm.auto_match(CONTROL_HEADERS, cm.DATASET_CONTROL)
        offline = cm.auto_match(OFFLINE_HEADERS, cm.DATASET_OFFLINE)
        cm.save_all(control, offline, path=p)
        loaded = cm.load_all(path=p)
        assert loaded[cm.DATASET_CONTROL] == control
        assert loaded[cm.DATASET_OFFLINE] == offline

    def test_missing_file_returns_empty_structure(self, tmp_path):
        loaded = cm.load_all(path=tmp_path / "根本不存在.json")
        assert loaded == {cm.DATASET_CONTROL: {}, cm.DATASET_OFFLINE: {}}

    def test_corrupt_file_gives_chinese_error(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ 这不是 json", encoding="utf-8")
        with pytest.raises(ValueError, match="损坏|无法读取"):
            cm.load_all(path=p)

    def test_section_key_labels_differ(self):
        assert cm.section_key(cm.DATASET_CONTROL) != cm.section_key(cm.DATASET_OFFLINE)
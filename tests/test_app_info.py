# -*- coding: utf-8 -*-
"""第六轮单元测试：core/app_info.py（软件身份信息 + 界面文案渲染）。

本文件的模板字符串是「测试专用文案」，只用来验证渲染逻辑；
出厂真实模板的存在性/占位符合法性由 tests/test_config_loader_round6.py 校验。
这里不出现任何工艺参数，因此不违反「阈值只允许来自 config」的硬约束。
"""
from __future__ import annotations

from pathlib import Path

from cell_planner.core import app_info

CFG_FULL = {
    "app_info": {
        "name": "细胞培养接种与批次配置规划软件",
        "version": "9.9.9",
        "round_label": "测试轮次",
        "title_template": "{name}　{version}｜{round_label}｜{mode}",
        "locations_template": "配置 {config}｜数据 {data}｜日志 {log}｜说明书 {manual}",
        "manual_file": "使用说明.txt",
    }
}


# ==================== app_info() ====================
def test_app_info_returns_section_when_present():
    assert app_info.app_info(CFG_FULL)["version"] == "9.9.9"


def test_app_info_missing_or_wrong_type_returns_empty_dict():
    assert app_info.app_info({}) == {}
    assert app_info.app_info(None) == {}
    assert app_info.app_info({"app_info": "不是字典"}) == {}
    assert app_info.app_info({"app_info": 123}) == {}


# ==================== window_title() ====================
def test_window_title_renders_all_four_placeholders():
    title = app_info.window_title(CFG_FULL, "打包版")
    assert "细胞培养接种与批次配置规划软件" in title
    assert "9.9.9" in title
    assert "测试轮次" in title
    assert "打包版" in title
    assert "{" not in title            # 不许残留未替换的占位符


def test_window_title_mode_comes_from_argument_not_config():
    assert app_info.window_title(CFG_FULL, "源码版").endswith("源码版")
    assert "源码版" not in app_info.window_title(CFG_FULL, "打包版")


def test_window_title_default_template_when_config_empty():
    assert app_info.window_title({}, "源码版") == " "      # 默认模板 {name} {version}，两项都空


def test_window_title_falls_back_on_unknown_placeholder():
    cfg = {"app_info": {"name": "测试软件", "title_template": "{name} {不存在的键}"}}
    assert app_info.window_title(cfg, "打包版") == "测试软件（打包版）"


def test_window_title_falls_back_on_positional_placeholder():
    cfg = {"app_info": {"name": "测试软件", "title_template": "{0} 号"}}
    assert app_info.window_title(cfg, "源码版") == "测试软件（源码版）"


def test_window_title_survives_none_config():
    assert isinstance(app_info.window_title(None, "源码版"), str)


# ==================== locations_text() ====================
def test_locations_text_lists_all_paths():
    text = app_info.locations_text(
        CFG_FULL,
        config_path=Path("D:/x/config/config.yaml"),
        data_dir=Path("D:/x/data"),
        log_path=Path("D:/x/logs/软件运行日志.txt"),
        manual_path=Path("D:/x/使用说明.txt"),
    )
    for frag in ("config.yaml", "data", "软件运行日志.txt", "使用说明.txt"):
        assert frag in text


def test_locations_text_empty_when_template_missing():
    assert app_info.locations_text({}, config_path="c", data_dir=Path("d"),
                                   log_path=None, manual_path=None) == ""


def test_locations_text_blanks_missing_log_and_manual_but_keeps_row():
    text = app_info.locations_text(CFG_FULL, config_path="C:/a/config.yaml",
                                   data_dir=Path("C:/a/data"), log_path=None, manual_path=None)
    assert "config.yaml" in text and "data" in text
    assert "｜日志 ｜" in text                      # 日志位留空，不显示错误路径


def test_locations_text_returns_empty_when_config_or_data_missing():
    assert app_info.locations_text(CFG_FULL, config_path=None, data_dir=Path("d"),
                                   log_path=Path("l"), manual_path=Path("m")) == ""
    assert app_info.locations_text(CFG_FULL, config_path=Path("c"), data_dir=None,
                                   log_path=Path("l"), manual_path=Path("m")) == ""


def test_locations_text_empty_string_paths_treated_as_missing():
    assert app_info.locations_text(CFG_FULL, config_path="", data_dir=Path("d"),
                                   log_path=None, manual_path=None) == ""


def test_locations_text_falls_back_on_bad_template():
    cfg = {"app_info": {"locations_template": "配置 {config} {data} {没有这个键}"}}
    assert app_info.locations_text(cfg, config_path="c", data_dir=Path("d"),
                                   log_path=None, manual_path=None) == ""


# ==================== manual_path() ====================
def test_manual_path_joins_config_name_with_root():
    got = app_info.manual_path(CFG_FULL, Path("D:/软件"))
    assert got == Path("D:/软件/使用说明.txt")


def test_manual_path_none_when_name_missing():
    assert app_info.manual_path({}, Path("D:/软件")) is None
    assert app_info.manual_path({"app_info": {"manual_file": "  "}}, Path("D:/软件")) is None


# ==================== tab_titles()（第六轮：小屏可改短，名称进 config） ====================
def test_tab_titles_returns_requested_count():
    cfg = {"app_info": {"tab_titles": ["① 配置与校验", "② 硬件配置"]}}
    assert app_info.tab_titles(cfg, 2) == ["① 配置与校验", "② 硬件配置"]


def test_tab_titles_pads_short_list_with_empty_strings():
    cfg = {"app_info": {"tab_titles": ["只有一个"]}}
    assert app_info.tab_titles(cfg, 3) == ["只有一个", "", ""]


def test_tab_titles_empty_when_section_or_type_missing():
    assert app_info.tab_titles({}, 6) == []
    assert app_info.tab_titles({"app_info": {"tab_titles": "不是列表"}}, 6) == []
    assert app_info.tab_titles({"app_info": {"tab_titles": None}}, 6) == []


def test_tab_titles_strips_spaces_and_keeps_order():
    cfg = {"app_info": {"tab_titles": ["  ① 甲  ", "  ② 乙", None]}}
    assert app_info.tab_titles(cfg, 3) == ["① 甲", "② 乙", ""]


def test_tab_titles_zero_count_returns_empty():
    assert app_info.tab_titles({"app_info": {"tab_titles": ["多余"]}}, 0) == []

# -*- coding: utf-8 -*-
"""第七轮界面结构测试：外层三大板块、板块内子页签、统一外观、映射状态提示条。

只测「页面挂在哪、外观是否取自 config、按钮跳得对不对」，
不碰任何公式/校验/导入/分析逻辑（那些由 test_formulas、test_validators、
test_csv_reader、test_analysis、test_column_mapping 守着，本轮一律未改）。
每个用例用全新窗口：跳转子页签会改当前页，隔离开才互不干扰。
"""
from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                  # noqa: E402

from cell_planner.core import app_info as ai   # noqa: E402
from cell_planner.core import column_mapping as cmap  # noqa: E402
from cell_planner.core import config_loader as cl  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSize              # noqa: E402
from PySide6.QtGui import QIcon               # noqa: E402
from PySide6.QtWidgets import (               # noqa: E402
    QApplication, QGroupBox, QMessageBox, QScrollArea,
)

from cell_planner.ui import common, icons, main_window, theme  # noqa: E402

_MSGBOX_METHODS = ("information", "warning", "critical", "question")
_KEYS = main_window.MainWindow._PAGE_ORDER


@pytest.fixture()
def win(monkeypatch):
    """离屏构建整窗，并把 QMessageBox 静态方法打桩，防止弹窗挂住测试进程。"""
    QApplication.instance() or QApplication([])
    for name in _MSGBOX_METHODS:
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))
    window = main_window.MainWindow()
    yield window
    window.deleteLater()


def _sub_titles(window):
    """按「大板块序号 → 子页签序号」收集全部子页签名称。"""
    out = []
    for sub in window.sub_tabs:
        out.extend([sub.tabText(i) for i in range(sub.count())])
    return out


# ==================== 一、外层只剩 3 个大板块 ====================
def test_outer_tab_count_is_three(win):
    assert win.tabs.count() == 3, "主界面顶部必须只有 3 个大板块"


def test_outer_titles_come_from_config(win):
    cfg = cl.get_config()
    expect = [str(x).strip() for x in cfg["app_info"]["outer_tab_titles"]]
    assert [win.tabs.tabText(i) for i in range(win.tabs.count())] == expect
    assert ai.outer_tab_titles(cfg, 3) == expect


def test_outer_titles_have_no_old_numbering(win):
    """大板块名字里不带 ①–⑥ 序号，序号只留在子页签上（保证跨页文案仍然指得对）。"""
    for name in [win.tabs.tabText(i) for i in range(win.tabs.count())]:
        assert not any(mark in name for mark in "①②③④⑤⑥")


def test_three_plate_names(win):
    assert [win.tabs.tabText(i) for i in range(3)] == ["配置与校验", "分析与对比", "SOP 引导"]


# ==================== 二、原 6 页一页不少，且各就各位 ====================
def test_six_pages_all_present_once(win):
    assert set(win.pages) == set(_KEYS)
    positions = list(win.page_tabs.values())
    assert len(set(positions)) == 6, "同一张页面被挂了两遍"
    assert sum(sub.count() for sub in win.sub_tabs) == 6
    for mark in "①②③④⑤⑥":
        assert any(mark in text for text in _sub_titles(win)), "找不到带 %s 的子页签" % mark


def test_sub_tab_titles_match_config_order(win):
    cfg = cl.get_config()
    expect = [str(x).strip() for x in cfg["app_info"]["tab_titles"]]
    got = [win.sub_tabs[gi].tabText(si) for gi, si in (win.page_tabs[k] for k in _KEYS)]
    assert got == expect


def test_plate1_holds_planner_and_hardware(win):
    assert win.page_tabs["planner"] == (0, 0)
    assert win.page_tabs["hardware"] == (0, 1)
    assert win.sub_tabs[0].count() == 2


def test_plate2_order_is_mapping_then_analysis_then_template(win):
    """使用顺序：先映射 → 再分析 → 最后模板对比。"""
    assert win.page_tabs["mapping"] == (1, 0)
    assert win.page_tabs["analysis"] == (1, 1)
    assert win.page_tabs["template"] == (1, 2)
    titles = [str(x).strip() for x in cl.get_config()["app_info"]["tab_titles"]]
    # tab_titles 顺序是 ①②③④⑤⑥，板块②按使用顺序应为 ④ → ③ → ⑤
    assert [win.sub_tabs[1].tabText(i) for i in range(3)] == [titles[3], titles[2], titles[4]]
    assert win.tabs.widget(1) is win.sub_tabs[1]


def test_plate3_holds_sop_only(win):
    assert win.sub_tabs[2].count() == 1
    assert win.page_tabs["sop"] == (2, 0)


def test_hardware_page_is_still_scrollable(win):
    """第六轮的小屏适配不能因为换了挂载位置而丢失。"""
    hw = win.page("hardware")
    assert hw is not None and hw.findChildren(QScrollArea)


# ==================== 三、跳转：所有旧链接都指向新结构 ====================
@pytest.mark.parametrize("key", list(_KEYS))
def test_goto_page_reaches_every_page(win, key):
    assert win.goto_page(key) is True
    gi, si = win.page_tabs[key]
    assert win.tabs.currentIndex() == gi
    assert win.sub_tabs[gi].currentIndex() == si
    assert win.current_page_key() == key


def test_goto_page_rejects_unknown_key(win):
    win.goto_page("planner")
    assert win.goto_page("不存在的页面") is False
    assert win.current_page_key() == "planner"


def test_goto_page_rejects_empty_and_none(win):
    win.goto_page("sop")
    for bad in ("", None, 0, {}, "mapping "):
        assert win.goto_page(bad) is False, "非法键 %r 不该跳转" % (bad,)
    assert win.current_page_key() == "sop"


def test_page_lookup(win):
    for key in _KEYS:
        gi, si = win.page_tabs[key]
        assert win.page(key) is win.sub_tabs[gi].widget(si)
    assert win.page("nope") is None
    assert win.page(None) is None


def test_no_dead_links_to_removed_tabs(win):
    """旧属性名保留：跨页逻辑（④页取③页文件、③页写⑤页批次、⑥页链接）仍然连着同一批控件。"""
    assert win.analysis_tab is win.pages["analysis"]
    assert win.mapping_tab is win.pages["mapping"]
    assert win.template_tab is win.pages["template"]
    assert win.sop_tab is win.pages["sop"]


# ==================== 四、外观：全部取自 config.app_info.theme ====================
def test_window_stylesheet_uses_config_primary(win):
    cfg = cl.get_config()
    primary = str(cfg["app_info"]["theme"]["primary"])
    assert primary in win.styleSheet(), "整窗样式表没用上 config 里的主色"


def test_theme_overrides_change_stylesheet():
    css = theme.stylesheet({"app_info": {"theme": {"primary": "#123456"}}})
    assert "#123456" in css


def test_theme_survives_missing_or_broken_config():
    assert theme.stylesheet({}), "config 没有 theme 段也必须能出样式表"
    assert theme.stylesheet(None)
    assert theme.metrics({"app_info": {"theme": {"margin_outer": -5, "font_pt": "abc"}}})["margin_outer"] == 16
    assert theme.colors({"app_info": {"theme": {"primary": "不是颜色"}}})["primary"] == theme.DEFAULTS["primary"]


def test_semantic_colors_match_table_backgrounds():
    """绿/黄/红/灰必须和校验表格底色同源，避免「这页的黄和那页的黄不一样」。"""
    cfg = cl.get_config()
    bg = theme.level_bg(cfg)
    assert bg["pass"].upper() == common.LEVEL_BG[common.validators.LEVEL_PASS].name().upper()
    assert bg["warn"].upper() == common.LEVEL_BG[common.validators.LEVEL_WARN].name().upper()
    assert bg["error"].upper() == common.LEVEL_BG[common.validators.LEVEL_ERROR].name().upper()
    assert bg["none"].upper() == common.LEVEL_BG[common.LEVEL_NONE].name().upper()


def test_hint_style_levels(win):
    cfg = cl.get_config()
    assert theme.colors(cfg)["warn_bg"] in theme.hint_style(cfg, "warn")
    assert theme.colors(cfg)["pass_bg"] in theme.hint_style(cfg, "pass")
    assert theme.colors(cfg)["none_bg"] in theme.hint_style(cfg, "未知档位")


def test_outer_and_group_margins_come_from_config(win):
    m = theme.metrics(cl.get_config())
    root = win.centralWidget().layout()
    assert (root.contentsMargins().left(), root.contentsMargins().top()) == (m["margin_outer"], m["margin_outer"])
    assert root.spacing() == m["spacing"]
    for key in _KEYS:
        lay = win.page(key).layout()
        assert lay.contentsMargins().left() == m["margin_outer"], "%s 页外边距不统一" % key
    boxes = win.page("planner").findChildren(QGroupBox)
    assert boxes, "① 页没有语义分组"
    laid = [b for b in boxes if b.layout() is not None]
    assert laid
    box_lay = laid[0].layout()
    assert box_lay.contentsMargins().left() == m["margin_group"]
    assert box_lay.spacing() == m["spacing"]


def test_control_height_and_monospace_in_stylesheet(win):
    css = win.styleSheet()
    m = theme.metrics(cl.get_config())
    assert "min-height: %dpx" % m["control_height"] in css
    assert 'QTextEdit#resultsArea { font-family: "%s"' % m["mono_family"] in css
    assert win.txt_results.objectName() == "resultsArea"


def test_theme_module_does_not_import_qt():
    """theme.py 必须是无 Qt 依赖的纯函数模块，否则 core 层测试会被界面拖着走。"""
    src = inspect.getsource(theme)
    assert "PySide6" not in src


# ==================== 五、图标 ====================
def test_every_tab_has_icon(win):
    for i in range(win.tabs.count()):
        assert not win.tabs.tabIcon(i).isNull(), "第 %d 个大板块没有图标" % i
    for sub in win.sub_tabs:
        for i in range(sub.count()):
            assert not sub.tabIcon(i).isNull(), "子页签 %s 没有图标" % sub.tabText(i)


def test_icon_helper_never_crashes():
    cfg = cl.get_config()
    assert isinstance(icons.icon("查无此图", cfg), QIcon)
    assert icons.icon("查无此图", cfg).isNull()
    assert isinstance(icons.icon(None, cfg), QIcon)
    assert isinstance(icons.icon(None, None), QIcon)
    assert not icons.pixmap("gear", cfg, 32).isNull()
    assert icons.pixmap("gear", cfg, 0) is None           # 尺寸非法 -> 返回 None，不抛
    assert icons.pixmap("查无此图", cfg, 32) is None
    assert icons.pixmap(None, cfg, 32) is None


# ==================== 六、③ 离线分析子页的映射状态提示 ====================
def _full_mapping():
    return {cmap.DATASET_CONTROL: {"time": "Time", "do_percent": "DO [%]"},
            cmap.DATASET_OFFLINE: {"time": "Time", "cell_density_mcells_ml": "CD (x10^6 cells/mL)"}}


def test_map_hint_missing_returns_required_keyword(win, monkeypatch):
    tab = win.page("analysis")
    monkeypatch.setattr(cmap, "load_all", lambda *a, **k: {cmap.DATASET_CONTROL: {}, cmap.DATASET_OFFLINE: {}})
    tab._refresh_map_hint()
    text = tab.lbl_map_hint.text()
    assert "尝试自动匹配" in text
    assert theme.colors(cl.get_config())["none_bg"] in tab.lbl_map_hint.styleSheet()
    assert tab.btn_goto_map.isVisible() or tab.btn_goto_map.text()


def test_map_hint_counts_missing_fields(win, monkeypatch):
    tab = win.page("analysis")
    partial = {cmap.DATASET_CONTROL: {"time": "Time"}, cmap.DATASET_OFFLINE: {}}
    monkeypatch.setattr(cmap, "load_all", lambda *a, **k: partial)
    tab._refresh_map_hint()
    assert "缺少 3 个必需字段" in tab.lbl_map_hint.text()


def test_map_hint_green_when_mapping_complete(win, monkeypatch):
    tab = win.page("analysis")
    monkeypatch.setattr(cmap, "load_all", lambda *a, **k: _full_mapping())
    tab._refresh_map_hint()
    assert "映射已完成" in tab.lbl_map_hint.text()
    assert theme.colors(cl.get_config())["pass_bg"] in tab.lbl_map_hint.styleSheet()


def test_map_hint_degrades_when_mapping_file_broken(win, monkeypatch):
    tab = win.page("analysis")

    def boom(*a, **k):
        raise ValueError("映射文件是坏的")

    monkeypatch.setattr(cmap, "load_all", boom)
    tab._refresh_map_hint()                      # 不许抛
    assert "请先在『列名映射』完成必需字段映射" in tab.lbl_map_hint.text()
    assert "读不了" in tab.lbl_map_hint.text()


def test_map_hint_degrades_when_config_broken(win, monkeypatch):
    tab = win.page("analysis")

    def boom(*a, **k):
        raise ValueError("config 里没有字段清单")

    monkeypatch.setattr(cmap, "fields_for", boom)
    tab._refresh_map_hint()
    assert "请先在『列名映射』完成必需字段映射" in tab.lbl_map_hint.text()
    monkeypatch.undo()


def test_goto_map_button_jumps_to_mapping_subpage(win):
    tab = win.page("analysis")
    assert win.current_page_key() != "mapping"
    tab.btn_goto_map.click()
    assert win.current_page_key() == "mapping"


def test_goto_map_button_falls_back_to_hint(win, monkeypatch):
    tab = win.page("analysis")
    monkeypatch.setattr(win, "goto_page", lambda key: False)
    tab.btn_goto_map.click()                     # 只弹中文提示（已打桩），不崩
    assert win.current_page_key() != "mapping"


def test_map_hint_texts_are_not_hardcoded(win, monkeypatch):
    """本轮新增文案全部能在 config.app_info.ui_texts 里找到并覆盖。"""
    cfg = cl.get_config()
    tab = win.page("analysis")
    assert tab.btn_goto_map.text() == str(cfg["app_info"]["ui_texts"]["mapping_goto"])
    monkeypatch.setattr(cmap, "load_all", lambda *a, **k: {cmap.DATASET_CONTROL: {"time": "Time"}, cmap.DATASET_OFFLINE: {}})
    monkey_texts = {"mapping_missing": "自定义提示：{n} 项 / {ctrl} / {off}"}
    orig = cfg["app_info"]["ui_texts"].get("mapping_missing")
    cfg["app_info"]["ui_texts"].update(monkey_texts)
    try:
        tab._refresh_map_hint()
        assert tab.lbl_map_hint.text().startswith("自定义提示")
    finally:
        if orig is None:
            cfg["app_info"]["ui_texts"].pop("mapping_missing", None)
        else:
            cfg["app_info"]["ui_texts"]["mapping_missing"] = orig
        tab._refresh_map_hint()
    assert ai.ui_text(cfg, "查无此键", "兜底文案") == "兜底文案"
    assert ai.ui_text_fmt(cfg, "查无此键", "共 {n} 项", n=3) == "共 3 项"
    assert "{" in ai.ui_text_fmt(cfg, "查无此键", "模板占位符写错了 {oops}")


# ==================== 六、本轮补的跨页跳转与旧页名清理 ====================
def test_hardware_page_keeps_controls_without_intro(win):
    """说明文字移除后，硬件设置与保存入口仍然可用。"""
    from PySide6.QtWidgets import QLabel
    texts = [lab.text() for lab in win.page("hardware").findChildren(QLabel)]
    assert not any("在这里修改硬件上下限" in text for text in texts)
    assert win.hw_widgets
    assert win.btn_hw_save.text() == "保存并生效"


def test_no_ui_widget_jumps_by_tab_index(win, monkeypatch, tmp_path):
    """载入模板后必须落到「① 配置与校验」子页（新结构下按序号跳页已无意义）。"""
    from cell_planner.core import template_store as ts
    db = tmp_path / "templates.db"
    monkeypatch.setattr(ts, "db_path", lambda cfg=None: db)
    tab = win.page("template")
    tab.edit_name.setText("第七轮跳转用例模板")
    tab.save_template()
    assert tab.tbl_tpl.rowCount() == 1, "模板没写进临时库（测试用的 db_path 桩没生效）"
    tab.tbl_tpl.setCurrentCell(0, 0)
    assert win.goto_page("analysis")
    tab.load_template()
    assert win.current_page_key() == "planner"
    assert win.tabs.currentIndex() == 0


def test_hw_intro_text_can_be_overridden_in_config():
    """hw_intro 走 ui_texts：config 写了就用 config，占位符 {planner} 由代码填入真实子页名。"""
    cfg = {"app_info": {"ui_texts": {"hw_intro": "改完回到「{planner}」继续。"}}}
    assert ai.ui_text_fmt(cfg, "hw_intro", "兜底", planner="① 配置与校验") == \
        "改完回到「① 配置与校验」继续。"
    assert ai.ui_text_fmt({}, "hw_intro", "默认句子 {planner}", planner="X") == "默认句子 X"


# 工作流回归：不允许把旧结果与新输入混用。
@pytest.mark.parametrize("field", ["v_work", "cell_line", "expr_check"])
def test_changed_inputs_invalidate_results_and_block_export(win, monkeypatch, field):
    assert win._last is not None
    if field == "cell_line":
        win.widgets[field].setText("新细胞株")
    elif field == "expr_check":
        win.chk_expr.setChecked(not win.chk_expr.isChecked())
    else:
        spin = win.widgets[field]
        spin.setValue(spin.value() + 1)

    assert win._last is None
    assert win._sheet_rows() is None
    assert win.tbl.rowCount() == 0
    assert "重新计算" in win.lbl_summary.text()
    win._copy_sheet()
    assert win._last is None
    win.compute()
    assert win._last is not None
    assert len(win._last["results"]) == 18


def test_recipe_and_file_details_remain_accessible(win):
    assert win.recipe_panel.isHidden()
    win.recipe_toggle.click()
    assert not win.recipe_panel.isHidden()
    assert win.btn_recipe_save.parent() is not None


def test_analysis_is_first_screen_in_its_section(win):
    win.tabs.setCurrentIndex(1)
    assert win.current_page_key() == "analysis"



def test_parameter_sections_keep_all_inputs(win):
    expected = {"cell_line", "medium", "v_work", "cd_seed", "cd_inoc", "days",
                "vvm", "o2_ratio", "co2_ratio", "rpm", "temp_expr", "temp_growth",
                "ph", "do", "sampling_ml", "base_pct", "af_pct"}
    assert set(win.widgets) == expected
    assert [win.input_tabs.tabText(i) for i in range(win.input_tabs.count())] == ["接种", "培养", "预留"]
    for index in range(win.input_tabs.count()):
        win.input_tabs.setCurrentIndex(index)
        assert win.input_tabs.currentIndex() == index


def test_result_summary_tracks_current_calculation(win):
    current = win._last["inp"]
    assert win.result_metrics["seed"].text() == "%s mL" % main_window._fmt(current.v_seed_ml)
    assert win.result_metrics["medium"].text() == "%s mL" % main_window._fmt(current.v_medium_ml)
    assert win.result_metrics["air"].text() == "%s mL/min" % main_window._fmt(current.q_air_ml_min)
    win.widgets["v_work"].setValue(current.v_work_ml + 100)
    assert all(label.text() == "—" for label in win.result_metrics.values())
    assert win._sheet_rows() is None
    win.compute()
    assert win.result_metrics["seed"].text() == "%s mL" % main_window._fmt(win._last["inp"].v_seed_ml)



def test_error_opens_checks_and_blocks_export(win, monkeypatch):
    from cell_planner.core import validators
    win.result_tabs.setCurrentIndex(0)
    win.widgets["v_work"].setValue(100)
    win.compute()
    assert win.result_tabs.currentIndex() == 1
    assert any(r.level == validators.LEVEL_ERROR for r in win._last["results"])
    assert win.tbl.rowCount() == 18
    assert win._export_blocked_by_errors() is True
    win.result_tabs.setCurrentIndex(0)
    assert win.txt_results.toPlainText()

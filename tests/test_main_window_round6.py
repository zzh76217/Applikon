# -*- coding: utf-8 -*-
"""第六轮界面集成测试（整窗冒烟）：标题、页签数、文件位置提示条、人工复核提示。

只在 offscreen 平台离屏构建窗口，不真的显示出来；
顺手把 QMessageBox 的静态方法打桩，防止任何一处弹窗把测试进程永久挂住。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path                       # noqa: E402
import pytest                                  # noqa: E402

from cell_planner.core import config_loader as cl   # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QRect                        # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from cell_planner.ui import main_window        # noqa: E402

_MSGBOX_METHODS = ("information", "warning", "critical", "question")
_saved = {}


@pytest.fixture(scope="module")
def win():
    app = QApplication.instance() or QApplication([])
    for name in _MSGBOX_METHODS:
        _saved[name] = getattr(QMessageBox, name)
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))
    window = main_window.MainWindow()
    yield window
    for name, original in _saved.items():
        setattr(QMessageBox, name, original)


# ==================== 窗口标题（来自 config.app_info） ====================
def test_window_title_contains_version_and_run_mode(win):
    info = cl.get_config()["app_info"]
    title = win.windowTitle()
    assert str(info["version"]) in title
    assert str(info["name"]) in title
    assert "源码版" in title                       # 本测试是源码运行
    assert "{" not in title


# ==================== 六页齐全 ====================
def test_six_tabs_are_present(win):
    assert win.tabs.count() == 6
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    for mark in "①②③④⑤⑥":
        assert any(mark in text for text in labels)


def test_tab_titles_come_from_config_not_hardcoded(win):
    """AGENTS.md 硬约束：界面文案也集中在 config，页签名必须与 app_info.tab_titles 一致。"""
    expect = [str(x).strip() for x in cl.get_config()["app_info"]["tab_titles"]]
    assert [win.tabs.tabText(i) for i in range(win.tabs.count())] == expect


def test_window_fits_available_screen(win):
    """打包版必须能在 1280x800 / 1366x768 的实验笔记本上完整显示（否则底部按钮和第 6 页看不见）。"""
    geo = QApplication.primaryScreen().availableGeometry()
    assert win.width() <= geo.width(), "窗口宽 %d 超出屏幕可用宽 %d" % (win.width(), geo.width())
    assert win.height() <= geo.height(), "窗口高 %d 超出屏幕可用高 %d" % (win.height(), geo.height())


# ==================== 底部"你的文件都在这里"提示 ====================
def test_locations_label_lists_all_four_paths(win):
    text = win.lbl_locations.text()
    assert text, "底部文件位置提示为空，说明路径没渲染出来"
    assert Path(cl.CONFIG_FILE).name in text
    assert "data" in text
    assert str(cl.get_config()["app_info"]["log_file"]) in text
    assert str(cl.get_config()["app_info"]["manual_file"]) in text


def test_locations_label_is_findable_by_user(win):
    assert win.lbl_locations in win.findChildren(QLabel)


# ==================== AGENTS.md 硬约束 6：保留"需人工复核" ====================
def test_manual_review_disclaimer_is_on_screen(win):
    hits = [lab.text() for lab in win.findChildren(QLabel) if "人工复核" in lab.text()]
    assert hits, "界面上找不到「需人工复核」的提示（AGENTS.md 硬约束 6）"


# ==================== 计算仍然工作（回归第六轮改造没碰坏业务） ====================
def test_compute_still_returns_result(win):
    win.compute()
    assert win._last is not None and win._last["results"]
    assert all(v in win.widgets for v in ("v_work", "cd_inoc", "cd_seed", "vvm"))


# ==================== 第六轮真机踩坑：小屏（1280x752 可用区）适配 ====================
def test_hardware_tab_is_scrollable_so_it_does_not_push_window_offscreen(win):
    """② 硬件配置页控件最多，必须放进滚动区。

    未包 QScrollArea 时这一页 minimumSizeHint 高 918px，会把整窗最小高顶到 1009px，
    超过实验笔记本可用高（1366x768 扣任务栏约 752px），底部按钮和第 6 页签跑到屏幕外。
    """
    from PySide6.QtWidgets import QScrollArea

    hw_tab = win.tabs.widget(1)
    assert hw_tab.findChildren(QScrollArea), "② 硬件配置页没有滚动区"
    assert hw_tab.minimumSizeHint().height() <= 200, (
        "② 页最小高 %d px 过大，仍然会把窗口撑出屏幕" % hw_tab.minimumSizeHint().height()
    )


def test_window_minimum_size_fits_small_laptop(win):
    """整窗最小尺寸必须塞进 1024x768 的老笔记本（含任务栏后的可用区）。"""
    min_hint = win.minimumSizeHint()
    assert min_hint.width() <= 1024, "窗口最小宽 %d px 超过 1024，窄屏会切掉右侧页签" % min_hint.width()
    assert min_hint.height() <= 732, "窗口最小高 %d px 超过 732，底部内容会被顶出屏幕" % min_hint.height()


def test_locations_label_can_wrap(win):
    """底部路径提示条要能折行，否则一行长路径会把窗口最小宽度顶到 900+。"""
    assert win.lbl_locations.wordWrap(), "底部文件位置标签未开启自动折行"


# ==================== 第六轮真机踩坑：窗口边框（标题栏）不在 geometry() 里 ====================
def test_clamped_size_accounts_for_window_frame(win):
    """可用区 752 高、窗口 728 高但含标题栏实际 763 高时，必须缩到 701 才不超屏。"""
    avail = QRect(0, 0, 1280, 752)
    assert win._clamped_size(1200, 728, avail, 1235, 763) == (1200, 701)


def test_clamped_size_keeps_size_when_already_fitting(win):
    avail = QRect(0, 0, 1280, 752)
    assert win._clamped_size(1200, 700, avail, 1235, 735) == (1200, 700)
    assert win._clamped_size(1000, 400, avail, 1035, 435) == (1000, 400)


def test_clamped_size_shrinks_oversized_window(win):
    avail = QRect(0, 0, 1280, 752)
    assert win._clamped_size(1600, 900, avail, 1635, 935) == (1229, 701)


def test_clamped_size_never_goes_below_usable_floor(win):
    """极小屏幕（800x480）也要停在能用的下限，不能缩成一条缝。"""
    avail = QRect(0, 0, 800, 480)
    w, h = win._clamped_size(1200, 728, avail, 1235, 763)
    assert (w, h) == (win.MIN_WIDTH, win.MIN_HEIGHT)


def test_clamped_size_tolerates_missing_screen_info(win):
    """拿不到屏幕信息（None）就原样返回，绝不抛异常。"""
    assert win._clamped_size(1200, 728, None, 1235, 763) == (1200, 728)


def test_window_frame_actually_fits_available_area(win):
    """整窗（含边框）真实落点检查：显示后要触发收拢，底部和右边都不能超出可用区。"""
    win.show()
    QApplication.processEvents()
    geo = QApplication.primaryScreen().availableGeometry()
    frame = win.frameGeometry()
    assert win._size_clamped_on_show is True
    assert frame.bottom() <= geo.bottom(), "窗口底边框 %d 超出可用区 %d" % (frame.bottom(), geo.bottom())
    assert frame.right() <= geo.right(), "右边框 %d 超出可用区 %d" % (frame.right(), geo.right())

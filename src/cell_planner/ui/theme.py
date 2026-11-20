# -*- coding: utf-8 -*-
"""界面外观（第七轮：三大板块重构 + 视觉美化）。

只做一件事：把 config.app_info.theme 里的配色/字号/边距翻译成一份 QSS 字符串，
并对外提供统一的语义色（绿=通过、黄=警告、红=拦截）取值口。

本模块是纯函数模块：不 import Qt、不创建任何控件、不含任何工艺阈值或判定逻辑，
因此可以脱离界面直接单元测试；换配色/改边距只动 config.yaml，不动代码
（AGENTS.md 硬约束 2：严禁硬编码）。
"""
from __future__ import annotations

from typing import Mapping

# config 缺项/写错时的兜底值。数值与出厂 config.app_info.theme 一致，
# 语义色三档刻意与 ui/common.py 的 LEVEL_BG 保持同一颜色，避免"这页黄那页黄得不一样"。
DEFAULTS = {
    "primary": "#2E7D8C",
    "primary_dark": "#246573",
    "primary_light": "#E8F1F3",
    "window_bg": "#F4F6F7",
    "base_bg": "#FFFFFF",
    "text": "#26323A",
    "muted_text": "#8A96A0",
    "border": "#C7D3D8",
    "pass_bg": "#E3F4E3",
    "warn_bg": "#FFF6C8",
    "error_bg": "#FFD5D5",
    "none_bg": "#EEEEEE",
    "pass_fg": "#1B6B32",
    "warn_fg": "#8A6100",
    "error_fg": "#B00000",
    "font_family": "",
    "font_pt": 10,
    "title_pt": 11,
    "mono_family": "Consolas",
    "margin_outer": 16,
    "margin_group": 10,
    "spacing": 8,
    "control_height": 28,
}

_HEX_KEYS = tuple(k for k, v in DEFAULTS.items() if isinstance(v, str) and v.startswith("#"))
_INT_KEYS = ("font_pt", "title_pt", "margin_outer", "margin_group", "spacing", "control_height")

_QSS = """
QWidget { color: %(text)s; }
QMainWindow, QDialog { background-color: %(window_bg)s; }

/* ---- 页签：上层 3 个大板块 + 板块内子页签，同一套样式 ---- */
QTabWidget::pane { border: 1px solid %(border)s; border-radius: 6px;
                   background-color: %(base_bg)s; top: -1px; }
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab { background-color: %(primary_light)s; color: %(text)s;
               border: 1px solid %(border)s; border-bottom: none;
               border-top-left-radius: 6px; border-top-right-radius: 6px;
               padding: 5px 14px; margin-right: 3px; min-height: 22px; }
QTabBar::tab:selected { background-color: %(base_bg)s; color: %(primary_dark)s;
                        font-weight: bold; border-bottom: 3px solid %(primary)s; }
QTabBar::tab:hover:!selected { background-color: %(primary_light)s;
                               color: %(primary_dark)s; }
QTabBar::tab:disabled { color: %(muted_text)s; }

/* ---- 语义分组：标题加粗、比正文大一号 ---- */
QGroupBox { background-color: %(base_bg)s; border: 1px solid %(border)s;
            border-radius: 6px; margin-top: %(group_push)s;
            font-weight: bold; font-size: %(title_pt)spt; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
                   left: %(title_left)s; padding: 0 4px; color: %(primary_dark)s; }

/* ---- 按钮 ---- */
QPushButton { background-color: %(primary)s; color: #FFFFFF;
              border: 1px solid %(primary)s; border-radius: 4px;
              padding: 0 %(pad_h)s; min-height: %(ctrl_h)s; max-height: %(ctrl_h)s; }
QPushButton:hover { background-color: %(primary_dark)s; border-color: %(primary_dark)s; }
QPushButton:pressed { background-color: %(primary_dark)s; }
QPushButton:checked { background-color: %(primary_dark)s; }
QPushButton:disabled { background-color: %(border)s; color: %(muted_text)s;
                       border-color: %(border)s; }

/* ---- 输入控件：高度一致，便于左对齐成网格 ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateTimeEdit {
    background-color: %(base_bg)s; border: 1px solid %(border)s; border-radius: 4px;
    padding: 1px 6px; min-height: %(ctrl_h)s;
    selection-background-color: %(primary)s; selection-color: #FFFFFF; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateTimeEdit:focus {
    border: 1px solid %(primary)s; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background-color: %(window_bg)s; color: %(muted_text)s; }
QComboBox::drop-down { border: none; width: 18px; }
QTextEdit, QPlainTextEdit { background-color: %(base_bg)s; border: 1px solid %(border)s;
                            border-radius: 4px; padding: 4px;
                            selection-background-color: %(primary)s; selection-color: #FFFFFF; }
/* 数字结果区：等宽字体，逐行对齐好看 */
QTextEdit#resultsArea { font-family: "%(mono)s"; }

/* ---- 表格 ---- */
QTableWidget, QTableView { background-color: %(base_bg)s; border: 1px solid %(border)s;
                           border-radius: 4px; gridline-color: %(border)s;
                           alternate-background-color: %(window_bg)s;
                           selection-background-color: %(primary_light)s;
                           selection-color: %(text)s; }
QTableView::item:selected { background-color: %(primary_light)s; color: %(text)s; }
QHeaderView::section { background-color: %(primary_light)s; color: %(text)s;
                       font-weight: bold; border: none;
                       border-right: 1px solid %(border)s;
                       border-bottom: 1px solid %(border)s; padding: 4px; }
QTableCornerButton::section { background-color: %(primary_light)s; border: none; }

/* ---- 其他 ---- */
QLabel { background-color: transparent; }
QScrollArea { border: none; background-color: transparent; }
QSplitter::handle { background-color: %(window_bg)s; }
QCheckBox { spacing: %(spacing)s; }
QRadioButton { spacing: %(spacing)s; }
QProgressBar { border: 1px solid %(border)s; border-radius: 4px;
               background-color: %(base_bg)s; text-align: center; }
QProgressBar::chunk { background-color: %(primary)s; border-radius: 3px; }
QToolTip { background-color: %(base_bg)s; color: %(text)s;
           border: 1px solid %(primary)s; }
"""


def _node(cfg: Mapping) -> Mapping:
    """取 config.app_info.theme 这一小段；任何一层缺失或类型不对都退回空字典。"""
    if not isinstance(cfg, Mapping):
        return {}
    info = cfg.get("app_info")
    if not isinstance(info, Mapping):
        return {}
    theme = info.get("theme")
    return theme if isinstance(theme, Mapping) else {}


def colors(cfg: Mapping) -> dict:
    """配色取值：config 里写了就用 config，没写/写得不像颜色就用兜底值。"""
    node = _node(cfg)
    out = {}
    for key in _HEX_KEYS:
        val = str(node.get(key) or "").strip()
        out[key] = val if val.startswith("#") and 4 <= len(val) <= 9 else DEFAULTS[key]
    return out


def metrics(cfg: Mapping) -> dict:
    """尺寸取值（px / pt）。负数或非数字一律回退兜底，绝不把界面搞崩。"""
    node = _node(cfg)
    out = {}
    for key in _INT_KEYS:
        try:
            num = int(node.get(key, DEFAULTS[key]))
        except (TypeError, ValueError):
            num = DEFAULTS[key]
        out[key] = num if num > 0 else DEFAULTS[key]
    family = str(node.get("font_family") or "").strip()
    out["font_family"] = family
    mono = str(node.get("mono_family") or "").strip()
    out["mono_family"] = mono or DEFAULTS["mono_family"]
    return out


def level_bg(cfg: Mapping) -> dict:
    """校验语义底色：绿=通过、黄=警告、红=拦截/错误、灰=无数据。返回 {级别: 十六进制色}。"""
    c = colors(cfg)
    return {"pass": c["pass_bg"], "warn": c["warn_bg"], "error": c["error_bg"], "none": c["none_bg"]}


def level_fg(cfg: Mapping) -> dict:
    """校验语义文字色，与 level_bg 一一对应，保证各页面红黄绿用同一套颜色。"""
    c = colors(cfg)
    return {"pass": c["pass_fg"], "warn": c["warn_fg"], "error": c["error_fg"]}


def stylesheet(cfg: Mapping) -> str:
    """生成整窗样式表。任何异常都返回空串（宁可不美化，也不能因为样式写错打不开软件）。"""
    try:
        c = colors(cfg)
        m = metrics(cfg)
        fields = dict(c)
        fields.update({
            "title_pt": m["title_pt"],
            "mono": m["mono_family"],
            # 分组标题要独占一条"标题带"，否则加粗标题会压住分组里的第一行控件（例如表头）
            "group_push": "%dpx" % max(int(round(m["title_pt"] * 96 / 72)) + 5,
                                       m["spacing"] + 2),
            "title_left": "%dpx" % max(6, m["margin_group"]),
            "pad_h": "%dpx" % max(6, m["spacing"]),
            "ctrl_h": "%dpx" % m["control_height"],
            "spacing": "%dpx" % m["spacing"],
        })
        css = _QSS % fields
        if m["font_family"]:
            css += "\nQWidget { font-family: \"%s\"; font-size: %dpt; }" % (
                m["font_family"], m["font_pt"])
        else:
            css += "\nQWidget { font-size: %dpt; }" % m["font_pt"]
        return css
    except Exception:
        return ""


def hint_style(cfg: Mapping, level: str) -> str:
    """给"黄色提示条"这类行内提示用的样式串：level 取 pass/warn/error/none。
    语义色只从本模块出，界面各处不再各写各的红黄绿。"""
    c = colors(cfg)
    bg = {"pass": c["pass_bg"], "warn": c["warn_bg"], "error": c["error_bg"],
          "none": c["none_bg"], "": c["none_bg"]}.get(str(level), c["none_bg"])
    fg = {"pass": c["pass_fg"], "warn": c["warn_fg"], "error": c["error_fg"]}.get(str(level), c["text"])
    return ("background-color: %s; color: %s; border: 1px solid %s;"
            " border-radius: 4px; padding: 6px; font-weight: bold;" % (bg, fg, c["border"]))

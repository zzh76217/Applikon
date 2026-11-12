# -*- coding: utf-8 -*-
"""界面公共小工具（第五轮新增标签页共用）：红黄绿配色、表格填充、数值格式化。

这里只放"怎么显示"，不放任何工艺阈值或判定逻辑（判定全部在 core 层、阈值全部在 config）。
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
)

from cell_planner.core import validators
from cell_planner.core.analysis import LEVEL_ICON, LEVEL_NONE

# 背景色：绿=通过，黄=警告，红=错误，灰=无数据/不适用
LEVEL_BG = {
    validators.LEVEL_PASS: QColor(227, 244, 227),
    validators.LEVEL_WARN: QColor(255, 246, 200),
    validators.LEVEL_ERROR: QColor(255, 213, 213),
    LEVEL_NONE: QColor(238, 238, 238),
}

DASH = "—"


def fmt(value, digits: int = 3) -> str:
    """数值显示：None/空 → —；整数不带小数点；小数最多 digits 位且去掉末尾 0。"""
    if value is None or value == "":
        return DASH
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if x != x:                                  # NaN
        return DASH
    text = ("%%.%df" % digits) % x
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def make_table(headers: Sequence[str], rows: Optional[int] = 0) -> QTableWidget:
    tbl = QTableWidget(rows, len(headers))
    tbl.setHorizontalHeaderLabels(list(headers))
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.verticalHeader().setVisible(False)
    hdr = tbl.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.Interactive)
    hdr.setStretchLastSection(True)
    tbl.setColumnWidth(0, 150)
    return tbl


def fill_table(tbl: QTableWidget, header: Sequence[str], rows: Sequence[Sequence[object]],
               level_col: Optional[int] = None,
               level_of: Optional[Callable[[Sequence[object]], Optional[str]]] = None) -> None:
    """把 (表头, 行) 填进表格；level_col 给该列上红/黄/绿底色，level_of 可自定义取级别。"""
    tbl.clearContents()
    tbl.setColumnCount(len(header))
    tbl.setHorizontalHeaderLabels([str(h) for h in header])
    tbl.setRowCount(len(rows))
    for r, row in enumerate(rows):
        bg = None
        if level_of is not None:
            bg = LEVEL_BG.get(level_of(row))
        elif level_col is not None and level_col < len(row):
            bg = LEVEL_BG.get(str(row[level_col]))
        for c in range(len(header)):
            val = row[c] if c < len(row) else ""
            item = QTableWidgetItem("" if val is None else str(val))
            if val is None:
                item.setText(DASH)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if bg is not None and (c == level_col or level_of is not None):
                item.setBackground(bg)
            tbl.setItem(r, c, item)
    tbl.resizeColumnsToContents()
    tbl.horizontalHeader().setStretchLastSection(True)


def level_icon(level: Optional[str]) -> str:
    return LEVEL_ICON.get(str(level or ""), "")


def status_label(text: str = "", level: Optional[str] = None) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    if level in LEVEL_BG:
        col = LEVEL_BG[level]
        lbl.setStyleSheet("background-color: rgb(%d,%d,%d); padding: 4px; border-radius: 4px;"
                          % (col.red(), col.green(), col.blue()))
    return lbl


def banner(text: str, fg: str = "rgb(176,0,0)", bg: str = "rgb(255,235,235)") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: %s; background-color: %s; font-weight: bold; padding: 6px; border-radius: 4px;"
                      % (fg, bg))
    return lbl


def rows_to_clipboard(header: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """制表符文本，便于直接粘贴到 Excel/微信。"""
    lines = ["\t".join(str(h) for h in header)]
    for row in rows:
        lines.append("\t".join("" if v is None else str(v) for v in row))
    return "\n".join(lines)
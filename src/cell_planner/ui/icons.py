# -*- coding: utf-8 -*-
"""页签小图标（第七轮：三大板块 + 子页签各配一个图标）。

全部用 QPainter 现画，不引入任何图片文件、不加任何第三方依赖；
颜色取自 config.app_info.theme（默认蓝绿主色），因此换配色时图标跟着变。
拿不到 QApplication（比如在没有 GUI 的环境里跑单测）就返回空图标，绝不抛异常。
"""
from __future__ import annotations

from typing import Mapping, Optional

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from cell_planner.ui import theme

# 大板块图标：① 齿轮（配置）② 折线图（分析）③ 清单（SOP）
OUTER_ICON_NAMES = ("gear", "chart", "checklist")
# 子页签图标：沿用原 6 页的稳定键名
PAGE_ICON_NAMES = {
    "planner": "sliders",      # ① 配置与校验
    "hardware": "wrench",      # ② 硬件配置
    "analysis": "chart",       # ③ 离线分析
    "mapping": "link",         # ④ 列名映射
    "template": "database",    # ⑤ 模板库对比
    "sop": "book",             # ⑥ SOP 引导
}


def _accent(cfg: Optional[Mapping]) -> QColor:
    try:
        return QColor(theme.colors(cfg)["primary"])
    except Exception:
        return QColor("#2E7D8C")


def _gear(p: QPainter, s: float, c: QColor) -> None:
    """齿轮：外圈 8 个齿 + 中心孔。"""
    from math import cos, pi, sin
    cx, cy, r1, r2 = s / 2.0, s / 2.0, s * 0.30, s * 0.42
    for i in range(8):
        a = pi * i / 4.0
        p.drawLine(QPointF(cx + cos(a) * r1, cy + sin(a) * r1),
                   QPointF(cx + cos(a) * r2, cy + sin(a) * r2))
    p.drawEllipse(QPointF(cx, cy), r1, r1)
    p.drawEllipse(QPointF(cx, cy), r1 * 0.42, r1 * 0.42)


def _chart(p: QPainter, s: float, c: QColor) -> None:
    """折线图：坐标轴 + 一条上扬的折线 + 三个数据点。"""
    m = s * 0.16
    p.drawLine(QPointF(m, m), QPointF(m, s - m))
    p.drawLine(QPointF(m, s - m), QPointF(s - m, s - m))
    pts = [QPointF(m, s * 0.62), QPointF(s * 0.42, s * 0.40),
           QPointF(s * 0.60, s * 0.50), QPointF(s - m, s * 0.24)]
    p.drawPolyline(QPolygonF(pts))
    r = max(1.0, s * 0.05)
    for pt in pts:
        p.setBrush(c)
        p.drawEllipse(pt, r, r)
    p.setBrush(Qt.NoBrush)


def _checklist(p: QPainter, s: float, c: QColor) -> None:
    """清单：一块夹板 + 两行"打勾 + 文字线"。"""
    m = s * 0.16
    p.drawRoundedRect(QRectF(m, m * 0.8, s - 2 * m, s - m * 1.6), s * 0.06, s * 0.06)
    for i, y in enumerate((0.38, 0.62)):
        yy = s * y
        p.drawLine(QPointF(s * 0.26, yy), QPointF(s * 0.34, yy + s * 0.06))
        p.drawLine(QPointF(s * 0.34, yy + s * 0.06), QPointF(s * 0.46, yy - s * 0.06))
        p.drawLine(QPointF(s * 0.54, yy), QPointF(s - m - s * 0.04, yy))


def _sliders(p: QPainter, s: float, c: QColor) -> None:
    """参数滑块：三条横线，每条上一个滑钮。"""
    for i, (y, k) in enumerate(((0.30, 0.32), (0.50, 0.66), (0.70, 0.45))):
        yy = s * y
        p.drawLine(QPointF(s * 0.16, yy), QPointF(s * 0.84, yy))
        p.setBrush(c)
        p.drawEllipse(QPointF(s * k, yy), s * 0.07, s * 0.07)
        p.setBrush(Qt.NoBrush)


def _wrench(p: QPainter, s: float, c: QColor) -> None:
    """扳手：一根斜柄 + 开口端。"""
    p.drawLine(QPointF(s * 0.28, s * 0.72), QPointF(s * 0.70, s * 0.30))
    p.drawArc(QRectF(s * 0.56, s * 0.16, s * 0.28, s * 0.28), 40, 280)
    p.drawLine(QPointF(s * 0.22, s * 0.66), QPointF(s * 0.34, s * 0.78))


def _link(p: QPainter, s: float, c: QColor) -> None:
    """字段对应：两个小方块中间一根连接线（逻辑字段 ↔ 真实列名）。"""
    w = s * 0.24
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.20, w, w), s * 0.04, s * 0.04)
    p.drawRoundedRect(QRectF(s * 0.62, s * 0.58, w, w), s * 0.04, s * 0.04)
    p.drawLine(QPointF(s * 0.38, s * 0.32), QPointF(s * 0.62, s * 0.70))
    p.drawLine(QPointF(s * 0.26, s * 0.44), QPointF(s * 0.74, s * 0.56))


def _database(p: QPainter, s: float, c: QColor) -> None:
    """模板库：三层圆柱。"""
    w, h = s * 0.56, s * 0.16
    x = (s - w) / 2.0
    for y in (0.20, 0.42, 0.64):
        p.drawEllipse(QRectF(x, s * y, w, h))
    p.drawLine(QPointF(x, s * 0.20 + h / 2), QPointF(x, s * 0.64 + h / 2))
    p.drawLine(QPointF(x + w, s * 0.20 + h / 2), QPointF(x + w, s * 0.64 + h / 2))


def _book(p: QPainter, s: float, c: QColor) -> None:
    """SOP 手册：一本翻开的书。"""
    mid = s / 2.0
    p.drawLine(QPointF(mid, s * 0.20), QPointF(mid, s * 0.80))
    p.drawPolyline(QPolygonF([QPointF(mid, s * 0.20), QPointF(s * 0.18, s * 0.26),
                              QPointF(s * 0.18, s * 0.74), QPointF(mid, s * 0.80)]))
    p.drawPolyline(QPolygonF([QPointF(mid, s * 0.20), QPointF(s * 0.82, s * 0.26),
                              QPointF(s * 0.82, s * 0.74), QPointF(mid, s * 0.80)]))


_DRAWERS = {
    "gear": _gear, "chart": _chart, "checklist": _checklist, "sliders": _sliders,
    "wrench": _wrench, "link": _link, "database": _database, "book": _book,
}


def pixmap(name: str, cfg: Optional[Mapping] = None, size: int = 32):
    """画一个图标位图；名字不认识或没有 GUI 就返回 None。"""
    draw = _DRAWERS.get(str(name))
    if draw is None or size <= 0:
        return None
    try:
        color = _accent(cfg)
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(color)
            pen.setWidthF(max(1.4, size * 0.075))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            draw(p, float(size), color)
        finally:
            p.end()
        return pm
    except Exception:
        return None


def icon(name: str, cfg: Optional[Mapping] = None, selected_light: bool = False) -> QIcon:
    """取不同尺寸图标；深色选中页签使用浅色图标。"""
    out = QIcon()
    light_cfg = {"app_info": {"theme": {"primary": theme.colors(cfg or {})["base_bg"]}}}
    for size in (16, 32):
        pm = pixmap(name, cfg, size)
        if pm is not None:
            out.addPixmap(pm)
        if selected_light:
            light = pixmap(name, light_cfg, size)
            if light is not None:
                out.addPixmap(light, QIcon.Normal, QIcon.On)
                out.addPixmap(light, QIcon.Selected, QIcon.On)
    return out

# -*- coding: utf-8 -*-
"""图表显示（第五轮）：matplotlib 只用 Agg 后端画成 PNG 字节，再交给 QLabel 显示。

这样不引入任何额外 GUI 后端，也不会和 PySide6 抢事件循环；
matplotlib 缺失或画图异常时一律降级为一行中文提示，绝不让主程序崩溃。
坐标轴文字用英文（内置字体缺中文字形会显示成方块），中文说明放在界面上的标签里。
"""
from __future__ import annotations

import io
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

_DPI = 100
_SIZE = (7.2, 3.6)


def _plt():
    """延迟导入 matplotlib，强制 Agg。返回 pyplot 模块或 None。"""
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        from matplotlib import pyplot as plt
        return plt
    except Exception:                     # 环境缺依赖/字体缓存异常等
        return None


def _to_pixmap(png: bytes) -> Optional[QPixmap]:
    pm = QPixmap()
    return pm if pm.loadFromData(png) else None


def _figure_png_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight")
    plt_close(fig)
    return buf.getvalue()


def plt_close(fig) -> None:
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:
        pass


def _render(draw) -> Tuple[Optional[bytes], str]:
    """通用渲染：draw(plt, fig, ax) -> None；异常/缺依赖返回 (None, 中文原因)。"""
    plt = _plt()
    if plt is None:
        return None, "当前环境缺少绘图组件（matplotlib），图表暂不能显示，数值表格不受影响。"
    try:
        fig, ax = plt.subplots(figsize=_SIZE)
        draw(plt, fig, ax)
        return _figure_png_bytes(fig), ""
    except Exception as exc:                      # 数据形状怪异也不能崩
        return None, "图表生成失败（%s），数值表格不受影响。" % exc


def growth_chart(density: Sequence[Tuple[float, float]],
                 viability: Sequence[Tuple[float, float]]) -> Tuple[Optional[bytes], str]:
    """生长曲线：左轴细胞密度（×10⁶/mL），右轴活率（%）。"""
    def draw(plt, fig, ax):
        ax.grid(True, linestyle=":", alpha=0.4)
        ax.set_xlabel("time (h)")
        ax.set_ylabel("cell density (x10^6 cells/mL)")
        if density:
            ax.plot([p[0] for p in density], [p[1] for p in density], marker="o",
                    color="#1f77b4", linewidth=1.6, label="cell density")
        if viability:
            ax2 = ax.twinx()
            ax2.plot([p[0] for p in viability], [p[1] for p in viability], marker="s",
                     color="#d62728", linewidth=1.4, linestyle="--", label="viability")
            ax2.set_ylabel("viability (%)")
            ax2.set_ylim(0.0, 105.0)
        if density or viability:
            ax.legend(loc="best", fontsize=8)
    return _render(draw)


def metabolite_chart(glucose: Sequence[Tuple[float, Optional[float]]],
                     lactate: Sequence[Tuple[float, Optional[float]]]) -> Tuple[Optional[bytes], str]:
    """代谢趋势：葡萄糖 / 乳酸随时间（只画有数的点）。"""
    def draw(plt, fig, ax):
        ax.grid(True, linestyle=":", alpha=0.4)
        ax.set_xlabel("time (h)")
        ax.set_ylabel("glucose / lactate (g/L)")
        g = [(t, v) for t, v in glucose if v is not None]
        l = [(t, v) for t, v in lactate if v is not None]
        if g:
            ax.plot([p[0] for p in g], [p[1] for p in g], marker="o", color="#2ca02c", label="glucose")
        if l:
            ax.plot([p[0] for p in l], [p[1] for p in l], marker="^", color="#ff7f0e", label="lactate")
        if g or l:
            ax.legend(loc="best", fontsize=8)
    return _render(draw)


class ChartBox(QWidget):
    """一张图的位置：有图显示图，没图显示中文说明，绝不空白一片让人以为卡住。"""

    def __init__(self, caption: str = "", parent=None) -> None:
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self.lbl_caption = QLabel(caption)
        self.lbl_caption.setStyleSheet("font-weight: bold;")
        self._img = QLabel("（还没有数据）")
        self._img.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self._img.setMinimumHeight(40)
        self._lay.addWidget(self.lbl_caption)
        self._lay.addWidget(self._img, 1)

    def show_png(self, png: Optional[bytes], fallback: str = "") -> None:
        if png:
            pm = _to_pixmap(png)
            if pm is None:
                self.set_text(fallback or "图片显示失败，请查看数值表格。")
                return
            self._img.setPixmap(pm.scaled(self.width() or 720, self.height() or 320,
                                          Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self._img.setText("")
        else:
            self.set_text(fallback or "（没有可画的数据）")

    def set_text(self, text: str) -> None:
        self._img.setPixmap(QPixmap())
        self._img.setText(text)
        self._img.setStyleSheet("color: rgb(120,120,120);")
# -*- coding: utf-8 -*-
"""第六轮：生成程序图标 assets/app.ico（纯几何图形，不依赖字体，避免中文渲染问题）。
图案：锥形瓶轮廓 + 培养液 + 气泡，蓝绿配色，寓意细胞培养。
做法：Qt 只在 QImage 上画并另存 PNG，.ico 容器用纯 Python 结构体拼装（Windows 7+ 支持 ICO 内嵌 PNG）。
用法：python tools/make_icon.py
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QPainter,
                           QPen, QPolygonF)

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _paint_png_bytes(size: int, tmp_dir: str) -> bytes:
    """画一个 size x size 的图标，返回 PNG 字节。"""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = float(size)
    # 背景圆角方块
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(235, 245, 250)))
    p.drawRoundedRect(0, 0, size, size, max(2, s * 0.14), max(2, s * 0.14))
    # 锥形瓶轮廓
    neck_w = s * 0.14
    top_y = s * 0.14
    bot_y = s * 0.86
    shoulder_y = s * 0.32
    cx = s * 0.5
    body = QPolygonF([
        QPointF(cx - neck_w / 2, top_y),
        QPointF(cx + neck_w / 2, top_y),
        QPointF(cx + neck_w / 2, shoulder_y),
        QPointF(cx + s * 0.28, bot_y),
        QPointF(cx - s * 0.28, bot_y),
        QPointF(cx - neck_w / 2, shoulder_y),
    ])
    p.setBrush(QBrush(QColor(252, 254, 255)))
    p.setPen(QPen(QColor(35, 95, 140), max(1.0, s * 0.045)))
    p.drawPolygon(body)
    # 培养液（蓝绿）
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(60, 170, 150)))
    liq_top = s * 0.60
    span = bot_y - shoulder_y
    half_at_top = s * 0.28 * (liq_top - shoulder_y) / span if span > 0 else s * 0.28
    liquid = QPolygonF([
        QPointF(cx - half_at_top, liq_top),
        QPointF(cx + half_at_top, liq_top),
        QPointF(cx + s * 0.265, bot_y - s * 0.02),
        QPointF(cx - s * 0.265, bot_y - s * 0.02),
    ])
    p.drawPolygon(liquid)
    # 气泡
    p.setBrush(QBrush(QColor(255, 255, 255)))
    for (fx, fy, fr) in ((0.44, 0.70, 0.035), (0.55, 0.76, 0.028), (0.50, 0.645, 0.020)):
        p.drawEllipse(QPointF(s * fx, s * fy), s * fr, s * fr)
    # 瓶口横杠
    p.setPen(QPen(QColor(35, 95, 140), max(1.0, s * 0.05)))
    p.drawLine(QPointF(cx - neck_w, top_y), QPointF(cx + neck_w, top_y))
    p.end()
    png_path = os.path.join(tmp_dir, "icon_%d.png" % size)
    if not img.save(png_path, "PNG"):
        raise RuntimeError("PNG 保存失败（尺寸 %d）" % size)
    with open(png_path, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"\x89PNG"):
        raise RuntimeError("PNG 数据异常（尺寸 %d）" % size)
    return data


def build_ico(entries, out_path):
    """entries: [(size, png_bytes)]，写成 ICO（内嵌 PNG，Windows 7+ 可识别）。"""
    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)          # 保留字节, 资源类型=图标, 数量
    directory = b""
    payload = b""
    offset = 6 + 16 * count
    for size, png in entries:
        dim = 0 if size >= 256 else size               # 256 在目录项里写作 0
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)
    with open(out_path, "wb") as fh:
        fh.write(header + directory + payload)


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "assets")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "app.ico")
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    entries = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        for size in SIZES:
            entries.append((size, _paint_png_bytes(size, tmp_dir)))
    build_ico(entries, out)
    print("已生成图标：%s（%d 字节，含 %d 个尺寸：%s）"
          % (out, os.path.getsize(out), len(entries), ", ".join(str(s) for s in SIZES)))
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(int(code))
# -*- coding: utf-8 -*-
"""标签页⑥：SOP 防呆引导（第五轮 · 模块 5）。

检查条目全部来自 config.sop.stages（阶段名与条目文字都不写进代码），界面按阶段渲染复选框。
默认每次打开软件都是"全部未勾选"，必须逐条人工确认；确认单可一键复制或导出 CSV 存档。
本页面只是操作提示，不替代本实验室正式批准的 SOP 文件。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from cell_planner.core import sop_checklist as sop
from cell_planner.ui import common

FORCE_ASK = ("按 config.sop.require_all_checked_for_export 的要求，还有未确认条目时暂不能导出确认单。\n\n"
             "是否仍然强制导出？强制导出的确认单里，未勾选的条目会逐条标注为「%s」。\n\n（建议：先把剩下的条目逐条"
             "确认完再导出，正式记录更可靠。）")


class SopTab(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.cfg = host.cfg
        self.boxes: Dict[str, QCheckBox] = {}
        self.stage_labels: Dict[str, QLabel] = {}
        self._build_ui()
        self._update()

    # ---------------- 布局 ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.btn_uncheck = QPushButton("🔄 开始新批次：全部取消勾选")
        self.btn_check_copy = QPushButton("📋 复制确认单文本")
        self.btn_export = QPushButton("💾 导出确认单 CSV")
        for button in (self.btn_uncheck, self.btn_check_copy):
            button.setProperty("uiRole", "secondary")
        for b in (self.btn_uncheck, self.btn_check_copy, self.btn_export):
            bar.addWidget(b)
        bar.addStretch(1)
        outer.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, sop.total_items(self.cfg)))
        self.progress.setFormat("已确认 %v / %m 项（%p%）")
        outer.addWidget(self.progress)
        self.lbl_rule = common.status_label("")
        self.lbl_rule.setWordWrap(True)
        outer.addWidget(self.lbl_rule)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        self.lay = QVBoxLayout(page)
        self._build_stages()

        self.btn_uncheck.clicked.connect(self.uncheck_all)
        self.btn_check_copy.clicked.connect(self.copy_sheet)
        self.btn_export.clicked.connect(self.export_csv)

    def _build_stages(self) -> None:
        for st in sop.stages(self.cfg):
            box = QGroupBox("阶段 %d：%s" % (self._stage_no(st["key"]), st["name"]))
            v = QVBoxLayout(box)
            lbl = common.status_label("")
            v.addWidget(lbl)
            self.stage_labels[st["key"]] = lbl
            for i, text in enumerate(st["items"], start=1):
                cid = sop.item_id(st["key"], i)
                cb = QCheckBox(text)
                cb.setProperty("item_id", cid)
                cb.stateChanged.connect(lambda _=0: self._update())
                v.addWidget(cb)
                self.boxes[cid] = cb
            self.lay.addWidget(box)
        self.lay.addStretch(1)

    def _stage_no(self, key: str) -> int:
        for i, st in enumerate(sop.stages(self.cfg), start=1):
            if st["key"] == key:
                return i
        return 0

    # ---------------- 状态 ----------------
    def checked_ids(self) -> List[str]:
        return [cid for cid, cb in self.boxes.items() if cb.isChecked()]

    def _update(self) -> None:
        got = self.checked_ids()
        prog = sop.progress(got, self.cfg)
        self.progress.setMaximum(max(1, prog["total"]))
        self.progress.setValue(prog["done"])
        for st in prog["stages"]:
            lbl = self.stage_labels.get(st["key"])
            if lbl is not None:
                lbl.setText(("✅ " if st["all_done"] else "🟡 ") + st["text"])
                lbl.setStyleSheet("color: %s; font-weight: bold;"
                                  % ("rgb(0,120,0)" if st["all_done"] else "rgb(150,90,0)"))
        ok, message = sop.export_gate(got, self.cfg)
        self.lbl_rule.setText("正式操作以本实验室批准的 SOP 为准，需第二人复核。\n" + message)
        self.lbl_rule.setStyleSheet("color: %s; background-color: %s; padding: 6px; border-radius: 4px;"
                                    % (("rgb(0,110,0)" if ok and prog["all_done"] else "rgb(150,90,0)"),
                                       ("rgb(227,244,227)" if prog["all_done"] else "rgb(255,246,200)")))

    def _rule_text(self) -> str:
        n = sop.total_items(self.cfg)
        return ("本清单共 %d 项，来自 config.sop.stages（条目文字可在 config 里改，不用改代码）。"
                "当前要求：未全部勾选时%s导出确认单；每次打开软件默认全部未勾选%s。"
                "本软件不连接、不控制 my-Control 硬件，正式操作仍以本实验室批准的 SOP 为准，需第二人复核。"
                % (n,
                   "仍" if sop.require_all_checked(self.cfg) is False else "不能",
                   "" if sop.reset_on_new_batch(self.cfg) else "（本会话内可沿用上次勾选）"))

    def uncheck_all(self) -> None:
        for cb in self.boxes.values():
            cb.setChecked(False)
        self._update()
        QMessageBox.information(self, "已重置", "全部检查项已取消勾选。新批次请逐条重新确认后再打勾。")

    # ---------------- 复制 / 导出 ----------------
    def copy_sheet(self) -> None:
        text = sop.sheet_text(self.checked_ids(), self.cfg)
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "已复制", "SOP 确认单已复制到剪贴板，可直接粘贴到 Excel、Word 或微信。")

    def export_csv(self) -> None:
        got = self.checked_ids()
        ok, message = sop.export_gate(got, self.cfg)
        force = False
        if not ok:
            answer = QMessageBox.question(
                self, "还有未确认条目", FORCE_ASK % sop.NOT_CONFIRMED,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
            force = True
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(self, "导出 SOP 确认单 CSV",
                                              "SOP确认单_%s.csv" % stamp, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            out = sop.export_csv(path, got, self.cfg, force=force)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        tip = "确认单已导出：\n%s\n\n" % out
        if force:
            tip += "注意：本次为强制导出，未勾选条目已标注「%s」，请务必补做确认。\n\n" % sop.NOT_CONFIRMED
        QMessageBox.information(self, "已导出", tip + "操作人与第二人复核签名请在纸质/电子记录上补签。")

    # ---------------- 配置联动 ----------------
    def refresh_cfg(self) -> None:
        self.cfg = self.host.cfg
        try:
            ids = [row["id"] for row in sop.all_items(self.cfg)]
        except ValueError as exc:
            QMessageBox.warning(self, "config 里的 SOP 条目有问题", str(exc))
            return
        if sorted(ids) != sorted(self.boxes.keys()):
            self._clear_stages()
            self._build_stages()
        self._update()

    def _clear_stages(self) -> None:
        self.boxes = {}
        self.stage_labels = {}
        while self.lay.count():
            item = self.lay.takeAt(0)
            wid = item.widget()
            if wid is not None:
                wid.setParent(None)
                wid.deleteLater()
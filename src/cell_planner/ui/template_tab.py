# -*- coding: utf-8 -*-
"""标签页⑤：模板库与批次对比（第五轮 · 模块 4，答复#11）。

两件事：
  1) 实验方案模板：把①页当前参数存成模板，下次一键回填①页（SQLite：data/templates.db，本地文件，不联网）。
  2) 批次记录对比：③页分析完保存的批次摘要，勾选 2 个以上做"多批次关键参数对比"。
与第三轮的 JSON 配方互不替代：配方=①页输入快照（人可读可拷贝），模板=方案库（含备注），批次=分析结果摘要。
对比展示哪些字段由 config.template_library.compare_fields 决定，界面不写死。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from cell_planner.core import analysis as an
from cell_planner.core import template_store as ts
from cell_planner.ui import common

TPL_HEADERS = ["模板名称", "类型", "备注", "创建时间", "更新时间"]
BATCH_HEADERS = ["批次名", "保存时间", "是否模拟数据", "控制数据文件", "离线取样文件"]


class TemplateTab(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.cfg = host.cfg
        self._build_ui()
        self.refresh()

    # ---------------- 布局 ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll)
        lay = QVBoxLayout(page)

        # ---- 模板库 ----
        box_tpl = QGroupBox("实验方案模板")
        tl = QVBoxLayout(box_tpl)
        self.tbl_tpl = common.make_table(TPL_HEADERS)
        tl.addWidget(self.tbl_tpl)
        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("模板名称："))
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("同名模板将覆盖")
        row_name.addWidget(self.edit_name, 1)
        row_name.addWidget(QLabel("备注："))
        self.edit_note = QLineEdit()
        self.edit_note.setPlaceholderText("选填")
        row_name.addWidget(self.edit_note, 1)
        tl.addLayout(row_name)
        row_btn = QHBoxLayout()
        self.btn_save = QPushButton("把①页当前参数存为模板")
        self.btn_load = QPushButton("载入选中行 → ①页")
        self.btn_del = QPushButton("删除选中模板")
        self.btn_refresh = QPushButton("刷新")
        for button in (self.btn_load, self.btn_del, self.btn_refresh):
            button.setProperty("uiRole", "secondary")
        for b in (self.btn_save, self.btn_load, self.btn_del, self.btn_refresh):
            row_btn.addWidget(b)
        row_btn.addStretch(1)
        tl.addLayout(row_btn)
        lay.addWidget(box_tpl)

        # ---- 批次记录 ----
        box_bat = QGroupBox("批次记录")
        bl = QVBoxLayout(box_bat)
        self.tbl_batch = common.make_table(BATCH_HEADERS)
        self.tbl_batch.setSelectionMode(QAbstractItemView.ExtendedSelection)
        bl.addWidget(self.tbl_batch)
        row_b = QHBoxLayout()
        self.btn_cmp = QPushButton("对比选中批次（Ctrl 多选）")
        self.btn_del_batch = QPushButton("删除勾选的批次记录")
        self.btn_refresh_b = QPushButton("刷新")
        for button in (self.btn_del_batch, self.btn_refresh_b):
            button.setProperty("uiRole", "secondary")
        for b in (self.btn_cmp, self.btn_del_batch, self.btn_refresh_b):
            row_b.addWidget(b)
        row_b.addStretch(1)
        bl.addLayout(row_b)
        lay.addWidget(box_bat)

        # ---- 对比结果 ----
        box_cmp = QGroupBox("批次对比")
        cl = QVBoxLayout(box_cmp)
        self.tbl_cmp = common.make_table(["指标"])
        cl.addWidget(self.tbl_cmp)
        self.lbl_cmp = common.status_label("暂无对比结果")
        cl.addWidget(self.lbl_cmp)
        lay.addWidget(box_cmp, 1)

        self.btn_save.clicked.connect(self.save_template)
        self.btn_load.clicked.connect(self.load_template)
        self.btn_del.clicked.connect(self.delete_template)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_cmp.clicked.connect(self.compare)
        self.btn_del_batch.clicked.connect(self.delete_batches)
        self.btn_refresh_b.clicked.connect(self.refresh)

    # ---------------- 刷新列表 ----------------
    def refresh(self) -> None:
        err = []
        try:
            rows = ts.list_setup_templates()
        except ValueError as exc:
            rows, _ = [], err.append(str(exc))
        common.fill_table(self.tbl_tpl, TPL_HEADERS,
                          [[r["名称"], r["类型"], r["备注"], r["创建时间"], r["更新时间"]] for r in rows])
        if rows and self.tbl_tpl.rowCount():
            self.tbl_tpl.setCurrentCell(0, 0)

        try:
            brows = ts.list_batches()
        except ValueError as exc:
            brows, _ = [], err.append(str(exc))
        common.fill_table(self.tbl_batch, BATCH_HEADERS,
                          [[r["批次名"], r["保存时间"], r["是否模拟数据"],
                            _short(r["控制数据文件"]), _short(r["离线取样文件"])] for r in brows],
                          level_of=lambda r: (an.LEVEL_WARN if "SIMULATED" in str(r[2]) else an.LEVEL_PASS))
        db = ts.db_path(self.cfg)
        status = "模板库文件：%s（%s）" % (db, "已存在" if db.is_file() else "首次保存时自动创建")
        if err:
            status = "❌ " + "；".join(err)
        self.lbl_cmp.setText(status + "\n当前：模板 %d 个、批次记录 %d 个。" % (len(rows), len(brows)))

    def _selected_name(self, tbl, headers: List[str], what: str) -> Optional[str]:
        if not tbl.rowCount():
            QMessageBox.information(self, "列表是空的", "还没有%s，请先创建。" % what)
            return None
        r = tbl.currentRow()
        if r < 0:
            QMessageBox.information(self, "没选中行", "请先在表里点选一行%s，再做这一步。" % what)
            return None
        item = tbl.item(r, 0)
        return None if item is None else str(item.text())

    # ---------------- 模板操作 ----------------
    def save_template(self) -> None:
        name = self.edit_name.text().strip()
        if not name:
            name, ok = QInputDialog.getText(self, "保存实验方案模板",
                                            "给这个方案模板起个名字（建议含细胞株/体积）：")
            if not ok or not name.strip():
                return
            self.edit_name.setText(name.strip())
        params = {}
        try:
            params = dict(self.host._collect_params())
        except Exception as exc:                      # ①页理论上不会抛
            QMessageBox.critical(self, "取参数失败", "读取①页参数时出现问题：%s" % exc)
            return
        try:
            msg = ts.save_setup_template(name, params, note=self.edit_note.text().strip())
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "已保存", msg + "\n模板里记了 %d 项参数，下次点「载入选中行」即可回填①页。"
                                % len(params))
        self.refresh()

    def load_template(self) -> None:
        name = self._selected_name(self.tbl_tpl, TPL_HEADERS, "模板")
        if not name:
            return
        try:
            data = ts.load_setup_template(name)
        except ValueError as exc:
            QMessageBox.warning(self, "载入失败", str(exc))
            return
        params = data.get("参数") or {}
        if not isinstance(params, dict) or not params:
            QMessageBox.warning(self, "模板是空的", "模板「%s」里没有参数，请删除后重新保存。" % name)
            return
        try:
            self.host._apply_params(params)
            self.host.compute()
        except Exception as exc:
            QMessageBox.critical(self, "回填①页失败",
                                 "参数已读出，但填回①页时出问题：%s" % exc)
            return
        # 第七轮：主界面变成"3 大板块 + 板块内子页签"，按序号跳页已无意义，统一走 goto_page(key)
        moved = False
        goto = getattr(self.host, "goto_page", None)
        if callable(goto):
            try:
                moved = bool(goto("planner"))
            except Exception:
                moved = False
        if not moved:
            tabs = getattr(self.host, "tabs", None)
            if tabs is not None:
                tabs.setCurrentIndex(0)
        QMessageBox.information(self, "已载入", "模板「%s」的 %d 项参数已填入①页并重新计算。\n"
                                              "备注：%s\n别忘了：计算结果仍需人工复核。"
                                              % (name, len(params), data.get("备注") or "（无）"))

    def delete_template(self) -> None:
        name = self._selected_name(self.tbl_tpl, TPL_HEADERS, "模板")
        if not name:
            return
        if QMessageBox.question(self, "确认删除", "确定删除模板「%s」吗？删除后不能恢复。" % name,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            ts.delete_setup_template(name)
        except ValueError as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        QMessageBox.information(self, "已删除", "模板「%s」已删除。" % name)
        self.refresh()

    # ---------------- 批次操作 ----------------
    def _checked_batches(self) -> List[str]:
        names: List[str] = []
        for idx in self.tbl_batch.selectionModel().selectedRows():
            item = self.tbl_batch.item(idx.row(), 0)
            if item is not None:
                names.append(str(item.text()))
        if not names:
            row = self.tbl_batch.currentRow()
            item = self.tbl_batch.item(row, 0) if row >= 0 else None
            if item is not None:
                names = [str(item.text())]
        return names

    def compare(self) -> None:
        names = self._checked_batches()
        try:
            rows = ts.compare_batches(names, cfg=self.cfg)
        except ValueError as exc:
            QMessageBox.information(self, "还不能对比", str(exc))
            return
        headers = ["指标"] + names
        data = [[r["label"]] + [an.fmt_metric(r["key"], r["values"].get(n), self.cfg) for n in names]
                for r in rows]
        common.fill_table(self.tbl_cmp, headers, data)
        sim = [n for n in names if any("SIMULATED" in str(self.tbl_batch.item(i, 2).text())
                                      for i in range(self.tbl_batch.rowCount())
                                      if self.tbl_batch.item(i, 0)
                                      and self.tbl_batch.item(i, 0).text() == n)]
        note = "✅ 已对比 %d 个批次（%s）。" % (len(names), "、".join(names))
        if sim:
            note += "\n⚠️ 其中「%s」是 SIMULATED 模拟数据，只能用来验证对比功能，不能当真实批次结论。" % "、".join(sim)
        note += "\n提示：数值缺测显示为 —；对比结论仍需人工复核。"
        self.lbl_cmp.setText(note)

    def delete_batches(self) -> None:
        names = self._checked_batches()
        if not names:
            QMessageBox.information(self, "没选中批次", "请先在批次表里点选（可按住 Ctrl 多选）要删除的批次。")
            return
        if QMessageBox.question(self, "确认删除", "确定删除这 %d 个批次记录吗？\n%s\n删除后不能恢复。"
                                % (len(names), "、".join(names)),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        errs = []
        for name in names:
            try:
                ts.delete_batch(name)
            except ValueError as exc:
                errs.append(str(exc))
        if errs:
            QMessageBox.warning(self, "部分删除失败", "；".join(errs))
        else:
            QMessageBox.information(self, "已删除", "共删除 %d 个批次记录。" % len(names))
        self.refresh()

    # ---------------- 配置联动 ----------------
    def refresh_cfg(self) -> None:
        self.cfg = self.host.cfg
        self.refresh()


def _short(path: str, limit: int = 28) -> str:
    """文件路径太长时中间省略，只留文件名附近，表格里看得清。"""
    s = str(path or "")
    if not s:
        return common.DASH
    if len(s) <= limit:
        return s
    name = Path(s).name
    return "…" + name[-(limit - 1):] if len(name) > limit else s[:10] + "…" + name
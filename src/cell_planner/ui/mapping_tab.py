# -*- coding: utf-8 -*-
"""标签页④：列名映射（第五轮 · 模块 3 配套，答复#8）。

真实 my-Control 导出文件到手后，在这里把「逻辑字段」对应到「实际列名」并保存，
③「离线分析」页就会按这份映射读数据。映射存成人类可读的 JSON（路径见 config.column_mapping.mapping_file），
也可以直接用记事本改。表头读不出来 / 文件不存在等情况一律转成中文提示，不崩溃。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from cell_planner.core import column_mapping as cmap
from cell_planner.io_ import csv_reader as rd

HEADERS = ["逻辑字段（软件内部用的名字）", "单位", "必需", "对应到 CSV 的哪一列", "候选列名写法（供参考）"]
NONE_ITEM = "（不使用这一项）"
WAIT_ITEM = "（先选样例文件并读取表头）"


class MappingTab(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.cfg = host.cfg
        self.headers: Dict[str, List[str]] = {cmap.DATASET_CONTROL: [], cmap.DATASET_OFFLINE: []}
        self.edits: Dict[str, QLineEdit] = {}
        self.tables: Dict[str, QTableWidget] = {}
        self.combos: Dict[str, Dict[str, QComboBox]] = {}
        self.loaded: Dict[str, Dict[str, str]] = {cmap.DATASET_CONTROL: {}, cmap.DATASET_OFFLINE: {}}
        self._build_ui()
        self._refresh_cfg()

    # ---------------- 布局 ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll)
        lay = QVBoxLayout(page)

        box_pick = QGroupBox("选择 CSV 文件")
        pl = QVBoxLayout(box_pick)
        for kind in (cmap.DATASET_CONTROL, cmap.DATASET_OFFLINE):
            row = QHBoxLayout()
            row.addWidget(QLabel(cmap.DATASET_LABEL[kind] + "："))
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.setPlaceholderText("选择 CSV 文件")
            btn = QPushButton("浏览…")
            btn.clicked.connect(lambda _=False, k=kind, e=edit: self._pick(k, e))
            row.addWidget(edit, 1)
            row.addWidget(btn)
            pl.addLayout(row)
            self.edits[kind] = edit
        row_btn = QHBoxLayout()
        self.btn_use3 = QPushButton("使用分析页的文件")
        self.btn_load = QPushButton("读取表头")
        self.btn_use3.setProperty("uiRole", "secondary")
        self.btn_use3.clicked.connect(self._use_tab3_files)
        self.btn_load.clicked.connect(self._load_headers)
        row_btn.addWidget(self.btn_use3)
        row_btn.addWidget(self.btn_load)
        row_btn.addStretch(1)
        pl.addLayout(row_btn)
        lay.addWidget(box_pick)

        # 每个数据集一张映射表
        for kind in (cmap.DATASET_CONTROL, cmap.DATASET_OFFLINE):
            lay.addWidget(self._section_box(kind))

        box_act = QGroupBox("检查并保存")
        al = QVBoxLayout(box_act)
        row_act = QHBoxLayout()
        self.btn_save = QPushButton("💾 保存映射（③页立即生效）")
        self.btn_clear = QPushButton("本两页全部改回「不使用」")
        self.btn_check = QPushButton("检查映射是否与表头一致")
        self.btn_open = QPushButton("打开映射文件所在位置")
        for button in (self.btn_clear, self.btn_check, self.btn_open):
            button.setProperty("uiRole", "secondary")
        for b in (self.btn_save, self.btn_check, self.btn_clear, self.btn_open):
            row_act.addWidget(b)
        row_act.addStretch(1)
        al.addLayout(row_act)
        self.lbl_path = QLabel("")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("color: rgb(80,80,80);")
        al.addWidget(self.lbl_path)
        self.lbl_status = QLabel("还没有读取表头。")
        self.lbl_status.setWordWrap(True)
        al.addWidget(self.lbl_status)
        al.addWidget(self._boxed("检查结果（红=必须改，黄=建议确认）"))
        lay.addWidget(box_act)

        self.btn_save.clicked.connect(self._save)
        self.btn_check.clicked.connect(self._check)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_open.clicked.connect(self._open_dir)

    def _section_box(self, kind: str) -> QGroupBox:
        box = QGroupBox(cmap.DATASET_LABEL[kind])
        v = QVBoxLayout(box)
        tbl = _make_grid(HEADERS)
        v.addWidget(tbl)
        self.tables[kind] = tbl
        self.combos[kind] = {}
        row_btn = QHBoxLayout()
        btn_auto = QPushButton("按候选列名自动匹配这一类")
        btn_auto.setProperty("uiRole", "secondary")
        btn_auto.clicked.connect(lambda _=False, k=kind: self._auto_match(k))
        row_btn.addWidget(btn_auto)
        row_btn.addStretch(1)
        v.addLayout(row_btn)
        for f in cmap.fields_for(kind, self.cfg):
            self._append_field_row(kind, tbl, f)
        return box

    def _append_field_row(self, kind: str, tbl: QTableWidget, f: dict) -> None:
        r = tbl.rowCount()
        tbl.insertRow(r)
        texts = [f["label"], f["unit"] or "—", "必需" if f["required"] else "可选", "",
                 "、".join(f["candidates"]) or "（config 里没给候选写法）"]
        for c, text in enumerate(texts):
            if c == 3:
                continue
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if c == 2 and f["required"]:
                item.setForeground(Qt.darkRed)
            tbl.setItem(r, c, item)
        combo = QComboBox()
        combo.addItem(NONE_ITEM)
        combo.setEnabled(False)
        combo.setToolTip(WAIT_ITEM)
        tbl.setCellWidget(r, 3, combo)
        self.combos[kind][f["key"]] = combo

    def _boxed(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        v = QVBoxLayout(box)
        self.tbl_check = _make_grid(["级别", "说明"])
        v.addWidget(self.tbl_check)
        return box

    # ---------------- 表头读取 ----------------
    def _pick(self, kind: str, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 CSV 文件", str(Path.cwd()),
                                              "CSV 文件 (*.csv *.txt);;所有文件 (*)")
        if path:
            edit.setText(path)

    def _use_tab3_files(self) -> None:
        tab3 = getattr(self.host, "analysis_tab", None)
        if tab3 is None:
            QMessageBox.information(self, "找不到③页", "主窗口里没有③页控件，请直接用上面的「浏览…」。")
            return
        pairs = {cmap.DATASET_CONTROL: tab3.edit_ctrl.text().strip(),
                 cmap.DATASET_OFFLINE: tab3.edit_off.text().strip()}
        got = [k for k, v in pairs.items() if v]
        for k, v in pairs.items():
            if v:
                self.edits[k].setText(v)
        if not got:
            QMessageBox.information(self, "③页还没选文件",
                                    "请到③「离线分析」页先选 CSV，或在这里直接点「浏览…」。")
            return
        self._load_headers(got)

    def _read_header(self, kind: str):
        path = self.edits[kind].text().strip()
        if not path:
            return None
        try:
            raw = rd.read_raw_table(path, self.cfg)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "读不出表头", "%s读取失败：\n%s" % (cmap.DATASET_LABEL[kind], exc))
            return None
        self.headers[kind] = [str(h) for h in raw.header]
        combos = self.combos[kind]
        for combo in combos.values():
            combo.setEnabled(True)
            combo.clear()
            combo.addItem(NONE_ITEM)
            for h in self.headers[kind]:
                combo.addItem(h)
        # 保留已保存的映射：不在表头里的旧列名也塞进下拉框，便于用户看见问题
        for key, combo in combos.items():
            saved = str(self.loaded.get(kind, {}).get(key, "") or "")
            if saved and saved not in self.headers[kind]:
                combo.addItem(saved + "（表头里找不到）")
                combo.setCurrentText(saved + "（表头里找不到）")
            elif saved:
                combo.setCurrentText(saved)
            else:
                combo.setCurrentIndex(0)
        tip = "列名映射文件：%s（可直接用记事本查看/修改）" % cmap.mapping_path(self.cfg)
        self.lbl_path.setText(tip)
        sim = "（SIMULATED 模拟数据）" if raw.is_simulated else ""
        return "%s：共 %d 列、%d 行数据%s" % (cmap.DATASET_LABEL[kind], len(raw.header), raw.n_rows, sim)

    def _load_headers(self, only=None) -> None:
        kinds = list(only) if only else [cmap.DATASET_CONTROL, cmap.DATASET_OFFLINE]
        msgs = []
        for kind in kinds:
            info = self._read_header(kind)
            if info:
                msgs.append(info)
        if not msgs:
            self.lbl_status.setText("还没有读取表头。请先给至少一类文件选一个 CSV，再点「读取表头」。")
            QMessageBox.information(self, "还没选文件",
                                    "请先给「控制数据」或「离线取样数据」选一个实际的 CSV 文件。")
            return
        self.lbl_status.setText("✅ 已读取表头。\n" + "\n".join(msgs) +
                                "\n下一步：点「按候选列名自动匹配」，或者手动在下拉框里选列名，然后保存。")
        self._check()

    # ---------------- 自动匹配 / 清空 ----------------
    def _auto_match(self, kind: str) -> None:
        header = self.headers.get(kind) or []
        if not header:
            QMessageBox.information(self, "还没有表头",
                                    "请先为「%s」选择样例 CSV 并点「读取表头」。" % cmap.DATASET_LABEL[kind])
            return
        matched = cmap.auto_match(header, kind, self.cfg)
        hit = 0
        for key, combo in self.combos[kind].items():
            col = str(matched.get(key, "") or "")
            if col:
                combo.setCurrentText(col)
                hit += 1
            else:
                combo.setCurrentIndex(0)
        self.lbl_status.setText("自动匹配完成：「%s」匹配上 %d / %d 个字段。"
                                "对不上的请手动改，改完点「保存映射」。"
                                % (cmap.DATASET_LABEL[kind], hit, len(self.combos[kind])))

    def _current_mapping(self, kind: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, combo in self.combos[kind].items():
            text = str(combo.currentText() or "").strip()
            if text in (NONE_ITEM, WAIT_ITEM) or text.endswith("（表头里找不到）"):
                text = ""
            out[key] = text
        return out

    def _clear_all(self) -> None:
        for kind in self.combos:
            for combo in self.combos[kind].values():
                combo.setEnabled(True)
                combo.setCurrentIndex(0)
        self.lbl_status.setText("已把两类字段全部改回「不使用」。（还没写入文件）留空时，③页会自动按候选列名猜；"
                                "要让③页真的用上这份空映射，请点「保存映射」。")

    # ---------------- 检查 / 保存 ----------------
    def _gather_check(self) -> List[dict]:
        rows: List[dict] = []
        for kind in (cmap.DATASET_CONTROL, cmap.DATASET_OFFLINE):
            header = self.headers.get(kind) or []
            mapping = self._current_mapping(kind)
            if not header:
                rows.append({"level": "warn",
                             "text": "「%s」还没读表头，暂时无法检查这一类的映射。" % cmap.DATASET_LABEL[kind]})
                continue
            for msg in cmap.validate_mapping(mapping, header, kind, self.cfg):
                rows.append({"level": msg["level"], "text": "「%s」：%s" % (cmap.DATASET_LABEL[kind], msg["text"])})
        return rows

    def _check(self) -> None:
        rows = self._gather_check()
        self._fill_check(rows)
        n_err = sum(1 for r in rows if r["level"] == "error")
        n_warn = len(rows) - n_err
        if not rows:
            self.lbl_status.setText("✅ 映射检查通过：必需字段都已对应到实际存在的列，且没有一列被重复使用。")
        else:
            self.lbl_status.setText("检查结果：红色 %d 条、黄色 %d 条，详见下表。红色不解决，③页会读不出该字段。"
                                    % (n_err, n_warn))

    def _fill_check(self, rows: List[dict]) -> None:
        tbl = self.tbl_check
        tbl.clearContents()
        tbl.setRowCount(len(rows) or 1)
        data = rows or [{"level": "pass", "text": "没有发现问题。"}]
        for r, row in enumerate(data):
            icon = {"error": "🔴", "warn": "🟡", "pass": "✅"}.get(str(row["level"]), "🟡")
            for c, text in enumerate([icon, row["text"]]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                tbl.setItem(r, c, item)
        tbl.resizeColumnsToContents()
        tbl.horizontalHeader().setStretchLastSection(True)

    def _save(self) -> None:
        control = self._current_mapping(cmap.DATASET_CONTROL) if self.headers[cmap.DATASET_CONTROL] \
            else dict(self.loaded.get(cmap.DATASET_CONTROL) or cmap.blank_mapping(cmap.DATASET_CONTROL, self.cfg))
        offline = self._current_mapping(cmap.DATASET_OFFLINE) if self.headers[cmap.DATASET_OFFLINE] \
            else dict(self.loaded.get(cmap.DATASET_OFFLINE) or cmap.blank_mapping(cmap.DATASET_OFFLINE, self.cfg))
        untouched = [cmap.DATASET_LABEL[k] for k in (cmap.DATASET_CONTROL, cmap.DATASET_OFFLINE)
                     if not self.headers[k]]
        try:
            path = cmap.save_all(control, offline, cfg=self.cfg)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.loaded = {cmap.DATASET_CONTROL: control, cmap.DATASET_OFFLINE: offline}
        self.lbl_path.setText("列名映射文件：%s（可直接用记事本查看/修改）" % path)
        msg = "✅ 已保存到：\n%s\n\n回到③「离线分析」页点「▶ 运行分析」即可使用这份映射。" % path
        if untouched:
            msg += "\n\n注意：本次未读取表头的「%s」沿用了已保存的映射，没有改动。" % "、".join(untouched)
        QMessageBox.information(self, "已保存映射", msg)
        self._check()

    def _open_dir(self) -> None:
        path = cmap.mapping_path(self.cfg)
        self.lbl_status.setText("映射文件保存在：%s（不存在表示还没保存过）。"
                                "它在你电脑的 data 文件夹里，本软件不联网、不上传。" % path)

    # ---------------- 配置联动 ----------------
    def _refresh_cfg(self) -> None:
        self.cfg = self.host.cfg
        self.loaded = cmap.load_all(cfg=self.cfg)
        for kind in (cmap.DATASET_CONTROL, cmap.DATASET_OFFLINE):
            for key, combo in self.combos[kind].items():
                saved = str(self.loaded.get(kind, {}).get(key, "") or "")
                if self.headers.get(kind):
                    if saved and saved not in self.headers[kind]:
                        combo.addItem(saved + "（表头里找不到）")
                    if saved:
                        combo.setCurrentText(saved if saved in self.headers[kind]
                                             else saved + "（表头里找不到）")
                        continue
                combo.setCurrentIndex(0)
        self.lbl_path.setText("列名映射文件：%s%s" % (cmap.mapping_path(self.cfg),
                                                     "（已存在）" if cmap.mapping_path(self.cfg).is_file()
                                                     else "（还没有保存过，首次使用时会自动按候选列名猜）"))


def _make_grid(headers: List[str]) -> QTableWidget:
    tbl = QTableWidget(0, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    tbl.verticalHeader().setVisible(False)
    hdr = tbl.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.Interactive)
    hdr.setStretchLastSection(True)
    for c, width in enumerate([230, 70, 50, 260, 320][:len(headers)]):
        tbl.setColumnWidth(c, width)
    return tbl
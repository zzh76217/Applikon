# -*- coding: utf-8 -*-
"""标签页③：离线分析（第五轮 · 模块 3）。

导入 my-Control 导出的控制数据 CSV + 离线取样 CSV，产出：
生长曲线与 μ 拟合、摄糖/产乳酸趋势、DO 偏差报警、DO 消耗速率外推提示、收获建议。
判定阈值全部来自 config；界面所有异常都转成中文提示，不弹 traceback、不崩溃。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QVBoxLayout, QWidget,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from cell_planner.core import analysis as an
from cell_planner.core import app_info
from cell_planner.core import column_mapping as cmap
from cell_planner.core import template_store
from cell_planner.core.config_loader import get_config
from cell_planner.io_ import csv_reader as rd
from cell_planner.io_ import simulator
from cell_planner.ui import chart_view, common, theme

METAB_HEADERS = ["时刻(h)", "葡萄糖(g/L)", "葡萄糖(mmol/L)", "糖警戒",
                 "乳酸(g/L)", "乳酸(mmol/L)", "乳酸警戒", "说明"]

_LEVEL_BY_ICON = {common.level_icon(lv): lv for lv in
                  (an.LEVEL_PASS, an.LEVEL_WARN, an.LEVEL_ERROR, an.LEVEL_NONE)}
_WORST_FIRST = (an.LEVEL_ERROR, an.LEVEL_WARN, an.LEVEL_PASS, an.LEVEL_NONE)


def _worst_level(*icons: str) -> str:
    """把若干列的级别图标换算回级别，再取其中最严重的一档（给整行上底色用）。"""
    levels = [_LEVEL_BY_ICON.get(str(i), str(i)) for i in icons]
    for lv in _WORST_FIRST:
        if lv in levels:
            return lv
    return an.LEVEL_NONE



class AnalysisTab(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.cfg = host.cfg
        self.res: Optional[dict] = None
        self._build_ui()
        try:
            self._refresh_map_hint()      # 第七轮：首帧就显示映射状态，不必等到 showEvent
        except Exception:
            pass

    # ---------------- 布局 ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll)
        lay = QVBoxLayout(page)

        # 数据文件区
        box_file = QGroupBox("选择数据文件")
        bl = QVBoxLayout(box_file)
        self.edit_ctrl, row_ctrl = self._file_row("控制数据（DO/pH/温度/转速/MFC 随时间）")
        self.edit_off, row_off = self._file_row("离线取样（细胞密度/活率/葡萄糖/乳酸）")
        bl.addLayout(row_ctrl)
        bl.addLayout(row_off)
        row_btn = QHBoxLayout()
        self.btn_sim = QPushButton("生成模拟数据（仅测试）")
        self.btn_sim.setProperty("uiRole", "secondary")
        row_btn.addWidget(self.btn_sim)
        row_btn.addStretch(1)
        bl.addLayout(row_btn)
        # 第七轮：顶部一行映射状态提示（只做显示与跳转，不参与任何分析计算）
        row_map = QHBoxLayout()
        self.lbl_map_hint = QLabel("")
        self.lbl_map_hint.setWordWrap(True)
        self.btn_goto_map = QPushButton(app_info.ui_text(self.cfg, "mapping_goto", "去「列名映射」"))
        self.btn_goto_map.setMaximumWidth(160)
        self.btn_goto_map.setProperty("uiRole", "secondary")
        self.btn_goto_map.clicked.connect(self._goto_mapping)
        row_map.addWidget(self.lbl_map_hint, 1)
        row_map.addWidget(self.btn_goto_map)
        lay.addLayout(row_map)
        lay.addWidget(box_file)

        # 设定区
        box_set = QGroupBox("分析设定")
        form = QHBoxLayout(box_set)
        form.addWidget(QLabel("DO 设定点："))
        self.spin_do = QDoubleSpinBox()
        self.spin_do.setRange(0.0, 100.0)
        self.spin_do.setDecimals(1)
        self.spin_do.setMaximumWidth(150)
        self.spin_do.setSuffix(" %")
        self.spin_do.setValue(float(self.cfg["process_defaults"]["do_percent"]["set"]))
        form.addWidget(self.spin_do)
        form.addStretch(1)
        lay.addWidget(box_set)

        # 动作区
        row_act = QHBoxLayout()
        self.btn_run = QPushButton("▶ 运行分析")
        self.btn_export = QPushButton("导出分析报告 CSV")
        self.btn_copy = QPushButton("复制分析摘要")
        self.btn_save_batch = QPushButton("把本次分析存为批次记录（⑤页可对比）")
        for button in (self.btn_export, self.btn_copy, self.btn_save_batch):
            button.setProperty("uiRole", "secondary")
        for b in (self.btn_run, self.btn_export, self.btn_copy, self.btn_save_batch):
            row_act.addWidget(b)
        row_act.addStretch(1)
        lay.addLayout(row_act)

        self.banner = common.banner("")
        self.banner.setVisible(False)
        lay.addWidget(self.banner)

        self.lbl_status = common.status_label("暂无分析结果")
        lay.addWidget(self.lbl_status)

        # 结果区
        split = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        self.tbl_metrics = common.make_table(["指标", "数值"])
        ll.addWidget(self._boxed("批次关键参数摘要", self.tbl_metrics))
        self.tbl_events = common.make_table(["级别", "类型", "起始(h)", "结束(h)", "持续(分钟)", "最低DO(%)", "说明"])
        ll.addWidget(self._boxed("DO 报警事件", self.tbl_events))
        self.tbl_notes = common.make_table(["类型", "内容"])
        ll.addWidget(self._boxed("数据质量提示 / 错误", self.tbl_notes))
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.chart_growth = chart_view.ChartBox("生长曲线（细胞密度 + 活率）")
        self.chart_metab = chart_view.ChartBox("代谢趋势（葡萄糖 / 乳酸）")
        rl.addWidget(self.chart_growth)
        rl.addWidget(self.chart_metab)
        self.tbl_metab = common.make_table(["时刻(h)", "葡萄糖(g/L)", "葡萄糖(mmol/L)", "级别",
                                            "乳酸(g/L)", "乳酸(mmol/L)", "级别", "说明"])
        rl.addWidget(self._boxed("逐取样点代谢警戒线（g/L 与 mmol/L 同显）", self.tbl_metab))
        self.tbl_mu = common.make_table(["t1(h)", "t2(h)", "X1", "X2", "μ(1/天)", "倍增时间(h)"])
        rl.addWidget(self._boxed("逐段比生长速率 μ（公式 6）", self.tbl_mu))
        self.lbl_harvest = common.status_label("")
        rl.addWidget(self.lbl_harvest)
        split.addWidget(right)
        split.setSizes([560, 620])
        lay.addWidget(split, 1)

        self.btn_sim.clicked.connect(self._make_simulated)
        self.btn_run.clicked.connect(self.run_analysis)
        self.btn_export.clicked.connect(self.export_report)
        self.btn_copy.clicked.connect(self.copy_summary)
        self.btn_save_batch.clicked.connect(self.save_batch)
        self._refresh_cfg()

    def _file_row(self, label):
        row = QHBoxLayout()
        row.addWidget(QLabel(label + "："))
        edit = QLineEdit()
        edit.setPlaceholderText("选择 CSV 文件")
        edit.setReadOnly(True)
        btn = QPushButton("浏览…")
        row.addWidget(edit, 1)
        row.addWidget(btn)
        btn.clicked.connect(lambda _=False, e=edit: self._pick_file(e))
        return edit, row

    def _boxed(self, title, widget):
        box = QGroupBox(title)
        v = QVBoxLayout(box)
        v.addWidget(widget)
        return box

    def _pick_file(self, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 CSV 文件", str(Path.cwd()),
                                              "CSV 文件 (*.csv *.txt);;所有文件 (*)")
        if path:
            edit.setText(path)

    # ---------------- 配置联动 ----------------
    def _refresh_cfg(self) -> None:
        self.cfg = self.host.cfg
        do = self.cfg["process_defaults"]["do_percent"]
        self.spin_do.setValue(float(do["set"]))

    # ---------------- 试算：造模拟数据 ----------------
    def _make_simulated(self) -> None:
        try:
            files = simulator.generate(tag="演示")
        except Exception as exc:                      # 目录不可写等
            QMessageBox.critical(self, "生成失败", "模拟数据生成失败：" + str(exc))
            return
        for f in files:
            if "控制数据" in f.name:
                self.edit_ctrl.setText(str(f))
            else:
                self.edit_off.setText(str(f))
        self.banner.setVisible(True)
        self.banner.setText("⚠️ 当前选中的是【模拟数据 SIMULATED】，只能用来熟悉界面与验证算法，"
                            "严禁当成真实批次数据做决策；正式分析请使用 my-Control 导出的真实文件。")
        QMessageBox.information(self, "模拟数据已生成",
                                "已生成两份带 SIMULATED 标记的测试 CSV，并填到上面的文件框里。\n"
                                "现在点「▶ 运行分析」看看效果。")

    # ---------------- 第七轮：列名映射状态提示（依赖板块②子页 A 的保存结果） ----------------
    def _refresh_map_hint(self) -> None:
        """必需字段全部已对应 → 绿色"映射已完成"；有缺 → 黄色"请先在『列名映射』完成必需字段映射"。

        只读 config 与映射文件，不改任何分析逻辑；任何异常都降级成黄色提示，绝不崩。"""
        try:
            need = {}
            for kind in (cmap.DATASET_CONTROL, cmap.DATASET_OFFLINE):
                need[kind] = [f["key"] for f in cmap.fields_for(kind, self.cfg) if f.get("required")]
            saved = cmap.load_all(cfg=self.cfg)
        except Exception as exc:
            self.lbl_map_hint.setText(app_info.ui_text_fmt(
                self.cfg, "mapping_unreadable",
                "⚠️ 请先在『列名映射』完成必需字段映射：映射文件暂时读不了（{reason}），"
                "请到该页检查后重新保存。", reason="%s: %s" % (exc.__class__.__name__, exc)))
            self.lbl_map_hint.setStyleSheet(theme.hint_style(self.cfg, "warn"))
            self.lbl_map_hint.setVisible(True)
            self.btn_goto_map.setVisible(True)
            return
        missing = {}
        for kind, keys in need.items():
            got = saved.get(kind) or {}
            missing[kind] = [k for k in keys if not str(got.get(k) or "").strip()]
        n_miss = len(missing.get(cmap.DATASET_CONTROL, [])) + len(missing.get(cmap.DATASET_OFFLINE, []))
        all_empty = not any(str(value or "").strip() for kind in saved.values()
                            if isinstance(kind, dict) for value in kind.values())
        if all_empty:
            self.lbl_map_hint.setText(app_info.ui_text(self.cfg, "mapping_auto",
                "未保存列名映射：分析时将尝试自动匹配；若识别不正确，请检查列名映射。"))
            self.lbl_map_hint.setStyleSheet(theme.hint_style(self.cfg, "none"))
        elif n_miss == 0:
            self.lbl_map_hint.setText(app_info.ui_text_fmt(
                self.cfg, "mapping_ok",
                "✅ 列名映射已完成：{n} 个必需字段都已对应到真实列名，可以直接点「▶ 运行分析」。",
                n=len(need.get(cmap.DATASET_CONTROL, [])) + len(need.get(cmap.DATASET_OFFLINE, []))))
            self.lbl_map_hint.setStyleSheet(theme.hint_style(self.cfg, "pass"))
        else:
            self.lbl_map_hint.setText(app_info.ui_text_fmt(
                self.cfg, "mapping_missing",
                "⚠️ 请先在『列名映射』完成必需字段映射：还差 {n} 项（控制数据 {ctrl} 项、"
                "离线取样 {off} 项）。保存后回到本页会自动刷新。",
                n=n_miss,
                ctrl=len(missing.get(cmap.DATASET_CONTROL, [])),
                off=len(missing.get(cmap.DATASET_OFFLINE, []))))
            self.lbl_map_hint.setStyleSheet(theme.hint_style(self.cfg, "warn"))
        self.lbl_map_hint.setVisible(not all_empty)
        self.btn_goto_map.setVisible(True)

    def _goto_mapping(self) -> None:
        """一键跳到『④ 列名映射』子页；跳转不可用只给中文提示，不抛异常。"""
        try:
            goto = getattr(self.host, "goto_page", None)
            if not callable(goto) or not goto("mapping"):
                raise TypeError("主窗口没有可用的 goto_page")
        except Exception as exc:
            QMessageBox.warning(self, "跳转失败",
                                "无法自动跳到列名映射页，请手动点上方的「④ 列名映射」子页签。"
                                "原因：" + str(exc))

    def showEvent(self, event) -> None:
        """每次切到本子页都刷新一次映射状态提示（纯界面刷新，不涉及计算）。"""
        super().showEvent(event)
        try:
            self._refresh_map_hint()
        except Exception:
            pass

    # ---------------- 分析主流程 ----------------
    def _saved_mapping(self, kind: str) -> dict:
        try:
            allmap = cmap.load_all(cfg=self.cfg)
        except ValueError as exc:
            QMessageBox.warning(self, "列名映射文件有问题", str(exc))
            return {}
        return dict(allmap.get(kind) or {})

    def run_analysis(self) -> None:
        ctrl_path = self.edit_ctrl.text().strip()
        off_path = self.edit_off.text().strip()
        if not ctrl_path and not off_path:
            QMessageBox.warning(self, "还没选文件",
                                "请先至少选择一个 CSV 文件（控制数据或离线取样），或用「造一份模拟数据试算」。")
            return
        ctrl = rd.load_dataset(ctrl_path, cmap.DATASET_CONTROL, self._saved_mapping(cmap.DATASET_CONTROL), self.cfg) if ctrl_path else None
        off = rd.load_dataset(off_path, cmap.DATASET_OFFLINE, self._saved_mapping(cmap.DATASET_OFFLINE), self.cfg) if off_path else None
        try:
            res = an.analyze(ctrl, off, float(self.spin_do.value()), self.cfg)
        except Exception as exc:                      # 兜底：核心算法理论上不抛
            res = {"metrics": {}, "mu_fit": {}, "mu_segments": [], "do_events": [], "do_summary": {},
                   "do_extrapolation": {}, "metabolite_rows": [], "harvest": {"level": an.LEVEL_NONE,
                                                                              "text": "分析失败"},
                   "warnings": [], "errors": ["分析过程中出现异常：" + str(exc)], "is_simulated": False,
                   "notes": [], "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        res["paths"] = {"control": ctrl_path, "offline": off_path, "do_setpoint": float(self.spin_do.value())}
        self.res = res
        self.host.last_analysis = res
        self._render(res, ctrl, off)

    def _render(self, res: dict, ctrl, off) -> None:
        sim = bool(res.get("is_simulated"))
        self.banner.setVisible(sim)
        if sim:
            why = []
            for ds in (ctrl, off):
                if ds is not None and getattr(ds, "is_simulated", False):
                    why.append("%s：%s" % (Path(ds.path).name, ds.simulated_reason))
            self.banner.setText("⚠️ 本次用的是【模拟数据 SIMULATED】——" + "；".join(why)
                                + "。只能用于熟悉界面与算法验证，严禁作为真实批次决策依据。")
        n_err = len(res.get("errors") or [])
        if n_err:
            self.lbl_status.setText("🔴 分析未能完成：共 %d 个错误，详见下方「数据质量提示 / 错误」表。" % n_err)
            common.fill_table(self.tbl_notes, ["类型", "内容"],
                              [["错误", t] for t in res["errors"]]
                              + [["提示", t] for t in (res.get("warnings") or []) + (res.get("notes") or [])])
            QMessageBox.warning(self, "分析未能完成",
                                "以下问题需要先解决（详见「数据质量提示 / 错误」表）：\n· " + "\n· ".join(res["errors"]))
        else:
            rows = [["提示", t] for t in (res.get("warnings") or [])]
            rows += [["说明", t] for t in (res.get("notes") or [])]
            common.fill_table(self.tbl_notes, ["类型", "内容"], rows or [["提示", "数据读取顺利，没有问题。"]])
        # 指标表
        m = res.get("metrics") or {}
        keys = [str(x["key"]) for x in self.cfg["template_library"]["compare_fields"]]
        extra = [k for k in m if k not in keys]
        mrows = [[an.metric_label(k, self.cfg), an.fmt_metric(k, m.get(k), self.cfg)] for k in keys + extra]
        common.fill_table(self.tbl_metrics, ["指标", "数值"], mrows)
        # DO 事件
        ev = res.get("do_events") or []
        erows = [[common.level_icon(e.level), "偏差持续" if e.kind == "deviation" else "绝对红线",
                  common.fmt(e.start_h), common.fmt(e.end_h), common.fmt(e.duration_minutes, 1),
                  common.fmt(e.min_value), e.note] for e in ev]
        s = res.get("do_summary") or {}
        if not erows:
            erows = [["✅", "无报警", common.DASH, common.DASH, common.DASH, common.DASH,
                      "在所选数据里没有发现 DO 偏差超阈值或跌破绝对红线。"]]
        common.fill_table(self.tbl_events, ["级别", "类型", "起始(h)", "结束(h)", "持续(分钟)", "最低DO(%)", "说明"],
                          erows, level_col=0,
                          level_of=lambda r: {common.level_icon(an.LEVEL_ERROR): an.LEVEL_ERROR,
                                              common.level_icon(an.LEVEL_WARN): an.LEVEL_WARN,
                                              common.level_icon(an.LEVEL_PASS): an.LEVEL_PASS}.get(r[0]))
        # 代谢表
        mt = []
        for r in res.get("metabolite_rows") or []:
            mt.append([common.fmt(r["t_h"]), common.fmt(r["glucose_g_l"], 2), common.fmt(r["glucose_mmol_l"], 2),
                       common.level_icon(r["glucose_level"]),
                       common.fmt(r["lactate_g_l"], 2), common.fmt(r["lactate_mmol_l"], 2),
                       common.level_icon(r["lactate_level"]), r["glucose_text"] + " / " + r["lactate_text"]])
        common.fill_table(self.tbl_metab, METAB_HEADERS, mt, level_of=lambda r: _worst_level(r[3], r[6]))
        # μ 逐段
        mu = [[common.fmt(x["t1_h"]), common.fmt(x["t2_h"]), common.fmt(x["x1"]), common.fmt(x["x2"]),
               common.fmt(x["mu_per_day"], 4), common.fmt(x["doubling_time_hours"])]
              for x in res.get("mu_segments") or []]
        fit = res.get("mu_fit") or {}
        if fit.get("ok"):
            mu.insert(0, ["对数期回归", common.fmt(fit.get("n_points_used")) + " 个点",
                          str(fit.get("window_kind") or "—"), "R²=" + common.fmt(fit.get("r_squared"), 4),
                          common.fmt(fit.get("mu_per_day"), 4), common.fmt(fit.get("doubling_time_hours"))])
        common.fill_table(self.tbl_mu, ["t1(h)", "t2(h)", "X1", "X2", "μ(1/天)", "倍增时间(h)"], mu)
        # 收获建议 + 外推提示
        har = res.get("harvest") or {}
        txt = "%s %s" % (common.level_icon(har.get("level")), har.get("text") or "")
        ex = res.get("do_extrapolation") or {}
        if ex:
            txt += "\n%s" % str(ex.get("note") or "")
            if ex.get("ok"):
                txt += (" 按最近斜率推算：约 %s 分钟后跌破偏差阈值、约 %s 分钟跌破绝对红线（仅作提示，不作为报警判定）。"
                        % (common.fmt(ex.get("minutes_to_deviation"), 0),
                           common.fmt(ex.get("minutes_to_absolute_red"), 0)))
        level = har.get("level")
        self.lbl_harvest.setText(txt)
        self.lbl_harvest.setStyleSheet("background-color: %s; padding: 6px; border-radius: 4px;"
                                       % self._bg_css(level))
        if not n_err:
            n_ev = (res.get("do_summary") or {}).get("n_events", 0)
            self.lbl_status.setText(
                "✅ 分析完成：%s 个控制数据点、%s 个取样点、%s 条 DO 报警事件。"
                "结果仅供规划参考，正式决策需人工复核。"
                % (common.fmt(ctrl.n_points if ctrl is not None else 0),
                   common.fmt(off.n_points if off is not None else 0), common.fmt(n_ev)))
        # 图表
        png, msg = chart_view.growth_chart(off.pairs("cell_density_mcells_ml") if off is not None else [],
                                           off.pairs("viability_percent") if off is not None else [])
        self.chart_growth.show_png(png, msg)
        gp = [(r["t_h"], r["glucose_g_l"]) for r in res.get("metabolite_rows") or []]
        lp = [(r["t_h"], r["lactate_g_l"]) for r in res.get("metabolite_rows") or []]
        png2, msg2 = chart_view.metabolite_chart(gp, lp)
        self.chart_metab.show_png(png2, msg2)

    @staticmethod
    def _bg_css(level) -> str:
        col = common.LEVEL_BG.get(str(level or ""), common.LEVEL_BG[an.LEVEL_NONE])
        return "rgb(%d,%d,%d)" % (col.red(), col.green(), col.blue())

    # ---------------- 导出 / 复制 / 存批次 ----------------
    def _require_res(self) -> bool:
        if not self.res:
            QMessageBox.warning(self, "还没有分析结果", "请先点「▶ 运行分析」，跑出结果后再做这一步。")
            return False
        return True

    def export_report(self) -> None:
        if not self._require_res():
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(self, "导出分析报告 CSV", "批次分析报告_%s.csv" % stamp,
                                              "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            out = an.export_report_csv(self.res, path, self.cfg)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "已导出", "分析报告已导出到：\n%s\n\n提示：报告仅供规划参考，正式决策需人工复核。"
                                % out)

    def copy_summary(self) -> None:
        if not self._require_res():
            return
        secs = an.report_sections(self.res, self.cfg)
        lines = ["%s：%s" % (a, b) for a, b in an.report_disclaimer_lines(self.res, self.cfg)]
        lines.append("")
        for title, header, rows in secs:
            lines.append("【" + title + "】")
            lines.append("\t".join(str(h) for h in header))
            for r in rows:
                lines.append("\t".join("" if v is None else str(v) for v in r))
            lines.append("")
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "已复制", "分析摘要已复制到剪贴板，可直接粘贴到 Excel 或微信。")

    def save_batch(self) -> None:
        if not self._require_res():
            return
        m = self.res.get("metrics") or {}
        if not m:
            QMessageBox.warning(self, "没有可保存的摘要", "本次分析没有产出关键参数，请检查数据文件与列名映射。")
            return
        default = ""
        for key in ("control", "offline"):
            p = (self.res.get("paths") or {}).get(key)
            if p:
                default = Path(p).stem.replace("SIMULATED_", "")
                break
        name, ok = QInputDialog.getText(self, "保存批次记录", "给这个批次起个名字（建议含日期/细胞株）：",
                                        text=default or datetime.now().strftime("批次%Y%m%d"))
        if not ok:
            return
        try:
            msg = template_store.save_batch(name, m,
                                            source_control=str((self.res.get("paths") or {}).get("control") or ""),
                                            source_offline=str((self.res.get("paths") or {}).get("offline") or ""),
                                            is_simulated=bool(self.res.get("is_simulated")))
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "已保存", msg + "\n到⑤「模板库与批次对比」页可以勾选多个批次做对比。")

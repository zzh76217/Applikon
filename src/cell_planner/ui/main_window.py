# -*- coding: utf-8 -*-
"""模块 1 批次配置规划器 —— 第二轮最小单页版。
布局：左侧"参数输入区"；右侧上部"计算结果区"、下部"校验提示区"（R01-R13）。
启动：双击工程根目录 启动软件.bat，或命令行 python run.py。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from cell_planner.core import formulas, validators
from cell_planner.core.config_loader import get_config

_LEVEL_BG = {
    validators.LEVEL_PASS: QColor(227, 244, 227),
    validators.LEVEL_WARN: QColor(255, 246, 200),
    validators.LEVEL_ERROR: QColor(255, 213, 213),
}


def _fmt(x: float) -> str:
    """数值显示：整数不带小数点，小数最多 2 位。"""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return ("%.2f" % x).rstrip("0").rstrip(".")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = get_config()
        self.setWindowTitle("细胞培养接种与批次配置规划软件 — 批次配置规划（第二轮最小版）")
        self.resize(1120, 740)
        self.widgets = {}
        self.defaults = {}
        self._build_ui()
        self._fill_defaults()
        self.compute()

    # ---------------- 构建界面 ----------------
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        splitter = QSplitter()
        outer.addWidget(splitter, 1)

        # 左：参数输入区
        input_box = QGroupBox("参数输入区（数值均可按实验需要修改）")
        input_lay = QVBoxLayout(input_box)
        form_host = QWidget()
        self.form = QFormLayout(form_host)
        input_lay.addWidget(form_host, 1)
        btn_row = QHBoxLayout()
        self.btn_calc = QPushButton("计算并校验")
        self.btn_calc.setDefault(True)
        self.btn_reset = QPushButton("恢复默认值")
        btn_row.addWidget(self.btn_calc)
        btn_row.addWidget(self.btn_reset)
        input_lay.addLayout(btn_row)
        splitter.addWidget(input_box)

        self._build_fields()
        self.btn_calc.clicked.connect(self.compute)
        self.btn_reset.clicked.connect(self._restore)

        # 右：上结果、下校验
        right = QSplitter()
        right.setOrientation(Qt.Vertical)
        result_box = QGroupBox("计算结果区（开机配置预览，可整段复制）")
        rb_lay = QVBoxLayout(result_box)
        self.txt_results = QTextEdit()
        self.txt_results.setReadOnly(True)
        rb_lay.addWidget(self.txt_results)
        right.addWidget(result_box)

        valid_box = QGroupBox("校验提示区（R01–R13，第三轮补齐 R14–R18）")
        vb_lay = QVBoxLayout(valid_box)
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["规则", "名称", "结果", "提示说明"])
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.verticalHeader().setVisible(False)
        head = self.tbl.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(3, QHeaderView.Stretch)
        vb_lay.addWidget(self.tbl)
        right.addWidget(valid_box)
        right.setSizes([300, 420])
        splitter.addWidget(right)
        splitter.setSizes([400, 700])

        self.lbl_summary = QLabel("")
        outer.addWidget(self.lbl_summary)
        tip = QLabel("提醒：计算结果仅供规划参考，正式上机前必须由操作人员人工复核。")
        tip.setStyleSheet("color: rgb(176, 0, 0); font-weight: bold;")
        outer.addWidget(tip)

    def _add_line(self, key, label, value):
        w = QLineEdit()
        self.form.addRow(label, w)
        self.widgets[key] = w
        self.defaults[key] = value

    def _add_spin(self, key, label, value, decimals, suffix, minimum=0.0, maximum=999999.0):
        w = QDoubleSpinBox()
        w.setDecimals(decimals)
        w.setRange(minimum, maximum)
        w.setSuffix((" " + suffix) if suffix else "")
        self.form.addRow(label, w)
        self.widgets[key] = w
        self.defaults[key] = value

    def _build_fields(self) -> None:
        pd = self.cfg["process_defaults"]
        ui_def = self.cfg["ui_defaults"]
        la = self.cfg["liquid_additives"]
        self._add_line("cell_line", "细胞株", ui_def["cell_line_name"])
        self._add_line("medium", "培养基类型", ui_def["medium_type"])
        self._add_spin("v_work", "目标工作体积", ui_def["working_volume_ml"], 0, "mL", 0.0, 3100.0)
        self._add_spin("cd_seed", "种子液浓度 CD_seed", ui_def["seed_conc_mcells_ml"], 2, "×10⁶ cells/mL", 0.0, 100.0)
        self._add_spin("cd_inoc", "目标接种密度 CD_inoc", pd["inoculum_density_mcells_ml"]["set"], 2, "×10⁶ cells/mL", 0.0, 100.0)
        self._add_spin("days", "培养天数", pd["culture_days"]["set"], 0, "天", 0.0, 365.0)
        self._add_spin("vvm", "通气量（vvm）", pd["aeration_vvm"]["set"], 2, "vvm", 0.0, 5.0)
        self._add_spin("o2_ratio", "O2 补充比例", pd["o2_ratio_percent"]["set"], 1, "% of Air", 0.0, 100.0)
        self._add_spin("co2_ratio", "CO2 配比", pd["co2_ratio_percent"]["set"], 1, "% of Air", 0.0, 100.0)
        self._add_spin("rpm", "搅拌初始转速", pd["agitation_rpm"]["set"], 0, "rpm", 0.0, 2000.0)
        self._add_spin("temp_growth", "生长阶段温度", pd["temp_growth_c"]["set"], 1, "°C", 0.0, 45.0)
        self.chk_expr = QCheckBox("启用表达阶段降温")
        self.defaults["expr_check"] = bool(ui_def["expression_temp_enabled"])
        self.form.addRow(self.chk_expr)
        self._add_spin("temp_expr", "表达阶段温度", pd["temp_expression_c"]["set"], 1, "°C", 0.0, 45.0)
        self.chk_expr.toggled.connect(self.widgets["temp_expr"].setEnabled)
        self._add_spin("ph", "pH 设定点", pd["ph_setpoint"]["set"], 2, "", 0.0, 14.0)
        self._add_spin("do", "DO 设定点", pd["do_percent"]["set"], 0, "%", 0.0, 100.0)
        self._add_spin("base_pct", "碱液预留（占工作体积）", la["base_fraction_of_working"]["default"] * 100.0, 1, "%", 0.0, 50.0)
        self._add_spin("af_pct", "消泡剂预留（占工作体积）", la["antifoam_fraction_of_working"]["default"] * 100.0, 2, "%", 0.0, 50.0)

    def _fill_defaults(self) -> None:
        for key, val in self.defaults.items():
            w = self.widgets.get(key)
            if isinstance(w, QLineEdit):
                w.setText(str(val))
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(float(val))
        self.chk_expr.setChecked(self.defaults["expr_check"])
        self.widgets["temp_expr"].setEnabled(self.defaults["expr_check"])

    def _restore(self) -> None:
        self._fill_defaults()
        self.compute()

    # ---------------- 计算与校验 ----------------
    def compute(self) -> None:
        w = self.widgets
        v_work = w["v_work"].value()
        cd_seed = w["cd_seed"].value()
        cd_inoc = w["cd_inoc"].value()
        vvm = w["vvm"].value()
        o2r = w["o2_ratio"].value()
        co2r = w["co2_ratio"].value()
        rpm = w["rpm"].value()
        temp_g = w["temp_growth"].value()
        temp_e = w["temp_expr"].value() if self.chk_expr.isChecked() else None
        ph = w["ph"].value()
        do = w["do"].value()
        try:
            v_seed = formulas.inoculum_volume_ml(v_work, cd_inoc, cd_seed)
            v_base = v_work * w["base_pct"].value() / 100.0
            v_af = v_work * w["af_pct"].value() / 100.0
            v_medium = formulas.medium_volume_ml(v_work, v_seed, v_base, v_af)
            q_air = formulas.air_flow_ml_min(vvm, v_work)
            q_o2 = formulas.o2_flow_ml_min(q_air, o2r)
            q_co2 = formulas.co2_flow_ml_min(q_air, co2r)
        except ValueError as exc:
            QMessageBox.critical(self, "输入有误", str(exc))
            return
        inp = validators.SetupInputs(
            v_work_ml=v_work, v_seed_ml=v_seed, v_medium_ml=v_medium,
            q_air_ml_min=q_air, q_o2_ml_min=q_o2, q_co2_ml_min=q_co2,
            rpm=rpm, temp_growth_c=temp_g, temp_expression_c=temp_e,
            ph_setpoint=ph, do_percent=do,
            o2_ratio_percent=o2r, co2_ratio_percent=co2r,
            cd_inoc_mcells_ml=cd_inoc, cd_seed_mcells_ml=cd_seed,
        )
        results = validators.run_validation(inp, self.cfg)
        self._render_results(inp, v_base, v_af)
        self._render_table(results)

    def _render_results(self, inp, v_base, v_af) -> None:
        ap = self.cfg["alkali_pump"]
        lines = [
            "=== 开机配置预览（第二轮文字版，一键复制/导出在模块 1 完善轮提供）===",
            "细胞株：%s        培养基：%s" % (self.widgets["cell_line"].text() or "（未填写）",
                                            self.widgets["medium"].text() or "（未填写）"),
            "",
            "目标工作体积 V_work：      %s mL" % _fmt(inp.v_work_ml),
            "接种体积 V_seed（公式1）： %s mL" % _fmt(inp.v_seed_ml),
            "碱液预留 V_base：          %s mL" % _fmt(v_base),
            "消泡剂 V_antifoam：        %s mL" % _fmt(v_af),
            "培养基补液 V_medium（公式2）：%s mL" % _fmt(inp.v_medium_ml),
            "",
            "Air 流量 Q_air（公式3）：  %s mL/min（vvm = %s）" % (_fmt(inp.q_air_ml_min), _fmt(self.widgets["vvm"].value())),
            "O2 流量 Q_O2（公式4）：    %s mL/min（Air 的 %s%%）" % (_fmt(inp.q_o2_ml_min), _fmt(inp.o2_ratio_percent)),
            "CO2 流量 Q_CO2（公式5）：  %s mL/min（Air 的 %s%%）" % (_fmt(inp.q_co2_ml_min), _fmt(inp.co2_ratio_percent)),
            "",
            "搅拌初始转速：             %s rpm" % _fmt(inp.rpm),
            "生长阶段温度：             %s °C" % _fmt(inp.temp_growth_c),
        ]
        if inp.temp_expression_c is not None:
            lines.append("表达阶段温度：             %s °C（启用降温）" % _fmt(inp.temp_expression_c))
        lines += [
            "pH 设定点：                %s" % _fmt(inp.ph_setpoint),
            "DO 设定点：                %s %%" % _fmt(inp.do_percent),
            "碱泵流量系数建议：         不超过 %s mL/(min·L)（%s）" % (_fmt(ap["max_rate_ml_per_min_per_L"]), ap["note"]),
        ]
        self.txt_results.setPlainText("\n".join(lines))

    def _render_table(self, results) -> None:
        self.tbl.setRowCount(len(results))
        n_err = n_warn = 0
        for row, r in enumerate(results):
            if r.level == validators.LEVEL_ERROR:
                n_err += 1
            elif r.level == validators.LEVEL_WARN:
                n_warn += 1
            cells = [r.rule_id, r.name, r.display, r.message]
            bg = _LEVEL_BG[r.level]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(bg)
                if col <= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(row, col, item)
        self.lbl_summary.setText("校验汇总：错误 %d 项，警告 %d 项。" % (n_err, n_warn)
                                 + ("存在 🔴 错误时禁止按此配置上机！" if n_err else
                                    ("存在 🟡 警告，可继续但需人工确认。" if n_warn else "全部通过 ✅。")))


def main() -> int:
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()

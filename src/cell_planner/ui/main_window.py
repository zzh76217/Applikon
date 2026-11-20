# -*- coding: utf-8 -*-
"""主窗口（第七轮）：外层三大板块，板块内子页签承载原来的六个页面。

板块①「配置与校验」：子页签 ① 配置与校验、② 硬件配置
板块②「分析与对比」：子页签 ④ 列名映射 → ③ 离线分析 → ⑤ 模板库对比（按使用顺序排）
板块③「SOP 引导」：子页签 ⑥ SOP 引导
下面六段仍是第五轮那六页，内容、公式、校验、导入逻辑一律未动，只换了挂载位置与外观。

（历史说明·第五轮）六个标签页的内容职责如下。
① 批次配置与校验：参数输入区 / 计算结果区 / 校验提示区（R01-R18 全部 18 条）+ 配方 + 开机配置单导出。
② 硬件配置：改体积上下限、MFC 量程与推荐默认值，写回 config/config.yaml（保留注释，先备份 .bak）。
③ 离线分析：导入 my-Control 控制数据 CSV + 离线取样 CSV，生长曲线/μ、糖乳酸警戒、DO 偏差、收获建议、报告导出。
④ 列名映射：把逻辑字段对应到真实导出文件的列名（答复#8），存成 data/column_mapping.json。
⑤ 模板库与批次对比：实验方案模板（SQLite，答复#11）+ 多批次关键参数对比。
⑥ SOP 防呆引导：按 config.sop.stages 逐条勾选确认，可复制或导出确认单。
所有阈值/上下限/条目文字均来自 config，界面不硬编码；启动：双击 启动软件.bat 或命令行 python run.py。"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from cell_planner.core import formulas, recipe_store, sheet_export, validators
from cell_planner.core.config_loader import PROJECT_ROOT, config_source, get_config
from cell_planner.core.diagnostics import bundled_asset, log_file, write_diagnostic
from cell_planner.core import app_info
from cell_planner.core.config_writer import update_config_file
from cell_planner.ui import icons, theme
from cell_planner.ui.analysis_tab import AnalysisTab
from cell_planner.ui.mapping_tab import MappingTab
from cell_planner.ui.sop_tab import SopTab
from cell_planner.ui.template_tab import TemplateTab

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


def _cfg_get(cfg: dict, path: tuple):
    node = cfg
    for key in path:
        node = node[key]
    return node


# 子页签兜底名称：config.app_info.tab_titles 缺失或没写全时按顺序补位（第六轮：窄屏可改短）
# 顺序即 _PAGE_ORDER：① 配置与校验 ② 硬件配置 ③ 离线分析 ④ 列名映射 ⑤ 模板库对比 ⑥ SOP 引导
_TAB_FALLBACK_TITLES = (
    "① 配置与校验", "② 硬件配置", "③ 离线分析",
    "④ 列名映射", "⑤ 模板库对比", "⑥ SOP 引导",
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = get_config()
        self.setWindowTitle(self._window_title())
        self._fit_to_screen(1200, 780)
        self._size_clamped_on_show = False   # 第六轮：显示后还要按边框再收一次
        self.widgets = {}
        self.defaults = {}       # key -> 可调用对象，从"当前 config"取默认值（硬件配置页改完即生效）
        self._last = None        # 最近一次 compute() 的结果，供导出/复制使用
        self.last_analysis = None   # ③页最近一次分析结果，供⑤页提示用
        self._build_ui()
        self._fill_defaults()
        self.compute()

    # ================= 第六轮：窗口标题与文件位置提示（渲染逻辑在 core/app_info.py，可单测） =================
    def _window_title(self) -> str:
        mode = "打包版" if getattr(sys, "frozen", False) else "源码版"
        return app_info.window_title(self.cfg, mode)

    def _locations_text(self) -> str:
        info = self.cfg.get("app_info") or {}
        try:
            data_dir = (PROJECT_ROOT / str(self.cfg["storage"]["templates_db_path"])).parent
            manual = PROJECT_ROOT / str(info.get("manual_file") or "")
        except Exception:
            data_dir = manual = None
        return app_info.locations_text(
            self.cfg,
            config_path=config_source(),
            data_dir=data_dir,
            log_path=log_file(),
            manual_path=manual,
        )

    def _tab_titles(self) -> list:
        """页签名称取自 config，缺位用内置兜底名补齐，改错也不影响功能。"""
        got = app_info.tab_titles(self.cfg, len(_TAB_FALLBACK_TITLES))
        return [got[i] or _TAB_FALLBACK_TITLES[i] for i in range(len(_TAB_FALLBACK_TITLES))]

    def _fit_to_screen(self, want_w: int, want_h: int) -> None:
        """窗口尺寸跟着屏幕走：1280x800 / 1366x768 的实验笔记本上，
        固定 1200x780 会被系统缩放顶出屏幕，底部按钮和第 6 个页签都看不见。"""
        width, height = want_w, want_h
        try:
            geo = QApplication.primaryScreen().availableGeometry()
            width = max(760, min(want_w, geo.width() - 24))
            height = max(520, min(want_h, geo.height() - 24))
        except Exception:
            pass          # 拿不到屏幕信息就用原始期望尺寸，绝不让主程序崩
        self.resize(width, height)

    MIN_WIDTH = 760      # 再小就挤坏三区布局（窄屏兜底用）
    MIN_HEIGHT = 520
    SCREEN_MARGIN = 8    # 留给任务栏/边缘的余量（像素）

    def _available_geometry(self):
        """屏幕可用区（已扣任务栏）。拿不到就返回 None，绝不抛异常。"""
        try:
            return QApplication.primaryScreen().availableGeometry()
        except Exception:
            return None

    def _clamped_size(self, width: int, height: int, avail, frame_w: int, frame_h: int):
        """纯计算：把客户区尺寸缩到「连标题栏和边框」都落在屏幕可用区内。

        geometry() 不含窗口边框，真机上按可用区缩完仍然会超出十几像素，
        所以这里用 frameGeometry 的尺寸差（边框厚度）再扣一次。
        """
        if avail is None:
            return width, height
        extra_w = max(0, frame_w - width)
        extra_h = max(0, frame_h - height)
        room_w = avail.width() - 2 * self.SCREEN_MARGIN - extra_w
        room_h = avail.height() - 2 * self.SCREEN_MARGIN - extra_h
        # 只缩不涨：窗口本来就比下限小时，不能反过来把用户窗口撑大
        new_w = min(width, max(self.MIN_WIDTH, room_w))
        new_h = min(height, max(self.MIN_HEIGHT, room_h))
        return new_w, new_h

    def showEvent(self, event) -> None:
        """第一次显示后按真实边框收一次尺寸（只收一次，避免反复抖动）。"""
        super().showEvent(event)
        if self._size_clamped_on_show:
            return
        self._size_clamped_on_show = True
        frame = self.frameGeometry()
        new_w, new_h = self._clamped_size(self.width(), self.height(), self._available_geometry(), frame.width(), frame.height())
        if (new_w, new_h) != (self.width(), self.height()):
            self.resize(new_w, new_h)

    # ================= 总体布局：三大板块（第七轮，仅改界面结构，不改任何业务逻辑） =================
    # 外层只有 3 个大标签，名称来自 config.app_info.outer_tab_titles；
    # 原来平铺的 6 个页签变成"板块内的子页签"，名称仍来自 config.app_info.tab_titles。
    # 页面键名（planner/hardware/analysis/mapping/template/sop）是稳定标识，
    # 界面跳转、单元测试都用键名定位，不再依赖页签序号。
    _PAGE_ORDER = ("planner", "hardware", "analysis", "mapping", "template", "sop")
    _PAGE_GROUPS = (
        ("planner", "hardware"),                      # 板块① 配置与校验
        ("mapping", "analysis", "template"),          # 板块② 分析与对比（先映射、再分析、后对比）
        ("sop",),                                     # 板块③ SOP 引导
    )
    _OUTER_FALLBACK_TITLES = ("配置与校验", "分析与对比", "SOP 引导")

    def _outer_titles(self) -> list:
        """大板块名称取自 config，缺位用内置兜底名补齐。"""
        got = app_info.outer_tab_titles(self.cfg, len(self._OUTER_FALLBACK_TITLES))
        return [got[i] or self._OUTER_FALLBACK_TITLES[i] for i in range(len(self._OUTER_FALLBACK_TITLES))]

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        # 六个页面控件的构造顺序与内容与重构前完全一致，只是不再直接平铺到主标签栏
        built = {"planner": self._build_planner_tab(), "hardware": self._build_hardware_tab()}
        self.analysis_tab = built["analysis"] = AnalysisTab(self)
        self.mapping_tab = built["mapping"] = MappingTab(self)
        self.template_tab = built["template"] = TemplateTab(self)
        self.sop_tab = built["sop"] = SopTab(self)

        titles = self._tab_titles()
        outer_names = self._outer_titles()
        self.pages = {}          # 页面键名 -> 控件
        self.page_tabs = {}      # 页面键名 -> (大板块序号, 子页签序号)
        self.sub_tabs = []       # 每个大板块内部那个 QTabWidget
        self.tabs = QTabWidget()
        self.tabs.setObjectName("outerTabs")
        self.tabs.setMovable(False)
        for gi, group in enumerate(self._PAGE_GROUPS):
            sub = QTabWidget()
            sub.setObjectName("subTabs%d" % gi)
            sub.setMovable(False)
            sub.setDocumentMode(True)
            sub.tabBar().setExpanding(False)
            sub.tabBar().setUsesScrollButtons(True)
            for si, key in enumerate(group):
                sub.addTab(built[key], titles[self._PAGE_ORDER.index(key)])
                sub.setTabIcon(si, icons.icon(icons.PAGE_ICON_NAMES[key], self.cfg))
                self.pages[key] = built[key]
                self.page_tabs[key] = (gi, si)
            self.tabs.addTab(sub, outer_names[gi])
            self.tabs.setTabIcon(gi, icons.icon(icons.OUTER_ICON_NAMES[gi], self.cfg))
            self.sub_tabs.append(sub)
        outer.addWidget(self.tabs, 1)

        tip = QLabel("提醒：计算结果仅供规划参考，正式上机前必须由操作人员人工复核。本软件不连接、不控制 my-Control 硬件。")
        tip.setStyleSheet("color: rgb(176, 0, 0); font-weight: bold;")
        outer.addWidget(tip)
        loc = QLabel(self._locations_text())
        loc.setStyleSheet("color: rgb(90, 90, 90);")
        loc.setTextInteractionFlags(Qt.TextSelectableByMouse)   # 第六轮：路径可全选复制，便于排障
        loc.setWordWrap(True)          # 第六轮：小屏（1024 宽）下折行，别把窗口最小宽度顶宽
        self.lbl_locations = loc                                # 第六轮：留出引用，单元测试与后续功能用
        outer.addWidget(loc)
        self._apply_appearance()

    # ================= 第七轮：统一外观（配色/字号/边距全部来自 config.app_info.theme） =================
    def _apply_appearance(self) -> None:
        """样式表与间距都从 config 生成；任何一处出错都只是"不美化"，绝不影响启动。"""
        try:
            self.setStyleSheet(theme.stylesheet(self.cfg))
        except Exception:
            self.setStyleSheet("")
        try:
            self._apply_metrics()
        except Exception:
            pass

    def _apply_metrics(self) -> None:
        """全局边距：子页外边距 margin_outer、分组内 margin_group、控件间距 spacing，
        统一在遍历里设置，避免逐页手写导致各页留白不一致。"""
        m = theme.metrics(self.cfg)
        root = self.centralWidget().layout()
        if root is not None:
            root.setContentsMargins(m["margin_outer"], m["margin_outer"],
                                    m["margin_outer"], m["margin_outer"])
            root.setSpacing(m["spacing"])
        for page in self.pages.values():
            lay = page.layout()
            if lay is not None:
                lay.setContentsMargins(m["margin_outer"], m["margin_outer"],
                                       m["margin_outer"], m["margin_outer"])
                lay.setSpacing(m["spacing"])
        for box in self.findChildren(QGroupBox):
            lay = box.layout()
            if lay is not None:
                lay.setContentsMargins(m["margin_group"], m["margin_group"] + 6,
                                       m["margin_group"], m["margin_group"])
                lay.setSpacing(m["spacing"])

    # ================= 第七轮：页面跳转（取代按页签序号定位的旧写法）=================
    def page(self, key: str):
        """按稳定键名取页面控件；不认识就返回 None，由调用方给中文提示。"""
        return self.pages.get(str(key))

    def goto_page(self, key: str) -> bool:
        """跳到指定页面：先切大板块，再切板块内子页签。非法键返回 False，不抛异常。"""
        pos = self.page_tabs.get(str(key))
        if not pos:
            return False
        gi, si = pos
        try:
            self.tabs.setCurrentIndex(gi)
            self.sub_tabs[gi].setCurrentIndex(si)
        except Exception:
            return False
        return True

    def current_page_key(self) -> str:
        """当前显示的页面键名（不在六大页面里时返回空串）。"""
        try:
            gi = self.tabs.currentIndex()
            widget = self.sub_tabs[gi].currentWidget()
            for key, page in self.pages.items():
                if page is widget:
                    return key
        except Exception:
            return ""
        return ""


    # ================= 标签页①：批次配置与校验 =================
    def _build_planner_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)

        splitter = QSplitter()
        lay.addWidget(splitter, 1)

        # 左：参数输入区（含配方条）
        input_box = QGroupBox("参数输入区（数值均可按实验需要修改）")
        input_lay = QVBoxLayout(input_box)

        recipe_row = QHBoxLayout()
        self.edit_recipe = QLineEdit()
        self.edit_recipe.setPlaceholderText(str(self.cfg["recipes"]["builtin_default_name"]))
        self.cmb_recipe = QComboBox()
        self.cmb_recipe.setMinimumWidth(150)
        btn_row_r = QHBoxLayout()
        self.btn_recipe_save = QPushButton("保存为配方")
        self.btn_recipe_load = QPushButton("调用配方")
        self.btn_recipe_del = QPushButton("删除配方")
        for b in (self.btn_recipe_save, self.btn_recipe_load, self.btn_recipe_del):
            btn_row_r.addWidget(b)
        recipe_row.addWidget(QLabel("配方名："))
        recipe_row.addWidget(self.edit_recipe, 1)
        recipe_row.addWidget(QLabel("已存配方："))
        recipe_row.addWidget(self.cmb_recipe)
        input_lay.addLayout(recipe_row)
        input_lay.addLayout(btn_row_r)
        self.btn_recipe_save.clicked.connect(self._recipe_save)
        self.btn_recipe_load.clicked.connect(self._recipe_load)
        self.btn_recipe_del.clicked.connect(self._recipe_delete)
        self.cmb_recipe.activated.connect(lambda name: self.edit_recipe.setText(name))

        # 小屏适配：参数行多，在高缩放（dpr 2.25）的笔记本上表单本身就有 700+ px 高，
        # 装进滚动区后整窗最小高才压得下来，底部按钮与第 6 个页签不会被顶出屏幕。
        form_host = QWidget()
        self.form = QFormLayout(form_host)
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setWidget(form_host)
        input_lay.addWidget(self.form_scroll, 1)
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
        self._recipe_refresh()

        # 右：上结果、下校验
        right = QSplitter()
        right.setOrientation(Qt.Vertical)
        result_box = QGroupBox("计算结果区（开机配置预览）")
        rb_lay = QVBoxLayout(result_box)
        export_row = QHBoxLayout()
        self.btn_export_csv = QPushButton("一键导出开机配置单（CSV）")
        self.btn_copy = QPushButton("一键复制配置单文本")
        export_row.addWidget(self.btn_export_csv)
        export_row.addWidget(self.btn_copy)
        rb_lay.addLayout(export_row)
        self.txt_results = QTextEdit()
        self.txt_results.setObjectName("resultsArea")   # 第七轮：等宽字体，数字逐行对齐
        self.txt_results.setReadOnly(True)
        rb_lay.addWidget(self.txt_results)
        right.addWidget(result_box)
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_copy.clicked.connect(self._copy_sheet)
        if not bool(self.cfg["setup_sheet_export"].get("clipboard_copy", True)):
            self.btn_copy.setEnabled(False)

        valid_box = QGroupBox("校验提示区（R01–R18，共 18 条）")
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
        right.setSizes([330, 430])
        splitter.addWidget(right)
        splitter.setSizes([420, 740])

        self.lbl_summary = QLabel("")
        lay.addWidget(self.lbl_summary)
        return tab

    def _add_line(self, key, label, getter):
        w = QLineEdit()
        self.form.addRow(label, w)
        self.widgets[key] = w
        self.defaults[key] = getter

    def _add_spin(self, key, label, getter, decimals, suffix, minimum=0.0, maximum=999999.0):
        w = QDoubleSpinBox()
        w.setDecimals(decimals)
        w.setRange(minimum, maximum)
        w.setSuffix((" " + suffix) if suffix else "")
        self.form.addRow(label, w)
        self.widgets[key] = w
        self.defaults[key] = getter

    def _build_fields(self) -> None:
        g = lambda *path: (lambda cfg=self.cfg, p=path: _cfg_get(self.cfg, p))
        self._add_line("cell_line", "细胞株", g("ui_defaults", "cell_line_name"))
        self._add_line("medium", "培养基类型", g("ui_defaults", "medium_type"))
        self._add_spin("v_work", "目标工作体积", g("ui_defaults", "working_volume_ml"), 0, "mL", 0.0, 99999.0)
        self._add_spin("cd_seed", "种子液浓度 CD_seed", g("ui_defaults", "seed_conc_mcells_ml"), 2, "×10⁶ cells/mL", 0.0, 100.0)
        self._add_spin("cd_inoc", "目标接种密度 CD_inoc", g("process_defaults", "inoculum_density_mcells_ml", "set"), 2, "×10⁶ cells/mL", 0.0,
                       float(self.cfg["density_input"]["reactor_initial_density_hard_max_mcells_ml"]))
        self._add_spin("days", "培养天数", g("process_defaults", "culture_days", "set"), 0, "天", 0.0, 365.0)
        self._add_spin("vvm", "通气量（vvm）", g("process_defaults", "aeration_vvm", "set"), 2, "vvm", 0.0, 5.0)
        self._add_spin("o2_ratio", "O2 补充比例", g("process_defaults", "o2_ratio_percent", "set"), 1, "% of Air", 0.0, 100.0)
        self._add_spin("co2_ratio", "CO2 配比", g("process_defaults", "co2_ratio_percent", "set"), 1, "% of Air", 0.0, 100.0)
        self._add_spin("rpm", "搅拌初始转速", g("process_defaults", "agitation_rpm", "set"), 0, "rpm", 0.0, 2000.0)
        self.chk_expr = QCheckBox("启用表达阶段降温")
        self.defaults["expr_check"] = g("ui_defaults", "expression_temp_enabled")
        self.form.addRow("", self.chk_expr)
        self._add_spin("temp_expr", "表达阶段温度", g("process_defaults", "temp_expression_c", "set"), 1, "°C", 0.0, 45.0)
        self.chk_expr.toggled.connect(self.widgets["temp_expr"].setEnabled)
        self._add_spin("temp_growth", "生长阶段温度", g("process_defaults", "temp_growth_c", "set"), 1, "°C", 0.0, 45.0)
        self._add_spin("ph", "pH 设定点", g("process_defaults", "ph_setpoint", "set"), 2, "", 0.0, 14.0)
        self._add_spin("do", "DO 设定点", g("process_defaults", "do_percent", "set"), 0, "%", 0.0, 100.0)
        self._add_spin("sampling_ml", "计划累计取样体积", g("ui_defaults", "sampling_total_ml"), 0, "mL", 0.0, 99999.0)
        self._add_spin("base_pct", "碱液预留（占工作体积）",
                       lambda: self.cfg["liquid_additives"]["base_fraction_of_working"]["default"] * 100.0, 1, "%", 0.0, 50.0)
        self._add_spin("af_pct", "消泡剂预留（占工作体积）",
                       lambda: self.cfg["liquid_additives"]["antifoam_fraction_of_working"]["default"] * 100.0, 2, "%", 0.0, 50.0)

    def _fill_defaults(self) -> None:
        for key, getter in self.defaults.items():
            w = self.widgets.get(key)
            val = getter()
            if isinstance(w, QLineEdit):
                w.setText(str(val))
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(float(val))
        self.chk_expr.setChecked(bool(self.defaults["expr_check"]()))
        self.widgets["temp_expr"].setEnabled(self.chk_expr.isChecked())

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
            rpm=w["rpm"].value(), temp_growth_c=w["temp_growth"].value(),
            temp_expression_c=w["temp_expr"].value() if self.chk_expr.isChecked() else None,
            ph_setpoint=w["ph"].value(), do_percent=w["do"].value(),
            o2_ratio_percent=o2r, co2_ratio_percent=co2r,
            cd_inoc_mcells_ml=cd_inoc, cd_seed_mcells_ml=cd_seed,
            vvm=vvm, culture_days=w["days"].value(), sampling_total_ml=w["sampling_ml"].value(),
        )
        results = validators.run_validation(inp, self.cfg)
        self._last = dict(inp=inp, v_base=v_base, v_af=v_af, results=results)
        self._render_results(inp, v_base, v_af)
        self._render_table(results)

    def _render_results(self, inp, v_base, v_af) -> None:
        ap = self.cfg["alkali_pump"]
        lines = [
            "=== 开机配置预览（可点上方按钮导出 CSV 或整段复制）===",
            "细胞株：%s        培养基：%s" % (self.widgets["cell_line"].text() or "（未填写）",
                                            self.widgets["medium"].text() or "（未填写）"),
            "",
            "目标工作体积 V_work：      %s mL" % _fmt(inp.v_work_ml),
            "接种体积 V_seed（公式1）： %s mL" % _fmt(inp.v_seed_ml),
            "碱液预留 V_base：          %s mL" % _fmt(v_base),
            "消泡剂 V_antifoam：        %s mL" % _fmt(v_af),
            "培养基补液 V_medium（公式2）：%s mL" % _fmt(inp.v_medium_ml),
            "",
            "Air 流量 Q_air（公式3）：  %s mL/min（vvm = %s）" % (_fmt(inp.q_air_ml_min), _fmt(inp.vvm)),
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
            "培养周期：                 %s 天" % _fmt(inp.culture_days),
            "计划累计取样：             %s mL" % _fmt(inp.sampling_total_ml),
            "碱泵流量系数建议：         不超过 %s mL/(min·L)（%s）" % (_fmt(ap["max_rate_ml_per_min_per_L"]), ap["note"]),
        ]
        lines += self._supplement_rows(inp)
        self.txt_results.setPlainText("\n".join(lines))

    def _supplement_rows(self, inp) -> list:
        """第四轮：补充公式展示行（提示词文档§四(四)）。
        k 为 null 时按"黄色文字警告、不崩溃"处理（同叶轮直径 D 缺参数模式）；
        配置被手工改坏导致缺键时也仅输出一行警告，绝不抛异常。"""
        extra = []
        try:
            n_total = formulas.total_cells_millions(inp.v_work_ml, inp.cd_inoc_mcells_ml)
            unit = str(self.cfg["total_cells"]["display_unit"])
            extra.append("总需细胞数 N_total（补充公式A）：      %s %s（即 %s cells）" % (
                _fmt(n_total), unit, formulas.scientific_cn(n_total * 1000000.0)))
            sug = formulas.agitation_start_rpm_suggestion(
                inp.v_work_ml, self.cfg["agitation_start_suggestion"]["bands_ml"])
            extra.append("搅拌启动建议转速（补充公式B）：      %s rpm（按工作体积分段，仅建议，实际仍受 R05 校验）" % _fmt(sug))
            mp = self.cfg["mixing_physics"]
            if bool(mp.get("shear_gamma_enabled", False)):
                k = mp.get("impeller_constant_k")
                if k is None:
                    extra.append("⚠️ 缺少叶轮常数 k，无法估算剪切速率 γ（补充公式C），"
                                 "请在 config.yaml 的 mixing_physics.impeller_constant_k 补充后自动生效")
                else:
                    gamma = formulas.shear_gamma_per_s(inp.rpm, k)
                    extra.append("表观剪切速率估算 γ（补充公式C）：      %s 1/s（γ≈k×N，k=%s；%s）" % (
                        _fmt(gamma), _fmt(k), mp.get("shear_gamma_note", "")))
        except (ValueError, KeyError, TypeError) as exc:
            extra.append("⚠️ 补充公式展示项无法计算（配置可能不完整）：" + str(exc))
        return extra

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
        self.lbl_summary.setText("校验汇总：共 %d 条规则：错误 %d 项，警告 %d 项，通过 %d 项。" % (
            len(results), n_err, n_warn, len(results) - n_err - n_warn)
            + ("存在 🔴 错误时禁止按此配置上机！" if n_err else
               ("存在 🟡 警告，可继续但需人工确认。" if n_warn else "全部通过 ✅。")))

    # ---------------- 配置单导出 / 复制 ----------------
    def _export_blocked_by_errors(self) -> bool:
        """第四轮红线（提示词文档§五(二)）：config setup_sheet_strict.block_export_on_error 为 true 时，
        存在任何 🔴 错误即禁止导出/复制配置单；为 false 时退回第三轮的"询问确认"行为。"""
        errors = [r for r in self._last["results"] if r.level == validators.LEVEL_ERROR]
        if not errors:
            return False
        strict = bool(self.cfg.get("setup_sheet_strict", {}).get("block_export_on_error", False))
        if strict:
            detail = "\n".join("· %s %s：%s" % (r.rule_id, r.name, r.message) for r in errors)
            QMessageBox.warning(
                self, "存在红色错误，已禁止导出",
                "当前配置有 %d 项 🔴 错误，按约定禁止生成配置单。请修正输入后重新点「计算并校验」。\n\n%s" % (len(errors), detail))
            return True
        answer = QMessageBox.question(
            self, "存在红色错误",
            "当前配置有 %d 项 🔴 错误，本不应上机。仍要导出配置单留档吗？" % len(errors),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer != QMessageBox.Yes


    def _sheet_rows(self):
        if self._last is None:
            return None
        return sheet_export.build_sheet_rows(
            self._last["inp"], self._last["v_base"], self._last["v_af"],
            self.widgets["cell_line"].text(), self.widgets["medium"].text(),
            self._last["results"], self.cfg)

    def _export_csv(self) -> None:
        rows = self._sheet_rows()
        if rows is None:
            QMessageBox.warning(self, "尚未计算", "请先点「计算并校验」，再导出配置单。")
            return
        if self._export_blocked_by_errors():
            return
        default = str(PROJECT_ROOT / ("开机配置单_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M")))
        path, _ = QFileDialog.getSaveFileName(self, "导出开机配置单 CSV", default, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            saved = sheet_export.export_sheet_csv(path, rows, self.cfg)
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", "无法写入文件：" + str(exc))
            return
        QMessageBox.information(self, "导出完成",
                                "配置单已保存到：\n" + str(saved) + "\n双击该文件可用 Excel/WPS 打开（已处理中文编码）。")

    def _copy_sheet(self) -> None:
        rows = self._sheet_rows()
        if rows is None:
            QMessageBox.warning(self, "尚未计算", "请先点「计算并校验」，再复制配置单。")
            return
        if self._export_blocked_by_errors():
            return
        QApplication.clipboard().setText("\t".join(sheet_export.HEADER) + "\n" +
                                         "\n".join("\t".join(str(c) for c in row[1:]) for row in rows[1:]))
        QMessageBox.information(self, "已复制", "配置单已复制到剪贴板，可直接粘贴到 Excel 或微信。")

    # ---------------- 配方 ----------------
    def _collect_params(self) -> dict:
        params = {}
        for key, w in self.widgets.items():
            if isinstance(w, QLineEdit):
                params[key] = w.text()
            elif isinstance(w, QDoubleSpinBox):
                params[key] = w.value()
        params["expr_check"] = self.chk_expr.isChecked()
        return params

    def _apply_params(self, params: dict) -> None:
        for key, val in params.items():
            w = self.widgets.get(key)
            if w is None:
                continue
            try:
                if isinstance(w, QLineEdit):
                    w.setText(str(val))
                elif isinstance(w, QDoubleSpinBox):
                    w.setValue(float(val))
            except (TypeError, ValueError):
                pass   # 配方里多余/非法的字段直接忽略，不影响其余参数载入
        self.chk_expr.setChecked(bool(params.get("expr_check", False)))
        self.widgets["temp_expr"].setEnabled(self.chk_expr.isChecked())

    def _recipe_refresh(self, select: str = "") -> None:
        self.cmb_recipe.clear()
        self.cmb_recipe.addItems(recipe_store.list_recipes())
        if select:
            self.cmb_recipe.setCurrentText(select)

    def _recipe_save(self) -> None:
        name = self.edit_recipe.text().strip() or str(self.cfg["recipes"]["builtin_default_name"])
        try:
            path = recipe_store.save_recipe(name, self._collect_params())
        except ValueError as exc:
            QMessageBox.warning(self, "配方名不合法", str(exc))
            return
        self._recipe_refresh(select=name)
        QMessageBox.information(self, "配方已保存", "配方「%s」已保存到：\n%s" % (name, path))

    def _recipe_load(self) -> None:
        name = self.cmb_recipe.currentText().strip() or self.edit_recipe.text().strip()
        if not name:
            QMessageBox.warning(self, "未选择配方", "请先在「已存配方」下拉框中选择一个配方。")
            return
        try:
            params = recipe_store.load_recipe(name)
        except ValueError as exc:
            QMessageBox.critical(self, "无法读取配方", str(exc))
            return
        self._apply_params(params)
        self.edit_recipe.setText(name)
        self.compute()

    def _recipe_delete(self) -> None:
        name = self.cmb_recipe.currentText().strip()
        if not name:
            QMessageBox.warning(self, "未选择配方", "请先在下拉框中选择要删除的配方。")
            return
        answer = QMessageBox.question(self, "确认删除", "确定删除配方「%s」吗？此操作不可撤销。" % name,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            recipe_store.delete_recipe(name)
        except ValueError as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self._recipe_refresh()

    # ================= 标签页②：硬件配置 =================
    HW_SCALAR_SPECS = [
        # (分组, 键路径, 显示名, 单位, 小数位, 显示换算倍数)
        ("反应器与 MFC 量程", ("hardware", "min_working_volume_ml"), "最小工作体积", "mL", 0, 1),
        ("反应器与 MFC 量程", ("hardware", "max_working_volume_ml"), "最大工作体积", "mL", 0, 1),
        ("反应器与 MFC 量程", ("hardware", "mfc_max_ml_min", "air"), "Air MFC 量程上限", "mL/min", 0, 1),
        ("反应器与 MFC 量程", ("hardware", "mfc_max_ml_min", "n2"), "N₂ MFC 量程上限", "mL/min", 0, 1),
        ("反应器与 MFC 量程", ("hardware", "mfc_max_ml_min", "o2"), "O₂ MFC 量程上限", "mL/min", 0, 1),
        ("反应器与 MFC 量程", ("hardware", "mfc_max_ml_min", "co2"), "CO₂ MFC 量程上限", "mL/min", 0, 1),
        ("推荐参数默认值（其他）", ("process_defaults", "culture_days", "set"), None, None, None, None),
        ("其他建议值", ("alkali_pump", "max_rate_ml_per_min_per_L"), "碱泵流量系数上限建议", "mL/(min·L)", 3, 1),
        ("其他建议值", ("sampling", "max_cumulative_fraction_of_working"), "累计取样体积上限（占工作体积）", "%", 1, 100),
        ("其他建议值", ("ui_defaults", "working_volume_ml"), "配置页默认工作体积", "mL", 0, 1),
        ("其他建议值", ("ui_defaults", "seed_conc_mcells_ml"), "配置页默认种子液浓度", "×10⁶ cells/mL", 2, 1),
    ]
    HW_RANGE_SPECS = [
        # (键路径前缀, 显示名, 单位, 小数位, 换算倍数, 值键名)
        (("process_defaults", "temp_growth_c"), "生长阶段温度", "°C", 1, 1, "set"),
        (("process_defaults", "temp_expression_c"), "表达阶段温度", "°C", 1, 1, "set"),
        (("process_defaults", "ph_setpoint"), "pH 设定点", "", 2, 1, "set"),
        (("process_defaults", "do_percent"), "DO 设定点", "%", 0, 1, "set"),
        (("process_defaults", "agitation_rpm"), "搅拌初始转速", "rpm", 0, 1, "set"),
        (("process_defaults", "aeration_vvm"), "通气强度 vvm", "vvm", 2, 1, "set"),
        (("process_defaults", "o2_ratio_percent"), "O2 补充比例", "%", 1, 1, "set"),
        (("process_defaults", "co2_ratio_percent"), "CO2 配比", "%", 1, 1, "set"),
        (("process_defaults", "inoculum_density_mcells_ml"), "目标接种密度 CD_inoc", "×10⁶ cells/mL", 2, 1, "set"),
        (("process_defaults", "culture_days"), "培养周期", "天", 0, 1, "set"),
        (("liquid_additives", "base_fraction_of_working"), "碱液预留比例", "%", 1, 100, "default"),
        (("liquid_additives", "antifoam_fraction_of_working"), "消泡剂预留比例", "%", 2, 100, "default"),
    ]

    def _build_hardware_tab(self) -> QWidget:
        # 小屏适配：本页控件最多（多组量程 + 默认值/下限/上限表），
        # 装进滚动区，否则会把整个窗口撑高到屏幕外，底部按钮看不全。
        host = QWidget()
        host_lay = QVBoxLayout(host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host_lay.addWidget(scroll)
        tab = QWidget()
        lay = QVBoxLayout(tab)
        scroll.setWidget(tab)
        # 第七轮：这句话里要点名"回去哪个子页"，因此直接取 config 里的子页签名称，避免写死旧页名
        try:
            planner_name = self._tab_titles()[0]
        except Exception:
            planner_name = "① 配置与校验"
        intro = QLabel(app_info.ui_text_fmt(
            self.cfg, "hw_intro",
            "在这里修改硬件上下限与推荐参数默认值，点「保存并生效」后写回 config/config.yaml"
            "（自动保留注释，并备份为 config.yaml.bak）。\n"
            "改完回到「{planner}」点「恢复默认值」即可套用新默认；所有校验规则会立即使用新阈值。",
            planner=planner_name))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.hw_widgets = []   # (kind, spec, widget(s))
        groups = {}
        for spec in self.HW_SCALAR_SPECS:
            group, path, label, unit, dec, scale = spec
            if label is None:
                continue   # 占位行（值在下方区间表中编辑）
            if group not in groups:
                box = QGroupBox(group)
                form = QFormLayout(box)
                groups[group] = (box, form)
                lay.addWidget(box)
            spin = QDoubleSpinBox()
            spin.setDecimals(dec)
            spin.setRange(0.0, 9999999.0)
            spin.setSuffix(" " + unit)
            groups[group][1].addRow(label, spin)
            self.hw_widgets.append(("scalar", spec, spin))

        range_box = QGroupBox("工艺参数推荐范围（默认值 / 下限 / 上限）")
        grid = QGridLayout(range_box)
        for col, text in enumerate(["参数", "单位", "默认值", "下限", "上限"]):
            head_item = QLabel(text)
            head_item.setStyleSheet("font-weight: bold;")
            grid.addWidget(head_item, 0, col)
        for row, spec in enumerate(self.HW_RANGE_SPECS, start=1):
            base, label, unit, dec, scale, vkey = spec
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(QLabel(unit), row, 1)
            spins = []
            for col, sub in enumerate((vkey, "min", "max"), start=2):
                spin = QDoubleSpinBox()
                spin.setDecimals(dec)
                spin.setRange(0.0, 9999999.0)
                grid.addWidget(spin, row, col)
                spins.append(spin)
            self.hw_widgets.append(("range", spec, spins))
        lay.addWidget(range_box)

        btn_row = QHBoxLayout()
        self.btn_hw_save = QPushButton("保存并生效（写回 config.yaml）")
        self.btn_hw_reload = QPushButton("放弃修改，重新读取当前配置")
        btn_row.addWidget(self.btn_hw_save)
        btn_row.addWidget(self.btn_hw_reload)
        lay.addLayout(btn_row)
        self.lbl_hw_status = QLabel("")
        self.lbl_hw_status.setWordWrap(True)
        lay.addWidget(self.lbl_hw_status)
        lay.addStretch(1)
        self.btn_hw_save.clicked.connect(self._hw_save)
        self.btn_hw_reload.clicked.connect(self._hw_fill)
        self._hw_fill()
        return host

    def _hw_fill(self) -> None:
        for kind, spec, w in self.hw_widgets:
            if kind == "scalar":
                _, path, _, _, _, scale = spec
                w.setValue(float(_cfg_get(self.cfg, tuple(path))) * scale)
            else:
                base, _, _, _, scale, vkey = spec
                vals = (vkey, "min", "max")
                for spin, sub in zip(w, vals):
                    spin.setValue(float(_cfg_get(self.cfg, tuple(base) + (sub,))) * scale)

    def _hw_collect_updates(self):
        updates = {}
        errors = []
        for kind, spec, w in self.hw_widgets:
            if kind == "scalar":
                _, path, label, unit, _, scale = spec
                updates[tuple(path)] = w.value() / scale
            else:
                base, label, unit, _, scale, vkey = spec
                v_set, v_min, v_max = (spin.value() / scale for spin in w)
                if v_min > v_max:
                    errors.append("「%s」下限 %s 大于上限 %s。" % (label, _fmt(v_min), _fmt(v_max)))
                if not (v_min <= v_set <= v_max):
                    errors.append("「%s」默认值 %s 不在上下限 %s–%s 之间。" % (label, _fmt(v_set), _fmt(v_min), _fmt(v_max)))
                for sub, val in ((vkey, v_set), ("min", v_min), ("max", v_max)):
                    updates[tuple(base) + (sub,)] = val
        hw = updates.get(("hardware", "min_working_volume_ml"))
        hx = updates.get(("hardware", "max_working_volume_ml"))
        if hw is not None and hx is not None and hw >= hx:
            errors.append("最小工作体积 %s mL 必须小于最大工作体积 %s mL。" % (_fmt(hw), _fmt(hx)))
        return updates, errors

    def _refresh_extra_tabs(self) -> None:
        """②页写回 config 后，让③④⑤⑥页重读阈值/映射/条目，避免新旧参数打架。
        单个页面刷新失败不影响其他页面，问题汇总后由调用方显示。"""
        targets = ((self.analysis_tab, "_refresh_cfg"), (self.mapping_tab, "_refresh_cfg"),
                   (self.template_tab, "refresh_cfg"), (self.sop_tab, "refresh_cfg"))
        problems = []
        for widget, method in targets:
            try:
                getattr(widget, method)()
            except Exception as exc:                  # 某页刷新失败不能连累已保存的配置
                problems.append("%s：%s" % (type(exc).__name__, exc))
        return problems

    def _hw_save(self) -> None:
        updates, errors = self._hw_collect_updates()
        if errors:
            QMessageBox.warning(self, "硬件配置有误", "以下问题未解决，已拒绝保存：\n· " + "\n· ".join(errors))
            return
        answer = QMessageBox.question(
            self, "确认写回配置文件",
            "将把 %d 项配置写回 config/config.yaml（原文件会先备份为 config.yaml.bak）。\n是否继续？" % len(updates),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            return
        try:
            update_config_file(updates)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.cfg = get_config()
        self._hw_fill()
        problems = self._refresh_extra_tabs()
        if problems:
            QMessageBox.warning(self, "部分页面未刷新",
                                "配置已保存成功，但下面这些页面没能跟着刷新（不影响 config 内容）：\n· "
                                + "\n· ".join(problems))
        self.lbl_hw_status.setText("✅ %s 已保存并立即生效（共 %d 项）。旧配置备份：config/config.yaml.bak" % (
            datetime.now().strftime("%H:%M:%S"), len(updates)))
        QMessageBox.information(self, "保存成功", "硬件配置已写回 config.yaml 并立即生效。\n如需让输入框恢复新默认值，请回到①页点「恢复默认值」。")



def _excepthook(exc_type, exc, tb) -> None:
    """未预期异常也用中文弹窗说明，绝不静默闪退（完整堆栈同时打到控制台便于定位）。"""
    detail = "".join(traceback.format_exception(exc_type, exc, tb)).strip().splitlines()
    last = detail[-1] if detail else str(exc)
    write_diagnostic("\n".join(detail), level="异常")
    text = ("软件遇到一个没预料到的问题，已尽量保住界面不闪退。\n\n"
            "出错信息：%s\n\n"
            "你可以：\n"
            "1) 点「确定」后继续使用其他功能；\n"
            "2) 若反复出现，请截图本窗口并联系开发者（配置文件与数据文件不会被改动）。" % last)
    try:
        QMessageBox.warning(None, "软件遇到问题", text)
    except Exception:
        pass


def main() -> int:
    """程序入口：双击工程根目录的 启动软件.bat，或在命令行执行  python run.py。"""
    sys.excepthook = _excepthook
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        from PySide6.QtGui import QIcon
        app.setApplicationName(str((get_config().get("app_info") or {}).get("name", "")))
        icon_path = bundled_asset(str((get_config().get("app_info") or {}).get("icon_file", "")))
        if icon_path:
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass
    try:
        win = MainWindow()
    except Exception as exc:
        detail = traceback.format_exc().strip().splitlines()
        log_path = write_diagnostic("\n".join(detail), level="启动失败")
        QMessageBox.critical(
            None, "软件启动失败",
            "无法启动，多半是 config\\config.yaml 有问题、被别的程序占用，或安装位置不可写。\n\n出错信息：%s\n\n"
            "完整原因已写进日志：%s\n请把这条信息和日志文件一起发给开发者，不要反复双击。"
            % (detail[-1] if detail else exc, log_path or "（日志文件没能写成功）"))
        return 1
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

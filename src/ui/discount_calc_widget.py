# -*- coding: utf-8 -*-
"""折扣推算页面 — 统一工作台布局与计算流程。"""

import os
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QMessageBox, QProgressBar,
    QTabWidget, QRadioButton, QButtonGroup,
    QDoubleSpinBox, QApplication, QCheckBox, QLineEdit,
    QFrame, QFileDialog, QComboBox, QGridLayout
)
from PySide6.QtCore import Signal

from src.config import Config
from src.services.discount_calc_svc import DiscountCalcService
from src.services.shipping_service import ShippingService
from src.ui.result_table import ResultTable
from src.ui.match_data_table import MatchDataTable
from src.ui.calc_data_table import CalcDataTable
from src.ui.raw_table import RawTable

logger = logging.getLogger(__name__)


class DiscountCalcWidget(QWidget):
    """折扣推算页: 操作栏 + 结果表"""

    calculate_requested = Signal()
    import_requested = Signal(str)
    import_done = Signal()
    export_requested = Signal()

    STRATEGY_DISCOUNT_ONLY = "discount_only"
    STRATEGY_PRICE_ONLY = "price_only"
    STRATEGY_BOTH = "both"
    STRATEGY_KEEP_DISCOUNT = "keep_discount"
    STRATEGY_ZERO_DISCOUNT = "zero_discount"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._pending_file_path = None
        self._worker = None
        self._last_commission_table = None
        self._last_strategy = "discount_only"
        self._last_exchange_rate = 12.0
        self._last_shop_type = "wb_cross_border"
        self._last_currency = "CNY"
        self._is_matched = False
        self._pending_auto_calculate = False
        self._match_count = 0
        self._svc = None  # Injected via set_service() from MainWindow
        self._commission_db = None  # Injected via set_service() from MainWindow
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self._step_status_labels = {}
        self._calc_mode = "profit_rate"

        # ── Step 1 — 导入数据 ──
        step1 = QFrame()
        step1.setObjectName("stepBlock")
        s1_layout = QVBoxLayout(step1)
        s1_layout.setContentsMargins(10, 8, 10, 8)
        s1_layout.setSpacing(4)

        s1_title_row = QHBoxLayout()
        s1_title_row.setSpacing(10)
        s1_title = QLabel("步骤 1  ·  导入数据")
        s1_title.setObjectName("stepTitle")
        s1_title_row.addWidget(s1_title)
        s1_status = QLabel("待执行")
        s1_status.setObjectName("stepStatus")
        s1_title_row.addWidget(s1_status)
        s1_title_row.addStretch()
        self._step_status_labels[1] = s1_status
        s1_layout.addLayout(s1_title_row)

        s1_controls = QHBoxLayout()
        s1_controls.setSpacing(10)
        self.btn_select = QPushButton("导入 Excel 模板")
        self.btn_select.setProperty("class", "btn-primary")
        self.btn_select.setFixedHeight(32)
        self.btn_select.clicked.connect(self._on_select_file)
        s1_controls.addWidget(self.btn_select)

        self.lbl_file = QLabel("未导入数据")
        self.lbl_file.setObjectName("fileSummary")
        s1_controls.addWidget(self.lbl_file, stretch=1)

        self.lbl_currency = QLabel("")
        self.lbl_currency.setProperty("class", "stat-label")
        s1_controls.addWidget(self.lbl_currency)
        s1_layout.addLayout(s1_controls)

        layout.addWidget(step1)

        # ── Step 2 — 匹配基础数据 ──
        step2 = QFrame()
        step2.setObjectName("stepBlock")
        s2_layout = QVBoxLayout(step2)
        s2_layout.setContentsMargins(10, 8, 10, 8)
        s2_layout.setSpacing(4)

        s2_title_row = QHBoxLayout()
        s2_title_row.setSpacing(10)
        s2_title = QLabel("步骤 2  ·  匹配基础数据")
        s2_title.setObjectName("stepTitle")
        s2_title_row.addWidget(s2_title)
        s2_status = QLabel("待执行")
        s2_status.setObjectName("stepStatus")
        s2_title_row.addWidget(s2_status)
        s2_title_row.addStretch()
        self._step_status_labels[2] = s2_status
        s2_layout.addLayout(s2_title_row)

        s2_controls = QHBoxLayout()
        s2_controls.setSpacing(10)
        self.combo_shop_type = QComboBox()
        self.combo_shop_type.currentIndexChanged.connect(self._on_shop_type_changed)
        s2_controls.addWidget(self._make_field_label("店铺"))
        s2_controls.addWidget(self.combo_shop_type)

        self.combo_commission = QComboBox()
        self.combo_commission.currentIndexChanged.connect(self._on_commission_changed)
        s2_controls.addWidget(self._make_field_label("佣金表"))
        s2_controls.addWidget(self.combo_commission)

        self.spin_default_commission = QDoubleSpinBox()
        self.spin_default_commission.setRange(0.0, 100.0)
        self.spin_default_commission.setDecimals(1)
        self.spin_default_commission.setValue(30.0)
        self.spin_default_commission.setSuffix(" %")
        self.spin_default_commission.setFixedWidth(90)
        self.spin_default_commission.setToolTip("未匹配到类目时使用的默认佣金率")
        s2_controls.addWidget(self._make_field_label("默认佣金率"))
        s2_controls.addWidget(self.spin_default_commission)

        self._commission_category_source = QComboBox()
        self._commission_category_source.addItems(["飞书产品类目", "Excel表格类目"])
        self._commission_category_source.setToolTip(
            "选择匹配佣金率时使用哪个类目来源：\n"
            "• 飞书产品类目：使用SKU匹配到的飞书产品的类目\n"
            "• Excel表格类目：使用导入Excel B列(类目)的值"
        )
        self._commission_category_source.currentIndexChanged.connect(
            lambda: self._save_category_source()
        )
        s2_controls.addWidget(self._make_field_label("佣金类目来源"))
        s2_controls.addWidget(self._commission_category_source)

        self.rb_rate_realtime = QRadioButton("实时汇率")
        self.rb_rate_specified = QRadioButton("手动")
        grp_rate = QButtonGroup(self)
        grp_rate.addButton(self.rb_rate_realtime)
        grp_rate.addButton(self.rb_rate_specified)
        self.rb_rate_realtime.setChecked(True)

        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.01, 100.0)
        self.spin_rate.setDecimals(4)
        self.spin_rate.setValue(12.0)
        self.spin_rate.setFixedWidth(100)
        self.spin_rate.setEnabled(False)
        self.rb_rate_specified.toggled.connect(self.spin_rate.setEnabled)
        self.rb_rate_realtime.toggled.connect(lambda _: self._refresh_dashboard())
        self.rb_rate_specified.toggled.connect(lambda _: self._refresh_dashboard())
        self.spin_rate.valueChanged.connect(lambda _: self._refresh_dashboard())

        s2_controls.addWidget(self.rb_rate_realtime)
        s2_controls.addWidget(self.rb_rate_specified)
        s2_controls.addWidget(self.spin_rate)

        self.btn_match = QPushButton("执行匹配")
        self.btn_match.setProperty("class", "btn-primary")
        self.btn_match.setFixedHeight(32)
        self.btn_match.setToolTip("匹配SKU + 佣金 + 计算运费")
        self.btn_match.clicked.connect(self._on_match)
        s2_controls.addWidget(self.btn_match)
        s2_controls.addStretch()
        s2_layout.addLayout(s2_controls)

        layout.addWidget(step2)

        # ── Step 3 — 计算盈亏 ──
        step3 = QFrame()
        step3.setObjectName("stepBlock")
        s3_layout = QVBoxLayout(step3)
        s3_layout.setContentsMargins(10, 8, 10, 8)
        s3_layout.setSpacing(4)

        s3_title_row = QHBoxLayout()
        s3_title_row.setSpacing(10)
        s3_title = QLabel("步骤 3  ·  计算盈亏")
        s3_title.setObjectName("stepTitle")
        s3_title_row.addWidget(s3_title)
        s3_status = QLabel("待执行")
        s3_status.setObjectName("stepStatus")
        s3_title_row.addWidget(s3_status)
        s3_title_row.addStretch()
        self._step_status_labels[3] = s3_status
        s3_layout.addLayout(s3_title_row)

        s3_controls = QHBoxLayout()
        s3_controls.setSpacing(10)

        self.rb_profit_rate = QRadioButton("按利润率")
        self.rb_fixed_profit = QRadioButton("按固定利润")
        self.btn_group_calc_mode = QButtonGroup(self)
        self.btn_group_calc_mode.addButton(self.rb_profit_rate)
        self.btn_group_calc_mode.addButton(self.rb_fixed_profit)
        self.rb_profit_rate.setChecked(True)
        self.rb_profit_rate.toggled.connect(self._on_calc_mode_changed)

        self.spin_target_profit = QDoubleSpinBox()
        self.spin_target_profit.setRange(0, 100)
        self.spin_target_profit.setDecimals(1)
        self.spin_target_profit.setSuffix(" %")
        self.spin_target_profit.setValue(10.0)
        self.spin_target_profit.setFixedWidth(100)

        s3_controls.addWidget(self.rb_profit_rate)
        s3_controls.addWidget(self.rb_fixed_profit)
        s3_controls.addWidget(self.spin_target_profit)

        self.btn_calculate = QPushButton("计算盈亏")
        self.btn_calculate.setProperty("class", "btn-primary")
        self.btn_calculate.setFixedHeight(32)
        self.btn_calculate.setEnabled(False)
        self.btn_calculate.setToolTip("计算盈亏、折扣推算")
        self.btn_calculate.clicked.connect(self._on_calculate)
        s3_controls.addWidget(self.btn_calculate)

        self.btn_run_all = QPushButton("一键测算")
        self.btn_run_all.setProperty("class", "btn-outline")
        self.btn_run_all.setFixedHeight(32)
        self.btn_run_all.clicked.connect(self._on_run_all)
        s3_controls.addWidget(self.btn_run_all)

        self.lbl_match_status = QLabel("")
        self.lbl_match_status.setProperty("class", "stat-label")
        s3_controls.addWidget(self.lbl_match_status)
        s3_controls.addStretch()
        s3_layout.addLayout(s3_controls)

        layout.addWidget(step3)

        # ── Step 4 — 导出建议 ──
        step4 = QFrame()
        step4.setObjectName("stepBlock")
        s4_layout = QVBoxLayout(step4)
        s4_layout.setContentsMargins(10, 8, 10, 8)
        s4_layout.setSpacing(4)

        s4_title_row = QHBoxLayout()
        s4_title_row.setSpacing(10)
        s4_title = QLabel("步骤 4  ·  导出建议")
        s4_title.setObjectName("stepTitle")
        s4_title_row.addWidget(s4_title)
        s4_status = QLabel("待执行")
        s4_status.setObjectName("stepStatus")
        s4_title_row.addWidget(s4_status)
        s4_title_row.addStretch()
        self._step_status_labels[4] = s4_status
        s4_layout.addLayout(s4_title_row)

        s4_controls = QHBoxLayout()
        s4_controls.setSpacing(10)

        self.combo_strategy = QComboBox()
        self.combo_strategy.addItem("折扣优先", self.STRATEGY_DISCOUNT_ONLY)
        self.combo_strategy.addItem("价格优先", self.STRATEGY_PRICE_ONLY)
        self.combo_strategy.addItem("价格 + 折扣", self.STRATEGY_BOTH)
        self.combo_strategy.addItem("保持折扣调价", self.STRATEGY_KEEP_DISCOUNT)
        self.combo_strategy.addItem("折扣归零调价", self.STRATEGY_ZERO_DISCOUNT)
        self.combo_strategy.currentIndexChanged.connect(self._on_strategy_changed)
        s4_controls.addWidget(self._make_field_label("输出策略"))
        s4_controls.addWidget(self.combo_strategy)

        self.btn_export = QPushButton("导出建议")
        self.btn_export.setProperty("class", "btn-success")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setMinimumWidth(100)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(lambda: self.export_requested.emit())
        s4_controls.addWidget(self.btn_export)

        self.btn_export_unmatched_sku = QPushButton("导出未匹配SKU")
        self.btn_export_unmatched_sku.setProperty("class", "btn-outline")
        self.btn_export_unmatched_sku.setMinimumWidth(110)
        self.btn_export_unmatched_sku.setToolTip("导出SKU未匹配到的商品到Excel")
        self.btn_export_unmatched_sku.clicked.connect(self._on_export_unmatched_sku)
        s4_controls.addWidget(self.btn_export_unmatched_sku)

        self.btn_export_unmatched_category = QPushButton("导出未匹配类目")
        self.btn_export_unmatched_category.setProperty("class", "btn-outline")
        self.btn_export_unmatched_category.setMinimumWidth(110)
        self.btn_export_unmatched_category.setToolTip("导出类目未匹配到的商品到Excel")
        self.btn_export_unmatched_category.clicked.connect(self._on_export_unmatched_category)
        s4_controls.addWidget(self.btn_export_unmatched_category)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setProperty("class", "stat-label")
        s4_controls.addWidget(self.lbl_summary)
        s4_controls.addStretch()
        s4_layout.addLayout(s4_controls)

        layout.addWidget(step4)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ── 筛选栏 ──
        filter_wrap = QFrame()
        filter_wrap.setObjectName("filterBar")
        filter_row = QHBoxLayout(filter_wrap)
        filter_row.setContentsMargins(12, 10, 12, 10)
        filter_row.setSpacing(6)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索 SKU / 类目 / 匹配状态")
        self.search_input.setMinimumWidth(220)
        self.search_input.setMaximumWidth(280)
        self.search_input.setObjectName("searchInput")
        filter_row.addWidget(self.search_input)

        self.chk_profit_filter = QCheckBox("盈亏额低于")
        self.chk_profit_filter.setObjectName("filterCheck")
        filter_row.addWidget(self.chk_profit_filter)

        self.spin_profit_threshold = QDoubleSpinBox()
        self.spin_profit_threshold.setRange(-999999, 999999)
        self.spin_profit_threshold.setDecimals(2)
        self.spin_profit_threshold.setValue(0)
        self.spin_profit_threshold.setFixedWidth(100)
        self.spin_profit_threshold.setEnabled(False)
        filter_row.addWidget(self.spin_profit_threshold)

        self.chk_unmatched = QCheckBox("仅显示未匹配SKU")
        self.chk_unmatched.setObjectName("filterCheck")
        filter_row.addWidget(self.chk_unmatched)

        self.chk_unmatched_category = QCheckBox("仅显示未匹配类目")
        self.chk_unmatched_category.setObjectName("filterCheck")
        filter_row.addWidget(self.chk_unmatched_category)

        self.btn_apply_filter = QPushButton("确定筛选")
        self.btn_apply_filter.setProperty("class", "btn-primary")
        self.btn_apply_filter.setMinimumWidth(72)
        filter_row.addWidget(self.btn_apply_filter)

        self.btn_clear_filter = QPushButton("清除筛选")
        self.btn_clear_filter.setProperty("class", "btn-outline")
        self.btn_clear_filter.setMinimumWidth(72)
        filter_row.addWidget(self.btn_clear_filter)

        filter_row.addSpacing(12)

        self.lbl_filter_count = QLabel("")
        self.lbl_filter_count.setProperty("class", "stat-label")
        filter_row.addWidget(self.lbl_filter_count)
        filter_row.addStretch()

        layout.addWidget(filter_wrap)

        # Connect filter signals
        self.chk_profit_filter.toggled.connect(self.spin_profit_threshold.setEnabled)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.btn_apply_filter.clicked.connect(self._apply_filters)
        self.btn_clear_filter.clicked.connect(self._clear_filters)

        # ── Tab Widget: 4-tab layout ──
        self.tabs = QTabWidget()
        self.tabs.setObjectName("discountTabs")

        # Tab 1: 原始数据
        self.raw_table = RawTable()

        # Tab 2: 匹配数据
        self.match_table = MatchDataTable()
        self.match_table.setObjectName("matchTable")

        # Tab 3: 计算数据
        self.calc_table = CalcDataTable()
        self.calc_table.setObjectName("calcTable")

        # Tab 4: 结果数据
        self.result_table = ResultTable()
        self.result_table.setObjectName("resultTable")

        self.tabs.addTab(self.raw_table, "原始数据")
        self.tabs.addTab(self.match_table, "匹配数据")
        self.tabs.addTab(self.calc_table, "计算数据")
        self.tabs.addTab(self.result_table, "结果数据")

        # Update filter count when switching tabs
        self.tabs.currentChanged.connect(lambda: self._update_filter_count())

        layout.addWidget(self.tabs, stretch=1)
        self._load_shop_type_options()
        self._load_commission_options()
        self._sync_controls_from_state()
        self._refresh_dashboard()

    def _make_field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _load_shop_type_options(self):
        self.combo_shop_type.blockSignals(True)
        self.combo_shop_type.clear()
        try:
            for tpl in ShippingService().list_templates():
                if not tpl.get("enabled", True):
                    continue
                label = f"{tpl['display_name']} · {tpl['currency_display']}"
                self.combo_shop_type.addItem(label, tpl["key"])
        except Exception:
            self.combo_shop_type.addItem("WB 跨境 · CNY", "wb_cross_border")
        self.combo_shop_type.blockSignals(False)

    def _load_commission_options(self):
        self.combo_commission.blockSignals(True)
        self.combo_commission.clear()
        if self._commission_db is not None:
            tables = self._commission_db.get_commission_tables()
        else:
            tables = []
        for t in tables:
            shop_label = "本土" if t.shop_type == "local" else "跨境"
            label = f"{t.platform.upper()} {shop_label} · {t.row_count:,} 条"
            self.combo_commission.addItem(label, t.table_name)
        if self.combo_commission.count() == 0:
            self.combo_commission.addItem("WB 跨境 · 默认", "commission_wb_cross_border")
        self.combo_commission.blockSignals(False)

    def _sync_controls_from_state(self):
        self._set_combo_by_data(self.combo_shop_type, self._last_shop_type)
        self._set_combo_by_data(self.combo_commission, self._last_commission_table or "commission_wb_cross_border")
        self._set_combo_by_data(self.combo_strategy, self._last_strategy)
        self._update_currency_labels()

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value):
        if value is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _on_shop_type_changed(self):
        selected = self.combo_shop_type.currentData()
        if selected:
            self._last_shop_type = selected
        expected_table = "commission_wb_local" if self._last_shop_type == "wb_local" else "commission_wb_cross_border"
        self._set_combo_by_data(self.combo_commission, expected_table)
        self._update_currency_labels()
        self._refresh_dashboard()

    def _on_commission_changed(self):
        selected = self.combo_commission.currentData()
        if selected:
            self._last_commission_table = selected
            if "local" in selected:
                self._last_shop_type = "wb_local"
            else:
                self._last_shop_type = "wb_cross_border"
            self._set_combo_by_data(self.combo_shop_type, self._last_shop_type)
        self._update_currency_labels()
        self._refresh_dashboard()

    def _on_strategy_changed(self):
        selected = self.combo_strategy.currentData()
        if selected:
            self._last_strategy = selected
        self._refresh_dashboard()

    def _update_currency_labels(self):
        self._last_currency = "RUB" if self._last_shop_type == "wb_local" else "CNY"
        self.lbl_currency.setText(f"计算币种: {self._last_currency}")

    def _refresh_dashboard(self):
        # Step 1: 导入数据
        if self._file_path:
            self._update_step_status(1, "done")
        else:
            self._update_step_status(1, "pending")

        # Step 2: 匹配基础数据
        if not self._file_path:
            self._update_step_status(2, "pending")
        elif not self._is_matched:
            self._update_step_status(2, "active")
        else:
            self._update_step_status(2, "done")

        # Step 3: 计算盈亏
        if not self._is_matched:
            self._update_step_status(3, "pending")
        elif self.has_calc_done():
            self._update_step_status(3, "done")
        else:
            self._update_step_status(3, "active")

        # Step 4: 导出建议
        if self.has_calc_done():
            self._update_step_status(4, "active")
        else:
            self._update_step_status(4, "pending")

    def _on_select_file(self):
        """选择 Excel 文件并交给后台线程导入。"""
        if self.combo_commission.count() == 0:
            QMessageBox.warning(self, "提示", "请先准备佣金表，再导入 Excel 模板。")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Excel 模板",
            "",
            "Excel文件 (*.xlsx *.xls);;所有文件 (*)",
        )
        if not file_path:
            return
        self._pending_file_path = file_path
        self._last_commission_table = self.combo_commission.currentData() or "commission_wb_cross_border"
        self._update_currency_labels()
        self.btn_select.setEnabled(False)
        self.btn_match.setEnabled(False)
        self.btn_calculate.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_run_all.setEnabled(False)
        self.lbl_file.setText(f"{os.path.basename(file_path)} · 正在导入...")
        self.lbl_match_status.setText("导入中...")
        self._update_step_status(1, "active")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.import_requested.emit(file_path)

    def set_import_result(self, file_path: str, count: int):
        """Called by MainWindow after async import completes."""
        self._file_path = file_path
        self._pending_file_path = None
        # 从数据库查询实际导入行数（比依赖worker返回值更可靠）
        actual_count = self._svc.db.get_import_row_count()
        if actual_count <= 0:
            actual_count = count
        self.lbl_file.setText(f"{os.path.basename(file_path)} · {actual_count} 行已导入")
        self._is_matched = False
        self._match_count = 0
        self._calc_done = False
        self.btn_select.setEnabled(True)
        self.btn_match.setEnabled(True)
        self.btn_calculate.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_run_all.setEnabled(True)
        self.lbl_match_status.setText("")
        self.progress.setVisible(False)
        self._load_raw_data()
        self._refresh_dashboard()
        QApplication.processEvents()
        self.import_done.emit()
        self.tabs.setCurrentIndex(0)

    def set_import_error(self, err: str):
        """Called by MainWindow if async import fails."""
        self._file_path = None
        self._pending_file_path = None
        self.btn_select.setEnabled(True)
        self.btn_match.setEnabled(False)
        self.btn_calculate.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_run_all.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_file.setText("未导入数据")
        self.lbl_match_status.setText("")
        self._update_step_status(1, "pending")
        self._refresh_dashboard()
        QMessageBox.warning(self, "导入失败", f"无法导入Excel文件:\n{err}")

    def _on_match(self):
        """Start matching process using inline settings."""
        if not self._file_path:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return

        self._last_shop_type = self.combo_shop_type.currentData() or "wb_cross_border"
        self._last_commission_table = self.combo_commission.currentData() or "commission_wb_cross_border"
        self._last_exchange_rate = self.get_exchange_rate()
        self.btn_match.setEnabled(False)
        self.btn_calculate.setEnabled(False)
        self.lbl_match_status.setText("匹配中...")
        self._update_step_status(2, "active")
        self.progress.setVisible(True)
        self.progress.setRange(0, 1)  # Will be updated by progress signal
        self.progress.setValue(0)

        # Emit signal for MainWindow to handle
        self.calculate_requested.emit()

    def _on_calculate(self):
        """Start calculation using matched results and inline strategy."""
        if not self._is_matched:
            QMessageBox.information(self, "提示", "请先进行匹配计算")
            return

        self._last_strategy = self.combo_strategy.currentData() or self.STRATEGY_DISCOUNT_ONLY
        self.btn_calculate.setEnabled(False)
        self.progress.setVisible(True)
        self._update_step_status(3, "active")
        self._refresh_dashboard()

        self.calculate_requested.emit()

    def _on_run_all(self):
        """One-click full workflow for faster operations."""
        if not self._file_path:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return
        if self._is_matched:
            self._on_calculate()
        else:
            self._pending_auto_calculate = True
            self._on_match()

    # ── External interface ──

    def set_service(self, svc: DiscountCalcService, commission_db=None):
        """Set service with all DB connections"""
        self._svc = svc
        self._commission_db = commission_db
        # Restore saved category source
        if self._svc and hasattr(self._svc, 'db'):
            saved = self._svc.db.get_config('commission_category_source')
            if saved:
                self._commission_category_source.blockSignals(True)
                self.set_commission_category_source(saved)
                self._commission_category_source.blockSignals(False)

    def get_file_path(self):
        return self._file_path

    def get_strategy(self):
        return self.combo_strategy.currentData() or self._last_strategy

    def get_commission_table(self):
        return self.combo_commission.currentData() or self._last_commission_table or "commission_wb_cross_border"

    def set_export_enabled(self, enabled: bool):
        self.btn_export.setEnabled(enabled)

    def update_summary(self, summary: dict):
        self.lbl_summary.setText(
            f"盈利: {summary.get('profit', 0)}  |  亏损: {summary.get('loss', 0)}  |  "
            f"未匹配: {summary.get('unmatched', 0)}  |  总计: {summary.get('total', 0)}"
        )
        self._refresh_dashboard()

    # ── Raw data display ──

    def _load_raw_data(self):
        """Load and display raw imported data in the raw_table"""
        rows = self._svc.db.get_import_rows()
        if not rows:
            self.raw_table.clear_data()
            return

        # col_indices maps to: row_number, brand, category, wb_article, seller_sku, barcode,
        #                       wb_stock, seller_stock, turnover, current_price, current_discount,
        #                       new_price, new_discount
        col_indices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 11, 13]
        data_rows = []
        for row in rows:
            extracted = [row[idx] if idx < len(row) else "" for idx in col_indices]
            # Calculate 折后价格: current_price * (1 - current_discount / 100)
            # extracted[9] = current_price (from col index 10)
            # extracted[10] = current_discount (from col index 12)
            try:
                price = float(str(extracted[9]).replace(",", "").strip()) if extracted[9] else 0
            except (ValueError, TypeError):
                price = 0
            try:
                discount = float(str(extracted[10]).replace(",", "").strip()) if extracted[10] else 0
            except (ValueError, TypeError):
                discount = 0
            discounted = round(price * (1 - discount / 100), 2) if price and discount else price
            # Insert 折后价格 after current_discount (at index 11)
            extracted.insert(11, f"{discounted:.2f}" if discounted else "")
            data_rows.append(extracted)
        self.raw_table.populate(data_rows)

    def get_default_commission(self) -> float:
        """获取用户设置的未匹配类目默认佣金率"""
        return self.spin_default_commission.value()

    def get_commission_category_source(self) -> str:
        """返回佣金类目来源: 'feishu' 或 'excel'"""
        return 'excel' if self._commission_category_source.currentIndex() == 1 else 'feishu'

    def set_commission_category_source(self, source: str):
        """设置佣金类目来源"""
        self._commission_category_source.setCurrentIndex(1 if source == 'excel' else 0)

    def _save_category_source(self):
        """持久化佣金类目来源到app_config"""
        if self._svc and hasattr(self._svc, 'db'):
            source = self.get_commission_category_source()
            self._svc.db.save_config('commission_category_source', source)

    def get_exchange_rate(self) -> float:
        """Returns the exchange rate to use (CNY→RUB)"""
        if self.rb_rate_specified.isChecked():
            return self.spin_rate.value()
        from src.services.exchange_rate import ExchangeRateService
        rate = ExchangeRateService().get_cny_to_rub()
        return rate if rate > 0 else 12.0

    def set_match_result(self, count: int):
        """Called by MainWindow after match completes."""
        self._is_matched = count > 0
        self._match_count = count
        self.btn_match.setEnabled(True)
        self.btn_calculate.setEnabled(count > 0)
        self.lbl_match_status.setText(f"已匹配 {count} 条" if count > 0 else "无匹配结果")
        self.progress.setVisible(False)
        self._refresh_dashboard()
        # Auto-chain calculate if _pending_auto_calculate flag is set
        if self._pending_auto_calculate and count > 0:
            self._pending_auto_calculate = False
            self._on_calculate()

    def set_calc_result(self, count: int):
        """Called by MainWindow after calculation completes."""
        self.btn_calculate.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_file.setText(f"已计算 {count} 条结果")
        self._calc_done = True  # 标记已完成过计算，参数修改后可重算
        self._refresh_dashboard()

    def is_matched(self) -> bool:
        return self._is_matched

    def has_calc_done(self) -> bool:
        """是否已完成过计算（参数修改后可直接重算）"""
        return getattr(self, '_calc_done', False)

    def get_match_count(self) -> int:
        return self._match_count

    def _detect_currency(self, table_name: str) -> str:
        """Detect currency from commission table name"""
        if "本土" in (table_name or "") or "local" in (table_name or ""):
            return "RUB"
        return "CNY"

    def stop_worker(self):
        """Stop the worker thread gracefully."""
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.quit()
            self._worker.wait(3000)
            if self._worker.isRunning():
                self._worker.terminate()
                self._worker.wait(1000)

    def get_currency(self) -> str:
        return getattr(self, '_last_currency', 'CNY')

    # ── Calc mode & step status ──

    def get_calc_mode(self) -> str:
        """Return current calc mode: 'profit_rate' or 'fixed_profit'"""
        return "fixed_profit" if self.rb_fixed_profit.isChecked() else "profit_rate"

    def get_target_profit_amount(self) -> float:
        """Return the inline target profit value"""
        return self.spin_target_profit.value()

    def _on_calc_mode_changed(self):
        """Switch spin_target_profit between rate (%) and amount (¥)"""
        if self.rb_fixed_profit.isChecked():
            self._calc_mode = "fixed_profit"
            self.spin_target_profit.setRange(0, 100000)
            self.spin_target_profit.setDecimals(2)
            self.spin_target_profit.setSuffix(" ¥")
            self.spin_target_profit.setValue(20.0)
        else:
            self._calc_mode = "profit_rate"
            self.spin_target_profit.setRange(0, 100)
            self.spin_target_profit.setDecimals(1)
            self.spin_target_profit.setSuffix(" %")
            self.spin_target_profit.setValue(10.0)

    def _update_step_status(self, step: int, status: str):
        """Update step status indicator.
        status: 'pending' | 'active' | 'done'
        """
        label = self._step_status_labels.get(step)
        if not label:
            return
        colors = {"pending": "#9CA3AF", "active": "#4338CA", "done": "#059669"}
        texts = {"pending": "待执行", "active": "进行中...", "done": "已完成 ✓"}
        label.setText(texts.get(status, ""))
        label.setStyleSheet(
            f"color: {colors.get(status, '#9CA3AF')}; font-size: 11px; font-weight: 600;"
        )
        # Update the step block frame objectName for QSS styling
        # Walk up to find the QFrame parent (stepBlock)
        parent = label.parent()
        if parent and isinstance(parent, QFrame):
            if status == "done":
                parent.setObjectName("stepBlockDone")
            elif status == "active":
                parent.setObjectName("stepBlockActive")
            else:
                parent.setObjectName("stepBlock")
            parent.setStyleSheet("")  # Force re-apply QSS

    # ── 筛选功能 ──

    def _all_tables(self):
        """Return all 4 table views."""
        return [self.raw_table, self.match_table, self.calc_table, self.result_table]

    def _on_search_changed(self, text: str):
        """Live search — applied to all 4 tables."""
        for tbl in self._all_tables():
            tbl._proxy.set_search_text(text)
        self._update_filter_count()

    def _on_export_unmatched_sku(self):
        """导出SKU未匹配到的商品到Excel"""
        self._export_unmatched("sku")

    def _on_export_unmatched_category(self):
        """导出类目未匹配到的商品到Excel"""
        self._export_unmatched("category")

    def _export_unmatched(self, match_type: str):
        """Export unmatched items to Excel.

        match_type: "sku" or "category"
        """
        if not self._file_path:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return

        combined = self._svc.get_import_data()
        if not combined:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return

        unmatched = []
        for imp, calc in combined:
            if calc is None:
                unmatched.append(imp)
            else:
                sku_ok = bool(calc[2])
                cat_ok = bool(calc[3])
                if match_type == "sku" and not sku_ok:
                    unmatched.append(imp)
                elif match_type == "category" and not cat_ok:
                    unmatched.append(imp)

        if not unmatched:
            label = "未匹配SKU" if match_type == "sku" else "未匹配类目"
            QMessageBox.information(
                self, "提示", f"所有商品的{label}都已匹配，无需导出"
            )
            return

        label = "未匹配SKU" if match_type == "sku" else "未匹配类目"
        default_name = (
            os.path.splitext(os.path.basename(self._file_path))[0]
            + f"_{label}.xlsx"
        )
        save_path, _ = QFileDialog.getSaveFileName(
            self, f"导出{label}", default_name, "Excel文件 (*.xlsx)"
        )
        if not save_path:
            return

        try:
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = label

            headers = [
                "行号", "品牌", "类目", "WB货号", "卖家货号", "条码",
                "WB库存", "卖家库存", "周转率", "原价", "新价", "当前折扣", "新折扣",
            ]
            ws.append(headers)

            for imp in unmatched:
                ws.append([
                    imp[1] or "", imp[2] or "", imp[3] or "",
                    imp[4] or "", imp[5] or "", imp[6] or "",
                    imp[7] or "", imp[8] or "", imp[9] or "",
                    imp[10] or "", imp[11] or "", imp[12] or "",
                    imp[13] or "",
                ])

            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)

            wb.save(save_path)
            QMessageBox.information(
                self, "导出成功",
                f"{label}共 {len(unmatched)} 条\n已保存到:\n{save_path}",
            )
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"导出出错:\n{e}")

    def _apply_filters(self):
        """Apply all active filters to all 4 tables."""
        for tbl in self._all_tables():
            proxy = tbl._proxy
            proxy.clear_all_filters()

            # Re-apply search text
            search = self.search_input.text().strip()
            if search:
                proxy.set_search_text(search)

            # 盈亏额筛选: profit < threshold
            if self.chk_profit_filter.isChecked():
                threshold = self.spin_profit_threshold.value()
                profit_col = self._find_column(tbl, "profit")
                if profit_col is not None:
                    proxy.set_numeric_filter(profit_col, "<", threshold)

            # 未匹配SKU筛选: cost_matched == False (displayed as "❌")
            if self.chk_unmatched.isChecked():
                unmatched_col = self._find_first_column(tbl, ("cost_matched", "sku_matched"))
                if unmatched_col is not None:
                    proxy.set_column_filter(unmatched_col, {"❌"})

            # 未匹配类目筛选: category_matched == False (displayed as "❌")
            if self.chk_unmatched_category.isChecked():
                unmatched_cat_col = self._find_column(tbl, "category_matched")
                if unmatched_cat_col is not None:
                    proxy.set_column_filter(unmatched_cat_col, {"❌"})

        self._update_filter_count()

    def _update_filter_count(self):
        """Update the filter count label (from active tab)."""
        current = self.tabs.currentWidget()
        if not hasattr(current, '_proxy'):
            return
        total = current._model.rowCount()
        visible = current._proxy.rowCount()
        has_filter = (self.chk_profit_filter.isChecked()
                      or self.chk_unmatched.isChecked()
                      or self.chk_unmatched_category.isChecked()
                      or self.search_input.text().strip())
        if has_filter:
            self.lbl_filter_count.setText(f"筛选结果: {visible}/{total} 条")
        else:
            self.lbl_filter_count.setText("")

    def _clear_filters(self):
        """Clear all filters on all 4 tables."""
        self.chk_profit_filter.setChecked(False)
        self.chk_unmatched.setChecked(False)
        self.chk_unmatched_category.setChecked(False)
        self.search_input.clear()
        for tbl in self._all_tables():
            tbl._proxy.clear_all_filters()
        self.lbl_filter_count.setText("")

    def _find_column(self, table, col_key: str) -> int | None:
        """Find column index by key in a table's model."""
        for i, (key, _, _) in enumerate(table._model.COLUMNS):
            if key == col_key:
                return i
        return None

    def _find_first_column(self, table, col_keys: tuple[str, ...]) -> int | None:
        """Find the first matching column index from a list of candidate keys."""
        for key in col_keys:
            col = self._find_column(table, key)
            if col is not None:
                return col
        return None

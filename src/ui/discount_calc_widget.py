# -*- coding: utf-8 -*-
"""折扣推算页面 — 统一工作台布局与计算流程。"""

import os
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QMessageBox, QProgressBar,
    QTabWidget, QCheckBox, QLineEdit,
    QFrame, QFileDialog, QDoubleSpinBox,
)
from PySide6.QtCore import Signal, QTimer

from src.services.discount_calc_svc import DiscountCalcService
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

        # State attributes (replacing old inline controls)
        self._calc_mode = "profit_rate"
        self._target_value = 10.0
        self._default_commission = 30.0
        self._commission_category_source_val = "feishu"
        self._exchange_rate_mode = "realtime"
        self._calc_done = False
        self._drawer = None
        self._export_filter_mode = "profit_value"
        self._export_filter_threshold = 0.0
        self._export_filter_threshold_local = 0.0
        self._export_filter_mode_local = "profit_value"

        # Debounced search timer (300ms)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._do_search)

        self._build_ui()

    # ═══════════════════════════════════════════════════════════════
    #  UI Construction
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # ── Toolbar (48px) ──
        toolbar = QFrame()
        toolbar.setObjectName("calcToolbar")
        toolbar.setFixedHeight(48)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(12, 6, 12, 6)
        tl.setSpacing(6)

        self.btn_import = QPushButton("📥 导入Excel")
        self.btn_import.setProperty("class", "btn-primary")
        self.btn_import.setFixedHeight(32)
        self.btn_import.clicked.connect(self._on_select_file)
        tl.addWidget(self.btn_import)

        self.btn_match = QPushButton("🔗 执行匹配")
        self.btn_match.setProperty("class", "btn-primary")
        self.btn_match.setFixedHeight(32)
        self.btn_match.setEnabled(False)
        self.btn_match.clicked.connect(self._on_match)
        tl.addWidget(self.btn_match)

        self.btn_calc = QPushButton("📊 计算盈亏")
        self.btn_calc.setProperty("class", "btn-primary")
        self.btn_calc.setFixedHeight(32)
        self.btn_calc.setEnabled(False)
        self.btn_calc.clicked.connect(self._on_calculate)
        tl.addWidget(self.btn_calc)

        self.btn_export = QPushButton("📤 导出结果")
        self.btn_export.setProperty("class", "btn-success")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(lambda: self.export_requested.emit())
        tl.addWidget(self.btn_export)

        self.btn_run_all = QPushButton("⚡ 一键测算")
        self.btn_run_all.setProperty("class", "btn-accent")
        self.btn_run_all.setFixedHeight(32)
        self.btn_run_all.clicked.connect(self._on_run_all)
        tl.addWidget(self.btn_run_all)

        tl.addStretch()

        # Step status text
        self.lbl_step_status = QLabel(
            "导入: ○未执行 → 匹配: ○未执行 → 计算: ○未执行 → 导出: ○未执行"
        )
        self.lbl_step_status.setProperty("class", "stat-label")
        self.lbl_step_status.setStyleSheet("font-size: 11px;")
        tl.addWidget(self.lbl_step_status)

        # Settings gear button
        self.btn_settings = QPushButton("⚙ 设置")
        self.btn_settings.setProperty("class", "btn-outline")
        self.btn_settings.setFixedHeight(32)
        self.btn_settings.clicked.connect(self._on_open_settings)
        tl.addWidget(self.btn_settings)

        layout.addWidget(toolbar)

        # ── Info Bar (36px) ──
        info_bar = QFrame()
        info_bar.setObjectName("infoBar")
        info_bar.setFixedHeight(36)
        ib = QHBoxLayout(info_bar)
        ib.setContentsMargins(12, 4, 12, 4)
        ib.setSpacing(10)

        self.lbl_file = QLabel("未导入数据")
        self.lbl_file.setObjectName("fileSummary")
        ib.addWidget(self.lbl_file)

        ib.addStretch()

        self.lbl_match_status = QLabel("")
        self.lbl_match_status.setProperty("class", "stat-label")
        ib.addWidget(self.lbl_match_status)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setProperty("class", "stat-label")
        ib.addWidget(self.lbl_summary)

        self.btn_export_unmatched_sku = QPushButton("导出未匹配SKU")
        self.btn_export_unmatched_sku.setProperty("class", "btn-outline")
        self.btn_export_unmatched_sku.setMinimumWidth(110)
        self.btn_export_unmatched_sku.setFixedHeight(28)
        self.btn_export_unmatched_sku.setToolTip("导出SKU未匹配到的商品到Excel")
        self.btn_export_unmatched_sku.clicked.connect(self._on_export_unmatched_sku)
        ib.addWidget(self.btn_export_unmatched_sku)

        self.btn_export_unmatched_category = QPushButton("导出未匹配类目")
        self.btn_export_unmatched_category.setProperty("class", "btn-outline")
        self.btn_export_unmatched_category.setMinimumWidth(110)
        self.btn_export_unmatched_category.setFixedHeight(28)
        self.btn_export_unmatched_category.setToolTip("导出类目未匹配到的商品到Excel")
        self.btn_export_unmatched_category.clicked.connect(self._on_export_unmatched_category)
        ib.addWidget(self.btn_export_unmatched_category)

        layout.addWidget(info_bar)

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

        # Update filter count and re-apply search when switching tabs
        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tabs, stretch=1)

        # ── Settings Drawer (overlay) ──
        from src.ui.discount_settings_drawer import DiscountSettingsDrawer
        self._drawer = DiscountSettingsDrawer(parent=self)
        self._drawer.applied.connect(self._on_drawer_applied)
        self._drawer.saved_as_default.connect(self._on_drawer_saved)

        self._refresh_dashboard()

    # ═══════════════════════════════════════════════════════════════
    #  Settings Drawer
    # ═══════════════════════════════════════════════════════════════

    def _on_open_settings(self):
        """Open the settings drawer with current values."""
        if self._drawer is None:
            return
        self._load_drawer_commission_tables()
        self._drawer.set_values(
            shop_type=self._last_shop_type,
            commission_table=self._last_commission_table,
            default_commission=self._default_commission,
            category_source=self._commission_category_source_val,
            exchange_rate_mode=self._exchange_rate_mode,
            exchange_rate_value=self._last_exchange_rate,
            calc_mode=self._calc_mode,
            target_value=self._target_value,
            strategy=self._last_strategy,
            export_filter_mode=self._export_filter_mode,
            export_filter_threshold=self._export_filter_threshold,
        )
        self._drawer.open()

    def _on_drawer_applied(self):
        """User clicked Apply in drawer — sync values from drawer to internal state."""
        vals = self._drawer.get_values()
        self._last_shop_type = vals["shop_type"]
        self._last_commission_table = vals["commission_table"]
        self._default_commission = vals["default_commission"]
        self._commission_category_source_val = vals["category_source"]
        self._exchange_rate_mode = vals["exchange_rate_mode"]
        self._last_exchange_rate = vals["exchange_rate_value"]
        self._calc_mode = vals["calc_mode"]
        self._target_value = vals["target_value"]
        self._last_strategy = vals["strategy"]
        if "export_filter_mode" in vals:
            mode = vals["export_filter_mode"]
            self._export_filter_mode = mode
            self._export_filter_mode_local = mode  # Also update local
        if "export_filter_threshold" in vals:
            threshold = vals["export_filter_threshold"]
            self._export_filter_threshold = threshold
            self._export_filter_threshold_local = threshold  # Also update local
        # Update currency
        self._last_currency = "RUB" if self._last_shop_type == "wb_local" else "CNY"
        self._drawer.close()
        self._refresh_dashboard()

    def _on_drawer_saved(self):
        """User clicked Save Default in drawer — persist to database with feedback."""
        vals = self._drawer.get_values()
        try:
            if self._svc and hasattr(self._svc, 'db'):
                count = 0
                for key, value in vals.items():
                    if value is not None:
                        self._svc.db.save_config(f"drawer_{key}", str(value))
                        count += 1
                QMessageBox.information(self, "保存成功", f"✅ 已保存 {count} 项设置为默认值")
            else:
                QMessageBox.warning(self, "保存失败", "❌ 数据库连接不可用")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"❌ 无法保存设置：{e}")
        self._drawer.close()

    def refresh_theme(self, theme: str):
        """Notify drawer and tables of theme change."""
        if self._drawer is not None:
            self._drawer.refresh_theme(theme)
        # Refresh child table views
        for tbl in (self.raw_table, self.match_table, self.calc_table, self.result_table):
            if tbl is not None:
                tbl.refresh_theme()

    def _load_drawer_defaults(self):
        """Restore saved drawer defaults from app_config on startup."""
        if self._svc is None or not hasattr(self._svc, 'db'):
            return
        saved = self._svc.db.get_all_config()
        if not saved:
            return
        # Map drawer_* keys to state attributes
        key_map = {
            "drawer_shop_type": ("shop_type", str),
            "drawer_commission_table": ("commission_table", str),
            "drawer_default_commission": ("default_commission", float),
            "drawer_category_source": ("category_source", str),
            "drawer_exchange_rate_mode": ("exchange_rate_mode", str),
            "drawer_exchange_rate_value": ("exchange_rate_value", float),
            "drawer_calc_mode": ("calc_mode", str),
            "drawer_target_value": ("target_value", float),
            "drawer_strategy": ("strategy", str),
            "drawer_export_filter_mode": ("export_filter_mode_cross", str),
            "drawer_export_filter_threshold": ("export_filter_threshold_cross", float),
            "drawer_export_filter_mode_local": ("export_filter_mode_local", str),
            "drawer_export_filter_threshold_local": ("export_filter_threshold_local", float),
        }
        attr_map = {
            "shop_type": "_last_shop_type",
            "commission_table": "_last_commission_table",
            "default_commission": "_default_commission",
            "category_source": "_commission_category_source_val",
            "exchange_rate_mode": "_exchange_rate_mode",
            "exchange_rate_value": "_last_exchange_rate",
            "calc_mode": "_calc_mode",
            "target_value": "_target_value",
            "strategy": "_last_strategy",
            "export_filter_mode_cross": "_export_filter_mode",
            "export_filter_threshold_cross": "_export_filter_threshold",
            "export_filter_mode_local": "_export_filter_mode_local",
            "export_filter_threshold_local": "_export_filter_threshold_local",
        }
        for db_key, (name, converter) in key_map.items():
            raw = saved.get(db_key, "")
            if not raw:
                continue
            try:
                setattr(self, attr_map[name], converter(raw))
            except (ValueError, TypeError):
                pass  # Keep hardcoded default if conversion fails

    def _load_drawer_commission_tables(self):
        """Populate drawer's commission table dropdown from commission DB."""
        if self._drawer is None:
            return
        if self._commission_db is not None:
            tables = self._commission_db.get_commission_tables()
        else:
            tables = []
        items = []
        for t in tables:
            shop_label = "本土" if t.shop_type == "local" else "跨境"
            label = f"{t.platform.upper()} {shop_label} · {t.row_count:,} 条"
            items.append((label, t.table_name))
        self._drawer.load_commission_tables(items)

    # ═══════════════════════════════════════════════════════════════
    #  Dashboard / Status
    # ═══════════════════════════════════════════════════════════════

    def _refresh_dashboard(self):
        """Update the step status bar text and button states."""
        parts = []

        # Step 1: Import
        if self._file_path and self._svc:
            actual_count = self._svc.db.get_import_row_count()
            parts.append(
                f"导入: ✅ {actual_count}行" if actual_count > 0
                else "导入: ✅ 已选文件"
            )
            self.btn_match.setEnabled(True)
        else:
            parts.append("导入: ○未执行")
            self.btn_match.setEnabled(False)
            self.btn_calc.setEnabled(False)
            self.btn_export.setEnabled(False)

        # Step 2: Match
        if self._is_matched:
            parts.append(f"匹配: ✅ {self._match_count}条")
            self.btn_calc.setEnabled(True)
        else:
            parts.append("匹配: ○未执行")

        # Step 3: Calculate
        if self.has_calc_done():
            parts.append("计算: ✅ 已完成")
            self.btn_export.setEnabled(True)
        else:
            parts.append("计算: ○未执行")

        # Step 4: Export
        if self.has_calc_done():
            parts.append("导出: ○待导出")
        else:
            parts.append("导出: ○未执行")

        self.lbl_step_status.setText(" → ".join(parts))

    # ═══════════════════════════════════════════════════════════════
    #  File Selection & Import
    # ═══════════════════════════════════════════════════════════════

    def _on_select_file(self):
        """选择 Excel 文件并交给后台线程导入。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Excel 模板",
            "",
            "Excel文件 (*.xlsx *.xls);;所有文件 (*)",
        )
        if not file_path:
            return
        self._pending_file_path = file_path
        self._last_commission_table = self._last_commission_table or "commission_wb_cross_border"
        self._last_currency = "RUB" if self._last_shop_type == "wb_local" else "CNY"
        self.btn_import.setEnabled(False)
        self.btn_match.setEnabled(False)
        self.btn_calc.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_run_all.setEnabled(False)
        self.lbl_file.setText(f"{os.path.basename(file_path)} · 正在导入...")
        self.lbl_match_status.setText("导入中...")
        self._refresh_dashboard()
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
        self.btn_import.setEnabled(True)
        self.btn_match.setEnabled(True)
        self.btn_calc.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_run_all.setEnabled(True)
        self.lbl_match_status.setText("")
        self.progress.setVisible(False)
        self._load_raw_data()
        self._refresh_dashboard()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        self.import_done.emit()
        self.tabs.setCurrentIndex(0)

    def set_import_error(self, err: str):
        """Called by MainWindow if async import fails."""
        self._file_path = None
        self._pending_file_path = None
        self.btn_import.setEnabled(True)
        self.btn_match.setEnabled(False)
        self.btn_calc.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_run_all.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_file.setText("未导入数据")
        self.lbl_match_status.setText("")
        self._refresh_dashboard()
        QMessageBox.warning(self, "导入失败", f"无法导入Excel文件:\n{err}")

    # ═══════════════════════════════════════════════════════════════
    #  Match / Calculate / Run-All
    # ═══════════════════════════════════════════════════════════════

    def _on_match(self):
        """Start matching process using state-stored settings."""
        if not self._file_path:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return

        # Use state attributes (set via drawer or defaults)
        self._last_exchange_rate = self.get_exchange_rate()
        self.btn_match.setEnabled(False)
        self.btn_calc.setEnabled(False)
        self.lbl_match_status.setText("匹配中...")
        self._refresh_dashboard()
        self.progress.setVisible(True)
        self.progress.setRange(0, 1)  # Will be updated by progress signal
        self.progress.setValue(0)

        # Emit signal for MainWindow to handle
        self.calculate_requested.emit()

    def _on_calculate(self):
        """Start calculation using matched results and state-stored strategy."""
        if not self._is_matched:
            QMessageBox.information(self, "提示", "请先进行匹配计算")
            return

        self.btn_calc.setEnabled(False)
        self.progress.setVisible(True)
        self._refresh_dashboard()

        self.calculate_requested.emit()

    def _on_run_all(self):
        """One-click full workflow: match → auto-calculate.
        
        Bug fixes:
        - btn_run_all disabled during operation
        - Already-matched forces re-match to pick up changed params
        - Zero-match case resets _pending_auto_calculate properly
        """
        if not self._file_path:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return
        self.btn_run_all.setEnabled(False)
        self._pending_auto_calculate = True
        self._is_matched = False  # Force re-match with current params
        self._on_match()

    # ═══════════════════════════════════════════════════════════════
    #  External interface (called by MainWindow)
    # ═══════════════════════════════════════════════════════════════

    def set_service(self, svc: DiscountCalcService, commission_db=None):
        """Set service with all DB connections"""
        self._svc = svc
        self._commission_db = commission_db
        # Restore saved category source
        if self._svc and hasattr(self._svc, 'db'):
            saved = self._svc.db.get_config('commission_category_source')
            if saved:
                self._commission_category_source_val = saved
        self._load_drawer_defaults()

    def get_file_path(self):
        return self._file_path

    def get_strategy(self):
        return self._last_strategy

    def get_commission_table(self):
        tbl = self._last_commission_table
        if tbl is None or tbl == "None":
            return "commission_wb_cross_border"
        return tbl

    def get_export_filter_mode(self) -> str:
        if self._last_shop_type == "wb_local":
            return self._export_filter_mode_local
        return self._export_filter_mode

    def get_export_filter_threshold(self) -> float:
        if self._last_shop_type == "wb_local":
            return self._export_filter_threshold_local
        return self._export_filter_threshold

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

    # ── Getters for worker params (called by MainWindow) ──

    def get_default_commission(self) -> float:
        """获取用户设置的未匹配类目默认佣金率"""
        return self._default_commission

    def get_commission_category_source(self) -> str:
        """返回佣金类目来源: 'feishu' 或 'excel'"""
        return self._commission_category_source_val

    def set_commission_category_source(self, source: str):
        """设置佣金类目来源"""
        self._commission_category_source_val = source

    def get_exchange_rate(self) -> float:
        """Returns the exchange rate to use (CNY→RUB)"""
        if self._exchange_rate_mode == "manual":
            return self._last_exchange_rate
        from src.services.exchange_rate import ExchangeRateService
        rate = ExchangeRateService().get_cny_to_rub()
        return rate if rate > 0 else 12.0

    def set_match_result(self, count: int):
        """Called by MainWindow after match completes.
        
        Bug 1 fix: _pending_auto_calculate always reset, even on zero-match.
        Bug 2 fix: btn_run_all re-enabled.
        """
        self._is_matched = count > 0
        self._match_count = count
        self.btn_match.setEnabled(True)
        self.btn_calc.setEnabled(count > 0)
        self.btn_run_all.setEnabled(True)
        self.lbl_match_status.setText(f"已匹配 {count} 条" if count > 0 else "无匹配结果")
        self.progress.setVisible(False)
        self._refresh_dashboard()
        # Auto-chain calculate if _pending_auto_calculate flag is set
        if self._pending_auto_calculate:
            self._pending_auto_calculate = False
            if count > 0:
                self._on_calculate()

    def set_calc_result(self, count: int):
        """Called by MainWindow after calculation completes.
        
        Bug 2 fix: btn_run_all re-enabled.
        """
        self.btn_calc.setEnabled(True)
        self.btn_run_all.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_file.setText(f"已计算 {count} 条结果")
        self._calc_done = True
        self._refresh_dashboard()

    # ── State queries ──

    def is_matched(self) -> bool:
        return self._is_matched

    def has_calc_done(self) -> bool:
        """是否已完成过计算（参数修改后可直接重算）"""
        return getattr(self, '_calc_done', False)

    def get_match_count(self) -> int:
        return self._match_count

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

    # ── Calc mode ──

    def get_calc_mode(self) -> str:
        """Return current calc mode: 'profit_rate' or 'fixed_profit'"""
        return self._calc_mode

    def get_target_profit_amount(self) -> float:
        """Return the stored target profit value"""
        return self._target_value

    # ═══════════════════════════════════════════════════════════════
    #  筛选功能
    # ═══════════════════════════════════════════════════════════════

    def _all_tables(self):
        """Return all 4 table views."""
        return [self.raw_table, self.match_table, self.calc_table, self.result_table]

    def _on_search_changed(self, text: str):
        """Debounced search — restarts timer; actual search in _do_search."""
        self._search_timer.start()

    def _do_search(self):
        """Apply search text to currently visible tab only."""
        text = self.search_input.text().strip()
        current_tab = self.tabs.currentWidget()
        if hasattr(current_tab, '_proxy'):
            current_tab._proxy.set_search_text(text)
        self._update_filter_count()

    def _on_tab_changed(self, index):
        """When user switches tab, apply existing search to the new tab."""
        text = self.search_input.text().strip()
        if text:
            self._do_search()
        else:
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

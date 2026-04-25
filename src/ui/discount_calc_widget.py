# -*- coding: utf-8 -*-
"""折扣推算页面 — 文件导入 + 计算结果（设置通过导入对话框配置）"""

import os
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QMessageBox, QProgressBar,
    QTabWidget, QDialog, QRadioButton, QButtonGroup,
    QDoubleSpinBox, QApplication, QCheckBox, QLineEdit
)
from PySide6.QtCore import Signal, QThread

from src.config import Config
from src.models.database import DatabaseManager
from src.services.discount_calc_svc import DiscountCalcService
from src.ui.result_table import ResultTable
from src.ui.match_data_table import MatchDataTable
from src.ui.calc_data_table import CalcDataTable
from src.ui.import_settings_dialog import ImportSettingsDialog
from src.ui.calc_settings_dialog import CalcSettingsDialog
from src.ui.raw_table import RawTable

logger = logging.getLogger(__name__)


class CalcWorker(QThread):
    """后台计算线程"""
    progress = Signal(int, int)
    finished = Signal(int)  # result count
    error = Signal(str)

    def __init__(self, svc, params_dict, commission_table, strategy, exchange_rate):
        super().__init__()
        self.svc = svc
        self.params_dict = params_dict
        self.commission_table = commission_table
        self.strategy = strategy
        self.exchange_rate = exchange_rate

    def run(self):
        try:
            count = self.svc.calculate(
                self.params_dict, self.commission_table, self.strategy,
                exchange_rate=self.exchange_rate)
            if not self.isInterruptionRequested():
                self.finished.emit(count)
        except Exception as e:
            if not self.isInterruptionRequested():
                logger.exception("CalcWorker error")
                self.error.emit(str(e))


class DiscountCalcWidget(QWidget):
    """折扣推算页: 操作栏 + 结果表"""

    calculate_requested = Signal()
    import_done = Signal()
    export_requested = Signal()

    STRATEGY_DISCOUNT_ONLY = "discount_only"
    STRATEGY_PRICE_ONLY = "price_only"
    STRATEGY_BOTH = "both"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._worker = None
        self._last_commission_table = None
        self._last_strategy = "discount_only"
        self._last_exchange_rate = 12.0
        self._last_shop_type = "wb_cross_border"
        self._is_matched = False
        self._match_count = 0
        self._db = DatabaseManager(Config.DB_DISCOUNT_CALC_PATH,
                                   init_tables=["import_rows", "calc_results", "app_config"])
        self._svc = DiscountCalcService(db=self._db)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── 操作栏 ──
        op_card = QGroupBox("操作面板")
        op_layout = QVBoxLayout(op_card)
        op_layout.setSpacing(10)

        # 第一行: 文件选择
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.btn_select = QPushButton("导入 Excel")
        self.btn_select.setProperty("class", "btn-primary")
        self.btn_select.setFixedHeight(36)
        self.btn_select.clicked.connect(self._on_select_file)
        file_row.addWidget(self.btn_select)

        self.lbl_file = QLabel("未导入数据")
        self.lbl_file.setProperty("class", "stat-label")
        file_row.addWidget(self.lbl_file)

        self.lbl_currency = QLabel("")
        self.lbl_currency.setProperty("class", "stat-label")
        file_row.addWidget(self.lbl_currency)
        file_row.addStretch()
        op_layout.addLayout(file_row)

        # 第二行: 匹配计算 + 开始计算 + 导出按钮
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.btn_match = QPushButton("匹配计算")
        self.btn_match.setProperty("class", "btn-primary")
        self.btn_match.setFixedHeight(36)
        self.btn_match.setToolTip("匹配SKU + 佣金 + 计算运费")
        self.btn_match.clicked.connect(self._on_match)
        action_row.addWidget(self.btn_match)

        self.btn_calculate = QPushButton("开始计算")
        self.btn_calculate.setProperty("class", "btn-primary")
        self.btn_calculate.setFixedHeight(36)
        self.btn_calculate.setEnabled(False)  # Disabled until match is done
        self.btn_calculate.setToolTip("计算盈亏、折扣推算")
        self.btn_calculate.clicked.connect(self._on_calculate)
        action_row.addWidget(self.btn_calculate)

        self.btn_export = QPushButton("导出结果")
        self.btn_export.setProperty("class", "btn-success")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setMinimumWidth(140)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(lambda: self.export_requested.emit())
        action_row.addWidget(self.btn_export)

        self.lbl_match_status = QLabel("未匹配")
        self.lbl_match_status.setProperty("class", "stat-label")
        action_row.addWidget(self.lbl_match_status)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setProperty("class", "stat-label")
        action_row.addWidget(self.lbl_summary)
        # 汇率选择
        self.rb_rate_realtime = QRadioButton("实时汇率")
        self.rb_rate_specified = QRadioButton("指定")
        grp_rate = QButtonGroup(self)
        grp_rate.addButton(self.rb_rate_realtime)
        grp_rate.addButton(self.rb_rate_specified)
        self.rb_rate_realtime.setChecked(True)
        
        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.01, 100.0)
        self.spin_rate.setDecimals(4)
        self.spin_rate.setValue(12.0)
        self.spin_rate.setFixedWidth(90)
        self.spin_rate.setEnabled(False)
        self.rb_rate_specified.toggled.connect(self.spin_rate.setEnabled)
        
        action_row.addWidget(self.rb_rate_realtime)
        action_row.addWidget(self.rb_rate_specified)
        action_row.addWidget(self.spin_rate)
        action_row.addStretch()
        op_layout.addLayout(action_row)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        op_layout.addWidget(self.progress)

        layout.addWidget(op_card)

        # ── 筛选栏 ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索...")
        self.search_input.setMinimumWidth(160)
        self.search_input.setMaximumWidth(200)
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

        self.btn_apply_filter = QPushButton("确定筛选")
        self.btn_apply_filter.setProperty("class", "btn-primary")
        self.btn_apply_filter.setMinimumWidth(72)
        filter_row.addWidget(self.btn_apply_filter)

        self.btn_clear_filter = QPushButton("清除筛选")
        self.btn_clear_filter.setProperty("class", "btn-outline")
        self.btn_clear_filter.setMinimumWidth(72)
        filter_row.addWidget(self.btn_clear_filter)

        self.lbl_filter_count = QLabel("")
        self.lbl_filter_count.setProperty("class", "stat-label")
        filter_row.addWidget(self.lbl_filter_count)
        filter_row.addStretch()

        layout.addLayout(filter_row)

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

    def _on_select_file(self):
        """打开导入设置对话框"""
        dlg = ImportSettingsDialog(self)
        # Pre-select previous commission table if available
        if self._last_commission_table:
            for i in range(dlg.combo_commission.count()):
                if dlg.combo_commission.itemData(i) == self._last_commission_table:
                    dlg.combo_commission.setCurrentIndex(i)
                    break
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        file_path = dlg.get_file_path()
        if not file_path:
            return
        try:
            self._file_path = file_path
            self._last_commission_table = dlg.get_commission_table()

            # Detect currency from commission table name
            currency = self._detect_currency(self._last_commission_table)
            self._last_currency = currency
            self.lbl_currency.setText(f"计算币种: {currency}")

            count = self._svc.import_from_excel(file_path)
            QApplication.processEvents()
            self.lbl_file.setText(f"{os.path.basename(file_path)}  ({count} 行已导入)")
            self.lbl_file.setProperty("class", "stat-profit")
            self._is_matched = False
            self._match_count = 0
            self._calc_done = False
            self.btn_match.setEnabled(True)
            self.btn_calculate.setEnabled(False)
            self.lbl_match_status.setText("")
            self.progress.setVisible(False)
            self._load_raw_data()
            QApplication.processEvents()
            self.import_done.emit()
            self.tabs.setCurrentIndex(0)  # Switch to raw data tab
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法导入Excel文件:\n{e}")

    def _on_match(self):
        """Start matching process."""
        if not self._file_path:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return

        from src.ui.match_settings_dialog import MatchSettingsDialog
        dlg = MatchSettingsDialog(self, last_shop_type=self._last_shop_type)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._last_shop_type = dlg.get_shop_type()
        self._last_commission_table = dlg.get_commission_table()
        self._last_exchange_rate = self.get_exchange_rate()
        self.btn_match.setEnabled(False)
        self.btn_calculate.setEnabled(False)
        self.lbl_match_status.setText("匹配中...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 1)  # Will be updated by progress signal
        self.progress.setValue(0)

        # Emit signal for MainWindow to handle
        self.calculate_requested.emit()

    def _on_calculate(self):
        """Start calculation using matched results."""
        if not self._is_matched:
            QMessageBox.information(self, "提示", "请先进行匹配计算")
            return

        dlg = CalcSettingsDialog(
            self,
            last_strategy=self._last_strategy,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._last_strategy = dlg.get_strategy()
        self.btn_calculate.setEnabled(False)
        self.progress.setVisible(True)

        self.calculate_requested.emit()

    # ── External interface ──

    def set_service(self, svc: DiscountCalcService):
        """Set service with all DB connections"""
        self._svc = svc

    def get_file_path(self):
        return self._file_path

    def get_strategy(self):
        return self._last_strategy

    def get_commission_table(self):
        return self._last_commission_table or "commission_wb_cross_border"

    def set_export_enabled(self, enabled: bool):
        self.btn_export.setEnabled(enabled)

    def update_summary(self, summary: dict):
        self.lbl_summary.setText(
            f"盈利: {summary.get('profit', 0)}  |  亏损: {summary.get('loss', 0)}  |  "
            f"未匹配: {summary.get('unmatched', 0)}  |  总计: {summary.get('total', 0)}"
        )

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

    def set_calc_result(self, count: int):
        """Called by MainWindow after calculation completes."""
        self.btn_calculate.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_file.setText(f"已计算 {count} 条结果")
        self._calc_done = True  # 标记已完成过计算，参数修改后可重算

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

    # ── 筛选功能 ──

    def _all_tables(self):
        """Return all 4 table views."""
        return [self.raw_table, self.match_table, self.calc_table, self.result_table]

    def _on_search_changed(self, text: str):
        """Live search — applied to all 4 tables."""
        for tbl in self._all_tables():
            tbl._proxy.set_search_text(text)
        self._update_filter_count()

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
                cost_col = self._find_column(tbl, "cost_matched")
                if cost_col is not None:
                    proxy.set_column_filter(cost_col, {"❌"})

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
                      or self.search_input.text().strip())
        if has_filter:
            self.lbl_filter_count.setText(f"筛选结果: {visible}/{total} 条")
        else:
            self.lbl_filter_count.setText("")

    def _clear_filters(self):
        """Clear all filters on all 4 tables."""
        self.chk_profit_filter.setChecked(False)
        self.chk_unmatched.setChecked(False)
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

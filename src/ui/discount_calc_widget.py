# -*- coding: utf-8 -*-
"""折扣推算页面 — 文件导入 + 计算结果（设置通过导入对话框配置）"""

import os
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QMessageBox, QProgressBar,
    QTabWidget, QTableWidget, QTableWidgetItem,
    QMenu, QDialog, QHeaderView
)
from PySide6.QtCore import Qt, Signal, QThread

from src.config import Config
from src.models.database import DatabaseManager
from src.services.discount_calc_svc import DiscountCalcService
from src.ui.result_table import ResultTable
from src.ui.match_data_table import MatchDataTable
from src.ui.calc_data_table import CalcDataTable
from src.ui.import_settings_dialog import ImportSettingsDialog
from src.ui.calc_settings_dialog import CalcSettingsDialog

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
        self._last_rate_realtime = True  # track rate mode for dialog restore
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
        action_row.addStretch()
        op_layout.addLayout(action_row)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        op_layout.addWidget(self.progress)

        layout.addWidget(op_card)

        # ── Tab Widget: 4-tab layout ──
        self.tabs = QTabWidget()
        self.tabs.setObjectName("discountTabs")

        # Tab 1: 原始数据
        self.raw_table = QTableWidget()
        self.raw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.raw_table.setAlternatingRowColors(True)
        self.raw_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.raw_table.verticalHeader().setVisible(False)
        self.raw_table.setShowGrid(True)

        # Raw table filter/sort state
        self._raw_sort_col = -1
        self._raw_sort_order = Qt.SortOrder.AscendingOrder
        self._raw_col_filters = {}  # col_idx → set(allowed_values)
        self._raw_data_rows = []    # store raw data for filtering

        # Header setup
        raw_header = self.raw_table.horizontalHeader()
        raw_header.setSectionsClickable(True)
        raw_header.setSortIndicatorShown(True)
        raw_header.sectionClicked.connect(self._on_raw_header_clicked)
        raw_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        raw_header.customContextMenuRequested.connect(self._on_raw_header_context_menu)

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
            self.lbl_file.setText(f"{os.path.basename(file_path)}  ({count} 行已导入)")
            self.lbl_file.setProperty("class", "stat-profit")
            self._load_raw_data()
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
        self.btn_match.setEnabled(False)
        self.btn_calculate.setEnabled(False)
        self.lbl_match_status.setText("匹配中...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # Indeterminate

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
            last_rate=self._last_exchange_rate,
            last_rate_realtime=self._last_rate_realtime,
            commission_table=self._last_commission_table,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._last_strategy = dlg.get_strategy()
        self._last_exchange_rate = dlg.get_exchange_rate()
        self._last_rate_realtime = dlg.is_rate_realtime()
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
            self._raw_data_rows = []
            self.raw_table.setRowCount(0)
            return

        # col_indices maps to: row_number, brand, category, wb_article, seller_sku, barcode,
        #                       wb_stock, seller_stock, turnover, current_price, current_discount,
        #                       new_price, new_discount
        col_indices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 11, 13]
        self._raw_data_rows = []
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
            self._raw_data_rows.append(extracted)
        self._populate_raw_table()

    def _populate_raw_table(self):
        """Populate raw_table with filtered/sorted data"""
        if not self._raw_data_rows:
            self.raw_table.setRowCount(0)
            return
        data = list(self._raw_data_rows)
        # Column filters
        for col_idx, allowed_values in self._raw_col_filters.items():
            if not allowed_values:
                continue
            data = [row for row in data
                    if str(row[col_idx] if col_idx < len(row) else "").strip() in allowed_values]
        # Sort
        if 0 <= self._raw_sort_col:
            col = self._raw_sort_col
            reverse = self._raw_sort_order == Qt.SortOrder.DescendingOrder
            def sort_key(row):
                val = row[col] if col < len(row) else ""
                try:
                    return (0, float(val))
                except (ValueError, TypeError):
                    return (1, str(val))
            data.sort(key=sort_key, reverse=reverse)
        # Populate
        headers = ["行号", "品牌", "类目", "WB货号", "卖家货号", "条码",
                   "WB库存", "卖家库存", "周转率", "当前价格", "当前折扣", "折后价格",
                   "新价格", "新折扣"]
        self.raw_table.setRowCount(len(data))
        self.raw_table.setColumnCount(len(headers))
        self.raw_table.setHorizontalHeaderLabels(headers)
        for i, row in enumerate(data):
            for j in range(len(headers)):
                val = row[j] if j < len(row) else ""
                text = str(val) if val is not None else ""
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.raw_table.setItem(i, j, item)
        raw_header = self.raw_table.horizontalHeader()
        raw_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        raw_header.setStretchLastSection(True)

    def _on_raw_header_clicked(self, col_idx):
        if col_idx == 0:
            return
        if self._raw_sort_col == col_idx:
            if self._raw_sort_order == Qt.SortOrder.AscendingOrder:
                self._raw_sort_order = Qt.SortOrder.DescendingOrder
            else:
                self._raw_sort_col = -1
                self._raw_sort_order = Qt.SortOrder.AscendingOrder
        else:
            self._raw_sort_col = col_idx
            self._raw_sort_order = Qt.SortOrder.AscendingOrder
        if self._raw_sort_col >= 0:
            self.raw_table.horizontalHeader().setSortIndicator(self._raw_sort_col, self._raw_sort_order)
        self._populate_raw_table()

    def _on_raw_header_context_menu(self, pos):
        col_idx = self.raw_table.horizontalHeader().logicalIndexAt(pos)
        if col_idx < 0:
            return
        global_pos = self.raw_table.horizontalHeader().mapToGlobal(pos)
        self._show_raw_filter_menu(col_idx, global_pos)

    def _show_raw_filter_menu(self, col_idx, global_pos):
        if not self._raw_data_rows or col_idx >= len(self._raw_data_rows[0]):
            return
        headers_count = self.raw_table.columnCount()
        if col_idx >= headers_count:
            return
        from PySide6.QtGui import QAction, QActionGroup
        header_name = self.raw_table.horizontalHeaderItem(col_idx)
        header_text = header_name.text() if header_name else f"列{col_idx}"
        unique_values = sorted(set(
            str(row[col_idx] if col_idx < len(row) else "").strip()
            for row in self._raw_data_rows
        ))
        if not unique_values:
            return
        menu = QMenu(self)
        menu.setWindowTitle(f"筛选: {header_text}")
        select_all_action = QAction("全选", self)
        clear_action = QAction("清除筛选", self)
        menu.addAction(select_all_action)
        menu.addAction(clear_action)
        menu.addSeparator()
        current_allowed = self._raw_col_filters.get(col_idx)
        group = QActionGroup(self)
        group.setExclusive(False)
        val_actions = {}
        for val in unique_values:
            display = val if val else "(空)"
            action = QAction(display, self)
            action.setCheckable(True)
            if current_allowed is None:
                action.setChecked(True)
            else:
                action.setChecked(val in current_allowed)
            menu.addAction(action)
            group.addAction(action)
            val_actions[action] = val
        menu.addSeparator()
        apply_action = QAction("✓ 应用筛选", self)
        menu.addAction(apply_action)
        chosen = menu.exec(global_pos)
        if chosen == apply_action:
            checked_values = set(v for a, v in val_actions.items() if a.isChecked())
            if len(checked_values) == len(unique_values) or not checked_values:
                self._raw_col_filters.pop(col_idx, None)
            else:
                self._raw_col_filters[col_idx] = checked_values
            self._populate_raw_table()
        elif chosen in (select_all_action, clear_action):
            self._raw_col_filters.pop(col_idx, None)
            self._populate_raw_table()

    def get_exchange_rate(self) -> float:
        """Returns the exchange rate to use (CNY→RUB)"""
        return self._last_exchange_rate

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

    def is_matched(self) -> bool:
        return self._is_matched

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

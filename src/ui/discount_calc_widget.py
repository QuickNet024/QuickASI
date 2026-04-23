# -*- coding: utf-8 -*-
"""折扣推算页面 — 策略/模式选择 + 文件上传 + 计算结果表 + 导出"""

import os
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QRadioButton, QButtonGroup,
    QGroupBox, QMessageBox, QSplitter, QFrame
)
from PySide6.QtCore import Qt, Signal

from src.ui.result_table import ResultTable

logger = logging.getLogger(__name__)


class DiscountCalcWidget(QWidget):
    """折扣推算页: 上方操作栏 + 下方结果表"""

    calculate_requested = Signal(str, str, str)   # file_path, strategy, mode
    export_requested = Signal()

    STRATEGY_DISCOUNT_ONLY = "discount_only"
    STRATEGY_PRICE_ONLY = "price_only"
    STRATEGY_BOTH = "both"
    MODE_CROSS_BORDER = "cross_border"
    MODE_LOCAL = "local"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._rows = []
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
        self.btn_select = QPushButton("选择 Excel 文件")
        self.btn_select.setProperty("class", "btn-primary")
        self.btn_select.setFixedHeight(36)
        self.btn_select.clicked.connect(self._on_select_file)
        file_row.addWidget(self.btn_select)

        self.lbl_file = QLabel("未选择文件")
        self.lbl_file.setProperty("class", "stat-label")
        file_row.addWidget(self.lbl_file)
        file_row.addStretch()
        op_layout.addLayout(file_row)

        # 第二行: 策略 + 模式
        strategy_row = QHBoxLayout()
        strategy_row.setSpacing(12)

        strategy_row.addWidget(QLabel("策略:"))
        self.rb_discount = QRadioButton("仅折扣")
        self.rb_price = QRadioButton("仅调价")
        self.rb_both = QRadioButton("折扣+调价")
        self.rb_both.setChecked(True)
        grp_s = QButtonGroup(self)
        for rb in (self.rb_discount, self.rb_price, self.rb_both):
            grp_s.addButton(rb)
            strategy_row.addWidget(rb)

        strategy_row.addSpacing(20)

        strategy_row.addWidget(QLabel("模式:"))
        self.rb_cross = QRadioButton("跨境(CNY)")
        self.rb_local = QRadioButton("本土(RUB)")
        self.rb_cross.setChecked(True)
        grp_m = QButtonGroup(self)
        for rb in (self.rb_cross, self.rb_local):
            grp_m.addButton(rb)
            strategy_row.addWidget(rb)

        strategy_row.addStretch()
        op_layout.addLayout(strategy_row)

        # 第三行: 计算按钮 + 导出按钮
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.btn_calc = QPushButton("开始计算")
        self.btn_calc.setProperty("class", "btn-primary")
        self.btn_calc.setMinimumHeight(40)
        self.btn_calc.setMinimumWidth(140)
        self.btn_calc.clicked.connect(self._on_calculate)
        action_row.addWidget(self.btn_calc)

        self.btn_export = QPushButton("导出结果")
        self.btn_export.setProperty("class", "btn-success")
        self.btn_export.setMinimumHeight(40)
        self.btn_export.setMinimumWidth(140)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(lambda: self.export_requested.emit())
        action_row.addWidget(self.btn_export)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setProperty("class", "stat-label")
        action_row.addWidget(self.lbl_summary)
        action_row.addStretch()
        op_layout.addLayout(action_row)

        layout.addWidget(op_card)

        # ── 结果表格 ──
        self.result_table = ResultTable()
        self.result_table.setObjectName("resultTable")
        self.result_table.cellClicked.connect(self._on_row_clicked)
        layout.addWidget(self.result_table, stretch=1)

    # ── 文件选择 ──

    def _on_select_file(self):
        from src.services.excel_service import ExcelService
        path, _ = QFileDialog.getOpenFileName(
            self, "选择Excel模板", "",
            "Excel文件 (*.xlsx *.xls);;所有文件 (*)"
        )
        if not path:
            return
        try:
            svc = ExcelService()
            self._rows = svc.read_template(path)
            self._file_path = path
            name = os.path.basename(path)
            self.lbl_file.setText(f"{name}  ({len(self._rows)} 行)")
            self.lbl_file.setStyleSheet("color: #1E8E3E; font-size: 12px;")
        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"无法读取Excel文件:\n{e}")

    def _on_calculate(self):
        if not self._file_path:
            QMessageBox.warning(self, "提示", "请先选择Excel文件")
            return
        strategy = self.STRATEGY_BOTH
        if self.rb_discount.isChecked():
            strategy = self.STRATEGY_DISCOUNT_ONLY
        elif self.rb_price.isChecked():
            strategy = self.STRATEGY_PRICE_ONLY
        mode = self.MODE_CROSS_BORDER if self.rb_cross.isChecked() else self.MODE_LOCAL
        self.calculate_requested.emit(self._file_path, strategy, mode)

    def _on_row_clicked(self, row: int, col: int):
        # 由 MainWindow 接管处理
        pass

    # ── 外部接口 ──

    def get_file_path(self):
        return self._file_path

    def get_rows(self):
        return self._rows

    def set_rows(self, rows):
        self._rows = rows

    def set_export_enabled(self, enabled: bool):
        self.btn_export.setEnabled(enabled)

    def get_strategy(self):
        if self.rb_discount.isChecked():
            return self.STRATEGY_DISCOUNT_ONLY
        elif self.rb_price.isChecked():
            return self.STRATEGY_PRICE_ONLY
        return self.STRATEGY_BOTH

    def get_mode(self):
        return self.MODE_CROSS_BORDER if self.rb_cross.isChecked() else self.MODE_LOCAL

    def update_summary(self, profit, loss, unmatched, total):
        self.lbl_summary.setText(
            f"盈利: {profit}  |  亏损: {loss}  |  未匹配: {unmatched}  |  总计: {total}"
        )

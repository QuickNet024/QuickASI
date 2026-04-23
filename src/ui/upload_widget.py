# -*- coding: utf-8 -*-
"""Excel上传面板 - 文件选择 + 策略选择 + 计算触发"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QFileDialog, QRadioButton, QButtonGroup, QMessageBox
)
from PySide6.QtCore import Signal

from src.services.excel_service import ExcelService, ProductRow


class UploadWidget(QWidget):
    """Excel上传操作栏"""

    calculate_requested = Signal(str, str, str)  # file_path, strategy, mode
    export_requested = Signal()                    # export trigger

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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        # 文件选择
        self.btn_select = QPushButton("📁 选择Excel")
        self.btn_select.setFixedHeight(32)
        self.btn_select.clicked.connect(self._on_select_file)
        layout.addWidget(self.btn_select)

        self.lbl_file = QLabel("未选择文件")
        self.lbl_file.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(self.lbl_file)

        layout.addStretch()

        # 策略选择
        layout.addWidget(QLabel("策略:"))
        self.rb_discount = QRadioButton("只调折扣")
        self.rb_price = QRadioButton("只调价")
        self.rb_both = QRadioButton("两者结合")
        self.rb_both.setChecked(True)

        self._strategy_group = QButtonGroup(self)
        self._strategy_group.addButton(self.rb_discount)
        self._strategy_group.addButton(self.rb_price)
        self._strategy_group.addButton(self.rb_both)
        layout.addWidget(self.rb_discount)
        layout.addWidget(self.rb_price)
        layout.addWidget(self.rb_both)

        # 模式选择
        layout.addWidget(QLabel("模式:"))
        self.rb_cross = QRadioButton("跨境CNY")
        self.rb_local = QRadioButton("本土RUB")
        self.rb_cross.setChecked(True)

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.rb_cross)
        self._mode_group.addButton(self.rb_local)
        layout.addWidget(self.rb_cross)
        layout.addWidget(self.rb_local)

        layout.addStretch()

        # 计算按钮
        self.btn_calc = QPushButton("▶ 开始计算")
        self.btn_calc.setFixedHeight(32)
        self.btn_calc.setStyleSheet(
            "QPushButton { background: #1890ff; color: white; font-weight: bold; border-radius: 4px; padding: 0 16px; }"
            "QPushButton:hover { background: #40a9ff; }"
            "QPushButton:disabled { background: #d9d9d9; color: #999; }"
        )
        self.btn_calc.clicked.connect(self._on_calculate)
        layout.addWidget(self.btn_calc)

        # 导出按钮
        self.btn_export = QPushButton("📤 导出结果")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet(
            "QPushButton { background: #52c41a; color: white; font-weight: bold; border-radius: 4px; padding: 0 16px; }"
            "QPushButton:hover { background: #73d13d; }"
            "QPushButton:disabled { background: #d9d9d9; color: #999; }"
        )
        self.btn_export.clicked.connect(self._on_export)
        layout.addWidget(self.btn_export)

    def _on_select_file(self):
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
            name = path.split("/")[-1].split("\\")[-1]
            self.lbl_file.setText(f"{name} ({len(self._rows)} 行)")
            self.lbl_file.setStyleSheet("color: #333; font-size: 12px;")
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

    def _on_export(self):
        self.export_requested.emit()

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

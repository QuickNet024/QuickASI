# -*- coding: utf-8 -*-
"""导入设置对话框 — 选择文件 + 佣金表"""

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QGroupBox, QComboBox,
    QDialogButtonBox, QMessageBox
)
from PySide6.QtCore import Qt

from src.config import Config
from src.models.database import DatabaseManager


class ImportSettingsDialog(QDialog):
    """导入Excel前设置文件和佣金表"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入设置")
        self.setMinimumWidth(520)
        self._file_path = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # ── 1. 文件选择 ──
        file_group = QGroupBox("Excel文件")
        file_layout = QHBoxLayout(file_group)
        self.btn_file = QPushButton("选择文件")
        self.btn_file.setProperty("class", "btn-primary")
        self.btn_file.setFixedHeight(32)
        self.btn_file.clicked.connect(self._select_file)
        file_layout.addWidget(self.btn_file)
        self.lbl_file = QLabel("未选择文件")
        self.lbl_file.setProperty("class", "stat-label")
        file_layout.addWidget(self.lbl_file, stretch=1)
        layout.addWidget(file_group)

        # ── 2. 佣金表 ──
        comm_group = QGroupBox("佣金表")
        comm_layout = QHBoxLayout(comm_group)
        self.combo_commission = QComboBox()
        self.combo_commission.setMinimumWidth(280)
        self._load_commission_tables()
        comm_layout.addWidget(self.combo_commission)
        comm_layout.addStretch()
        layout.addWidget(comm_group)

        # ── 3. 确认/取消按钮 ──
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("确认导入")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择Excel模板", "",
            "Excel文件 (*.xlsx *.xls);;所有文件 (*)"
        )
        if path:
            self._file_path = path
            self.lbl_file.setText(os.path.basename(path))
            self.lbl_file.setProperty("class", "stat-profit")

    def _load_commission_tables(self):
        comm_db = DatabaseManager(Config.DB_COMMISSION_PATH,
                                  init_tables=["commissions", "commission_meta", "app_config"])
        tables = comm_db.get_commission_tables()
        self.combo_commission.clear()
        for t in tables:
            shop_label = "本土" if t.shop_type == "local" else "跨境"
            label = f"{t.platform.upper()} {shop_label} ({t.row_count:,}条)"
            self.combo_commission.addItem(label, t.table_name)
        # Default: WB跨境
        for i in range(self.combo_commission.count()):
            if "跨境" in self.combo_commission.itemText(i):
                self.combo_commission.setCurrentIndex(i)
                break

    def _on_accept(self):
        if not self._file_path:
            QMessageBox.warning(self, "提示", "请先选择Excel文件")
            return
        self.accept()

    # ── Getters ──

    def get_file_path(self):
        return self._file_path

    def get_commission_table(self):
        data = self.combo_commission.currentData()
        return data or "commission_wb_cross_border"

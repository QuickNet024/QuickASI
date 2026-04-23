# -*- coding: utf-8 -*-
"""API 设置弹窗 — 通用组件，供各接口模块共用"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox, QCheckBox,
    QLineEdit, QDialog, QFormLayout, QDialogButtonBox,
    QProgressBar, QComboBox, QSizePolicy,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt

from src.models.database import DatabaseManager


class ApiSettingsDialog(QDialog):
    """通用 API 设置弹窗 — 字段列表自动生成表单"""

    def __init__(self, title, fields, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._fields = fields
        self._edits = {}
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        for item in self._fields:
            key, label, default = item[0], item[1], item[2]
            is_password = item[3] if len(item) > 3 else False
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.Password if is_password else QLineEdit.Normal)
            edit.setText(self.db.get_config(key, default))
            self._edits[key] = edit
            form.addRow(label + ":", edit)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_save(self):
        for key, edit in self._edits.items():
            self.db.save_config(key, edit.text().strip())
        QMessageBox.information(self, "保存成功", "设置已保存")
        self.accept()

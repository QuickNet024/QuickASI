# -*- coding: utf-8 -*-
"""计算设置对话框 — 策略选择"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QRadioButton, QButtonGroup,
    QGroupBox, QDialogButtonBox
)


class CalcSettingsDialog(QDialog):
    """计算前设置策略"""

    def __init__(self, parent=None, last_strategy="discount_only"):
        super().__init__(parent)
        self.setWindowTitle("计算设置")
        self.setMinimumWidth(460)
        self._build_ui(last_strategy)

    def _build_ui(self, last_strategy):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # ── 策略选择 ──
        strat_group = QGroupBox("策略")
        strat_layout = QHBoxLayout(strat_group)
        self.rb_discount = QRadioButton("仅折扣")
        self.rb_price = QRadioButton("仅调价")
        self.rb_both = QRadioButton("折扣+调价")
        grp = QButtonGroup(self)
        for rb in (self.rb_discount, self.rb_price, self.rb_both):
            grp.addButton(rb)
            strat_layout.addWidget(rb)
        # Restore previous selection
        if last_strategy == "price_only":
            self.rb_price.setChecked(True)
        elif last_strategy == "both":
            self.rb_both.setChecked(True)
        else:
            self.rb_discount.setChecked(True)
        strat_layout.addStretch()
        layout.addWidget(strat_group)

        # ── 确认/取消按钮 ──
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("开始计算")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_strategy(self):
        if self.rb_discount.isChecked():
            return "discount_only"
        elif self.rb_price.isChecked():
            return "price_only"
        return "both"

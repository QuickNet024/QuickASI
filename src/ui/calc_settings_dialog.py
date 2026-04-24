# -*- coding: utf-8 -*-
"""计算设置对话框 — 策略 + 汇率"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QRadioButton, QButtonGroup,
    QGroupBox, QDoubleSpinBox, QDialogButtonBox
)


class CalcSettingsDialog(QDialog):
    """计算前设置策略和汇率"""

    def __init__(self, parent=None, last_strategy="discount_only", last_rate=12.0,
                 last_rate_realtime=True, commission_table=None):
        super().__init__(parent)
        self.setWindowTitle("计算设置")
        self.setMinimumWidth(460)
        # Detect currency from commission table name
        # Default CNY (show exchange rate); switch to RUB only for 本土/local tables
        self._currency = "CNY"
        if commission_table and ("本土" in commission_table or "local" in commission_table.lower()):
            self._currency = "RUB"
        self._build_ui(last_strategy, last_rate, last_rate_realtime)

    def _build_ui(self, last_strategy, last_rate, last_rate_realtime):
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

        # ── 汇率选择 ──
        self.rate_group = QGroupBox("汇率")
        rate_layout = QHBoxLayout(self.rate_group)
        self.rb_rate_realtime = QRadioButton("实时汇率")
        self.rb_rate_specified = QRadioButton("指定汇率")
        grp_rate = QButtonGroup(self)
        grp_rate.addButton(self.rb_rate_realtime)
        grp_rate.addButton(self.rb_rate_specified)

        # Restore previous selection
        if last_rate_realtime:
            self.rb_rate_realtime.setChecked(True)
        else:
            self.rb_rate_specified.setChecked(True)

        rate_layout.addWidget(self.rb_rate_realtime)
        rate_layout.addWidget(self.rb_rate_specified)

        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.01, 100.0)
        self.spin_rate.setValue(last_rate)
        self.spin_rate.setDecimals(4)
        self.spin_rate.setPrefix("1 CNY = ")
        self.spin_rate.setSuffix(" RUB")
        self.spin_rate.setFixedWidth(160)
        self.spin_rate.setEnabled(not last_rate_realtime)
        self.rb_rate_specified.toggled.connect(self.spin_rate.setEnabled)
        rate_layout.addWidget(self.spin_rate)
        rate_layout.addStretch()

        # 本土模式提示（放在 rate_group 外部，独立显示）
        self.lbl_rate_hint = QLabel("本土店铺无需汇率转换")
        self.lbl_rate_hint.setStyleSheet("color: #999; font-style: italic;")
        self.lbl_rate_hint.setVisible(False)

        layout.addWidget(self.rate_group)
        layout.addWidget(self.lbl_rate_hint)

        # ── 本土/跨境模式切换 ──
        if self._currency == "RUB":
            self.rate_group.setVisible(False)
            self.lbl_rate_hint.setVisible(True)
            self.spin_rate.setValue(1.0)
        else:
            self.rate_group.setVisible(True)
            self.lbl_rate_hint.setVisible(False)

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

    def get_exchange_rate(self) -> float:
        if self._currency == "RUB":
            return 1.0
        if self.rb_rate_specified.isChecked():
            return self.spin_rate.value()
        from src.services.exchange_rate import ExchangeRateService
        ex_svc = ExchangeRateService()
        rate = ex_svc.get_cny_to_rub()
        return rate if rate > 0 else 12.0

    def is_rate_realtime(self) -> bool:
        return self.rb_rate_realtime.isChecked()

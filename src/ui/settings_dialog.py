# -*- coding: utf-8 -*-
"""参数配置对话框"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QDoubleSpinBox, QDialogButtonBox, QLabel
)
from PySide6.QtCore import Qt

from src.config import Config


class SettingsDialog(QDialog):
    """参数配置对话框 - 15+ 参数分两组显示"""

    # 定义参数: (key, label, suffix, decimals, min, max, step)
    COST_PARAMS = [
        ("risk_rate", "汇率风险系数", "", 3, 0.500, 3.000, 0.005),
        ("dropship_fee", "代发费", " RUB", 1, 0, 500, 1),
        ("pack_fee", "包装费", " RUB", 1, 0, 200, 1),
        ("scan_fee", "平台扫码费", " RUB", 1, 0, 50, 0.5),
        ("return_process_fee", "退货处理费(含取件)", " RUB", 1, 0, 500, 1),
        ("ad_fixed", "广告固定支出", " RUB", 1, 0, 10000, 10),
    ]

    RATE_PARAMS = [
        ("damage_rate", "货损率", " %", 1, 0, 100, 0.5),
        ("return_rate", "退货率", " %", 1, 0, 100, 0.5),
        ("residual_loss_rate", "退货残值损失率", " %", 1, 0, 100, 0.5),
        ("commission_discount", "佣金优惠减免率", " %", 1, 0, 100, 0.5),
        ("withdraw_fee", "提现手续费", " %", 1, 0, 10, 0.1),
        ("member_disc", "会员折扣率", " %", 1, 0, 50, 0.5),
        ("ops_rate", "运营成本率", " %", 1, 0, 50, 0.5),
        ("ad_percent", "广告费率ACOS", " %", 1, 0, 100, 0.5),
        ("default_commission", "未匹配类目默认佣金率", " %", 1, 0, 100, 0.5),
    ]

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("参数配置")
        self.setMinimumWidth(480)
        self._spinboxes = {}
        self._build_ui(current_params)

    def _build_ui(self, current_params: dict):
        layout = QVBoxLayout(self)

        # 成本参数组
        cost_group = QGroupBox("成本参数")
        cost_form = QFormLayout()
        cost_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        for key, label, suffix, decimals, lo, hi, step in self.COST_PARAMS:
            sb = self._make_spinbox(decimals, lo, hi, step, suffix)
            sb.setValue(current_params.get(key, Config.DEFAULT_PARAMS.get(key, 0)))
            self._spinboxes[key] = sb
            cost_form.addRow(label + ":", sb)
        cost_group.setLayout(cost_form)
        layout.addWidget(cost_group)

        # 费率参数组
        rate_group = QGroupBox("费率参数")
        rate_form = QFormLayout()
        rate_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        for key, label, suffix, decimals, lo, hi, step in self.RATE_PARAMS:
            sb = self._make_spinbox(decimals, lo, hi, step, suffix)
            sb.setValue(current_params.get(key, Config.DEFAULT_PARAMS.get(key, 0)))
            self._spinboxes[key] = sb
            rate_form.addRow(label + ":", sb)
        rate_group.setLayout(rate_form)
        layout.addWidget(rate_group)

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _make_spinbox(self, decimals, lo, hi, step, suffix):
        sb = QDoubleSpinBox()
        sb.setDecimals(decimals)
        sb.setRange(lo, hi)
        sb.setSingleStep(step)
        if suffix:
            sb.setSuffix(suffix)
        return sb

    def get_params(self) -> dict:
        return {key: sb.value() for key, sb in self._spinboxes.items()}

# -*- coding: utf-8 -*-
"""计算详情对话框 - 点击表格行时弹出显示所有中间计算值"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QFormLayout,
    QLabel, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt


class CalcDetailDialog(QDialog):
    """只读对话框，展示单行计算的完整详情"""

    def __init__(self, result: dict, params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("计算详情")
        self.setMinimumWidth(420)
        self._build_ui(result, params)

    def _build_ui(self, result: dict, params: dict):
        layout = QVBoxLayout(self)

        # ── Section 1: 基本信息 ──
        info_group = QGroupBox("基本信息")
        info_form = QFormLayout()
        info_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        info_form.addRow("卖家货号:", QLabel(str(result.get("seller_sku", "-"))))
        info_form.addRow("类目:", QLabel(str(result.get("category", "-"))))
        info_form.addRow("当前价格:", self._value_label(result.get("current_price"), ".2f"))
        info_form.addRow("当前折扣:", self._value_label(result.get("current_discount"), "%"))
        info_form.addRow("折后价格:", self._value_label(result.get("discounted_price"), ".2f"))
        info_form.addRow("分销价格:", self._value_label(result.get("distribution_price"), ".2f"))
        info_form.addRow("商品成本匹配:", QLabel("✅" if result.get("cost_matched") else "❌"))
        info_form.addRow("佣金匹配状态:", QLabel(str(result.get("commission_source") or "-")))
        info_form.addRow("佣金率:", self._value_label(result.get("commission_rate"), "%"))
        info_form.addRow("库存:", QLabel(str(result.get("inventory")) if result.get("inventory") is not None else "-"))

        info_group.setLayout(info_form)
        layout.addWidget(info_group)

        calc_result = result.get("_calc_result")

        if calc_result is None:
            no_data = QLabel("无计算数据（产品未匹配）")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data.setProperty("class", "stat-label")
            layout.addWidget(no_data)
        else:
            # ── Section 2: 计算中间值 ──
            mid_group = QGroupBox("计算中间值")
            mid_form = QFormLayout()
            mid_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            mid_form.addRow("平台运费:", self._float_label(calc_result.shipping_fee))
            mid_form.addRow("基础成本(Cbase):", self._float_label(calc_result.cbase))
            mid_form.addRow("风险成本(Crisk):", self._float_label(calc_result.crisk))
            mid_form.addRow("费率总计(R_Total):", self._float_label(calc_result.r_total))
            mid_form.addRow("总固定成本:", self._float_label(calc_result.total_fixed))

            mid_group.setLayout(mid_form)
            layout.addWidget(mid_group)

            # ── Section 3: 计算结果 ──
            res_group = QGroupBox("计算结果")
            res_form = QFormLayout()
            res_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            res_form.addRow("盈亏平衡价:", self._float_label(calc_result.breakeven))
            res_form.addRow("当前盈亏:", self._float_label(calc_result.current_profit))
            res_form.addRow("最大安全折扣:", QLabel(f"{calc_result.max_discount}%"))
            res_form.addRow("最低安全价格:", self._float_label(calc_result.min_price))

            res_group.setLayout(res_form)
            layout.addWidget(res_group)

            # ── Section 4: 使用参数 ──
            param_group = QGroupBox("使用参数")
            param_form = QFormLayout()
            param_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            param_form.addRow("风险系数:", self._float_label(params.get("risk_rate", 0)))
            param_form.addRow("代发费:", self._float_label(params.get("dropship_fee", 0)))
            param_form.addRow("包装费:", self._float_label(params.get("pack_fee", 0)))
            param_form.addRow("扫描费:", self._float_label(params.get("scan_fee", 0)))
            param_form.addRow("退货处理费:", self._float_label(params.get("return_process_fee", 0)))
            param_form.addRow("残损率:", QLabel(f"{params.get('residual_loss_rate', 0):.1f}%"))
            param_form.addRow("破损率:", QLabel(f"{params.get('damage_rate', 0):.1f}%"))
            param_form.addRow("退货率:", QLabel(f"{params.get('return_rate', 0):.1f}%"))

            param_group.setLayout(param_form)
            layout.addWidget(param_group)

        # ── 关闭按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    @staticmethod
    def _float_label(val) -> QLabel:
        """Format a numeric value as .2f label."""
        if val is None:
            return QLabel("-")
        try:
            return QLabel(f"{float(val):.2f}")
        except (ValueError, TypeError):
            return QLabel(str(val))

    @staticmethod
    def _value_label(val, fmt: str) -> QLabel:
        """Format a value with the given format suffix (% or .2f)."""
        if val is None:
            return QLabel("-")
        try:
            fval = float(val)
            if fmt == "%":
                return QLabel(f"{int(fval)}%")
            return QLabel(f"{fval:.2f}")
        except (ValueError, TypeError):
            return QLabel(str(val) if val else "-")

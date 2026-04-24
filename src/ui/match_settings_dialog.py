# -*- coding: utf-8 -*-
"""匹配设置对话框 — 运费配置选择"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout,
    QLabel, QRadioButton, QButtonGroup,
    QGroupBox, QDialogButtonBox
)


class MatchSettingsDialog(QDialog):
    """匹配前选择运费配置"""

    def __init__(self, parent=None, last_shop_type="wb_cross_border"):
        super().__init__(parent)
        self.setWindowTitle("匹配设置")
        self.setMinimumWidth(420)
        self._shop_type = last_shop_type
        self._build_ui(last_shop_type)

    def _build_ui(self, last_shop_type):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # ── 运费配置选择 ──
        config_group = QGroupBox("运费配置")
        config_layout = QVBoxLayout(config_group)

        self.rb_cross_border = QRadioButton("WB跨境 · 本土仓发货")
        self.rb_cross_border.setChecked(True)

        # Show config details
        try:
            from src.services.shipping_service import ShippingService
            svc = ShippingService()
            cfg = svc.get_config("wb_cross_border")
            detail = f"首升 ¥{cfg['base_fee']:.0f} + 续升 ¥{cfg['rate_per_unit']:.0f}/L"
        except Exception:
            detail = "首升 ¥8 + 续升 ¥2/L"
        lbl_detail = QLabel(f"    {detail}")

        self.rb_local = QRadioButton("WB本土 · FBS (暂未开放)")
        self.rb_local.setEnabled(False)  # v1.0.0 disabled

        grp = QButtonGroup(self)
        grp.addButton(self.rb_cross_border)
        grp.addButton(self.rb_local)

        config_layout.addWidget(self.rb_cross_border)
        config_layout.addWidget(lbl_detail)
        config_layout.addWidget(self.rb_local)
        layout.addWidget(config_group)

        # ── 确认/取消按钮 ──
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("开始匹配")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_shop_type(self) -> str:
        if self.rb_cross_border.isChecked():
            return "wb_cross_border"
        return "wb_cross_border"  # default

    def get_commission_table(self) -> str:
        shop_type = self.get_shop_type()
        if shop_type == "wb_local":
            return "commission_wb_local"
        return "commission_wb_cross_border"
